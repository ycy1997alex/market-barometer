"""價格管線：抓 → 比對 → 落地（ToDo §9 Day 24 第 4、6、7 項）。

流程刻意是這個順序：
  1. 讀本機已存的（price_current）
  2. 抓新的（yfinance，逐檔、節流）
  3. **比對**重疊日期 —— 只記旗標，不改資料（§4.1）
  4. 落地兩份（price_raw 稽核 + price_current 計算用）
  5. 寫進 SQLite、寫 run log

任何單一標的的失敗都不得中止整批（§4.3）。
"""
from __future__ import annotations

import datetime as dt

from barometer import config
from barometer.datasources import yfinance_src
from barometer.datasources.base import COUNTER, FetchError
from barometer.domain import windows
from barometer.domain.reconcile import compare_overlap
from barometer.pipeline.runlog import RunLog
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


def _flag_missing_sessions(log: RunLog, final_dates: dict[str, list[dt.date]]) -> None:
    """同一批裡別人有、我沒有的交易日 —— 記一筆，不修。

    既有的兩個偵測器都不看這個方向：`stale` 只認「有這一格但值是空的」，
    整列不存在不算；`compare_overlap` 只比重疊日期，不在重疊裡的它連看都不看。
    兩個都沒錯，但 `0050.TW` 的洞因此連續四天沒有任何警報。

    **分市場比。** 台股與美股的交易日不對齊（2026-09-07 美國勞動節台股照常），
    `day24_stocks` 那一批 15 檔混著兩個市場，拿整批的聯集去比會全部亮燈。
    """
    groups: dict[bool, list[str]] = {}
    for symbol in final_dates:
        groups.setdefault(config.is_tw(symbol), []).append(symbol)

    for members in groups.values():
        reference = sorted({d for s in members for d in final_dates[s]})
        for symbol in members:
            missing = windows.missing_sessions(final_dates[symbol], reference)
            if not missing:
                continue
            days = "、".join(d.isoformat() for d in missing)
            log.set_count(f"missing_sessions::{symbol}", len(missing))
            log.note(f"{symbol}: 缺了同批其他標的有的 {len(missing)} 個交易日"
                     f"（{days}）—— 資料未自動修改")


def run(
    symbols: list[str],
    task: str,
    period: str = "1y",
    run_date: dt.date | None = None,
) -> RunLog:
    run_date = run_date or dt.date.today()
    as_of = dt.datetime.now()
    log = RunLog(task=task)
    COUNTER.reset()

    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    final_dates: dict[str, list[dt.date]] = {}

    try:
        for symbol in symbols:
            try:
                bars = yfinance_src.fetch_daily(symbol, period=period, as_of=as_of)
            except FetchError as exc:
                # 單一標的失敗 → 記下來，繼續跑完其他標的
                log.count("failed")
                log.note(f"{symbol}: 抓取失敗 — {exc}")
                continue

            stored = csv_audit.read_current(symbol)
            cmp = compare_overlap(stored, bars)
            if cmp.suspect_adjust:
                # §4.1：只記旗標，到此為止。重抓是手動的。
                ratio = f"，疑似比例 {cmp.ratio:.6g}" if cmp.ratio else ""
                log.note(
                    f"{symbol}: suspect_adjust — 重疊 {len(cmp.compared_dates)} 天"
                    f"有 {len(cmp.mismatches)} 格對不上{ratio}"
                    f"（資料未自動修改，需人工跑 tools/refetch.py）"
                )
                log.count("suspect_adjust")

            stale_n = sum(1 for b in bars if b.stale)
            if stale_n:
                log.note(f"{symbol}: {stale_n} 格缺值，已保留前一日值並標 stale")
                log.count("stale_cells", stale_n)

            csv_audit.write_raw(symbol, bars, run_date)
            written = csv_audit.write_current(symbol, bars)
            repo.upsert_prices(bars)

            if written.retained:
                # 來源這次沒回、本機留著的交易日。yfinance 的 T-1 遲到每天都會
                # 走到這裡 —— 所以要記，不記就跟原本安靜挖洞一樣查不出來。
                days = "、".join(d.isoformat() for d in written.retained)
                log.note(f"{symbol}: 來源這次沒回 {len(written.retained)} 個"
                         f"本機已有的交易日，已保留（{days}）")
                log.count("retained_sessions", len(written.retained))

            log.count("symbols_ok")
            log.set_count(f"rows::{symbol}", len(bars))
            final_dates[symbol] = [b.date for b in csv_audit.read_current(symbol)]

        _flag_missing_sessions(log, final_dates)

        log.quota["requests"] = COUNTER.snapshot()
        status = "partial" if log.counts.get("failed") else "ok"
        log.finish(status)
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    finally:
        repo.close()

    log.append()
    return log
