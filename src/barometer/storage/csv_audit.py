"""價格落地：兩份（ToDo §4.4 第 1 點）。

- price_raw\\<YYYY-MM-DD>\\  當天抓到什麼就存什麼，含 as_of，**append-only 的稽核軌跡**
- price_current\\            最新完整序列，允許被覆寫，計算用

為什麼要兩份：yfinance 會回頭改寫歷史（分割、除權息），而且改了不一定會說
（0050.TW 的 Stock Splits 欄位是空的）。只留一份「最新」就永遠證明不了它改過。

這些檔案全都在 STOCKDATA_ROOT 底下，**不進任何 repo**（§1 第 7 條）。
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from barometer import config
from barometer.domain.ports import PriceBar

_HEADER = [
    "symbol", "date", "open", "high", "low", "close",
    "volume_shares", "source", "as_of", "stale",
]


def _safe_name(symbol: str) -> str:
    """^TWII、0050.TW → 檔名安全的形式。"""
    return symbol.replace("^", "IDX_").replace("=", "_").replace("/", "_")


def _rows(bars: list[PriceBar]) -> list[list]:
    return [
        [b.symbol, b.date.isoformat(), b.open, b.high, b.low, b.close,
         b.volume_shares, b.source, b.as_of.isoformat(), int(b.stale)]
        for b in bars
    ]


def write_raw(symbol: str, bars: list[PriceBar], run_date: dt.date) -> Path:
    """寫進當天的稽核軌跡。同一天重跑會**附加**，不覆寫 —— 這就是重點。"""
    d = config.price_raw_dir(run_date.isoformat())
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_safe_name(symbol)}.csv"
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not exists:
            w.writerow(_HEADER)
        w.writerows(_rows(bars))
    return path


def write_current(symbol: str, bars: list[PriceBar]) -> Path:
    """寫最新完整序列。允許被覆寫。"""
    d = config.price_current_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_safe_name(symbol)}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_HEADER)
        w.writerows(_rows(bars))
    return path


def read_current(symbol: str) -> list[PriceBar]:
    """讀回最新序列。檔案不存在就是空的，不是錯誤（第一天本來就沒有）。"""
    path = config.price_current_dir() / f"{_safe_name(symbol)}.csv"
    if not path.exists():
        return []

    def num(v: str) -> float | None:
        return float(v) if v not in ("", "None") else None

    out: list[PriceBar] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append(
                PriceBar(
                    symbol=r["symbol"],
                    date=dt.date.fromisoformat(r["date"]),
                    open=num(r["open"]), high=num(r["high"]),
                    low=num(r["low"]), close=num(r["close"]),
                    volume_shares=num(r["volume_shares"]),
                    source=r["source"],
                    as_of=dt.datetime.fromisoformat(r["as_of"]),
                    stale=r["stale"] in ("1", "True", "true"),
                )
            )
    return out
