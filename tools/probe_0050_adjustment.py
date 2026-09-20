"""One-off 0050 source comparison across split and cash ex-dividend events.

Print only the event-day and preceding trading-day OHLC, volume, and close delta.
No credentials or full vendor price series are written to a repository.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer.datasources import shioaji_src


EVENTS = ((dt.date(2025, 6, 10), dt.date(2025, 6, 18)),
          (dt.date(2025, 7, 18), dt.date(2025, 7, 21)))
SELECTED = {day for pair in EVENTS for day in pair}
START = dt.date(2025, 6, 9)
END = dt.date(2025, 7, 22)


def twse_month(month: int) -> dict[dt.date, dict]:
    response = requests.get(
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
        params={"response": "json", "date": f"2025{month:02d}01", "stockNo": "0050"},
        headers={"User-Agent": "market-barometer/0.1 (personal research; contact via GitHub)"},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    rows = {}
    for values in body.get("data", []):
        roc_year, mo, day = values[0].split("/")
        date = dt.date(int(roc_year) + 1911, int(mo), int(day))
        rows[date] = {
            "close": float(values[6].replace(",", "")),
            "open": float(values[3].replace(",", "")),
            "high": float(values[4].replace(",", "")),
            "low": float(values[5].replace(",", "")),
            "volume": float(values[1].replace(",", "")),
        }
    return rows


def emit(label: str, data: dict[dt.date, dict]) -> None:
    print(label)
    for before, event in EVENTS:
        first, last = data.get(before), data.get(event)
        print(json.dumps({
            "before": before.isoformat(), "before_row": first,
            "event": event.isoformat(), "event_row": last,
            "close_delta": round(last["close"] - first["close"], 4) if first and last else None,
        }, ensure_ascii=False))


def main() -> None:
    completed: set[str] = set()
    # The adapter handles login, batching, logout, and quota reporting.
    try:
        shioaji_bars, usage = shioaji_src.fetch_daily("0050.TW", START, END)
        shioaji = {
            bar.date: {"close": bar.close, "open": bar.open, "high": bar.high,
                       "low": bar.low, "volume": bar.volume_shares}
            for bar in shioaji_bars if bar.date in SELECTED
        }
        emit("Shioaji", shioaji)
        print("Shioaji count", len(shioaji_bars), "quota remaining bytes", usage.get("remaining_bytes"))
        if SELECTED <= shioaji.keys():
            completed.add("Shioaji")
    except Exception as exc:
        print("Shioaji failed:", type(exc).__name__)

    try:
        frame = yf.Ticker("0050.TW").history(
            start=START.isoformat(), end=(END + dt.timedelta(days=1)).isoformat(),
            interval="1d", auto_adjust=False, actions=True,
        )
        yahoo = {
            idx.date(): {"close": float(row["Close"]), "open": float(row["Open"]),
                         "high": float(row["High"]), "low": float(row["Low"]),
                         "volume": float(row["Volume"]),
                         "adj_close": float(row["Adj Close"]) if "Adj Close" in row else None,
                         "dividend": float(row["Dividends"]) if "Dividends" in row else None,
                         "split": float(row["Stock Splits"]) if "Stock Splits" in row else None}
            for idx, row in frame.iterrows() if idx.date() in SELECTED
        }
        emit("Yahoo", yahoo)
        print("Yahoo count", len(frame))
        if SELECTED <= yahoo.keys():
            completed.add("Yahoo")
    except Exception as exc:
        print("Yahoo failed:", type(exc).__name__)

    try:
        official = twse_month(6) | twse_month(7)
        emit("TWSE", official)
        print("TWSE selected count", len(SELECTED & official.keys()))
        if SELECTED <= official.keys():
            completed.add("TWSE")
    except Exception as exc:
        print("TWSE failed:", type(exc).__name__)
    if completed != {"Shioaji", "Yahoo", "TWSE"}:
        raise SystemExit("One or more sources did not return all four event dates")


if __name__ == "__main__":
    main()
