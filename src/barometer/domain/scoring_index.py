"""大盤與 ETF 評分（ToDo §8.2、§9 Day 26 第 3 項）。純函式、零 I/O。

**結構刻意跟 scoring_macro.py 一樣**：第一層每個維度各自判「是否警示」並附
一句理由，第二層算未警示比例 × 100。兩層總經與大盤用同一把尺的形狀，才比得
起來；各發明一套只會多出一個要解釋的東西。

五個技術面維度（§8.2）：

    MA 排列（5/20/60）   位置關係，不是單一均線
    RSI(14)              **兩端都算警示**
    布林通道             收在帶外算警示
    年化波動度           近期 vs 長期的**倍數**，不是寫死的絕對值
    距 52 週高點回撤     回撤幅度

「一年」在兩個市場不是同一個數字（台股 243~244 根、美股 252 根），視窗寫死
就會讓台股永遠少算兩個維度 —— 見 LOOKBACK_FULL 那一段。

**波動度為什麼不用絕對門檻**：台股與美股的常態波動度本來就不同，寫死一個
30% 等於偷偷假設兩個市場一樣。拿標的自己的長期水準當分母，這把尺對兩邊才都
成立 —— 代價是它量的變成「相對於自己平常」，不是「相對於別人」。這是取捨，
Day 26 那句「那把尺憑什麼是這樣」講的就是這種東西。

**門檻是自己硬定的。** 每個常數旁邊都留了為什麼是這個數字，不是因為它有依據，
是因為半年後要改的時候得知道當初在想什麼（§8.3）。

§2.1 紅線：這裡**不產生**任何建議、行動字眼、或把分數翻譯成動作的欄位 ——
`to_dict()` 沒有 advice/action/signal 這種 key，而且有測試守著。
評分是量測，不是指示。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from barometer.domain.indicators import (
    annualised_volatility,
    bollinger_position,
    drawdown_from_high,
    moving_average,
    rsi,
)

Verdict = tuple[bool, str]

INSUFFICIENT = "資料不足"

# --- 門檻與它們的理由（§8.3：留一份「為什麼是這個數字」） ---

# RSI：70/30 是 Wilder 原始定義的慣例值，用它是為了跟外面講得通，不是因為它更準
RSI_HIGH = 70.0
RSI_LOW = 30.0
RSI_PERIOD = 14

# 布林：位置 > 1 或 < 0 就是收在帶外。2 個標準差同樣是慣例值
BOLL_PERIOD = 20

# 波動度：近 20 日相對「一年」的倍數。1.5 是「明顯比平常吵」的直覺值，沒有統計依據
VOL_RECENT = 20
VOL_RATIO = 1.5

# 回撤：距 52 週高點 10% 是常見的「修正」門檻，同樣是慣例不是推導
DRAWDOWN_PCT = -10.0

# --- 「一年」到底是幾根？兩個市場不一樣，這件事害過一次 ---
#
# 台股一年 243~244 根、美股 252 根。把回看視窗寫死成 250，台股就**永遠**
# 少算波動度與回撤兩個維度 —— 分數照樣算得出來（分母變成 3），看起來毫無異狀，
# 但台股與美股的分數量的根本不是同一組東西，放在同一頁上比就是錯的。
#
# 所以視窗改成「最多 LOOKBACK_FULL 根，至少 LOOKBACK_MIN 根」：
#   足額     → 就是 52 週
#   不足額   → 降級成「這段序列以來」，而且**理由字串要講出來自己降級了**
#   低於底線 → 資料不足，不硬算（SPCX 只有 59 根，就是這一格）
#
# 底線設 200 是因為它擋得住 SPCX（59 根）又放得過台股整年（243 根）。
# 這個數字同樣是自己定的，寫在這裡是為了半年後知道當初在想什麼（§8.3）。
LOOKBACK_FULL = 250
LOOKBACK_MIN = 200
DEGRADED = "已降級"

MA_PERIODS = (5, 20, 60)


def _clean(series: list[float | None]) -> list[float]:
    return [float(x) for x in series if x is not None]


# ---------------- 第一層：技術面各維度 ----------------

def alert_ma_stack(closes: list[float | None]) -> Verdict:
    """MA(5/20/60) 的位置關係。空頭排列（5 < 20 < 60）算警示。"""
    v = _clean(closes)
    if len(v) < max(MA_PERIODS):
        return False, INSUFFICIENT
    ma = [moving_average(v, p)[-1] for p in MA_PERIODS]
    if any(m is None for m in ma):
        return False, INSUFFICIENT
    m5, m20, m60 = ma  # type: ignore[misc]
    if m5 < m20 < m60:
        return True, f"空頭排列 MA5 {m5:,.2f} < MA20 {m20:,.2f} < MA60 {m60:,.2f}"
    if m5 > m20 > m60:
        return False, f"多頭排列 MA5 {m5:,.2f} > MA20 {m20:,.2f} > MA60 {m60:,.2f}"
    return False, f"均線糾結 MA5 {m5:,.2f} / MA20 {m20:,.2f} / MA60 {m60:,.2f}"


def alert_rsi(closes: list[float | None]) -> Verdict:
    """RSI(14)。**兩端都算警示** —— 過熱與過冷都是「落在不尋常的地方」。

    分數不是越高越好的方向盤。把 RSI 30 記成「好」、70 記成「壞」，等於偷偷
    塞進一個方向判斷，那已經是建議不是量測了。
    """
    v = _clean(closes)
    if len(v) <= RSI_PERIOD:
        return False, INSUFFICIENT
    r = rsi(v, RSI_PERIOD)[-1]
    if r is None:
        return False, INSUFFICIENT
    if r >= RSI_HIGH:
        return True, f"RSI(14) {r:.1f} ≥ {RSI_HIGH:.0f}"
    if r <= RSI_LOW:
        return True, f"RSI(14) {r:.1f} ≤ {RSI_LOW:.0f}"
    return False, f"RSI(14) {r:.1f}"


def alert_bollinger(closes: list[float | None]) -> Verdict:
    """收盤是否落在布林通道外。"""
    v = _clean(closes)
    if len(v) < BOLL_PERIOD:
        return False, INSUFFICIENT
    pos = bollinger_position(v, BOLL_PERIOD)
    if pos is None:
        return False, INSUFFICIENT
    if pos > 1.0:
        return True, f"收在上軌帶外（位置 {pos:.2f}）"
    if pos < 0.0:
        return True, f"收在下軌帶外（位置 {pos:.2f}）"
    return False, f"通道內位置 {pos:.2f}"


def _lookback(v: list[float]) -> tuple[list[float], str] | None:
    """取回看視窗，並回一段說明它是不是降級的。不足底線回 None。"""
    if len(v) < LOOKBACK_MIN:
        return None
    window = v[-LOOKBACK_FULL:]
    if len(window) < LOOKBACK_FULL:
        return window, f"（以 {len(window)} 個交易日代替 52 週，{DEGRADED}）"
    return window, ""


def alert_volatility(closes: list[float | None]) -> Verdict:
    """近期年化波動度相對長期水準的倍數。門檻是相對的，不是絕對的。"""
    v = _clean(closes)
    got = _lookback(v)
    if got is None:
        return False, INSUFFICIENT
    baseline_window, degraded = got
    recent = annualised_volatility(v[-VOL_RECENT:])
    baseline = annualised_volatility(baseline_window)
    if recent is None or not baseline:
        return False, INSUFFICIENT
    ratio = recent / baseline
    label = (f"近 {VOL_RECENT} 日年化波動 {recent * 100:.1f}%，"
             f"長期 {baseline * 100:.1f}%{degraded}")
    if ratio > VOL_RATIO:
        return True, f"{label}，{ratio:.2f} 倍 > {VOL_RATIO} 倍"
    return False, f"{label}，{ratio:.2f} 倍"


def alert_drawdown(closes: list[float | None]) -> Verdict:
    """距 52 週高點的回撤。

    序列不滿 52 週時，高點退化成「這段序列以來的高點」，而且**理由字串會
    自己說出降級了**，不假裝它還是 52 週（§10 SPCX）。低於 LOOKBACK_MIN 就
    回資料不足 —— 降級有底線，不是無限退讓。
    """
    v = _clean(closes)
    got = _lookback(v)
    if got is None:
        return False, INSUFFICIENT
    window, degraded = got
    dd = drawdown_from_high(window)
    if dd is None:
        return False, INSUFFICIENT
    pct = dd * 100.0
    if pct < DRAWDOWN_PCT:
        return True, f"距 52 週高點 {pct:.1f}%{degraded} < {DRAWDOWN_PCT:.0f}%"
    return False, f"距 52 週高點 {pct:.1f}%{degraded}"


TECHNICAL = {
    "ma_stack": alert_ma_stack,
    "rsi": alert_rsi,
    "bollinger": alert_bollinger,
    "volatility": alert_volatility,
    "drawdown": alert_drawdown,
}


# ---------------- 第二層：合成 ----------------

@dataclass(frozen=True, slots=True)
class IndexScore:
    """一個標的某一天的技術面評分。

    刻意**沒有** advice / level / action 欄位 —— 既有專案的 summarize() 會回
    「建議降低部位」，那正是 market-barometer 這一側不能有的（§2.1）。
    """

    symbol: str
    score: float | None
    valid: int
    alert_keys: list[str] = field(default_factory=list)
    subscores: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 1) if self.score is not None else None,
            "valid": self.valid,
            "alert_keys": list(self.alert_keys),
            "subscores": dict(self.subscores),
            "reasons": dict(self.reasons),
        }


def score_index(symbol: str, closes: list[float | None]) -> IndexScore:
    """未警示比例 × 100。算不出來的維度不計入分母。

    `subscores` 每一項是 0.0（警示）或 1.0（未警示），不是連續值 —— 跟
    scoring_macro 一樣，**只看有沒有警示，不看警示得多嚴重**。把嚴重程度也
    編進分數，等於又發明一把沒有依據的尺（§8.2 那段取捨）。
    """
    verdicts = {k: fn(closes) for k, fn in TECHNICAL.items()}
    usable = {k: v for k, v in verdicts.items() if v[1] != INSUFFICIENT}
    if not usable:
        return IndexScore(symbol=symbol, score=None, valid=0)

    hit = [k for k, (alert, _) in usable.items() if alert]
    return IndexScore(
        symbol=symbol,
        score=100.0 * (1.0 - len(hit) / len(usable)),
        valid=len(usable),
        alert_keys=hit,
        subscores={k: 0.0 if alert else 1.0 for k, (alert, _) in usable.items()},
        reasons={k: why for k, (_, why) in usable.items()},
    )


# ---------------- ETF 特有（§8.2） ----------------

def tracking_error(
    etf_closes: list[float | None], index_closes: list[float | None]
) -> float | None:
    """追蹤誤差：同一段期間 ETF 與指數的報酬差（百分點）。

    這是 §8.2 那五項 ETF 特有指標裡**唯一**用現有資料算得出來的 —— 其餘四項
    見 etf_data_gaps()。

    兩條序列長度不同就回 None，不猜怎麼對齊 —— 錯開一天的對齊會安靜地產生
    一個看起來合理的錯數字，那比沒有數字糟。
    """
    e = _clean(etf_closes)
    i = _clean(index_closes)
    if len(e) != len(i) or len(e) < 2 or e[0] == 0 or i[0] == 0:
        return None
    return ((e[-1] / e[0]) - (i[-1] / i[0])) * 100.0


# §8.2 列了五項 ETF 特有指標，現有資料只算得出追蹤誤差。其餘四項需要 NAV、
# 公開說明書的費用率、成分股異動公告、除息公告 —— 都不在這條管線的來源裡。
# **回「資料不足」，不硬掰數字**，跟 SPCX 中長期評分的處置一致（§10）。
_ETF_GAPS = ("內扣費用", "折溢價", "成分股調整", "配息與除息")


def etf_data_gaps(symbol: str) -> dict[str, str]:
    """這個標的有哪些 ETF 特有指標算不出來。指數沒有這些項目，回空 dict。"""
    if symbol.startswith("^"):
        return {}
    return {name: INSUFFICIENT for name in _ETF_GAPS}
