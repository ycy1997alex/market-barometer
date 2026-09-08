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


def alert_us10y(s: Series) -> Verdict:
    v = _need(s, 6)
    if not v:
        return False, INSUFFICIENT
    d = v[-1] - v[-6]
    hit = abs(d) > 0.20
    return hit, f"週變動 {d:+.2f} 個百分點（門檻 ±0.20）"


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


ALERT_FUNCS = {
    "vix": alert_vix, "dxy": alert_dxy, "us10y": alert_us10y,
    "t10y2y": alert_t10y2y, "cpi": alert_cpi, "unrate": alert_unrate,
    "phlfed": alert_phlfed, "fedfunds": alert_fedfunds,
    "usdtwd": alert_usdtwd, "sox": alert_sox, "tw_light": alert_tw_light,
    "tw_export": alert_tw_export, "tw_gdp": alert_tw_gdp,
    "cbc_rate": alert_cbc_rate,
    "claims": alert_claims, "payrolls": alert_payrolls,
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
