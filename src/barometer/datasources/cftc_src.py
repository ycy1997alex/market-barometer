"""CFTC 交易人持倉報告（COT）adapter（ToDo §7.1、§9 第八批 8-11）。

**免金鑰。** 走 CFTC 自己的 Socrata 端點
`https://publicreporting.cftc.gov/resource/6dca-aqww.json`（期貨版，實測
2026-09-22 最新一期是 2026-09-15；週五公布、資料日是週二）。

⚠️ **這是觀測項：不評分、不算百分位、不加解讀文字。**
「非商業淨多 −100,461 口，週變化 +2,000 口」本身就說完了。再加一句
「處於歷史高檔」需要一把「多高算高」的尺，而那把尺這裡沒有 —— 憑空造一把
就是把讀者的判斷換成我們的。

淨部位 = 非商業多單 − 非商業空單。週變化取官方自己算好的那兩欄，不自己從
兩期相減 —— 官方的版本考慮了合約改版與修正。
"""
from __future__ import annotations

import datetime as dt

import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle, retry_once

SOURCE = "cftc"

ENDPOINT = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

# 實測用的市場全名（代碼會變，名字不會）
MARKETS = {
    "cot_spx": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
    "cot_gold": "GOLD - COMMODITY EXCHANGE INC.",
    "cot_wti": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
}

TAIL = 30
_THROTTLE = Throttle(min_interval=1.0)
_UA = "market-barometer/0.1 (personal research; contact via GitHub)"


def _int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_report(rows: list[dict]) -> list[tuple[str, float]]:
    """回 (報告日, 非商業淨部位) 由舊到新。缺任一邊的那一列直接丟掉。"""
    out: list[tuple[str, float]] = []
    for row in rows:
        long_side = _int(row.get("noncomm_positions_long_all"))
        short_side = _int(row.get("noncomm_positions_short_all"))
        label = str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]
        if long_side is None or short_side is None or len(label) != 10:
            continue
        out.append((label, float(long_side - short_side)))
    if not out:
        raise FetchError("CFTC COT：沒有任何有效資料點")
    out.sort()
    return out[-TAIL:]


def weekly_change(rows: list[dict]) -> int | None:
    """最新一期的淨部位週變化，用官方算好的兩欄。"""
    if not rows:
        return None
    latest = max(rows, key=lambda row: str(row.get("report_date_as_yyyy_mm_dd") or ""))
    long_change = _int(latest.get("change_in_noncomm_long_all"))
    short_change = _int(latest.get("change_in_noncomm_short_all"))
    if long_change is None or short_change is None:
        return None
    return long_change - short_change


def fetch(market: str, limit: int = TAIL) -> list[dict]:
    def _get() -> list[dict]:
        _THROTTLE.wait()
        COUNTER.bump(SOURCE)
        try:
            resp = requests.get(
                ENDPOINT,
                params={"market_and_exchange_names": market, "$limit": limit,
                        "$order": "report_date_as_yyyy_mm_dd DESC"},
                timeout=30, headers={"User-Agent": _UA})
        except requests.RequestException as exc:
            raise FetchError(f"CFTC: {exc}") from exc
        if resp.status_code != 200:
            raise FetchError(f"CFTC: HTTP {resp.status_code}")
        return resp.json()

    return retry_once(_get, backoff=3.0)


def fetch_net_positions(market: str) -> list[tuple[str, float]]:
    return parse_report(fetch(market))


def data_date(series: list[tuple[str, float]]) -> dt.date | None:
    if not series:
        return None
    try:
        return dt.date.fromisoformat(series[-1][0])
    except ValueError:
        return None
