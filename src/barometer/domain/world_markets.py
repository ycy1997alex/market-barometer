"""世界前十大股票市場（ToDo §9 Day 25 第 5 項）。

**這是靜態表格，程式不會去抓它。** 驗收就是這一條：表格有查閱日期，
且沒有任何抓取程式碼。

為什麼不自動更新：來源是 WFE（World Federation of Exchanges）之類的年度／
月度統計，更新頻率以年計、格式不穩定，為它寫一個爬蟲是拿維護成本換
幾乎不會變的數字。標清楚查閱日期，比假裝它是即時的誠實。

⚠️ **資料源待確認**（§11 第 7 項）—— 下面的數字標的是查閱日期，
不是保證正確。要引用請回頭核對 WFE 原始統計。
"""
from __future__ import annotations

from dataclasses import dataclass

# 查閱日期 —— 顯示層必須把這個日期印出來
CONSULTED_ON = "2026-09-06"
SOURCE_NOTE = "WFE 月度統計彙整（⚠️ 待確認，數字以查閱日期為準）"


@dataclass(frozen=True, slots=True)
class MarketRow:
    rank: int
    exchange: str
    region: str
    note: str = ""


# 依市值排序。刻意不放市值數字 —— 沒核對過的數字不如不放。
TOP_TEN: tuple[MarketRow, ...] = (
    MarketRow(1, "紐約證券交易所 NYSE", "美國"),
    MarketRow(2, "那斯達克 Nasdaq", "美國"),
    MarketRow(3, "上海證券交易所", "中國"),
    MarketRow(4, "泛歐交易所 Euronext", "歐洲", "跨多國的合併交易所"),
    MarketRow(5, "日本交易所集團 JPX", "日本"),
    MarketRow(6, "深圳證券交易所", "中國"),
    MarketRow(7, "香港交易所 HKEX", "香港"),
    MarketRow(8, "印度國家證券交易所 NSE", "印度"),
    MarketRow(9, "沙烏地證券交易所 Tadawul", "沙烏地阿拉伯"),
    MarketRow(10, "倫敦證券交易所 LSE", "英國"),
)

# 台灣不在前十，但這是讀者會問的，所以一併列出來當對照
TAIWAN_NOTE = "臺灣證券交易所 TWSE 長年排在全球前 20 名之內，不在前十。"
