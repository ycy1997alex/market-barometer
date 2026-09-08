"""技術指標（ToDo §8.2）。純函式、零 I/O、零 UI 依賴。

缺值紀律（§4.3）：任何窗口內只要有 NaN 或 None，該格一律回 None，
不回 NaN —— NaN 會安靜地往下游傳染，None 會在顯示層明確變成「—」。
"""
from __future__ import annotations

import math

Number = float | int | None

TRADING_DAYS_PER_YEAR = 252


def _window(series: list[Number], end: int, size: int) -> list[float] | None:
    """取 series[end-size+1 : end+1]，任何一格不可用就回 None。"""
    start = end + 1 - size
    if start < 0:
        return None
    out: list[float] = []
    for v in series[start : end + 1]:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f):
            return None
        out.append(f)
    return out


def moving_average(series: list[Number], period: int) -> list[float | None]:
    """簡單移動平均。回傳與輸入等長的序列。"""
    if period < 1:
        raise ValueError("period 必須 >= 1")
    out: list[float | None] = []
    for i in range(len(series)):
        w = _window(series, i, period)
        out.append(None if w is None else sum(w) / period)
    return out


def rsi(series: list[Number], period: int = 14) -> list[float | None]:
    """Wilder RSI。第一個值用前 `period` 根變動的簡單平均起手，之後遞迴平滑。"""
    if period < 1:
        raise ValueError("period 必須 >= 1")
    n = len(series)
    out: list[float | None] = [None] * n

    clean = _window(series, n - 1, n) if n else None
    if clean is None or n < period + 1:
        return out

    gains = [max(clean[i] - clean[i - 1], 0.0) for i in range(1, n)]
    losses = [max(clean[i - 1] - clean[i], 0.0) for i in range(1, n)]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    if avg_gain == 0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def bollinger(
    series: list[Number], period: int = 20, num_std: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """布林通道 (中線, 上軌, 下軌)。標準差用母體標準差（ddof=0）。"""
    mid = moving_average(series, period)
    upper: list[float | None] = []
    lower: list[float | None] = []
    for i in range(len(series)):
        w = _window(series, i, period)
        if w is None or mid[i] is None:
            upper.append(None)
            lower.append(None)
            continue
        mean = mid[i]
        var = sum((x - mean) ** 2 for x in w) / period
        sd = math.sqrt(var)
        upper.append(mean + num_std * sd)
        lower.append(mean - num_std * sd)
    return mid, upper, lower


def bollinger_position(
    series: list[Number], period: int = 20, num_std: float = 2.0
) -> float | None:
    """最新一根在通道裡的位置：0 = 貼下軌、1 = 貼上軌。帶寬為 0 時回 0.5。"""
    mid, upper, lower = bollinger(series, period, num_std)
    if not series or upper[-1] is None or lower[-1] is None:
        return None
    last = series[-1]
    if last is None or math.isnan(float(last)):
        return None
    width = upper[-1] - lower[-1]
    if width == 0:
        return 0.5
    return (float(last) - lower[-1]) / width


def bollinger_bandwidth(
    series: list[Number], period: int = 20, num_std: float = 2.0
) -> float | None:
    """帶寬 = (上軌 − 下軌) / 中線。中線為 0 時回 None。"""
    mid, upper, lower = bollinger(series, period, num_std)
    if upper[-1] is None or lower[-1] is None or not mid[-1]:
        return None
    return (upper[-1] - lower[-1]) / mid[-1]


def annualised_volatility(
    prices: list[Number], periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> float | None:
    """年化波動度 = 日對數報酬的母體標準差 × sqrt(252)。

    需要至少兩個有效價格；缺值的那一段報酬直接跳過，不補值。
    """
    clean = [
        float(p)
        for p in prices
        if p is not None and not math.isnan(float(p)) and float(p) > 0
    ]
    if len(clean) < 2:
        return None
    rets = [math.log(clean[i] / clean[i - 1]) for i in range(1, len(clean))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(var) * math.sqrt(periods_per_year)


def drawdown_from_high(prices: list[Number]) -> float | None:
    """距期間高點的回撤，回傳負值或 0（-0.20 = 距高點 -20%）。

    SPCX 這種上市不滿一年的標的，呼叫端要把「52 週高點」降級成
    「上市以來高點」並標明（§10），這個函式只管給定序列裡的高點。
    """
    clean = [
        float(p) for p in prices if p is not None and not math.isnan(float(p))
    ]
    if not clean:
        return None
    high = max(clean)
    if high <= 0:
        return None
    return clean[-1] / high - 1.0
