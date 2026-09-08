"""總經指標清單（ToDo §7.3）。純資料定義，零 I/O。

從既有專案的 20 項調整成 **17 項進評分 + 7 項只顯示不評分**。
**不進評分的就只是名詞解釋，不要假裝它有份量。**

這次唯一刪掉的是 **^GSPC S&P 500**：從評分移到只顯示，因為它是被解釋的
對象，不是解釋變數。拿大盤去解釋大盤，等於把答案抄進題目裡。

**曾經被刪、後來作者要求加回來的三項**（2026-09-07）：

  - ICSA 初領失業金、PAYEMS 非農就業 —— Claude 當初以「與失業率共線」為由
    刪掉。作者指出那是其中一個學派的看法，另一派認為三者要配合看：
    失業率是**存量**、初領是每週的**邊際流量**、非農是每月的**淨增減**，
    量的是勞動市場的不同切面。只留存量會漏掉轉折。
  - EIA 原油庫存 —— Claude 當初以「需要另一把金鑰、貢獻低」為由刪掉。
    作者指出 2026 年 9 月的戰爭狀態下，庫存是供給面的直接讀數，跟油價
    （已在觀測項）講的不是同一件事。而且它其實**不需要金鑰**，走
    每週石油狀況報告的公開 CSV 就有。
"""
from __future__ import annotations

from dataclasses import dataclass

# 快取 TTL（§7.3）
TTL_MARKET_HOURS = 4    # yfinance
TTL_ECONOMIC_HOURS = 12  # FRED / 國發會 / 主計總處 / 央行


@dataclass(frozen=True, slots=True)
class Indicator:
    key: str
    name: str
    freq: str
    source: str
    sid: str
    fmt: str
    chg_pp: bool  # True = 顯示百分點絕對差，False = 顯示百分比變化率
    layer: str    # world / tw / observe
    note: str = ""

    @property
    def ttl_hours(self) -> int:
        return TTL_MARKET_HOURS if self.source == "yfinance" else TTL_ECONOMIC_HOURS

    @property
    def scored(self) -> bool:
        return self.layer in ("world", "tw")


# ---------------- 世界層評分（11 項） ----------------
WORLD: tuple[Indicator, ...] = (
    Indicator("vix", "VIX 恐慌指數", "每日", "yfinance", "^VIX",
              "{:.2f}", False, "world"),
    Indicator("dxy", "美元指數 DXY", "每日", "yfinance", "DX-Y.NYB",
              "{:.2f}", False, "world"),
    Indicator("us10y", "美債 10 年殖利率", "每日", "yfinance", "^TNX",
              "{:.2f}%", True, "world"),
    Indicator("t10y2y", "美債 10Y-2Y 利差", "每日", "fred", "T10Y2Y",
              "{:+.2f}%", True, "world",
              note="負值 = 殖利率曲線倒掛"),
    Indicator("cpi", "美國 CPI", "每月", "fred", "CPIAUCSL",
              "{:.1f}", False, "world"),
    Indicator("unrate", "美國失業率", "每月", "fred", "UNRATE",
              "{:.1f}%", True, "world"),
    Indicator("phlfed", "費城 Fed 製造業指數", "每月", "fred",
              "GACDFSA066MSFRBPHI", "{:+.1f}", True, "world",
              note="擴散指數，榮枯線 = 0（不是 ISM 的 50）"),
    Indicator("fedfunds", "Fed 利率上限", "不定期", "fred", "DFEDTARU",
              "{:.2f}%", True, "world"),
    Indicator("claims", "美國初領失業金", "每週", "fred", "ICSA",
              "{:,.0f}", False, "world",
              note="每週的邊際流量，跟失業率（存量）量的不是同一件事"),
    Indicator("payrolls", "美國非農就業", "每月", "fred", "PAYEMS",
              "{:,.0f} 千人", False, "world",
              note="每月的淨增減；與失業率共線與否，各學派看法不同"),
    Indicator("crude_stocks", "美國原油庫存", "每週", "eia", "WPSR",
              "{:,.1f} 百萬桶", False, "world",
              note="供給面的直接讀數，與油價講的不是同一件事"),
)

# ---------------- 台灣層評分（6 項） ----------------
TAIWAN: tuple[Indicator, ...] = (
    Indicator("usdtwd", "USD/TWD", "每日", "yfinance", "TWD=X",
              "{:.3f}", False, "tw"),
    Indicator("sox", "費城半導體 SOX", "每日", "yfinance", "^SOX",
              "{:,.0f}", False, "tw",
              note="把美國的 SOX 放進台灣層是個判斷，理由是台股半導體占比極高"),
    Indicator("tw_light", "台灣景氣對策信號", "每月", "ndc", "6099",
              "{:.0f} 分", False, "tw"),
    Indicator("tw_export", "台灣外銷訂單動向指數", "每月", "ndc", "6099",
              "{:.2f}", False, "tw"),
    Indicator("tw_gdp", "台灣經濟成長率 YoY", "每季", "dgbas", "6799",
              "{:+.2f}%", True, "tw"),
    Indicator("cbc_rate", "台灣央行重貼現率", "不定期", "cbc", "lp-640",
              "{:.2f}%", True, "tw"),
)

# ---------------- 只顯示不評分（7 項） ----------------
OBSERVE: tuple[Indicator, ...] = (
    Indicator("gold", "黃金期貨", "每日", "yfinance", "GC=F",
              "{:,.0f}", False, "observe"),
    Indicator("wti", "WTI 原油", "每日", "yfinance", "CL=F",
              "{:.2f}", False, "observe"),
    Indicator("spx", "S&P 500", "每日", "yfinance", "^GSPC",
              "{:,.0f}", False, "observe",
              note="被解釋的對象，不是解釋變數 —— 所以移出評分"),
    Indicator("eurusd", "EUR/USD", "每日", "yfinance", "EURUSD=X",
              "{:.4f}", False, "observe"),
    Indicator("usdjpy", "USD/JPY", "每日", "yfinance", "JPY=X",
              "{:.2f}", False, "observe"),
    Indicator("usdcny", "USD/CNY", "每日", "yfinance", "CNY=X",
              "{:.4f}", False, "observe"),
    Indicator("btc", "比特幣", "每日", "yfinance", "BTC-USD",
              "{:,.0f}", False, "observe"),
)

ALL: tuple[Indicator, ...] = WORLD + TAIWAN + OBSERVE
BY_KEY: dict[str, Indicator] = {i.key: i for i in ALL}

SCORED = WORLD + TAIWAN


def light_name(score: float) -> str:
    """台灣景氣對策信號燈號（官方切點，綜合分數 9~45）。"""
    if score >= 38:
        return "紅燈（過熱）"
    if score >= 32:
        return "黃紅燈（趨熱）"
    if score >= 23:
        return "綠燈（穩定）"
    if score >= 17:
        return "黃藍燈（趨弱）"
    return "藍燈（低迷）"
