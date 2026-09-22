"""把資料層的東西組成 render 層的 view model（ToDo §9 Day 27 第 3 項）。

這一層是**轉接**：它認得 storage（讀 SQLite），也認得 render 的 Row / Tab，
但 render 那邊永遠不認得 storage —— 界線在這裡轉一次，
tests/test_layer_boundary.py 才守得住 §3.2。

market-barometer 的四個分頁（§0）：
    世界總體經濟 / 台灣總體經濟 / 台股大盤&ETF / 美股大盤&ETF

**每一列各自帶自己的資料日期**，頁面上沒有單一的更新時間（§9 Day 25 第 3 項）。
"""
from __future__ import annotations

import datetime as dt

from barometer import config
from barometer.domain import freshness, macro_spec, sampling, summary, scoring_index, scoring_macro
from barometer.domain.coverage import Coverage
from barometer.domain.chips import reading as chip_reading
from barometer.pipeline import run_scores
from barometer.pipeline.runlog import read_runs
from barometer.render import svg
from barometer.render.page import Row, Tab
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo

WORLD_INTRO = (
    f"{len(macro_spec.WORLD)} 項進評分。黃金、原油、匯率、比特幣只顯示不評分，"
    "不進評分的就只是名詞解釋，不假裝它有份量。"
)
TW_INTRO = (
    "六項進評分。把美國的費城半導體 SOX 放進台灣層是一個判斷，不是理所當然："
    "理由是台股半導體占比極高。"
)
INDEX_INTRO = (
    "五個技術面維度，分數是「未警示維度的比例」。"
    "評分是量測，不是指示：這一頁只有分數與分項，沒有任何行動建議。"
)


def _macro_rows(repo: SqliteRepo, indicators) -> list[Row]:
    rows: list[Row] = []
    for ind in indicators:
        cached = repo.get_macro(ind.key)
        if cached is None or not cached.series:
            rows.append(
                Row(label=ind.name, value=None, data_date=None, freq=ind.freq,
                    note=ind.note or "尚未抓取")
            )
            continue
        state = freshness.assess_source_series(
            ind.freq, cached.data_date, dt.date.today(),
            [value for _, value in cached.series], key=ind.key,
        )
        if not state.usable:
            note = "｜".join(part for part in (ind.note, state.reason) if part)
            rows.append(Row(
                label=ind.name, value=None,
                data_date=(cached.data_date.isoformat() if cached.data_date else None),
                freq=ind.freq, note=note,
                source=cached.source,
                fetched_at=cached.fetched_at.strftime("%Y-%m-%d %H:%M"),
            ))
            continue
        series = [(d, v) for d, v in cached.series]
        last = series[-1][1]
        note = ind.note
        if cached.stale_reason:
            note = f"{note}｜更新失敗，顯示快取（{cached.stale_reason}）".lstrip("｜")
        rows.append(
            Row(
                label=ind.name,
                value=ind.fmt.format(last) if last is not None else None,
                data_date=(cached.data_date.isoformat() if cached.data_date
                           else series[-1][0]),
                freq=ind.freq,
                series=series[-30:],
                note=note,
                source=cached.source,
                fetched_at=cached.fetched_at.strftime("%Y-%m-%d %H:%M"),
            )
        )
    return rows


def _macro_coverage(repo: SqliteRepo, indicators) -> Coverage:
    valid = 0
    today = dt.date.today()
    for ind in indicators:
        cached = repo.get_macro(ind.key)
        if cached is None or not cached.series:
            continue
        state = freshness.assess_source_series(
            ind.freq, cached.data_date, today,
            [value for _, value in cached.series], key=ind.key)
        if not state.usable:
            continue
        _, reason = scoring_macro.ALERT_FUNCS[ind.key](cached.series)
        if reason != scoring_macro.INSUFFICIENT:
            valid += 1
    return Coverage(valid, len(indicators))


def _macro_alerts(repo: SqliteRepo, indicators) -> tuple[dict[str, bool], dict[str, str]]:
    """逐項警示與它們的名稱，給 8-9 的算術總結句用。算不出來的不計入分母。"""
    alerts: dict[str, bool] = {}
    names: dict[str, str] = {}
    today = dt.date.today()
    for ind in indicators:
        cached = repo.get_macro(ind.key)
        if cached is None or not cached.series:
            continue
        state = freshness.assess_source_series(
            ind.freq, cached.data_date, today,
            [value for _, value in cached.series], key=ind.key)
        if not state.usable:
            continue
        hit, reason = scoring_macro.ALERT_FUNCS[ind.key](cached.series)
        if reason == scoring_macro.INSUFFICIENT:
            continue
        alerts[ind.key] = hit
        names[ind.key] = ind.name
    return alerts, names


def _score_chart(repo: SqliteRepo, scope: str, label: str) -> str:
    """分數歷史的混合取樣折線圖（§5.3、8-10）。沒有歷史就不畫，不畫空盒子。"""
    history = [(record.as_of.isoformat(), record.score)
               for record in repo.get_scores(scope, "-") if record.score is not None]
    points = sampling.mixed_sample(history, today=dt.date.today())
    if not points:
        return ""
    return svg.score_chart(points, label=label)


def _index_rows(symbols) -> list[Row]:
    rows: list[Row] = []
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    try:
        return _index_rows_from_repo(symbols, repo)
    finally:
        repo.close()


def _index_rows_from_repo(symbols, repo: SqliteRepo) -> list[Row]:
    rows: list[Row] = []
    for symbol in symbols:
        bars = csv_audit.read_current(symbol)
        if not bars:
            rows.append(Row(label=symbol, value=None, data_date=None,
                            note="本機沒有序列"))
            continue

        state = freshness.assess_source_series(
            "每日", bars[-1].date, dt.date.today(),
            [bar.close for bar in bars], key=symbol,
        )
        if not state.usable:
            rows.append(Row(
                label=symbol, value=None, data_date=bars[-1].date.isoformat(),
                freq="每日", note=state.reason,
                source=bars[-1].source,
                fetched_at=bars[-1].as_of.strftime("%Y-%m-%d %H:%M"),
            ))
            continue

        adjusted = repo.get_adjusted_prices(symbol)
        if not adjusted or adjusted[-1].date < bars[-1].date:
            rows.append(Row(
                label=symbol, value=None, data_date=bars[-1].date.isoformat(),
                freq="每日", note="還原序列資料不足，無法計分",
                source=bars[-1].source,
                fetched_at=bars[-1].as_of.strftime("%Y-%m-%d %H:%M"),
            ))
            continue
        scored = run_scores.score_series(symbol, adjusted)
        summary = run_scores.summarize_window(scored)
        latest_date, latest = scored[-1]

        notes = [chip_reading(symbol).caveat]
        gaps = scoring_index.etf_data_gaps(symbol)
        if gaps:
            notes.append(f"ETF 特有但算不出來的：{'、'.join(gaps)}")
        if latest.alert_keys:
            notes.append("警示維度：" + "、".join(
                latest.reasons[k] for k in latest.alert_keys
            ))

        wavg = summary["weighted_average"]
        rows.append(
            Row(
                label=symbol,
                value=(f"{latest.score:.1f}" if latest.score is not None else None),
                data_date=latest_date.isoformat(),
                freq="每日",
                series=[(d.isoformat(), s.score) for d, s in scored],
                change=(f"五日加權 {wavg:.1f}（{latest.valid} 個維度）"
                        if wavg is not None else None),
                note="｜".join(n for n in notes if n),
                coverage=latest.coverage,
                coverage_name="技術面",
                source=bars[-1].source,
                fetched_at=bars[-1].as_of.strftime("%Y-%m-%d %H:%M"),
            )
        )
    return rows


def build_tabs() -> list[Tab]:
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    try:
        world = _macro_rows(repo, macro_spec.WORLD + macro_spec.OBSERVE)
        taiwan = _macro_rows(repo, macro_spec.TAIWAN)
        world_coverage = _macro_coverage(repo, macro_spec.WORLD)
        taiwan_coverage = _macro_coverage(repo, macro_spec.TAIWAN)
        world_alerts, world_names = _macro_alerts(repo, macro_spec.WORLD)
        taiwan_alerts, taiwan_names = _macro_alerts(repo, macro_spec.TAIWAN)
        world_chart = _score_chart(repo, "macro_world", "世界層分數")
        taiwan_chart = _score_chart(repo, "macro_tw", "台灣層分數")
    finally:
        repo.close()

    return [
        Tab(key="world", title="世界總體經濟", rows=world,
            intro=f"{summary.layer_sentence('世界層', world_alerts, world_names)}"
                  f"｜{world_coverage.label('世界層')}"
                  f"{'｜低涵蓋・分數降級' if world_coverage.degraded else ''}｜{WORLD_INTRO}",
            coverage=world_coverage, chart=world_chart),
        Tab(key="tw", title="台灣總體經濟", rows=taiwan,
            intro=f"{summary.layer_sentence('台灣層', taiwan_alerts, taiwan_names)}"
                  f"｜{taiwan_coverage.label('台灣層')}"
                  f"{'｜低涵蓋・分數降級' if taiwan_coverage.degraded else ''}｜{TW_INTRO}",
            coverage=taiwan_coverage, chart=taiwan_chart),
        Tab(key="tw_index", title="台股大盤與 ETF",
            rows=_index_rows(config.TW_SYMBOLS), intro=INDEX_INTRO),
        Tab(key="us_index", title="美股大盤與 ETF",
            rows=_index_rows(config.US_SYMBOLS), intro=INDEX_INTRO),
    ]


def last_fetch_at() -> str | None:
    """管線最後一次**抓資料**跑完的時間（不是發布時間，也不是現在時間）。

    來源是 run log，而不是 `datetime.now()` —— 用現在時間的話，發布腳本自己
    跑一下就會把那行時間刷新，即使一整天沒抓到任何新東西。那正是這個欄位
    最容易變成謊話的方式。

    只認真的有抓資料的那幾種 task；publish、verify、full_reconcile 這些
    不算「抓取」。查不到就回 None，讓頁面整行不顯示。
    """
    fetch_tasks = {
        "daily_tw", "daily_us", "macro", "day24_bootstrap",
        "day24_stocks", "chips_tw", "chips_tw_evening", "chips_tw_late",
        "crosscheck_tw",
    }
    stamps: list[str] = []
    today = dt.date.today()
    for ym in {today.strftime("%Y-%m"),
               (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")}:
        for r in read_runs(ym):
            if r.get("task") in fetch_tasks and r.get("ended_at"):
                stamps.append(r["ended_at"])
    if not stamps:
        return None
    return max(stamps).replace("T", " ")[:16]
