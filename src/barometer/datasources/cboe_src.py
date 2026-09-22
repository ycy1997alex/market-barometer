"""CBOE VIX3M adapter（ToDo §7.1、§9 第八批 8-3）。

**免金鑰。** 來源是 CBOE 自己掛的日線 CSV：
`https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv`
實測 2026-09-22 取到 2026-09-21（T-1），格式 `DATE,OPEN,HIGH,LOW,CLOSE`，
日期是美式 `MM/DD/YYYY`。

⚠️ **不留 Yahoo fallback。** Yahoo 的 `^VIX3M` 已經凍結 —— 留著當退路等於
「官方壞掉時安靜地改用一條不會動的序列」，那比直接缺料還糟：缺料看得出來，
凍結的序列看起來很正常，而且會一路算進分數裡。
"""
from __future__ import annotations

import csv
import datetime as dt
import io

import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle, retry_once

SOURCE = "cboe"

VIX3M_HISTORY = ("https://cdn.cboe.com/api/global/us_indices/daily_prices/"
                 "VIX3M_History.csv")

# 一天更新一次的靜態檔，沒必要打得密
_THROTTLE = Throttle(min_interval=1.0)
_UA = "market-barometer/0.1 (personal research; contact via GitHub)"

TAIL = 30


def parse_history(text: str, tail: int = TAIL) -> list[tuple[str, float]]:
    """回 (ISO 日期, 收盤) 由舊到新。收盤空白的列直接丟掉，不補 0。"""
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        raw_date = (row.get("DATE") or "").strip()
        raw_close = (row.get("CLOSE") or "").strip()
        if not raw_date or not raw_close:
            continue
        try:
            day = dt.datetime.strptime(raw_date, "%m/%d/%Y").date()
            close = float(raw_close)
        except ValueError:
            continue
        rows.append((day.isoformat(), close))
    if not rows:
        raise FetchError("CBOE VIX3M：沒有任何有效資料點")
    rows.sort()
    return rows[-tail:]


def fetch_vix3m(tail: int = TAIL) -> list[tuple[str, float]]:
    def _get() -> str:
        _THROTTLE.wait()
        COUNTER.bump(SOURCE)
        try:
            resp = requests.get(VIX3M_HISTORY, timeout=30, headers={"User-Agent": _UA})
        except requests.RequestException as exc:
            raise FetchError(f"CBOE: {exc}") from exc
        if resp.status_code != 200:
            raise FetchError(f"CBOE: HTTP {resp.status_code}")
        return resp.text

    return parse_history(retry_once(_get, backoff=3.0), tail=tail)


def data_date(series: list[tuple[str, float]]) -> dt.date | None:
    if not series:
        return None
    try:
        return dt.date.fromisoformat(series[-1][0])
    except ValueError:
        return None
