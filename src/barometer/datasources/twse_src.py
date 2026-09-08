"""TWSE adapter：三大法人買賣超（T86）等盤後資料（ToDo §6、§10）。

節流：請求間隔 **≥ 0.6 秒**；以 (dataset, 日期) 為鍵整檔快取（§6）。
UA：TWSE 用**誠實標示用途**的 UA（不是偽裝瀏覽器，也不是預設 UA）。

⚠️ **T86 盤後才有**：當天下午之前抓會拿到空 CSV。
空 CSV 要當「這天還沒有」，**不要當成 0** —— 把「還沒公布」和「當天真的是 0」
混為一談，是這一層最容易出的錯（§10）。

單位：**T86 的買賣超是「股」**，而 K 線的量是「張」。內部一律存股，
顯示層才換算（§1 第 10 條）。既有專案在這裡留過一個
「標題寫張、資料其實是股」的 bug。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass

import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle

SOURCE = "twse"

_T86 = ("https://www.twse.com.tw/fund/T86"
        "?response=csv&date={date:%Y%m%d}&selectType=ALL")

_THROTTLE = Throttle(min_interval=0.6)

# 誠實標示用途，不偽裝瀏覽器
_UA = "market-barometer/0.1 (personal research; contact via GitHub)"

# (dataset, 日期) → 結果，整檔快取（§6 規則 5）
_CACHE: dict[tuple[str, str], list[dict]] = {}
_MARGIN_CACHE: dict[str, "MarginReport"] = {}


class NotPublishedYet(FetchError):
    """空 CSV —— 這天的盤後資料**還沒公布**，不是「這天成交 0」。"""


def _get(url: str) -> str:
    _THROTTLE.wait()
    COUNTER.bump(SOURCE)
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": _UA})
    except requests.RequestException as exc:
        raise FetchError(f"TWSE: {exc}") from exc
    if resp.status_code != 200:
        raise FetchError(f"TWSE: HTTP {resp.status_code}")
    resp.encoding = "big5hkscs"
    return resp.text


def _num(s: str) -> float | None:
    s = s.strip().replace(",", "").replace('"', "")
    if not s or s == "--":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_t86(date: dt.date) -> list[dict]:
    """三大法人買賣超（個股別）。買賣超單位是**股**。

    空 CSV → 丟 NotPublishedYet，讓呼叫端能區分「還沒公布」與「真的是 0」。
    """
    key = ("t86", date.isoformat())
    if key in _CACHE:
        return _CACHE[key]

    text = _get(_T86.format(date=date))

    # TWSE 的 CSV 前面有標題列，真正的表頭是含「證券代號」的那一列
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if "證券代號" in ln), None
    )
    if start is None:
        raise NotPublishedYet(
            f"TWSE T86 {date}: 空 CSV —— 這天的盤後資料還沒公布"
            f"（或不是交易日）。這不等於買賣超是 0。"
        )

    rows: list[dict] = []
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    header = [h.strip().replace('"', "") for h in next(reader)]
    for row in reader:
        if len(row) < len(header) or not row[0].strip().strip('"'):
            continue
        rec = dict(zip(header, row))
        code = rec.get("證券代號", "").strip().strip('"').replace("=", "")
        if not code:
            continue
        rows.append(
            {
                "date": date,
                "symbol": code,
                "name": rec.get("證券名稱", "").strip().strip('"'),
                # 單位：股
                "foreign_net_shares": _num(rec.get("外陸資買賣超股數(不含外資自營商)", "")
                                           or rec.get("外資買賣超股數", "")),
                "trust_net_shares": _num(rec.get("投信買賣超股數", "")),
                "dealer_net_shares": _num(rec.get("自營商買賣超股數", "")),
                "total_net_shares": _num(rec.get("三大法人買賣超股數", "")),
            }
        )

    if not rows:
        raise NotPublishedYet(
            f"TWSE T86 {date}: 解析後沒有任何列 —— 視為還沒公布，不是 0"
        )

    _CACHE[key] = rows
    return rows


# ---------------- 融資融券（MI_MARGN，ToDo §9 Day 26 第 2 項） ----------------

_MARGN = ("https://www.twse.com.tw/exchangeReport/MI_MARGN"
          "?response=csv&date={date:%Y%m%d}&selectType=MS")

# 「沒資料」在 TWSE 這裡不是空字串，是這一句中文
_NO_DATA = "沒有符合條件的資料"


@dataclass(frozen=True, slots=True)
class MarginReport:
    """一天的市場融資融券餘額。

    ⚠️ **單位是「張」**（TWSE 表上寫「交易單位」）—— 同一天的 T86 買賣超卻是
    **「股」**。兩份都是 TWSE 的盤後資料、都在同一支 adapter 裡，單位卻不同，
    所以欄位名一律帶 `_lots` / `_shares` 字尾把它釘死（§1 第 10 條）。

    ⚠️ **「今日餘額」是暫定值，「前日餘額」才是定稿。** 這不是我的判斷，是
    TWSE 自己在備註寫的：各授信機構在成交次日仍繼續調帳，所以「請以『前日
    餘額』為準，而以『今日餘額』為輔助參考資料」。

    後果是：想要 D 這天的定稿餘額，得等 D+1 抓回來的「前日餘額」。當天抓到
    的那個數字會再變。這件事不寫進型別就會被忘掉 —— 所以這裡刻意把兩個
    數字掛在**不同的日期**上（`provisional_for` 是當天、`final_for` 是前一個
    交易日），而不是擺成兩個平行欄位讓人自己記得誰是誰。
    """

    date: dt.date
    margin_prev_lots: float | None      # 融資・前日餘額（定稿）
    margin_today_lots: float | None     # 融資・今日餘額（暫定）
    short_prev_lots: float | None       # 融券・前日餘額（定稿）
    short_today_lots: float | None      # 融券・今日餘額（暫定）
    margin_prev_ktwd: float | None      # 融資金額・前日餘額（仟元）
    margin_today_ktwd: float | None     # 融資金額・今日餘額（仟元）

    unit: str = "張"

    @property
    def provisional_for(self) -> dt.date:
        """「今日餘額」屬於的日期 —— 就是當天，但值是暫定的。"""
        return self.date

    @property
    def provisional_margin_lots(self) -> float | None:
        return self.margin_today_lots

    @property
    def final_for(self) -> dt.date | None:
        """「前日餘額」屬於的日期 —— **前一個交易日**，不是當天。

        這裡只往前退一個日曆日當標記用。真正是哪一天要跟 price_daily 對，
        adapter 層沒有交易日曆也刻意不維護一份（§1 第 6 條）。
        """
        return self.date - dt.timedelta(days=1) if self.date else None

    @property
    def final_margin_lots(self) -> float | None:
        return self.margin_prev_lots

    @property
    def margin_today_shares(self) -> float | None:
        """張 → 股。資料層存張是因為 TWSE 就是這樣給的，換算只在這一處。"""
        if self.margin_today_lots is None:
            return None
        return self.margin_today_lots * 1000


def parse_margin(text: str, date: dt.date) -> MarginReport:
    """解析 MI_MARGN 的 CSV。

    空回應／「沒有符合條件的資料」→ NotPublishedYet，**不是餘額 0**。
    非交易日與「盤後還沒公布」在回應上長得一樣，程式分不出來也不必分 ——
    兩者的處置相同（§10）。
    """
    if not text.strip() or _NO_DATA in text:
        raise NotPublishedYet(
            f"TWSE MI_MARGN {date}: 沒有符合條件的資料 —— 這天還沒公布"
            f"（或不是交易日）。這不等於融資融券餘額是 0。"
        )

    wanted = {
        "融資(交易單位)": "margin",
        "融券(交易單位)": "short",
        "融資金額(仟元)": "margin_ktwd",
    }
    found: dict[str, tuple[float | None, float | None]] = {}

    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        label = row[0].strip().strip('"')
        if label not in wanted:
            continue
        # 欄序：項目, 買進, 賣出, 現金(券)償還, 前日餘額, 今日餘額
        prev = _num(row[4]) if len(row) > 4 else None
        today = _num(row[5]) if len(row) > 5 else None
        found[wanted[label]] = (prev, today)

    if "margin" not in found:
        raise NotPublishedYet(
            f"TWSE MI_MARGN {date}: 解析後找不到融資列 —— 視為還沒公布，不是 0"
        )

    m_prev, m_today = found["margin"]
    s_prev, s_today = found.get("short", (None, None))
    k_prev, k_today = found.get("margin_ktwd", (None, None))

    return MarginReport(
        date=date,
        margin_prev_lots=m_prev,
        margin_today_lots=m_today,
        short_prev_lots=s_prev,
        short_today_lots=s_today,
        margin_prev_ktwd=k_prev,
        margin_today_ktwd=k_today,
    )


def fetch_margin(date: dt.date) -> MarginReport:
    """市場融資融券餘額。單位「張」，見 MarginReport 的說明。"""
    key = date.isoformat()
    if key in _MARGIN_CACHE:
        return _MARGIN_CACHE[key]
    report = parse_margin(_get(_MARGN.format(date=date)), date)
    _MARGIN_CACHE[key] = report
    return report
