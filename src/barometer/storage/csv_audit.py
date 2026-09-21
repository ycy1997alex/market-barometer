"""價格落地：兩份（ToDo §4.4 第 1 點）。

- price_raw\\<YYYY-MM-DD>.jsonl.gz  每天一檔，含 as_of，**append-only 的稽核軌跡**
- price_current\\            最新未還原序列，允許被覆寫，比對與顯示用

為什麼要兩份：yfinance 會回頭改寫歷史（分割、除權息），而且改了不一定會說
（0050.TW 的 Stock Splits 欄位是空的）。只留一份「最新」就永遠證明不了它改過。

這些檔案全都在 STOCKDATA_ROOT 底下，**不進任何 repo**（§1 第 7 條）。
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
from pathlib import Path
from typing import NamedTuple

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
    """Append this fetch to one compressed daily audit file, never overwrite."""
    path = config.price_raw_path(run_date.isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "at", encoding="utf-8", newline="\n") as fh:
        for row in _rows(bars):
            record = {key: "" if value is None else str(value) for key, value in zip(_HEADER, row)}
            fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return path


def read_raw(run_date: dt.date) -> list[dict[str, str]]:
    """Read both daily gzip records and any not-yet-migrated legacy CSVs."""
    out: list[dict[str, str]] = []
    path = config.price_raw_path(run_date.isoformat())
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            out.extend(json.loads(line) for line in fh if line.strip())
    legacy_dir = config.price_raw_dir(run_date.isoformat())
    if legacy_dir.exists():
        for legacy in sorted(legacy_dir.glob("*.csv")):
            with legacy.open(newline="", encoding="utf-8") as fh:
                out.extend(dict(row) for row in csv.DictReader(fh))
    return out


class CurrentWrite(NamedTuple):
    """寫完之後呼叫端需要知道的兩件事。

    `retained` 是「來源這次沒回、本機留著」的那些交易日。空的才是正常的一天 ——
    非空就要進 run log，安靜地補洞跟安靜地挖洞一樣糟，兩者事後都查不出來。
    """
    path: Path
    retained: list[dt.date]


def write_current(
    symbol: str, bars: list[PriceBar], replace: bool = False
) -> CurrentWrite:
    """寫最新完整序列。**同一天的以這次抓回來的為準，本機獨有的日期留著。**

    原本這裡是整份覆寫，而 yfinance 回 `0050.TW`、`006208.TW` 時固定會漏掉
    前一個交易日（隔天才補），於是顯示用的那份每天都有一個洞 —— SQLite 那份
    沒有（upsert 累積），偏偏 `build_page` 讀的是這份。連續四天沒人發現。

    保留既有的列是**補洞（backfill，§4.1）**：一個值都不動，只是不要把列刪掉。
    來源回頭改寫歷史是 `compare_overlap` 的職責（記旗標），不在這裡處理。

    `replace=True` 才是整條覆寫，只留給 `tools/refetch.py` —— 重抓的用途正是
    「本機這份是錯的」，那時候保留舊列會把要修掉的東西留下來（§1 紅線 6：
    重抓永遠是手動的）。
    """
    d = config.price_current_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_safe_name(symbol)}.csv"

    merged = list(bars)
    retained: list[dt.date] = []
    if not replace:
        incoming = {b.date for b in bars}
        kept = [b for b in _read_path(path) if b.date not in incoming]
        retained = sorted(b.date for b in kept)
        merged += kept
    merged.sort(key=lambda b: b.date)

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_HEADER)
        w.writerows(_rows(merged))
    return CurrentWrite(path=path, retained=retained)


def read_current(symbol: str) -> list[PriceBar]:
    """讀回最新序列。檔案不存在就是空的，不是錯誤（第一天本來就沒有）。"""
    return _read_path(config.price_current_dir() / f"{_safe_name(symbol)}.csv")


def _read_path(path: Path) -> list[PriceBar]:
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
