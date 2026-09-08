"""yfinance adapter（ToDo §6、§4.3）。

節流：批次之間 sleep 1 秒，**禁用 threads=True**（§6 規則 2）。yfinance 沒有官方
速率數字，但實測會被暫時封鎖，所以寧可慢。

缺值紀律（§4.3）：單一欄位缺值 → 保留前一日值、該格標 stale、記進 run log、
繼續跑完其他標的。**任何單一標的的失敗都不得中止整批。**
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from barometer.datasources.base import COUNTER, FetchError, Throttle
from barometer.domain.ports import PriceBar

SOURCE = "yfinance"

# module-level 節流器 —— 任何呼叫路徑都繞不過去（§6 規則 1）
_THROTTLE = Throttle(min_interval=1.0)

_OHLC = ("Open", "High", "Low", "Close")


def _clean(value) -> float | None:
    """NaN → None。NaN 會安靜地往下游傳染，None 在顯示層是明確的「—」。"""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def bars_from_frame(
    symbol: str, df: pd.DataFrame, as_of: dt.datetime
) -> list[PriceBar]:
    """把 yfinance 的 DataFrame 轉成 PriceBar，順手處理缺值。

    抽成純轉換函式是為了能離線測 —— 測試餵 DataFrame 就好，不必打網路。
    """
    if df is None or df.empty:
        raise FetchError(f"{symbol}: yfinance 回了空的 DataFrame")

    # 多標的下載時欄位是 MultiIndex，這裡只處理單一標的
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)

    if "Close" not in df.columns:
        raise FetchError(
            f"{symbol}: 回應缺 Close 欄位（欄位集合會隨 auto_adjust 變，§4.4）"
        )

    bars: list[PriceBar] = []
    prev: dict[str, float | None] = {k: None for k in _OHLC}

    for idx, row in df.iterrows():
        date = idx.date() if hasattr(idx, "date") else dt.date.fromisoformat(str(idx))
        values = {k: _clean(row.get(k)) for k in _OHLC}
        volume = _clean(row.get("Volume"))

        # 任何一欄缺 → 這一格是 stale，缺的欄位保留前一日值
        stale = any(v is None for v in values.values())
        for k in _OHLC:
            if values[k] is None:
                values[k] = prev[k]

        bars.append(
            PriceBar(
                symbol=symbol,
                date=date,
                open=values["Open"],
                high=values["High"],
                low=values["Low"],
                close=values["Close"],
                volume_shares=volume,
                source=SOURCE,
                as_of=as_of,
                stale=stale,
            )
        )
        for k in _OHLC:
            if values[k] is not None:
                prev[k] = values[k]

    return bars


def fetch_daily(
    symbol: str,
    period: str = "1y",
    auto_adjust: bool = False,
    as_of: dt.datetime | None = None,
) -> list[PriceBar]:
    """抓一檔的日線。

    auto_adjust=False 是刻意的，但要記得它**不等於**原始價格 —— yfinance 回的
    Close 已含分割調整（§4.4）。這一層不做任何修正，比對與修復是別層的事。
    """
    import yfinance as yf

    _THROTTLE.wait()
    COUNTER.bump(SOURCE)
    as_of = as_of or dt.datetime.now()

    try:
        df = yf.Ticker(symbol).history(
            period=period, interval="1d", auto_adjust=auto_adjust
        )
    except Exception as exc:  # noqa: BLE001 — 任何失敗都只讓這一檔 stale
        raise FetchError(f"{symbol}: yfinance 抓取失敗 — {exc}") from exc

    return bars_from_frame(symbol, df, as_of=as_of)


def fetch_many(
    symbols: list[str],
    period: str = "1y",
    as_of: dt.datetime | None = None,
) -> tuple[dict[str, list[PriceBar]], dict[str, str]]:
    """逐檔抓（不併發）。回傳 (成功的, 失敗原因)。

    單一標的失敗只記進失敗表，不丟例外 —— 整批照樣跑完（§4.3）。
    """
    ok: dict[str, list[PriceBar]] = {}
    failed: dict[str, str] = {}
    for sym in symbols:
        try:
            ok[sym] = fetch_daily(sym, period=period, as_of=as_of)
        except FetchError as exc:
            failed[sym] = str(exc)
    return ok, failed
