"""inline SVG 繪圖（ToDo §3.4、§9 Day 25 第 4 項）。

**不用任何圖表函式庫。** 產出是一段自足的 `<svg>`，直接嵌進 HTML ——
頁面最後要被加密塞進 `<iframe srcdoc>`，外部相依只會變成破圖。

核心規則：**頻率決定畫法。**

  日頻   → 連續折線。中間每一天都有值，連起來是誠實的。
  月/季/不定期 → **階梯 + 點**。把每月一個點用直線連起來，等於宣稱中間那些
                日子有值而且線性變化 —— 那是畫出來的，不是量到的。

這條規則是 Day 25 第 4 項的驗收：「月頻的 CPI 與日頻的利差畫在同一頁而不誤導」。

這一層是表現層，**不得 import storage/ 或 datasources/**（tests/test_layer_boundary.py 守著）。
"""
from __future__ import annotations

from html import escape

FREQ_CONTINUOUS = "continuous"
FREQ_STEPPED = "stepped"

# 只有日頻可以連續 —— 其餘一律階梯，不確定時也走階梯（保守的那一邊）
_CONTINUOUS_FREQS = {"每日", "daily"}

WIDTH = 240
HEIGHT = 48
PAD = 4


def freq_style(freq: str) -> str:
    return FREQ_CONTINUOUS if freq in _CONTINUOUS_FREQS else FREQ_STEPPED


def _scale(
    values: list[float], width: int, height: int, pad: int
) -> list[tuple[float, float]]:
    n = len(values)
    lo, hi = min(values), max(values)
    span = hi - lo
    inner_h = height - 2 * pad
    inner_w = width - 2 * pad

    def y_of(v: float) -> float:
        if span == 0:
            return height / 2  # 全平的序列畫在中線，不要除以零
        return pad + inner_h * (1 - (v - lo) / span)

    if n == 1:
        return [(width / 2, y_of(values[0]))]
    return [
        (pad + inner_w * i / (n - 1), y_of(v)) for i, v in enumerate(values)
    ]


def _fmt(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _stepped(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """把每個點延伸成一段水平線，再垂直跳到下一個值。

    視覺上明說：這個值一直維持到下一次公布為止，中間沒有量測。
    """
    if len(points) < 2:
        return points
    out: list[tuple[float, float]] = []
    for i, (x, y) in enumerate(points):
        out.append((x, y))
        if i + 1 < len(points):
            nx = points[i + 1][0]
            out.append((nx, y))  # 水平延伸到下一個 x，再由下一圈垂直跳
    return out


def sparkline(
    series: list[tuple[str, float | None]],
    freq: str = "每日",
    width: int = WIDTH,
    height: int = HEIGHT,
    label: str = "",
) -> str:
    """畫一條迷你走勢線。

    缺值直接跳過，**不補 0** —— 補 0 會在圖上憑空造出一次崩跌。
    """
    clean = [(d, float(v)) for d, v in series if v is not None]

    head = (
        f'<svg class="spark" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="{escape(label or "走勢")}" '
        f'preserveAspectRatio="none">'
    )

    if not clean:
        return (
            head
            + f'<text class="no-data" x="{width / 2:.0f}" y="{height / 2 + 4:.0f}" '
            f'text-anchor="middle">—</text></svg>'
        )

    values = [v for _, v in clean]
    points = _scale(values, width, height, PAD)
    style = freq_style(freq)

    if style == FREQ_CONTINUOUS:
        body = f'<polyline class="line" points="{_fmt(points)}" fill="none"/>'
    else:
        body = (
            f'<polyline class="line step" points="{_fmt(_stepped(points))}" '
            f'fill="none"/>'
        )
        # 月頻與季頻：每個實際量到的點都要看得見
        body += "".join(
            f'<circle class="pt" cx="{x:.1f}" cy="{y:.1f}" r="2"/>'
            for x, y in points
        )

    return head + body + "</svg>"


def bar_meter(value: float, lo: float = 0.0, hi: float = 100.0) -> str:
    """一條 0~100 的水平量尺，給評分用。**只顯示數值位置，不標任何區間建議。**"""
    pct = 0.0 if hi == lo else max(0.0, min(1.0, (value - lo) / (hi - lo)))
    return (
        f'<svg class="meter" viewBox="0 0 100 8" width="100" height="8" '
        f'role="img" aria-label="{value:.1f}">'
        f'<rect class="track" x="0" y="3" width="100" height="2" rx="1"/>'
        f'<rect class="fill" x="0" y="3" width="{pct * 100:.1f}" height="2" rx="1"/>'
        f'<circle class="knob" cx="{pct * 100:.1f}" cy="4" r="3"/>'
        f"</svg>"
    )
