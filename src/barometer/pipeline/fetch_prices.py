"""價格管線：抓 → 比對 → 落地（ToDo §9 Day 24 第 4、6、7 項）。

流程刻意是這個順序：
  1. 讀本機已存的（price_current）
  2. 抓新的（yfinance，逐檔、節流）
  3. **比對**重疊日期 —— 只記旗標，不改資料（§4.1）
  4. 落地 price_raw 稽核、price_current 比對/顯示、price_adjusted 指標
  5. 寫進 SQLite、寫 run log

任何單一標的的失敗都不得中止整批（§4.3）。
"""
from __future__ import annotations

import datetime as dt

from barometer import config
from barometer.datasources import twse_src, yfinance_src
from barometer.datasources.cached import CachedSource
from barometer.datasources.base import COUNTER, FetchError
from barometer.domain import freshness, windows
from barometer.domain.ports import PriceBar
from barometer.domain.reconcile import detect_split_step
from barometer.pipeline.runlog import RunLog
from barometer.pipeline.notify import Notifier
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo

PRICE_FIELDS = ("open", "high", "low", "close", "volume_shares")


def _changed_fields(old: PriceBar, new: PriceBar) -> list[str]:
    return [field for field in PRICE_FIELDS if getattr(old, field) != getattr(new, field)]


def _recent_update(
    stored: list[PriceBar], fetched: list[PriceBar], n: int,
) -> tuple[list[PriceBar], list[PriceBar], list[tuple[PriceBar | None, PriceBar, str, bool]]]:
    """Return merged bars, actual writes, and field changes with revision eligibility."""
    if n < 1:
        raise ValueError("PRICE_REVISABLE_SESSIONS must be positive")
    old_by_date = {bar.date: bar for bar in stored}
    recent = set(windows.last_n_sessions(
        [bar.date for bar in stored] + [bar.date for bar in fetched], n,
    ))
    writes: list[PriceBar] = []
    changes: list[tuple[PriceBar | None, PriceBar, str, bool]] = []
    for new in fetched:
        old = old_by_date.get(new.date)
        if old is None:
            allowed = not stored or new.date in recent
            changes.extend((None, new, field, allowed) for field in PRICE_FIELDS)
            if allowed:
                old_by_date[new.date] = new
                writes.append(new)
            continue
        if new.stale and not old.stale:
            continue
        fields = _changed_fields(old, new)
        allowed = new.date in recent
        changes.extend((old, new, field, allowed) for field in fields)
        if allowed and (fields or old.stale != new.stale):
            old_by_date[new.date] = new
            writes.append(new)
    return sorted(old_by_date.values(), key=lambda bar: bar.date), writes, changes


def _traded_dates(bars: list[PriceBar]) -> list[dt.date]:
    """真的有成交的日期。休市日的假列不算。

    台股休市日（颱風假之類）個股仍會掛出一列 `Open=Close`、`volume=0`，
    指數則整列不存在 —— **沒有交易就沒有指數，那是對的**。拿個股的假列當
    基準，會把正確的指數判成缺漏（2026-07-10 實際發生過）。

    這種誤報還會賴著不走：那一天留在一年的滾動視窗裡，等於接下來十個月每天
    報一次。每天都報一句，就沒有人會再讀它 —— 偵測器就是這樣死掉的。
    """
    return [
        b.date for b in bars
        if not (b.volume_shares == 0 and b.open is not None and b.open == b.close)
    ]


def _flag_missing_sessions(log: RunLog, final_bars: dict[str, list[PriceBar]]) -> None:
    """同一批裡別人有、我沒有的交易日 —— 記一筆，不修。

    既有的兩個偵測器都不看這個方向：`stale` 只認「有這一格但值是空的」，
    整列不存在不算；`compare_overlap` 只比重疊日期，不在重疊裡的它連看都不看。
    兩個都沒錯，但 `0050.TW` 的洞因此連續四天沒有任何警報。

    **分市場比。** 台股與美股的交易日不對齊（2026-09-07 美國勞動節台股照常），
    `day24_stocks` 那一批 15 檔混著兩個市場，拿整批的聯集去比會全部亮燈。

    **基準只採真的有成交的日期**（見 `_traded_dates`）。
    """
    groups: dict[bool, list[str]] = {}
    for symbol in final_bars:
        groups.setdefault(config.is_tw(symbol), []).append(symbol)

    for members in groups.values():
        traded = {s: _traded_dates(final_bars[s]) for s in members}
        reference = sorted({d for s in members for d in traded[s]})
        for symbol in members:
            missing = windows.missing_sessions(traded[symbol], reference)
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
    force: bool = False,
) -> RunLog:
    run_date = run_date or dt.date.today()
    as_of = dt.datetime.now()
    log = RunLog(task=task)
    COUNTER.reset()

    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    cache = CachedSource(
        config.stockdata_root(), yfinance_src.fetch_daily,
        csv_audit.read_current, repo.get_adjusted_prices,
        ttl_seconds=config.PRICE_CACHE_TTL_SECONDS,
    )
    final_bars: dict[str, list[PriceBar]] = {}

    try:
        official: dict[str, PriceBar] = {}
        official_loaded = False
        for symbol in symbols:
            stored = csv_audit.read_current(symbol)
            stored_state = freshness.assess_source_series(
                "每日", stored[-1].date if stored else None, run_date,
                [bar.close for bar in stored], key=symbol,
            )
            try:
                result = cache.get(
                    symbol, period=period, force=force or not stored_state.usable,
                    as_of=as_of,
                )
            except FetchError as exc:
                # 單一標的失敗 → 記下來，繼續跑完其他標的
                log.count("failed")
                log.note(f"{symbol}: 抓取失敗 — {exc}")
                continue
            if result.from_cache:
                if not config.is_tw(symbol):
                    cutoff = windows.latest_complete_us_date()
                    if any(bar.date > cutoff for bar in result.current):
                        log.count("failed")
                        log.note(f"{symbol}: 本機快取含尚未收盤的美股日 K，需人工清理")
                        final_bars[symbol] = [bar for bar in result.current if bar.date <= cutoff]
                        continue
                log.count("cache_hits")
                log.count("symbols_ok")
                final_bars[symbol] = result.current
                continue
            bars = result.current
            adjusted = [bar for bar in result.adjusted if bar.date.weekday() != 6]
            if not config.is_tw(symbol):
                cutoff = windows.latest_complete_us_date()
                excluded = sorted({bar.date for bar in bars + adjusted
                                   if bar.date > cutoff or bar.date.weekday() >= 5})
                if excluded:
                    bars = [bar for bar in bars if bar.date <= cutoff and bar.date.weekday() < 5]
                    adjusted = [bar for bar in adjusted if bar.date <= cutoff and bar.date.weekday() < 5]
                    log.count("incomplete_sessions", len(excluded))
                    log.note(f"{symbol}: 美股尚未收盤或休市的日 K "
                             f"（{', '.join(str(day) for day in excluded)}）未落地")

            invalid = [bar.date for bar in bars if bar.date.weekday() == 6]
            if invalid:
                bars = [bar for bar in bars if bar.date.weekday() != 6]
                log.count("invalid_sessions", len(invalid))
                log.note(f"{symbol}: Yahoo 回傳週日非交易日列"
                         f"（{', '.join(str(day) for day in invalid)}），未落地")

            source_state = freshness.assess_source_series(
                "每日", bars[-1].date if bars else None, run_date,
                [bar.close for bar in bars], key=symbol,
            )
            if not source_state.usable:
                log.count("frozen")
                log.note(f"{symbol}: {source_state.reason}，來源未落地")
                cached_state = freshness.assess_source_series(
                    "每日", stored[-1].date if stored else None, run_date,
                    [bar.close for bar in stored], key=symbol,
                )
                if cached_state.usable:
                    final_bars[symbol] = stored
                    log.note(f"{symbol}: 降級到本機較新序列（{stored[-1].date}）")
                else:
                    log.count("failed")
                    log.note(f"{symbol}: 本機快取也不可用（{cached_state.reason}）")
                continue
            if not adjusted:
                log.count("failed")
                log.note(f"{symbol}: 還原日 K 沒有有效交易日")
                continue
            if symbol.endswith(".TW") or symbol.endswith(".TWO"):
                if symbol.endswith(".TW") and not official_loaded:
                    official_loaded = True
                    try:
                        official = twse_src.fetch_stock_day_all(run_date)
                    except FetchError as exc:
                        log.note(f"TWSE STOCK_DAY_ALL: {exc}；當日官方收盤補齊不可用")
                bars, supplement_status = twse_src.supplement_latest_close(
                    symbol, bars, official)
                if supplement_status == "supplemented":
                    log.count("twse_supplemented")
                    log.note(f"{symbol}: 最新收盤由 TWSE STOCK_DAY_ALL 補齊"
                             f"（{bars[-1].date}，實際來源 twse_stock_day_all）")
                elif supplement_status == "otc_uncovered":
                    log.note(f"{symbol}: STOCK_DAY_ALL 不含上櫃，官方收盤未補齊")
            step = detect_split_step(stored, bars)
            if step is not None:
                notice = twse_src.official_split_notice(symbol, step.event_date)
                confirmed = (notice is not None and
                             abs(step.price_ratio - 1 / notice.ratio) < 0.01)
                if confirmed:
                    message = (f"{symbol}: 證交所公告確認 {step.event_date} "
                               f"{notice.ratio:g}:1 分割，前段 {step.rows_affected} 根"
                               f"價格呈固定倍數；僅記旗標，資料未自動修改。{notice.url}")
                    repo.record_adjustment(symbol, as_of, step.event_date,
                                           notice.ratio, step.rows_affected, message)
                    log.count("split_notices")
                else:
                    message = (f"{symbol}: {step.event_date} 前整段呈固定倍數 "
                               f"{step.price_ratio:.6g}，尚無證交所公告確認，待查；"
                               "資料未自動修改")
                    log.count("suspect_adjust")
                log.note(message)
                Notifier(config.stockdata_root() / "alerts.jsonl",
                         config.stockdata_root() / "ALERT.md").record_local(
                             "價格分割待核對", message)
                final_bars[symbol] = stored
                continue
            merged, writes, changes = _recent_update(
                stored, bars, config.PRICE_REVISABLE_SESSIONS,
            )
            for old, new, field, allowed in changes:
                if old is None:
                    if not allowed:
                        log.note(f"{symbol} {new.date} {field}: 舊交易日缺列，僅記旗標，未自動補歷史")
                    continue
                previous = getattr(old, field)
                replacement = getattr(new, field)
                repo.record_conflict(
                    symbol, new.date, field, previous, replacement,
                    "yfinance_recent_update" if allowed else "stored_historical",
                    as_of,
                    old_value=previous, new_value=replacement,
                )
                log.note(f"{symbol} {new.date} {field}: {previous} → {replacement}；"
                         f"{'近窗已更新' if allowed else '舊史僅記旗標，未更新'}")
                log.count("price_revised" if allowed else "historical_flagged")

            stale_n = sum(1 for b in bars if b.stale)
            if stale_n:
                log.note(f"{symbol}: {stale_n} 格缺值，已保留前一日值並標 stale")
                log.count("stale_cells", stale_n)

            if writes:
                csv_audit.write_raw(symbol, bars, run_date)
                csv_audit.write_current(symbol, merged)
                repo.upsert_prices(writes)
            # Derived series: deliberately absent from the append-only raw audit.
            old_adjusted = {bar.date: bar for bar in repo.get_adjusted_prices(symbol)}
            adjusted_writes = [bar for bar in adjusted if
                               bar.date not in old_adjusted or
                               _changed_fields(old_adjusted[bar.date], bar) or
                               old_adjusted[bar.date].stale != bar.stale]
            if adjusted_writes:
                repo.upsert_adjusted_prices(adjusted_writes)

            retained = sorted({bar.date for bar in stored if
                               bars and bar.date >= bars[0].date} -
                              {bar.date for bar in bars})
            if retained:
                # 來源這次沒回、本機留著的交易日。yfinance 的 T-1 遲到每天都會
                # 走到這裡 —— 所以要記，不記就跟原本安靜挖洞一樣查不出來。
                days = "、".join(d.isoformat() for d in retained)
                log.note(f"{symbol}: 來源這次沒回 {len(retained)} 個"
                         f"本機已有的交易日，已保留（{days}）")
                log.count("retained_sessions", len(retained))

            log.count("symbols_ok")
            log.set_count(f"rows::{symbol}", len(bars))
            final_bars[symbol] = merged
            cache.mark_checked(symbol)

        _flag_missing_sessions(log, final_bars)

        log.quota["requests"] = COUNTER.snapshot()
        status = "partial" if log.counts.get("failed") or log.counts.get("frozen") else "ok"
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
