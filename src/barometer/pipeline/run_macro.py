"""總經管線（ToDo §9 Day 25 第 1、2 項）。

驗收：17 項評分指標 + 7 項觀測指標都有值或**明確的失敗原因**，
沒有任何一項讓整輪中止。

失敗策略（§7.3）：
  有舊快取 → 顯示快取值並標「更新失敗，顯示快取（原因）」
  無快取   → 顯示「—」與失敗原因
**單一指標失敗不擋整頁。**
"""
from __future__ import annotations

import datetime as dt
import sys

from barometer import config
from barometer.datasources import eia_src, fred_src, tw_gov_src, yfinance_src
from barometer.datasources.base import COUNTER, FetchError
from barometer.domain.macro_spec import ALL, SCORED, WORLD, TAIWAN
from barometer.domain.ports import MacroSeries
from barometer.domain.scoring_macro import ALERT_FUNCS, score_layer, summarize
from barometer.pipeline.runlog import RunLog
from barometer.storage.sqlite_repo import SqliteRepo

YF_PERIOD = "6mo"  # 近 6 個月日線收盤（§7.3）


def _fetch_one(ind) -> list[tuple[str, float]]:
    """依 source 分派。回 (日期, 值) 由舊到新。"""
    if ind.source == "yfinance":
        bars = yfinance_src.fetch_daily(ind.sid, period=YF_PERIOD)
        out = [
            (b.date.isoformat(), b.close) for b in bars if b.close is not None
        ]
        if not out:
            raise FetchError(f"{ind.sid}: 沒有任何有效收盤")
        return out
    if ind.source == "fred":
        return fred_src.fetch(ind.sid)
    if ind.source == "ndc":
        if ind.key == "tw_light":
            return tw_gov_src.fetch_tw_light()
        return tw_gov_src.fetch_tw_export()
    if ind.source == "dgbas":
        return tw_gov_src.fetch_tw_gdp()
    if ind.source == "cbc":
        return tw_gov_src.fetch_cbc_rate()
    if ind.source == "eia":
        # WPSR 是一張比較表不是序列，只給上週與本週兩個真實的點，
        # 中間不補（見 datasources/eia_src 的說明）
        return eia_src.fetch().as_series()
    raise FetchError(f"未知的資料源 {ind.source}")


def _data_date(series: list[tuple[str, float]]) -> dt.date | None:
    """把序列最後一格的標籤轉成日期。

    刻意容忍三種格式，因為頻率就是混雜的：日頻 2026-09-04、月頻 2026-07、
    季頻 2026Q2。轉不出來就回 None —— 顯示層照原字串標，不要瞎猜一個日期。
    """
    if not series:
        return None
    label = series[-1][0]
    try:
        return dt.date.fromisoformat(label)
    except ValueError:
        pass
    try:
        y, m = label.split("-")
        return dt.date(int(y), int(m), 1)
    except (ValueError, IndexError):
        pass
    if "Q" in label:
        try:
            y, q = label.split("Q")
            return dt.date(int(y), (int(q) - 1) * 3 + 1, 1)
        except (ValueError, IndexError):
            pass
    return None


def run(force: bool = False) -> tuple[RunLog, dict]:
    log = RunLog(task="macro")
    COUNTER.reset()
    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()

    now = dt.datetime.now()
    results: dict[str, dict] = {}

    try:
        for ind in ALL:
            cached: MacroSeries | None = repo.get_macro(ind.key)
            if not force and cached is not None:
                age_h = (now - cached.fetched_at).total_seconds() / 3600
                if age_h < ind.ttl_hours:
                    results[ind.key] = {
                        "series": cached.series,
                        "data_date": cached.data_date,
                        "status": "cached",
                        "note": f"快取（{age_h:.1f} 小時前）",
                    }
                    log.count("from_cache")
                    continue

            try:
                series = _fetch_one(ind)
                dd = _data_date(series)
                repo.put_macro(ind.key, series, fetched_at=now, data_date=dd)
                results[ind.key] = {
                    "series": series, "data_date": dd,
                    "status": "fresh", "note": "",
                }
                log.count("fetched")
            except Exception as exc:  # noqa: BLE001 — 單一指標失敗不擋整輪
                # FetchError 自己就寫了一句人看得懂的中文，直接用。
                # 其他例外要帶上型別 —— 一個 KeyError 的 str() 只有 'series'
                # 四個字，寫進 run log 之後完全查不出發生了什麼事。
                # 這是失敗演練跑出來才看見的（Day 28 第 4 項）。
                reason = (str(exc) if isinstance(exc, FetchError)
                          else f"{type(exc).__name__}: {exc}")
                log.count("failed")
                log.note(f"{ind.key}（{ind.name}）: {reason}")
                if cached is not None:
                    results[ind.key] = {
                        "series": cached.series,
                        "data_date": cached.data_date,
                        "status": "stale",
                        "note": f"更新失敗，顯示快取（{reason}）",
                    }
                else:
                    results[ind.key] = {
                        "series": [], "data_date": None,
                        "status": "missing", "note": f"抓取失敗：{reason}",
                    }

        # ---- 第一層：逐項警示判定 ----
        verdicts: dict[str, tuple[bool, str]] = {}
        for ind in SCORED:
            series = results[ind.key]["series"]
            if not series:
                continue  # 沒有值的指標不計入該層（權重自動正規化）
            verdicts[ind.key] = ALERT_FUNCS[ind.key](series)

        # ---- 第二層：層別評分 ----
        world = score_layer(
            {i.key: verdicts[i.key][0] for i in WORLD if i.key in verdicts}
        )
        taiwan = score_layer(
            {i.key: verdicts[i.key][0] for i in TAIWAN if i.key in verdicts}
        )
        summary = summarize(world, taiwan)

        for scope, layer in (("macro_world", world), ("macro_tw", taiwan)):
            if layer.score is not None:
                repo.put_score(
                    scope=scope, symbol="-", as_of=now.date(),
                    score=layer.score,
                    subscores={k: float(verdicts[k][0]) for k in layer.alert_keys},
                    price_version="macro",
                )

        log.quota["requests"] = COUNTER.snapshot()
        log.set_count("scored_indicators", len(verdicts))
        log.finish("partial" if log.counts.get("failed") else "ok")
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    finally:
        repo.close()

    log.append()
    return log, {"results": results, "verdicts": verdicts, "summary": summary}


def main() -> int:
    """排程任務 `Barometer-Macro`（每天 09:05）的進入點。

    `force=False` 是刻意的：TTL 由每條序列自己的更新頻率決定（§7.3），
    每小時去問一條每月才出一次的序列，只會把額度花在必定落空的請求上。
    """
    log, _ = run()
    print(f"[{log.started_at:%Y-%m-%d %H:%M}] macro "
          f"status={log.status} counts={log.counts}")
    for n in log.notes:
        print(f"  ! {n}")
    # partial 不算失敗 —— 單一指標失敗不該讓排程任務標成錯誤
    return 0 if log.status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
