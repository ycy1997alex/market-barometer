"""比對（ToDo §4.1）與 shioaji × yfinance 交叉比對（§4.2）。

**比對是煙霧偵測器、回看是補漏、重抓是修復。自動化只做第一件。**

這個模組**永遠不寫資料、永遠不修資料**。它回傳的是判斷，不是「該寫入什麼」。
自動修復一律不做 —— 半夜自己重寫歷史卻沒人知道，比壞掉還糟（§12 紅線第 7 條）。

純規則 → 放 domain，離線可測、零 I/O。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from barometer.domain.ports import PriceBar

# §4.2 的容忍度
CLOSE_TOLERANCE = 0.001   # 價格欄位相對差 0.1%
VOLUME_TOLERANCE = 0.01   # 成交量相對差 1%

# 浮點雜訊：比 0.1% 小兩個數量級，用來濾掉存取往返造成的尾差
_NOISE = 1e-6

PRICE_FIELDS = ("open", "high", "low", "close")


@dataclass(frozen=True, slots=True)
class CompareResult:
    """比對結果。刻意**不含**任何「該寫回什麼」的欄位。"""

    suspect_adjust: bool
    mismatches: list[dict] = field(default_factory=list)
    compared_dates: list[dt.date] = field(default_factory=list)
    ratio: float | None = None


def _rel_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b))
    return 0.0 if denom == 0 else abs(a - b) / denom


def compare_overlap(
    stored: list[PriceBar], fetched: list[PriceBar]
) -> CompareResult:
    """拿今天抓回來的，跟本機已存的**同一批日期**逐格比。

    只比重疊的日期 —— 新日期不是「對不上」，那是回看要補的洞。
    自己標成 stale 的列跳過（那格本來就是保留前一日值，比了只會製造假警報）。
    """
    stored_by_date = {b.date: b for b in stored if not b.stale}
    mismatches: list[dict] = []
    compared: list[dt.date] = []
    ratios: list[float] = []

    for new in fetched:
        old = stored_by_date.get(new.date)
        if old is None or new.stale:
            continue
        compared.append(new.date)
        if old.close is None or new.close is None:
            continue
        if _rel_diff(old.close, new.close) > _NOISE:
            mismatches.append(
                {
                    "symbol": new.symbol,
                    "date": new.date,
                    "field": "close",
                    "stored": old.close,
                    "fetched": new.close,
                }
            )
            if old.close:
                ratios.append(new.close / old.close)

    # 整條被乘上同一個常數 = 分割或除權息的指紋
    ratio = None
    if ratios and max(ratios) - min(ratios) < 1e-6:
        ratio = ratios[0]

    return CompareResult(
        suspect_adjust=bool(mismatches),
        mismatches=mismatches,
        compared_dates=sorted(compared),
        ratio=ratio,
    )


def cross_check(
    shioaji_bars: list[PriceBar],
    yf_bars: list[PriceBar],
    compare_volume: bool = True,
) -> tuple[list[PriceBar], list[dict]]:
    """§4.2 交叉比對，衝突以 shioaji 為主。

    - 兩邊都有 → 比對後以 shioaji 為主
    - 只有 yfinance 有 → 用 yfinance，source 標 yf_only
    - 只有 shioaji 有 → 用 shioaji
    - 兩邊都沒有 → 這裡不會出現（呼叫端負責保留前一日並標 stale）

    `compare_volume=False` 給**指數**用：指數的「成交量」兩家定義不同
    （實測 ^TWII 差約 2000 倍，而價格四欄完全對得上），硬比只會每天產生
    一堆假衝突，淹掉真正該注意的那幾筆。

    price_conflict 每天的筆數要進 run log。**筆數突然變多本身就是警報** ——
    這句話成立的前提是平常的筆數有意義，所以假衝突要在源頭就擋掉。
    """
    sj_by_date = {b.date: b for b in shioaji_bars}
    yf_by_date = {b.date: b for b in yf_bars}

    merged: list[PriceBar] = []
    conflicts: list[dict] = []

    for date in sorted(set(sj_by_date) | set(yf_by_date)):
        sj = sj_by_date.get(date)
        yf = yf_by_date.get(date)

        if sj is None:
            merged.append(_retag(yf, "yf_only"))
            continue
        if yf is None:
            merged.append(sj)
            continue

        for f in PRICE_FIELDS:
            a, b = getattr(sj, f), getattr(yf, f)
            if a is None or b is None:
                continue
            if _rel_diff(a, b) > CLOSE_TOLERANCE:
                conflicts.append(_conflict(sj.symbol, date, f, a, b))

        if compare_volume:
            a, b = sj.volume_shares, yf.volume_shares
            if a is not None and b is not None and _rel_diff(a, b) > VOLUME_TOLERANCE:
                conflicts.append(_conflict(sj.symbol, date, "volume", a, b))

        merged.append(sj)  # 衝突與否都以 shioaji 為主

    return merged, conflicts


def _conflict(
    symbol: str, date: dt.date, fld: str, sj_value: float, yf_value: float
) -> dict:
    return {
        "symbol": symbol,
        "date": date,
        "field": fld,
        "shioaji_value": sj_value,
        "yf_value": yf_value,
        "taken": "shioaji",
    }


def _retag(bar: PriceBar, source: str) -> PriceBar:
    return PriceBar(
        symbol=bar.symbol, date=bar.date, open=bar.open, high=bar.high,
        low=bar.low, close=bar.close, volume_shares=bar.volume_shares,
        source=source, as_of=bar.as_of, stale=bar.stale,
    )
