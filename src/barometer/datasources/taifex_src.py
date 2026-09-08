"""期交所 adapter：台指期未平倉與 put/call ratio（ToDo §8.2、§9 Day 26 第 2 項）。

節流：請求間隔 **≥ 0.6 秒**（比照 TWSE，期交所同樣沒有公布數字）。
UA：誠實標示用途，不偽裝瀏覽器（§6 規則 7）。

⚠️ **這一層的單位是「口」（contract）**。整套系統到這裡已經有三種單位：

    股（T86 買賣超、price_daily 內部一律存股）
    張（MI_MARGN 融資融券、台股顯示層）
    口（台指期未平倉）

三者互不換算 —— 一口台指期不是 1000 股任何東西。所以欄位名一律帶
`_contracts` 字尾，不給任何人「順手乘 1000」的機會（§10 張／股那一格的教訓）。

⚠️ **空回應的長相跟 TWSE 不一樣**：TWSE 回一句「很抱歉，沒有符合條件的資料」，
期交所回的是**只有表頭、沒有任何資料列**的 CSV。兩家長得完全不同，處置卻
相同 —— 一律當「這天還沒有」，不是 0（§10）。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

import requests

from barometer.datasources.base import COUNTER, FetchError, Throttle

SOURCE = "taifex"

_PCRATIO = "https://www.taifex.com.tw/cht/3/pcRatioDown"
_FUTCONTRACTS = "https://www.taifex.com.tw/cht/3/futContractsDateDown"

_THROTTLE = Throttle(min_interval=0.6)

_UA = "market-barometer/0.1 (personal research; contact via GitHub)"

_CACHE: dict[tuple[str, str], object] = {}

# 三大法人在期交所的身份別用字，跟 TWSE T86 的用字不同
INVESTOR_TYPES = ("自營商", "投信", "外資及陸資")


class NotPublishedYet(FetchError):
    """只有表頭沒有資料列 —— 這天的期交所資料**還沒公布**，不是「未平倉 0」。"""


def _post(url: str, data: dict) -> str:
    _THROTTLE.wait()
    COUNTER.bump(SOURCE)
    try:
        resp = requests.post(url, data=data, timeout=30,
                             headers={"User-Agent": _UA})
    except requests.RequestException as exc:
        raise FetchError(f"TAIFEX: {exc}") from exc
    if resp.status_code != 200:
        raise FetchError(f"TAIFEX: HTTP {resp.status_code}")
    resp.encoding = "big5hkscs"
    return resp.text


def _num(s: str) -> float | None:
    s = s.strip().replace(",", "").replace('"', "")
    if not s or s in ("--", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date(s: str) -> dt.date | None:
    """期交所的日期是 2026/09/04 這個格式。"""
    s = s.strip().replace('"', "")
    try:
        return dt.datetime.strptime(s, "%Y/%m/%d").date()
    except ValueError:
        return None


def _rows(text: str) -> list[list[str]]:
    """切成資料列（丟掉表頭與空列）。回空 list 代表只有表頭。"""
    out: list[list[str]] = []
    for i, row in enumerate(csv.reader(io.StringIO(text))):
        if i == 0 or not row or not row[0].strip():
            continue
        out.append(row)
    return out


# ---------------- put / call ratio ----------------

def parse_pc_ratio(text: str) -> list[dict]:
    """賣權／買權的成交量比與未平倉量比。

    回傳照原始順序（期交所給的是**新到舊**），不重排 —— 呼叫端要最新一筆就
    取 `[0]`，要按日期排自己排。這裡不替它決定。
    """
    rows = _rows(text)
    if not rows:
        raise NotPublishedYet(
            "TAIFEX pcRatio: 只有表頭沒有資料列 —— 這天還沒公布"
            "（或不是交易日）。這不等於 ratio 是 0。"
        )

    out: list[dict] = []
    for r in rows:
        d = _date(r[0])
        if d is None:
            continue
        out.append(
            {
                "date": d,
                "put_volume": _num(r[1]),
                "call_volume": _num(r[2]),
                "pc_volume_ratio_pct": _num(r[3]),
                "put_oi": _num(r[4]),
                "call_oi": _num(r[5]),
                "pc_oi_ratio_pct": _num(r[6]),
            }
        )
    if not out:
        raise NotPublishedYet("TAIFEX pcRatio: 解析後沒有任何列 —— 視為還沒公布")
    return out


def fetch_pc_ratio(start: dt.date, end: dt.date) -> list[dict]:
    key = ("pcratio", f"{start.isoformat()}~{end.isoformat()}")
    if key in _CACHE:
        return _CACHE[key]  # type: ignore[return-value]
    text = _post(
        _PCRATIO,
        {
            "queryStartDate": f"{start:%Y/%m/%d}",
            "queryEndDate": f"{end:%Y/%m/%d}",
        },
    )
    rows = parse_pc_ratio(text)
    _CACHE[key] = rows
    return rows


# ---------------- 三大法人台指期未平倉 ----------------

@dataclass(frozen=True, slots=True)
class FutOiReport:
    """一天的台指期三大法人未平倉。

    `by_investor[身份別]` 的每個 key 都以 `_contracts` 結尾 —— 單位是**口**，
    見模組 docstring。
    """

    date: dt.date
    product: str
    by_investor: dict[str, dict[str, float | None]] = field(default_factory=dict)
    unit: str = "口"

    @property
    def total_net_oi_contracts(self) -> float:
        """三大法人合計淨未平倉（口）。

        期交所不給合計列，這是自己加的 —— 加總前先確認三個身份別都在，
        少一個就會悄悄少算一塊。
        """
        return sum(
            (s.get("net_oi_contracts") or 0.0) for s in self.by_investor.values()
        )


def parse_fut_oi(text: str) -> FutOiReport:
    """解析 futContractsDateDown 的 CSV。

    欄序（0-based）：
        0 日期 / 1 商品名稱 / 2 身份別
        3~8   交易口數與契約金額（多、空、淨）
        9  多方未平倉口數 / 10 多方未平倉契約金額
        11 空方未平倉口數 / 12 空方未平倉契約金額
        13 多空未平倉口數淨額 / 14 多空未平倉契約金額淨額

    只取未平倉那幾欄 —— 「今天交易了幾口」是流量，「手上還留著幾口」才是
    §8.2 要的籌碼面讀數。
    """
    rows = _rows(text)
    if not rows:
        raise NotPublishedYet(
            "TAIFEX futContracts: 只有表頭沒有資料列 —— 這天還沒公布"
            "（或不是交易日）。這不等於未平倉是 0。"
        )

    date: dt.date | None = None
    product = ""
    by_investor: dict[str, dict[str, float | None]] = {}

    for r in rows:
        if len(r) < 14:
            continue
        d = _date(r[0])
        if d is None:
            continue
        date = date or d
        product = product or r[1].strip().strip('"')
        investor = r[2].strip().strip('"')
        by_investor[investor] = {
            "long_oi_contracts": _num(r[9]),
            "short_oi_contracts": _num(r[11]),
            "net_oi_contracts": _num(r[13]),
        }

    if date is None or not by_investor:
        raise NotPublishedYet(
            "TAIFEX futContracts: 解析後沒有任何身份別 —— 視為還沒公布"
        )

    return FutOiReport(date=date, product=product, by_investor=by_investor)


def fetch_fut_oi(date: dt.date, commodity: str = "TXF") -> FutOiReport:
    """台指期（TXF）三大法人未平倉。單位「口」。"""
    key = ("futoi", f"{commodity}:{date.isoformat()}")
    if key in _CACHE:
        return _CACHE[key]  # type: ignore[return-value]
    text = _post(
        _FUTCONTRACTS,
        {
            "firstDate": "",
            "lastDate": "",
            "queryStartDate": f"{date:%Y/%m/%d}",
            "queryEndDate": f"{date:%Y/%m/%d}",
            "commodityId": commodity,
        },
    )
    report = parse_fut_oi(text)
    _CACHE[key] = report
    return report
