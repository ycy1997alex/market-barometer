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


def wilder_ema(series: list[Number], period: int) -> list[float | None]:
    """Wilder smoothing seeded with the first complete simple average."""
    if period < 1:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(series)
    previous: float | None = None
    for i, value in enumerate(series):
        if previous is None:
            window = _window(series, i, period)
            if window is not None:
                previous = sum(window) / period
        elif value is None or not math.isfinite(float(value)):
            previous = None
        else:
            previous = (previous * (period - 1) + float(value)) / period
        out[i] = previous
    return out


def ema(series: list[Number], period: int) -> list[float | None]:
    """Standard span EMA; return warmup as missing while retaining its state."""
    if period < 1:
        raise ValueError("period must be positive")
    alpha = 2 / (period + 1)
    out: list[float | None] = []
    previous: float | None = None
    run = 0
    for value in series:
        if value is None or not math.isfinite(float(value)):
            previous, run = None, 0
            out.append(None)
            continue
        previous = float(value) if previous is None else alpha * float(value) + (1 - alpha) * previous
        run += 1
        out.append(previous if run >= period else None)
    return out


def stochastic_kd(
    highs: list[Number], lows: list[Number], closes: list[Number],
    period: int = 9, smooth: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC lengths differ")
    if period < 1 or smooth < 1:
        raise ValueError("period and smooth must be positive")
    k: list[float | None] = []
    d: list[float | None] = []
    last_k: float | None = None
    last_d: float | None = None
    for i, close in enumerate(closes):
        hi = _window(highs, i, period)
        lo = _window(lows, i, period)
        if hi is None or lo is None or close is None or not math.isfinite(float(close)):
            last_k = last_d = None
            k.append(None)
            d.append(None)
            continue
        highest, lowest = max(hi), min(lo)
        rsv = 50.0 if highest == lowest else (float(close) - lowest) / (highest - lowest) * 100
        last_k = rsv if last_k is None else (rsv + (smooth - 1) * last_k) / smooth
        last_d = last_k if last_d is None else (last_k + (smooth - 1) * last_d) / smooth
        k.append(last_k)
        d.append(last_d)
    return k, d


def macd(closes: list[Number]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast, slow = ema(closes, 12), ema(closes, 26)
    dif = [a - b if a is not None and b is not None else None for a, b in zip(fast, slow)]
    signal = ema(dif, 9)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(dif, signal)]
    return dif, signal, hist


def dmi_adx(
    highs: list[Number], lows: list[Number], closes: list[Number], period: int = 14,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC lengths differ")
    if period < 1:
        raise ValueError("period must be positive")
    n = len(closes)
    tr: list[Number] = [None] * n
    plus_dm: list[Number] = [None] * n
    minus_dm: list[Number] = [None] * n
    for i in range(1, n):
        values = (highs[i], lows[i], closes[i - 1], highs[i - 1], lows[i - 1])
        if any(v is None or not math.isfinite(float(v)) for v in values):
            continue
        high, low, previous_close, previous_high, previous_low = map(float, values)
        up, down = high - previous_high, previous_low - low
        tr[i] = max(high - low, abs(high - previous_close), abs(low - previous_close))
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
    atr = wilder_ema(tr, period)
    p_smooth = wilder_ema(plus_dm, period)
    m_smooth = wilder_ema(minus_dm, period)
    plus: list[float | None] = []
    minus: list[float | None] = []
    dx: list[Number] = []
    for a, p, m in zip(atr, p_smooth, m_smooth):
        if a is None or p is None or m is None or a <= 0:
            plus.append(None)
            minus.append(None)
            dx.append(None)
            continue
        pdi, mdi = 100 * p / a, 100 * m / a
        plus.append(pdi)
        minus.append(mdi)
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    return plus, minus, wilder_ema(dx, period)


def obv(closes: list[Number], volumes: list[Number]) -> list[float | None]:
    if len(closes) != len(volumes):
        raise ValueError("close/volume lengths differ")
    out: list[float | None] = []
    total = 0.0
    for i, (close, volume) in enumerate(zip(closes, volumes)):
        if close is None or volume is None or not all(math.isfinite(float(v)) for v in (close, volume)):
            out.append(None)
            continue
        if i and closes[i - 1] is not None:
            total += (1 if float(close) > float(closes[i - 1]) else -1 if float(close) < float(closes[i - 1]) else 0) * float(volume)
        out.append(total)
    return out


def roc(closes: list[Number], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        prev, now = closes[i - period], closes[i]
        if prev is not None and now is not None and all(math.isfinite(float(v)) for v in (prev, now)) and float(prev) != 0:
            out[i] = (float(now) / float(prev) - 1) * 100
    return out


def ma_slope(series: list[Number], days: int = 20) -> float | None:
    if days < 1:
        raise ValueError("days must be positive")
    if len(series) <= days or series[-1] is None or series[-1 - days] in (None, 0):
        return None
    now, before = float(series[-1]), float(series[-1 - days])
    return (now / before - 1) * 100 if math.isfinite(now) and math.isfinite(before) else None


def crossed_within(a: list[Number], b: list[Number], days: int, direction: str) -> bool:
    if len(a) != len(b) or days < 1 or direction not in {"up", "down"}:
        raise ValueError("invalid cross arguments")
    for i in range(max(1, len(a) - days), len(a)):
        prior = (a[i - 1], b[i - 1])
        current = (a[i], b[i])
        if any(v is None or not math.isfinite(float(v)) for v in prior + current):
            continue
        old, new = float(a[i - 1]) - float(b[i - 1]), float(a[i]) - float(b[i])
        if direction == "up" and old <= 0 < new or direction == "down" and old >= 0 > new:
            return True
    return False
