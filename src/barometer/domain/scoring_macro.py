"""世界層與台灣層總經評分（ToDo §9 Day 25 第 2 項）。

兩層結構：
  第一層 —— 每個指標各自判定「是否警示」，門檻邏輯彼此獨立
  第二層 —— 依層別算「未警示比例」，合成 0~100

**組分只看警示指標的比例，不看警示的嚴重程度。** VIX 26 與 VIX 45 對分數的
影響相同（都算一個警示）—— 嚴重程度由說明文字呈現，讓人自己判讀。這是刻意的
取捨：把「多嚴重」也編進分數，等於又多發明一把沒有依據的尺。

§2.1 紅線：這裡**不產生**任何建議、行動字眼、或把分數翻譯成動作的欄位。
評分是量測，不是指示 —— 氣壓計告訴你現在幾百帕，不告訴你要不要帶傘。

純函式、零 I/O。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

Series = list[tuple[str, float]]
Verdict = tuple[bool, str]

INSUFFICIENT = "資料不足"

# 央行：最近一次調整距今幾天以內算「政策剛動過」
CBC_RECENT_DAYS = 90


def _values(s: Series) -> list[float]:
    return [v for _, v in s if v is not None]


def _need(s: Series, n: int) -> list[float] | None:
    v = _values(s)
    return v if len(v) >= n else None


def _pct_move(v: list[float], lookback: int = 5) -> float:
    return (v[-1] / v[-1 - lookback] - 1.0) * 100.0


# ---------------- 第一層：世界層 ----------------

def alert_vix(s: Series) -> Verdict:
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    if x > 35:
        return True, f"VIX {x:.1f} > 35 強警示（恐慌）"
    if x > 25:
        return True, f"VIX {x:.1f} > 25 警示"
    return False, f"VIX {x:.1f}"


def alert_dxy(s: Series) -> Verdict:
    v = _need(s, 6)
    if not v:
        return False, INSUFFICIENT
    d = _pct_move(v)
    hit = abs(d) > 2.0
    return hit, f"5 日變動 {d:+.2f}%（門檻 ±2%）"


# 8-12：原本寫死在函式裡的 0.20。校準要改的就是這個數字，
# 所以它得有名字 —— 實證結果見 Reports/Alert_Threshold_Calibration。
US10Y_MOVE_PP = 0.25   # 8-12 校準：±0.20 是 18.4 次/年（偏多），±0.25 是 8.6 次/年


def alert_us10y(s: Series) -> Verdict:
    v = _need(s, 6)
    if not v:
        return False, INSUFFICIENT
    d = v[-1] - v[-6]
    hit = abs(d) > US10Y_MOVE_PP
    return hit, f"週變動 {d:+.2f} 個百分點（門檻 ±{US10Y_MOVE_PP:.2f}）"


def alert_t10y2y(s: Series) -> Verdict:
    """10Y-2Y 利差：負值就是倒掛，本身即為警示。"""
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    if x < 0:
        return True, f"利差 {x:+.2f}% 倒掛"
    return False, f"利差 {x:+.2f}%"


def alert_cpi(s: Series) -> Verdict:
    v = _need(s, 13)
    if not v:
        return False, INSUFFICIENT
    yoy = (v[-1] / v[-13] - 1.0) * 100.0
    mom = (v[-1] / v[-2] - 1.0) * 100.0
    hit = yoy > 3.0 or mom > 0.4
    return hit, f"YoY {yoy:+.2f}%（門檻 3%）、MoM {mom:+.2f}%（門檻 0.4%）"


def alert_unrate(s: Series) -> Verdict:
    """Sahm 法則：最新值 − 近 12 個月最低值 >= 0.5 個百分點。"""
    v = _need(s, 13)
    if not v:
        return False, INSUFFICIENT
    low = min(v[-12:])
    gap = v[-1] - low
    hit = gap >= 0.5
    return hit, f"Sahm 法則：{v[-1]:.1f}% − 近 12 月最低 {low:.1f}% = {gap:+.2f}pp"


def alert_phlfed(s: Series) -> Verdict:
    """擴散指數，榮枯線 = 0（不是 ISM 的 50）。"""
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    return x < 0, f"指數 {x:+.1f}（榮枯線 0）"


def alert_fedfunds(s: Series) -> Verdict:
    v = _need(s, 2)
    if not v:
        return False, INSUFFICIENT
    base = v[-31] if len(v) >= 31 else v[0]
    hit = v[-1] != base
    return hit, f"目前 {v[-1]:.2f}%，近 30 筆基準 {base:.2f}%"


# ---------------- 第一層：台灣層 ----------------

def alert_usdtwd(s: Series) -> Verdict:
    v = _need(s, 6)
    if not v:
        return False, INSUFFICIENT
    d = _pct_move(v)
    hit = abs(d) > 1.5
    return hit, f"5 日變動 {d:+.2f}%（門檻 ±1.5%）"


def alert_sox(s: Series) -> Verdict:
    v = _need(s, 60)
    if not v:
        return False, INSUFFICIENT
    ma60 = sum(v[-60:]) / 60
    hit = v[-1] < ma60
    return hit, f"收盤 {v[-1]:,.0f}，60 日均線 {ma60:,.0f}"


def alert_tw_light(s: Series) -> Verdict:
    """兩端都警示：過冷與過熱皆屬環境異常。"""
    from barometer.domain.macro_spec import light_name

    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    hit = x <= 16 or x >= 38
    return hit, f"綜合分數 {x:.0f} 分，{light_name(x)}"


def alert_tw_export(s: Series) -> Verdict:
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    return x < 50, f"動向指數 {x:.2f}（榮枯線 50）"


def alert_tw_gdp(s: Series) -> Verdict:
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    return x < 0, f"最新一季 YoY {x:+.2f}%"


def alert_cbc_rate(s: Series, today: dt.date | None = None) -> Verdict:
    """序列是**歷次調整紀錄**，不是日資料 —— 剛調過息 = 政策變動注意。

    判定看的是「距今幾天」，不是「值有沒有變」：這張表裡相鄰兩列的值必然不同
    （不然不會被記成一次調整），拿值去比會永遠亮燈。實測 2026-09-06 抓到的
    最新一次調整是 2024-03-22，早就過了觀察窗。
    """
    if not s:
        return False, INSUFFICIENT
    last_date_s, rate = s[-1]
    today = today or dt.date.today()
    try:
        last_date = dt.date.fromisoformat(last_date_s)
    except ValueError:
        return False, INSUFFICIENT

    days = (today - last_date).days
    hit = days <= CBC_RECENT_DAYS
    return hit, f"重貼現率 {rate:.2f}%，最近一次調整 {last_date_s}（距今 {days} 天）"


# --- 三項復活的指標（作者 2026-09-07 決定保留，見 macro_spec 的說明） ---

# 初領失業金：四週均值相對近期低點上升多少算轉弱。
# 20% 是衰退研究裡常見的量級，跟 Sahm 法則同一個家族的直覺，不是推導出來的。
CLAIMS_RISE_PCT = 20.0
CLAIMS_MIN_WEEKS = 8

# 原油庫存：週變化超過這個百分比算不尋常。兩端都算。
CRUDE_MOVE_PCT = 2.0


def alert_claims(s: Series) -> Verdict:
    """初領失業金：四週均值相對近期低點的升幅。

    **只有上升算警示，下降不算** —— 這一項刻意不是兩端都警示。初領下降是
    勞動市場轉強，把它記成「不尋常」會讓這條序列在景氣好的時候一直亮燈。

    用四週均值是因為週資料本身很吵（颱風、假期、單一大廠裁員都會跳），
    單週的高點沒有意義。
    """
    v = _need(s, CLAIMS_MIN_WEEKS)
    if not v:
        return False, INSUFFICIENT
    recent = sum(v[-4:]) / 4
    low = min(sum(v[i:i + 4]) / 4 for i in range(len(v) - 3))
    if low <= 0:
        return False, INSUFFICIENT
    rise = (recent / low - 1.0) * 100.0
    if rise > CLAIMS_RISE_PCT:
        return True, (f"初領四週均值 {recent:,.0f}，較近期低點 {low:,.0f} "
                      f"上升 {rise:.1f}%（門檻 {CLAIMS_RISE_PCT:.0f}%）")
    return False, f"初領四週均值 {recent:,.0f}，較近期低點上升 {rise:.1f}%"


def alert_payrolls(s: Series) -> Verdict:
    """非農就業：月增為負就是警示。

    這一項看的是**淨增減**，不是水位。非農總人數本身一直在長，拿水位去比
    永遠不會亮燈；真正有意義的是那個月增掉到負的那一刻。
    """
    v = _need(s, 2)
    if not v:
        return False, INSUFFICIENT
    change = v[-1] - v[-2]
    if change < 0:
        return True, f"非農就業月增 {change:+,.0f} 千人（就業人數減少）"
    return False, f"非農就業月增 {change:+,.0f} 千人"


def alert_crude_stocks(wow_change_pct: float | None) -> Verdict:
    """原油庫存週變化。**兩端都算警示。**

    急速去化代表供給緊張（2026 年 9 月戰爭期間最值得注意的那一端），
    急速累積代表需求塌陷。兩種都是不尋常，方向的解讀留給讀的人。

    收的是 WPSR 直接給的週變化百分比，不是自己從序列算的 —— 那張表本來
    就是比較表，它算好的數字比我從兩個點推的可靠（見 datasources/eia_src）。
    """
    if wow_change_pct is None:
        return False, INSUFFICIENT
    if wow_change_pct < -CRUDE_MOVE_PCT:
        return True, (f"原油庫存週變化 {wow_change_pct:+.1f}%，快速去化"
                      f"（門檻 ±{CRUDE_MOVE_PCT:.0f}%）")
    if wow_change_pct > CRUDE_MOVE_PCT:
        return True, (f"原油庫存週變化 {wow_change_pct:+.1f}%，快速累積"
                      f"（門檻 ±{CRUDE_MOVE_PCT:.0f}%）")
    return False, f"原油庫存週變化 {wow_change_pct:+.1f}%"


def alert_crude_stocks_series(s: Series) -> Verdict:
    """讓原油庫存也吃得下通用的 `Series` 簽名。

    WPSR 那張表本來就給了算好的週變化百分比，而這裡是從兩個點自己推 ——
    兩者是同一個算式套在同一組數字上，結果相同。

    做這層包裝是為了保住一條不變式：**每一個進評分的指標都在 ALERT_FUNCS
    裡有一筆**。少了這條，`run_macro` 就得記得替某幾個指標走特例，
    而那種「要記得」的事情遲早會被忘掉（而且忘掉的時候不會報錯，
    只會安靜地少算一個維度）。
    """
    v = _need(s, 2)
    if not v or v[-2] == 0:
        return False, INSUFFICIENT
    return alert_crude_stocks((v[-1] / v[-2] - 1.0) * 100.0)


# --- 8-1：信用利差與淨流動性 ---
#
# 兩個門檻都是工程上的起手值，不是從歷史推導出來的 —— 8-12 會拿回測的觸發頻率
# 校準它們。寫成具名常數就是為了那時候只要改這裡。
HY_SPREAD_RISE_PP = 1.0      # 相對近期低點擴大幾個百分點算警示
HY_SPREAD_LOOKBACK = 20      # 近期低點的視窗（約一個月的交易日）
LIQUIDITY_DROP_PCT = 1.0     # 四週淨流動性收縮幾 % 算警示
LIQUIDITY_WEEKS = 4


def alert_credit_spread(s: Series) -> Verdict:
    """高收益債信用利差：相對近期低點的擴大幅度。

    **只有擴大算警示。** 利差收斂是風險偏好回來，把它記成不尋常，這條序列
    在多頭時會一直亮燈 —— 同 `alert_claims` 的理由。

    看的是升幅不是水位：利差本身的絕對水準隨信用週期而移動，而「股市還在撐、
    信用市場先報警」講的就是那個轉折。
    """
    v = _need(s, HY_SPREAD_LOOKBACK)
    if not v:
        return False, INSUFFICIENT
    low = min(v[-HY_SPREAD_LOOKBACK:])
    rise = v[-1] - low
    if rise >= HY_SPREAD_RISE_PP:
        return True, (f"利差 {v[-1]:.2f}%，較近期低點 {low:.2f}% 擴大 {rise:.2f} 個百分點"
                      f"（門檻 {HY_SPREAD_RISE_PP:.2f}）")
    return False, (f"利差 {v[-1]:.2f}%，較近期低點 {low:.2f}% 變動 "
                   f"{rise:+.2f} 個百分點")


def alert_net_liquidity(s: Series) -> Verdict:
    """Fed 淨流動性 `WALCL − RRPONTSYD`：看四週**變化方向**，不看水位。

    ⚠️ **基期為 0 一律視為缺料。** `RRPONTSYD` 在 2013 年以前長期為 0，
    照著算變化率會得到 `inf`，壓進分數之後變成一個看起來很嚴重、其實不存在的
    「流動性極差」訊號。缺料就說缺料。
    """
    v = _need(s, LIQUIDITY_WEEKS + 1)
    if not v:
        return False, INSUFFICIENT
    base = v[-1 - LIQUIDITY_WEEKS]
    if base == 0:
        return False, INSUFFICIENT
    change = (v[-1] / base - 1.0) * 100.0
    if change < -LIQUIDITY_DROP_PCT:
        return True, (f"淨流動性四週變動 {change:+.2f}%，收縮"
                      f"（門檻 −{LIQUIDITY_DROP_PCT:.1f}%）")
    return False, f"淨流動性四週變動 {change:+.2f}%（門檻 −{LIQUIDITY_DROP_PCT:.1f}%）"


# 8-2：市場廣度。半數以下站上 200MA = 只剩少數類股在撐。
# 同樣是起手值，8-12 會用觸發頻率校準。
BREADTH_WEAK_PCT = 50.0


def alert_breadth_us(s: Series) -> Verdict:
    """類股 ETF 站上 200MA 的比例。

    ⚠️ **這是代理指標，不是真的漲跌家數。** 文字裡必須講出來，不然讀的人會
    以為看到的是 advance/decline。分母（當日有料的檔數）是另一條 OBSERVE 序列。
    """
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    tail = (f"（代理指標，不是漲跌家數；分母見「市場廣度分母」，"
            f"門檻 {BREADTH_WEAK_PCT:.0f}%）")
    if x < BREADTH_WEAK_PCT:
        return True, f"類股 ETF 站上 200MA 比例 {x:.0f}%{tail}"
    return False, f"類股 ETF 站上 200MA 比例 {x:.0f}%{tail}"


def alert_vix_term(s: Series) -> Verdict:
    """VIX 期限結構：近月 ÷ 三個月。

    比值 > 1 就是 backwardation —— 市場在為眼前的事定價，而不是為未來三個月。
    ⚠️ **水位高不等於在惡化**：VIX 30 但期限結構正常，跟 VIX 20 但倒掛，
    講的是兩件不同的事，所以這一項刻意不看 VIX 自己的水位（那是 `vix` 那一項）。
    """
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    if x > 1.0:
        return True, f"VIX/VIX3M {x:.3f} > 1，近月比三個月貴（backwardation）"
    return False, f"VIX/VIX3M {x:.3f}（1 以下為正常期限結構）"


# 8-4：市場定價與現行上限差一碼以上，算政策路徑與現況背離。
POLICY_GAP_PP = 0.25


def alert_policy_path(s: Series) -> Verdict:
    """Fed Funds 期貨隱含利率與現行上限的差距（百分點）。

    ⚠️ **這是「市場定價的政策路徑」。** 期貨報價給的是一個價格，把它翻譯成
    某某機率等於憑空多出一個沒有算過的分布 —— 那種措辭在這一項是紅線，
    不是文案偏好（§7.1）。`test_eighth_policy_path.py` 用 AST 守著。
    """
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    gap = v[-1]
    direction = "低於" if gap < 0 else "高於"
    body = (f"市場定價的政策路徑{direction}現行上限 {abs(gap):.2f} 個百分點"
            f"（門檻 {POLICY_GAP_PP:.2f}）")
    return abs(gap) >= POLICY_GAP_PP, body


# 8-5／8-7：兩項都是 20 個交易日的變化量。起手值，8-12 校準。
METAL_WINDOW = 20
METAL_FALL_PCT = 8.0        # 工業金屬需求的跌幅門檻
GOLD_OIL_RISE_PCT = 20.0    # 金油比的漲幅門檻


def alert_copper(s: Series) -> Verdict:
    """工業金屬需求：20 個交易日的變化。

    ⚠️ **文字不出現商品名稱或代碼。** 這一頁有分數，寫「銅走弱」會被讀成
    這個系統對那個商品有看法；它沒有，它只是拿它當需求的讀數（§7.1）。

    **只有下跌算警示。** 需求走弱是這一項要抓的東西；急漲多半是供給面的事，
    那不是這條序列說得清楚的。
    """
    v = _need(s, METAL_WINDOW + 1)
    if not v:
        return False, INSUFFICIENT
    change = _pct_move(v, METAL_WINDOW)
    if change < -METAL_FALL_PCT:
        return True, (f"工業金屬需求 20 日變動 {change:+.1f}%"
                      f"（門檻 −{METAL_FALL_PCT:.0f}%）")
    return False, f"工業金屬需求 20 日變動 {change:+.1f}%（門檻 −{METAL_FALL_PCT:.0f}%）"


def alert_gold_oil(s: Series) -> Verdict:
    """金油比：20 個交易日的變化。

    比值本身沒有一個「正常水位」可以比 —— 它隨著兩邊各自的供需長期漂移。
    會說話的是變化：急升代表資金往避險端跑。

    ⚠️ 分母缺料時這條序列**根本不會有那一天**（見 `ratio_series`），
    所以這裡拿到的一定是兩邊都有的日子；算不出來就回 `INSUFFICIENT`，
    不回 0、不拿舊值。
    """
    v = _need(s, METAL_WINDOW + 1)
    if not v:
        return False, INSUFFICIENT
    change = _pct_move(v, METAL_WINDOW)
    if change > GOLD_OIL_RISE_PCT:
        return True, (f"金油比 20 日變動 {change:+.1f}%，資金往避險端"
                      f"（門檻 +{GOLD_OIL_RISE_PCT:.0f}%）")
    return False, f"金油比 20 日變動 {change:+.1f}%（門檻 +{GOLD_OIL_RISE_PCT:.0f}%）"


# 8-6：近月與 +6 個月的價差水位。兩端都算不尋常，對稱映射。
OIL_CURVE_PCT = 8.0


def alert_oil_curve(s: Series) -> Verdict:
    """原油近遠月價差（遠月相對近月的百分比）。

    判定用的是**絕對價差水位**，不是它的變化：曲線形狀本身就是供需的讀數。
    負值是 backwardation（現貨比遠月貴，供給緊），正值是 contango。
    兩端都算不尋常，方向的解讀留給讀的人。
    """
    v = _need(s, 1)
    if not v:
        return False, INSUFFICIENT
    x = v[-1]
    tail = f"（門檻 ±{OIL_CURVE_PCT:.0f}%／6 個月）"
    if x < -OIL_CURVE_PCT:
        return True, f"遠月較近月低 {abs(x):.1f}%，backwardation{tail}"
    if x > OIL_CURVE_PCT:
        return True, f"遠月較近月高 {x:.1f}%，contango{tail}"
    return False, f"遠月較近月 {x:+.1f}%{tail}"


# 8-8：各國總經。⚠️ 只進總經層，不對任何國家的股指評分（§8）。
FX_MOVE_PCT = 2.5            # 8-12 校準：±2.0% 是 JPY 16.4／KRW 14.4 次/年，±2.5% 是 8.8／8.0
FOREIGN_POLICY_MONTHS = 12   # 政策利率「剛動過」的回看窗（月）


def alert_exports_yoy(s: Series) -> Verdict:
    """出口年增率：與 13 個月前相比。**轉負算警示。**

    出口是外需的直接讀數，對日韓這種外需導向的經濟體尤其如此。
    ⚠️ 基期為 0 視為缺料 —— 同 8-1 的理由，除以 0 得到的不是「成長無限大」。
    """
    v = _need(s, 13)
    if not v:
        return False, INSUFFICIENT
    base = v[-13]
    if base == 0:
        return False, INSUFFICIENT
    yoy = (v[-1] / base - 1.0) * 100.0
    if yoy < 0:
        return True, f"出口年增率 {yoy:+.1f}%（負成長）"
    return False, f"出口年增率 {yoy:+.1f}%"


def alert_fx_move(s: Series) -> Verdict:
    """匯率五日變動，**兩端都算**：急貶與急升都是不尋常。"""
    v = _need(s, 6)
    if not v:
        return False, INSUFFICIENT
    d = _pct_move(v)
    return abs(d) > FX_MOVE_PCT, f"5 日變動 {d:+.2f}%（門檻 ±{FX_MOVE_PCT:.0f}%）"


def alert_foreign_policy_rate(s: Series) -> Verdict:
    """央行政策利率：近一年內動過就是政策變動注意。

    跟 `alert_fedfunds` 同一個形狀，但這幾條是月頻，所以基準取的是月數不是筆數。
    """
    v = _need(s, 2)
    if not v:
        return False, INSUFFICIENT
    window = v[-(FOREIGN_POLICY_MONTHS + 1):]
    base = window[0]
    hit = v[-1] != base
    return hit, f"目前 {v[-1]:.3f}%，近 {len(window) - 1} 個月基準 {base:.3f}%"


ALERT_FUNCS = {
    "vix": alert_vix, "dxy": alert_dxy, "us10y": alert_us10y,
    "t10y2y": alert_t10y2y, "cpi": alert_cpi, "unrate": alert_unrate,
    "phlfed": alert_phlfed, "fedfunds": alert_fedfunds,
    "usdtwd": alert_usdtwd, "sox": alert_sox, "tw_light": alert_tw_light,
    "tw_export": alert_tw_export, "tw_gdp": alert_tw_gdp,
    "cbc_rate": alert_cbc_rate,
    "claims": alert_claims, "payrolls": alert_payrolls,
    "credit_spread": alert_credit_spread, "net_liquidity": alert_net_liquidity,
    "breadth_us": alert_breadth_us,
    "vix_term": alert_vix_term,
    "policy_path": alert_policy_path,
    "copper": alert_copper, "gold_oil": alert_gold_oil,
    "oil_curve": alert_oil_curve,
    # 8-8：日韓各一組（出口、匯率、央行政策）。⚠️ 不對任何國家的股指評分。
    "jp_exports": alert_exports_yoy, "kr_exports": alert_exports_yoy,
    "usdjpy": alert_fx_move, "usdkrw": alert_fx_move,
    "jp_policy": alert_foreign_policy_rate, "kr_policy": alert_foreign_policy_rate,
    # 原油庫存的原始判定收的是「週變化百分比」，這裡掛的是吃 Series 的包裝，
    # 讓「每個評分指標都有一筆」這條不變式成立（見 alert_crude_stocks_series）。
    "crude_stocks": alert_crude_stocks_series,
}


# ---------------- 第二層：層別評分 ----------------

@dataclass(frozen=True, slots=True)
class LayerScore:
    score: float | None
    valid: int
    alert_keys: list[str] = field(default_factory=list)


def score_layer(alerts: dict[str, bool]) -> LayerScore:
    """未警示比例 × 100。整層沒有有效指標 → score 是 None，該層不計入權重。"""
    if not alerts:
        return LayerScore(score=None, valid=0, alert_keys=[])
    hit = [k for k, v in alerts.items() if v]
    return LayerScore(
        score=100.0 * (1.0 - len(hit) / len(alerts)),
        valid=len(alerts),
        alert_keys=hit,
    )


LOW_DATA_THRESHOLD = 10


def summarize(world: LayerScore, taiwan: LayerScore) -> dict:
    """把兩層合成一個總分。兩層等權。

    刻意**沒有** advice / level 這類欄位 —— 既有專案的 summarize() 會回
    「建議降低部位、提高現金比重」，那正是 market-barometer 這一側不能有的（§2.1）。
    輸出到此為止：分數、分項、警示了哪幾項。
    """
    parts = [(1.0, layer) for layer in (world, taiwan) if layer.score is not None]
    total = (
        sum(w * layer.score for w, layer in parts) / sum(w for w, _ in parts)
        if parts
        else None
    )
    valid = world.valid + taiwan.valid
    return {
        "score": round(total, 1) if total is not None else None,
        "world": world.score,
        "taiwan": taiwan.score,
        "valid": valid,
        "alert_keys": world.alert_keys + taiwan.alert_keys,
        "low_data": valid < LOW_DATA_THRESHOLD,
    }
