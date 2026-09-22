"""折線圖取樣（ToDo §5.3、§9 第八批 8-10）。純函式、零 I/O。

**混合取樣：週頻涵蓋完整一年 + 近 5 個交易日日頻。**

折線圖是頁面體積的主因（日頻一年每條線 250 點，混合取樣約 55 點）。週頻的
邊際成本極低，而長期分數看的是 6~24 個月 —— 視窗砍成三個月等於把這張圖最有用
的那一段丟掉。

⚠️ **兩段解析度不同，畫的時候要標出來**（見 `render/svg.score_chart`），
否則近端的鋸齒會被誤讀成波動突然變大。
⚠️ **缺料是斷點。** 中間沒有資料的那一段，線要斷開 —— 接起來等於宣稱
那幾天有量測而且線性變化。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

WEEKLY = "週"
DAILY = "日"

YEAR_DAYS = 365
DAILY_TAIL = 5
# 兩點之間隔多久算斷點。週頻取樣本身就是一週一點，所以門檻要比一週寬一些，
# 不然每一段正常的週頻資料都會被判成斷開。
GAP_DAYS = 14


@dataclass(frozen=True, slots=True)
class Point:
    label: str
    value: float
    resolution: str
    gap_before: bool = False


def mixed_sample(series: list[tuple[str, float]], today: dt.date,
                 tail: int = DAILY_TAIL) -> list[Point]:
    """回混合取樣後的點。由舊到新，跨過缺料的那一點標 `gap_before`。"""
    rows = sorted((label, value) for label, value in series if value is not None)
    rows = [(label, value) for label, value in rows
            if (today - dt.date.fromisoformat(label)).days <= YEAR_DAYS]
    if not rows:
        return []

    recent = rows[-tail:]
    older = rows[:-tail] if len(rows) > tail else []

    # 一週留一點：取那一週最後一筆（最接近當週收尾的讀數）
    by_week: dict[tuple[int, int], tuple[str, float]] = {}
    for label, value in older:
        iso = dt.date.fromisoformat(label).isocalendar()
        by_week[(iso.year, iso.week)] = (label, value)

    points: list[Point] = []
    previous: dt.date | None = None
    for label, value in sorted(by_week.values()):
        day = dt.date.fromisoformat(label)
        points.append(Point(label, value, WEEKLY,
                            gap_before=previous is not None and (day - previous).days > GAP_DAYS))
        previous = day
    for label, value in recent:
        day = dt.date.fromisoformat(label)
        points.append(Point(label, value, DAILY,
                            gap_before=previous is not None and (day - previous).days > GAP_DAYS))
        previous = day
    return points
