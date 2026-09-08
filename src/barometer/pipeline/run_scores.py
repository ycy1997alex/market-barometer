"""大盤與 ETF 評分管線（ToDo §9 Day 26 第 3 項）。

流程：讀本機序列 → 逐日回算評分 → 寫 score_history → 算五日加權。

**逐日回算的意思是：算 D 這天的分數時，只餵給它 D 當天為止的序列。**
拿完整序列去算「D 那天的分數」會把後來才發生的事混進去 —— 那是回測最常見
的作弊方式，而且看不出來，因為數字仍然很合理。

`price_version` 這個欄位在這裡才有意義（§3.5）：分割或除權息之後所有價格型
指標都會變，**昨天的分數今天算會不一樣**。所以每一筆分數都記下它是用哪一版
價格算的，不然回頭比較的時候不知道差異來自市場還是來自資料被改寫。

§2.1：這一層只算分數與分項，不產生任何建議 —— 那條線由 domain/scoring_index.py
的型別擋住（IndexScore 沒有 advice 欄位），這裡不必也不能補上。
"""
from __future__ import annotations

import datetime as dt

from barometer import config
from barometer.domain import scoring_index, weighting, windows
from barometer.pipeline.runlog import RunLog
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo

SCOPE = "index"
WINDOW = 5


def score_series(
    symbol: str, bars: list, window: int = WINDOW
) -> list[tuple[dt.date, scoring_index.IndexScore]]:
    """逐日回算最近 `window` 個交易日的評分。

    每一天只看得到它自己以前的資料 —— 見模組 docstring。
    """
    by_date = {b.date: b for b in bars}
    session_days = windows.last_n_sessions(list(by_date), window)

    out: list[tuple[dt.date, scoring_index.IndexScore]] = []
    for day in session_days:
        closes = [b.close for b in bars if b.date <= day]
        out.append((day, scoring_index.score_index(symbol, closes)))
    return out


def summarize_window(
    scored: list[tuple[dt.date, scoring_index.IndexScore]]
) -> dict:
    """五日的簡單平均、加權平均與平滑化（§8.1）。

    **五個交易日只有五個點** —— 呼叫端把這個 dict 印出去的時候必須標定性
    觀察，不是統計證據（§12 第 10 條）。

    不滿五天**直接報錯，不降級**（2026-09-08 定案）。管線安靜產出一份少了
    幾檔的結果，比整支失敗糟得多 —— 沒有人會去比對「今天怎麼少了兩檔」。

    桌面 Presenter 那一側刻意相反：它回 None 並標「資料不足（N/5 天）」，
    因為使用者切到大盤分頁時畫面不該整頁掛掉。同一個狀況、兩種處置，
    差別在「有沒有人正在看著」。

    訊息要講出**是哪一檔、幾天、哪幾天** —— `weighting` 自己的錯誤只說
    「收到 3 個」，15 檔跑到一半炸掉時那句話沒有任何幫助。
    """
    if len(scored) != WINDOW:
        symbol = scored[0][1].symbol if scored else "（空序列）"
        days = "、".join(d.isoformat() for d, _ in scored) or "無"
        raise ValueError(
            f"{symbol}：五日視窗需要恰好 {WINDOW} 個交易日，"
            f"只有 {len(scored)}/{WINDOW} 天（{days}）。"
            "新上市或剛加進清單的標的會這樣 —— 補足交易日，或把它排除在這次評分之外。"
        )

    values = [s.score for _, s in scored]
    return {
        "dates": [d.isoformat() for d, _ in scored],
        "scores": values,
        "simple_average": weighting.simple_average(values),
        "weighted_average": weighting.weighted_average(values),
        "smoothed": weighting.smooth(values),
        "qualitative_only": True,  # 五個點，定性觀察
    }


def run(
    symbols: list[str],
    task: str = "scores_index",
    window: int = WINDOW,
    price_version: str = "v1",
) -> RunLog:
    log = RunLog(task=task)
    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()

    try:
        for symbol in symbols:
            bars = csv_audit.read_current(symbol)
            if not bars:
                log.count("no_data")
                log.note(f"{symbol}: 本機沒有序列，跳過（不是 0 分，是沒有資料）")
                continue

            scored = score_series(symbol, bars, window)
            wrote = 0
            for day, s in scored:
                if s.score is None:
                    log.note(f"{symbol} {day}: 資料不足，沒有分數（不寫 0）")
                    continue
                repo.put_score(
                    scope=SCOPE, symbol=symbol, as_of=day, score=s.score,
                    subscores=s.subscores, price_version=price_version,
                )
                wrote += 1

            summary = summarize_window(scored)
            log.set_count(f"scored::{symbol}", wrote)
            if summary["weighted_average"] is not None:
                log.set_count(
                    f"wavg::{symbol}", round(summary["weighted_average"], 1)
                )
            log.count("symbols_ok")

        log.finish("partial" if log.counts.get("no_data") else "ok")
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    except Exception as exc:
        # **記完 runlog 再重拋。** 失敗要大聲（所以重拋），但不能連
        # 「跑過、失敗在哪裡」都不留下 —— runlog 是 Day 28 回顧的主體，
        # 價格可以事後回補，執行紀錄補不回來。沒有紀錄的失敗，
        # 跟「排程根本沒觸發」在事後長得一模一樣。
        #
        # 已經累積的 counts 與 notes 全部留著，那是「跑到哪裡」的唯一線索。
        log.note(f"中止：{type(exc).__name__}: {exc}")
        log.finish("error")
        try:
            repo.record_run(
                run_id=log.run_id, task=log.task, started_at=log.started_at,
                ended_at=log.ended_at, status=log.status,
                counts=log.counts, quota=log.quota,
            )
        except Exception:  # noqa: BLE001
            # 資料庫也壞掉的時候，至少要保住 jsonl 那一份。
            # 這裡再拋一次會蓋掉原本的錯誤，那才是真的難查。
            pass
        log.append()
        raise
    finally:
        repo.close()

    log.append()
    return log
