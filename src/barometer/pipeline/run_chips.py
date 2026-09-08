"""市場級籌碼面管線（ToDo §9 Day 26 第 2 項）。

四個來源、三種單位，全部是**台股市場整體**的數字：

    TWSE T86        三大法人買賣超（**股**）—— 逐檔加總成市場合計
    TWSE MI_MARGN   融資融券餘額（**張**）
    期交所 futContracts  台指期三大法人未平倉（**口**）
    期交所 pcRatio       選擇權 put/call 未平倉比（%）

**任何一個來源缺席都不得中止整批**（§4.3 的規則同樣適用在這裡）。四個來源
的「沒資料」長相各不相同 —— TWSE 回一句中文、期交所回只有表頭 —— 但處置
一致：記一筆 note，那個維度當天就是沒有，**不是 0**（§10）。

融資「維持率」§8.2 有列，但市場級的維持率找不到公開來源（MI_MARGN 只給
餘額）。**沒有就是沒有，不從餘額硬推一個** —— 這一項記在 run log 的 note 裡
當作待確認，不假裝算得出來。

---

**四個來源的公布時間不一樣，所以分兩班抓：**

    三大法人 T86      約 17:30 更新完   → 18:00 那班抓得到
    台指期 / put-call  盤後很快就有      → 18:00 那班抓得到
    融資融券 MI_MARGN  約 21:30 更新完（可能更晚）→ 18:00 抓不到

18:00 那一班**刻意不去問融資融券** —— 不是抓了失敗，是根本不發那個請求。
少打一次註定落空的呼叫，run log 也不會每天多一筆看起來像故障的失敗（§6）。
補抓排在 22:30，只抓融資融券，而且是**併進**當天既有的那一列，不覆寫。

（這也是「頁面上為什麼不能只有一個更新時間」的另一個實例：同一天的台股盤後
資料，兩個來源就差了四個小時。）
"""
from __future__ import annotations

import datetime as dt

from barometer import config
from barometer.datasources import taifex_src, twse_src
from barometer.datasources.base import COUNTER, FetchError
from barometer.pipeline.runlog import RunLog
from barometer.storage.sqlite_repo import SqliteRepo

# §8.2 列了維持率，但沒有市場級的公開來源 —— 誠實記下來，不硬推
MISSING_BY_DESIGN = "融資維持率：市場級無公開來源，MI_MARGN 只給餘額（待確認）"

# 分班（見模組說明）。兩班加起來要涵蓋全部，而且不能重疊。
ALL_PARTS = ("t86", "margin", "futures", "pcratio")
EVENING_PARTS = ("t86", "futures", "pcratio")   # 18:00
LATE_PARTS = ("margin",)                        # 22:30


def merge_payload(existing: dict, incoming: dict) -> dict:
    """把後一班抓到的併進前一班寫好的那一列。

    兩條規矩：

    1. **同一個 key 由後來的覆寫** —— 融資的「今日餘額」本來就會被改。
    2. **`None` 不覆寫** —— 抓失敗回的是 None，不能讓一次失敗把前一班
       （或昨天）寫好的值洗掉。這跟 §4.3「缺值保留前一日值」同一個道理。
    """
    merged = dict(existing)
    merged.update({k: v for k, v in incoming.items() if v is not None})
    return merged


def _t86_market_total(date: dt.date, log: RunLog) -> dict:
    """T86 是逐檔的，市場合計要自己加總。單位維持「股」。"""
    rows = twse_src.fetch_t86(date)
    out = {
        "foreign_net_shares": 0.0,
        "trust_net_shares": 0.0,
        "dealer_net_shares": 0.0,
        "total_net_shares": 0.0,
    }
    for r in rows:
        for key, src in (
            ("foreign_net_shares", "foreign_net_shares"),
            ("trust_net_shares", "trust_net_shares"),
            ("dealer_net_shares", "dealer_net_shares"),
            ("total_net_shares", "total_net_shares"),
        ):
            v = r.get(src)
            if v is not None:
                out[key] += v
    log.set_count(f"t86_rows::{date.isoformat()}", len(rows))
    return out


def collect(
    date: dt.date, log: RunLog, parts: tuple[str, ...] = ALL_PARTS
) -> dict:
    """把指定的那幾個來源收成一個 payload。缺哪一塊就少哪幾個 key。

    `parts` 決定這一班要問哪些來源 —— 18:00 那班不含 `margin`，因為那時候
    證交所還沒公布（見模組說明）。**不問**跟**問了失敗**是兩回事：前者不會
    在 run log 留下看起來像故障的紀錄。
    """
    payload: dict = {}

    if "t86" in parts:
        try:
            payload.update(_t86_market_total(date, log))
        except FetchError as exc:
            log.note(f"{date} T86：{exc}")

    if "margin" in parts:
        try:
            m = twse_src.fetch_margin(date)
            payload["margin_lots"] = m.margin_today_lots
            payload["short_lots"] = m.short_today_lots
            # 「今日餘額」是暫定值，定稿要等隔天的「前日餘額」（見 MarginReport）
            payload["margin_is_provisional"] = True
            payload["margin_prev_lots"] = m.margin_prev_lots
        except FetchError as exc:
            log.note(f"{date} MI_MARGN：{exc}")

    if "futures" in parts:
        try:
            f = taifex_src.fetch_fut_oi(date)
            foreign = f.by_investor.get("外資及陸資", {})
            payload["fut_foreign_net_oi_contracts"] = foreign.get("net_oi_contracts")
            payload["fut_total_net_oi_contracts"] = f.total_net_oi_contracts
        except FetchError as exc:
            log.note(f"{date} 台指期未平倉：{exc}")

    if "pcratio" in parts:
        try:
            rows = taifex_src.fetch_pc_ratio(date, date)
            if rows:
                payload["pc_oi_ratio_pct"] = rows[0].get("pc_oi_ratio_pct")
                payload["pc_volume_ratio_pct"] = rows[0].get("pc_volume_ratio_pct")
        except FetchError as exc:
            log.note(f"{date} put/call ratio：{exc}")

    return payload


def run(
    dates: list[dt.date],
    task: str = "chips_tw",
    parts: tuple[str, ...] = ALL_PARTS,
) -> RunLog:
    log = RunLog(task=task)
    COUNTER.reset()
    if "margin" in parts:
        log.note(MISSING_BY_DESIGN)
    log.note(f"這一班抓：{'、'.join(parts)}")

    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    as_of = dt.datetime.now()

    try:
        for date in dates:
            payload = collect(date, log, parts)
            if not payload:
                # 這一班要的來源全都沒有 → 還沒公布，**不寫一列全零進去**
                log.count("days_empty")
                log.note(f"{date}：這一班的來源都沒有資料，當作還沒公布，不落地")
                continue
            # **併進既有的那一列，不覆寫** —— 22:30 那班不能洗掉 18:00 寫好的
            merged = merge_payload(repo.get_chips(date) or {}, payload)
            repo.put_chips(date, merged, as_of)
            log.count("days_ok")
            log.set_count(f"fields::{date.isoformat()}", len(merged))

        log.quota["requests"] = COUNTER.snapshot()
        log.finish("partial" if log.counts.get("days_empty") else "ok")
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    finally:
        repo.close()

    log.append()
    return log
