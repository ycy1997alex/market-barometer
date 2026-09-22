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
import datetime as dt

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
    # 8-6：固定到期月的合約在不同日期距到期的月數不同，前後不可比 ——
    # 這種序列進不了歷史重放，回測時當缺料處理（§7.1）。
    backtest: bool = True

    @property
    def ttl_hours(self) -> int:
        return TTL_MARKET_HOURS if self.source == "yfinance" else TTL_ECONOMIC_HOURS

    @property
    def scored(self) -> bool:
        return self.layer in ("world", "tw")


# ---------------- 世界層評分（25 項） ----------------
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
    Indicator("credit_spread", "高收益債信用利差", "每日", "fred", "BAMLH0A0HYM2",
              "{:.2f}%", True, "world",
              note="壓力的早期讀數：股市還在撐時信用市場通常先報警"),
    Indicator("net_liquidity", "Fed 淨流動性", "每週", "fred_derived",
              "WALCL-RRPONTSYD", "{:,.0f} 十億美元", False, "world",
              note="WALCL − RRPONTSYD 的變化方向，不是水位；基期為 0 視為缺料"),
    Indicator("breadth_us", "美股市場廣度（代理）", "每日", "yfinance_breadth",
              "SECTOR11_BREADTH", "{:.0f}%", False, "world",
              note="11 檔 SPDR 類股 ETF 站上 200MA 的比例；代理指標，不是真的漲跌家數。"
                   "缺料時分母用當日有料的檔數，見 OBSERVE 的「市場廣度分母」"),
    Indicator("vix_term", "VIX 期限結構", "每日", "cboe_derived", "VIX-VIX3M",
              "{:.3f}", False, "world",
              note="近月 ÷ 三個月，> 1 為 backwardation。三個月走 CBOE 官方 CSV，"
                   "不留 Yahoo 的 ^VIX3M 退路（已凍結）"),
    Indicator("policy_path", "市場定價的政策路徑", "每日", "policy_derived",
              "ZQ-DFEDTARU", "{:+.2f}%", True, "world",
              note="Fed Funds 期貨隱含利率（100 − 報價）與現行上限的差距；"
                   "給的是一個定價，不是任何一種機率"),
    Indicator("copper", "工業金屬需求", "每日", "yfinance", "HG=F",
              "{:.3f}", False, "world",
              note="以銅期貨的 20 日變化量測工業需求；看變化不看水位。"
                   "頁面講的是需求，不是對這個商品的看法"),
    Indicator("gold_oil", "金油比（風險偏好）", "每日", "ratio_derived", "GC-CL",
              "{:.1f}", False, "world",
              note="黃金 ÷ WTI 的 20 日變化；分母缺料那一天整天不算，不補舊值"),
    Indicator("oil_curve", "原油近遠月曲線", "每日", "curve_derived", "CL-DEFERRED",
              "{:+.1f}%", True, "world",
              note="遠月（+6 個月）相對近月的價差水位；遠月代碼依當月動態生成，"
                   "不進回測（距到期月數不同，前後不可比）",
              backtest=False),
    Indicator("jp_exports", "日本出口年增率", "每月", "fred", "XTEXVA01JPM667S",
              "{:,.0f}", False, "world", note="外需的直接讀數；只進總經層，不對日股評分"),
    Indicator("kr_exports", "南韓出口年增率", "每月", "fred", "XTEXVA01KRM667S",
              "{:,.0f}", False, "world", note="外需的直接讀數；只進總經層，不對韓股評分"),
    Indicator("usdjpy", "USD/JPY", "每日", "yfinance", "JPY=X",
              "{:.2f}", False, "world",
              note="8-8 把它從只顯示搬進評分：匯率是各國總經的一環"),
    Indicator("usdkrw", "USD/KRW", "每日", "yfinance", "KRW=X",
              "{:,.2f}", False, "world"),
    Indicator("jp_policy", "日本央行政策利率", "每月", "fred", "IRSTCI01JPM156N",
              "{:.3f}%", True, "world"),
    Indicator("kr_policy", "南韓央行政策利率", "每月", "fred", "IRSTCI01KRM156N",
              "{:.3f}%", True, "world"),
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

# ---------------- 只顯示不評分（14 項） ----------------
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
    Indicator("usdcny", "USD/CNY", "每日", "yfinance", "CNY=X",
              "{:.4f}", False, "observe"),
    Indicator("btc", "比特幣", "每日", "yfinance", "BTC-USD",
              "{:,.0f}", False, "observe"),
    Indicator("brent", "布蘭特原油", "每日", "yfinance", "BZ=F",
              "{:.2f}", False, "observe"),
    Indicator("silver", "白銀", "每日", "yfinance", "SI=F",
              "{:.2f}", False, "observe",
              note="同時是工業金屬與避險標的，兩種性質混在一起無法誠實地"
                   "說成單一讀數 —— 只顯示不評分"),
    Indicator("platinum", "白金", "每日", "yfinance", "PL=F",
              "{:,.0f}", False, "observe", note="貴金屬一律不評分"),
    Indicator("palladium", "鈀", "每日", "yfinance", "PA=F",
              "{:,.0f}", False, "observe", note="貴金屬一律不評分"),
    Indicator("cot_spx", "COT 非商業淨部位（S&P 500）", "每週", "cftc", "cot_spx",
              "{:+,.0f} 口", False, "observe",
              note="CFTC 交易人持倉報告，週五公布、資料日為週二。只顯示原始部位與"
                   "週變化，不評分、不排名、不加解讀"),
    Indicator("cot_gold", "COT 非商業淨部位（黃金）", "每週", "cftc", "cot_gold",
              "{:+,.0f} 口", False, "observe", note="同上，只顯示不解讀"),
    Indicator("cot_wti", "COT 非商業淨部位（WTI）", "每週", "cftc", "cot_wti",
              "{:+,.0f} 口", False, "observe", note="同上，只顯示不解讀"),
    Indicator("breadth_us_cover", "市場廣度分母", "每日", "yfinance_breadth",
              "SECTOR11_COVER", "{:.0f} 檔", False, "observe",
              note="當日算得出 200MA 的類股 ETF 檔數（滿額 11）。7/10 與 7/11 不是同一件事"),
)

ALL: tuple[Indicator, ...] = WORLD + TAIWAN + OBSERVE
BY_KEY: dict[str, Indicator] = {i.key: i for i in ALL}

SCORED = WORLD + TAIWAN

# Engineering release-lag assumptions for historical replay (§7.2). These are
# conservative calendar-day offsets, not a claim about each actual release or
# historical data vintage. Unknown series fail closed in available_series().
PUBLISH_LAG_DAYS: dict[str, int] = {
    "CPIAUCSL": 45, "UNRATE": 35, "PAYEMS": 35,
    "ICSA": 5, "WALCL": 8,
    # 8-1：利差是日頻 T-1；淨流動性跟著 WALCL 的週四公布走
    "BAMLH0A0HYM2": 1, "WALCL-RRPONTSYD": 8,
    "SECTOR11_BREADTH": 0,  # 8-2：收盤價當天就有
    "VIX-VIX3M": 1,         # 8-3：CBOE 的 CSV 是 T-1
    "ZQ-DFEDTARU": 1,       # 8-4：期貨收盤當天就有，跟著日頻走
    "HG=F": 0, "GC-CL": 0,  # 8-5／8-7：收盤價當天就有
    # 8-8：出口月報約次月中旬、央行月頻表跟著月底走；匯率是收盤價
    "XTEXVA01JPM667S": 45, "XTEXVA01KRM667S": 45,
    "IRSTCI01JPM156N": 30, "IRSTCI01KRM156N": 30,
    "JPY=X": 0, "KRW=X": 0,
    "T10Y2Y": 1, "DFEDTARU": 1,
    "GACDFSA066MSFRBPHI": 30,
    "^VIX": 0, "DX-Y.NYB": 0, "^TNX": 0,
    "TWD=X": 0, "^SOX": 0,
    "6099": 45, "6799": 90, "lp-640": 1, "WPSR": 7,
}


def available_series(
    series: list[tuple[str, float]], sid: str, as_of: dt.date,
) -> list[tuple[str, float]]:
    """Return only rows whose assumed publication date has arrived by as_of.

    Series labels are observation dates. The caller must use the returned prefix
    for *every* indicator calculation, including moving averages and changes.
    """
    lag = PUBLISH_LAG_DAYS[sid]
    def period_start(label: str) -> dt.date:
        if len(label) == 7 and label[4] == "-":
            return dt.date.fromisoformat(label + "-01")
        if len(label) == 6 and label[4] == "Q" and label[5] in "1234":
            return dt.date(int(label[:4]), (int(label[5]) - 1) * 3 + 1, 1)
        return dt.date.fromisoformat(label)

    return [(label, value) for label, value in series
            if period_start(label) + dt.timedelta(days=lag) <= as_of]


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
