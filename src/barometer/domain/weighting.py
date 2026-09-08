"""五日加權（ToDo §8.1）。

純函式，零 I/O。三個層級（總經、大盤 ETF、個股）共用同一組權重。

五個交易日只有五個點 —— 呼叫端輸出時一律標定性觀察，不是統計證據。
"""
from __future__ import annotations

import math

# 由舊到新：D-4、D-3、D-2、D-1、D-0
FIVE_DAY_WEIGHTS: tuple[float, ...] = (0.10, 0.15, 0.20, 0.25, 0.30)

Number = float | int | None


def _clean(values: list[Number]) -> list[float] | None:
    """把序列轉成乾淨的 float；有洞就回 None。

    有洞不硬算 —— 五個交易日缺一天，平均就沒有意義，回 None 讓顯示層標「資料不足」。
    """
    out: list[float] = []
    for v in values:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f):
            return None
        out.append(f)
    return out


def weighted_average(values: list[Number]) -> float | None:
    """五日加權平均。長度必須恰好是 5。"""
    if len(values) != len(FIVE_DAY_WEIGHTS):
        raise ValueError(
            f"五日加權需要恰好 {len(FIVE_DAY_WEIGHTS)} 個點，收到 {len(values)} 個"
        )
    clean = _clean(values)
    if clean is None:
        return None
    return sum(w * v for w, v in zip(FIVE_DAY_WEIGHTS, clean))


def simple_average(values: list[Number]) -> float | None:
    """簡單平均。與加權平均同時輸出，兩個數字並列（§8.1）。"""
    if len(values) != len(FIVE_DAY_WEIGHTS):
        raise ValueError(
            f"五日平均需要恰好 {len(FIVE_DAY_WEIGHTS)} 個點，收到 {len(values)} 個"
        )
    clean = _clean(values)
    if clean is None:
        return None
    return sum(clean) / len(clean)


def smooth(values: list[Number], window: int = 3) -> list[float | None]:
    """移動平均平滑化。窗口不足的前幾點回 None，不用半個窗口硬算。"""
    if window < 1:
        raise ValueError("window 必須 >= 1")
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        chunk = _clean(list(values[i + 1 - window : i + 1]))
        out.append(None if chunk is None else sum(chunk) / window)
    return out
