"""EIA 原油庫存 adapter（每週石油狀況報告 WPSR）。

**免金鑰。** 來源是 https://www.eia.gov/petroleum/supply/weekly/ 這一頁掛的
Table 1 機器可讀版（`ir.eia.gov/wpsr/table1.csv`）。EIA API v2 需要金鑰，
這條路不用；而 FRED 上只有 1930 年代的 NBER 舊序列，沒有現行的週度庫存。

---

**這支 CSV 的形狀跟其他來源都不一樣：它不是時間序列，是一張比較表。**

一列裡同時有本週、上週、週變化、去年同期、年變化：

    STUB_1     8/28/26   8/21/26  Difference  Percent Change  8/29/25  ...
    Crude Oil  711.064   718.636  -7.572      -1.100          825.417  ...

所以解析出來的是一個**快照**（`CrudeStocks`），不是 `list[tuple[str, float]]`。
硬把它攤成序列會產生一條只有三個點、日期還不連續的假序列 —— 顯示層畫出來
會像是「這三個時間點之間有量測」，而那不是真的。

**資料日期在表頭的欄位名裡**（`8/28/26`），不在任何一格資料裡。這是這支
adapter 最容易解錯的地方。

單位是**百萬桶**。系統裡第五種單位（股、張、口、%、百萬桶），所以欄位名
一律帶 `_mbbl` 字尾。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass

import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle

SOURCE = "eia"

WPSR_TABLE1 = "https://ir.eia.gov/wpsr/table1.csv"
LANDING_PAGE = "https://www.eia.gov/petroleum/supply/weekly/"

# 週報一週更新一次，沒必要打得比 TWSE 密
_THROTTLE = Throttle(min_interval=1.0)

_UA = "market-barometer/0.1 (personal research; contact via GitHub)"

CRUDE_ROW = "crude oil"


@dataclass(frozen=True, slots=True)
class CrudeStocks:
    """一次 WPSR 的原油庫存快照。單位百萬桶。"""

    data_date: dt.date | None
    prior_date: dt.date | None
    stocks_mbbl: float | None
    prior_week_mbbl: float | None
    wow_change_mbbl: float | None
    wow_change_pct: float | None
    year_ago_mbbl: float | None
    yoy_change_pct: float | None
    unit: str = "百萬桶"

    # 明確標示它是快照不是序列 —— 呼叫端不該把它當時間序列處理
    is_snapshot: bool = True

    def as_series(self) -> list[tuple[str, float]]:
        """給顯示層畫圖用的兩個點：上週與本週。

        **只給這兩個點，不補中間。** 兩個日期都是真的，畫出來是一段直線，
        而那段直線確實只連了兩個實際量測值。
        """
        pts: list[tuple[str, float]] = []
        if self.prior_date and self.prior_week_mbbl is not None:
            pts.append((self.prior_date.isoformat(), self.prior_week_mbbl))
        if self.data_date and self.stocks_mbbl is not None:
            pts.append((self.data_date.isoformat(), self.stocks_mbbl))
        return pts


def _num(s: str) -> float | None:
    s = s.strip().replace(",", "").replace('"', "")
    if not s or s in ("--", "-", "NA", "\x96 \x96"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date(s: str) -> dt.date | None:
    """表頭的日期是 `8/28/26` 這種兩位數年份的格式。"""
    s = s.strip().strip('"')
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_wpsr(text: str) -> CrudeStocks:
    """解析 WPSR Table 1，取出原油庫存那一列。

    找不到那一列就丟 FetchError，**不回一個全 None 的快照** —— 靜默的空值
    會一路流到頁面上變成「—」，看起來像「今天還沒公布」，而實際上是解析壞了。
    """
    if not text.strip():
        raise FetchError("EIA WPSR: 空回應")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise FetchError("EIA WPSR: 解析後沒有任何列")

    header = rows[0]
    this_week = _date(header[1]) if len(header) > 1 else None
    last_week = _date(header[2]) if len(header) > 2 else None

    for row in rows[1:]:
        if not row or row[0].strip().strip('"').lower() != CRUDE_ROW:
            continue
        return CrudeStocks(
            data_date=this_week,
            prior_date=last_week,
            stocks_mbbl=_num(row[1]) if len(row) > 1 else None,
            prior_week_mbbl=_num(row[2]) if len(row) > 2 else None,
            wow_change_mbbl=_num(row[3]) if len(row) > 3 else None,
            wow_change_pct=_num(row[4]) if len(row) > 4 else None,
            year_ago_mbbl=_num(row[5]) if len(row) > 5 else None,
            yoy_change_pct=_num(row[7]) if len(row) > 7 else None,
        )

    raise FetchError(
        "EIA WPSR: 找不到 Crude Oil 那一列 —— 報表格式可能變了，"
        "不回空值以免看起來像「還沒公布」"
    )


def fetch() -> CrudeStocks:
    _THROTTLE.wait()
    COUNTER.bump(SOURCE)
    try:
        resp = requests.get(WPSR_TABLE1, timeout=30, headers={"User-Agent": _UA})
    except requests.RequestException as exc:
        raise FetchError(f"EIA WPSR: {exc}") from exc
    if resp.status_code != 200:
        raise FetchError(f"EIA WPSR: HTTP {resp.status_code}")
    return parse_wpsr(resp.text)
