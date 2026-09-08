"""市場級籌碼面（ToDo §8.2、§9 Day 26 第 2 項）。純函式、零 I/O。

三個維度，全部是**台股市場整體**的數字，不是個股：

  1. 融資餘額（TWSE MI_MARGN，單位**張**）—— 散戶槓桿水位
  2. 台指期三大法人淨未平倉（期交所，單位**口**）—— 大額交易人的方向
  3. 選擇權 put/call 未平倉比（期交所，單位 %）—— 避險與情緒的相對強弱

**單位在這裡最容易出事**：同一個 snapshot 裡同時有股（T86 買賣超）、張（融資
融券）、口（台指期）。所以每個欄位名都自己帶單位字尾，而且有一個測試守著這
條命名規則 —— 既有專案在張／股上留過 bug，這次讓型別自己說話（§10）。

**兩個刻意的設計，都是為了不要每天亮燈：**

- 外資期貨看的是**方向翻轉**，不是水位高低。一路淨空的時候拿「還是淨空」去
  記警示，燈會天天亮，亮到沒有人看。這跟 §10 央行重貼現率那個坑是同一種錯 ——
  那張表是歷次調整紀錄，拿值去比必然永遠不同。判定要看「有沒有變」。
- 融資看的是**五日變化率**，不是餘額本身。餘額多少張是水位，墊高多快才是訊號。

**§8.2 的讀法規則**：三大法人對 ETF 的買賣多半是套利與申贖，跟指數不同義。
所以 `reading()` 會回一段 caveat，讓輸出層必須把它印出來 —— 這是「同一個指標
換個標的就不能同樣解讀」的實例，不是裝飾文字。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

Verdict = tuple[bool, str]

INSUFFICIENT = "資料不足"

# 融資餘額五日變化超過這個百分比 → 警示（散戶槓桿墊高得快）
MARGIN_SURGE_PCT = 3.0
MARGIN_MIN_POINTS = 6  # 要算五日變化，至少六個點

# put/call 未平倉比的兩端門檻（%）
PC_OI_HIGH = 150.0
PC_OI_LOW = 60.0


@dataclass(frozen=True, slots=True)
class ChipSnapshot:
    """某一天的市場籌碼面讀數。欄位名一律帶單位字尾（見模組 docstring）。"""

    date: dt.date | None = None
    foreign_net_shares: float | None = None       # T86 外資買賣超（股）
    trust_net_shares: float | None = None         # T86 投信買賣超（股）
    dealer_net_shares: float | None = None        # T86 自營商買賣超（股）
    total_net_shares: float | None = None         # T86 三大法人合計（股）
    margin_lots: float | None = None              # 融資餘額（張）
    short_lots: float | None = None               # 融券餘額（張）
    fut_foreign_net_oi_contracts: float | None = None   # 外資台指期淨未平倉（口）
    fut_total_net_oi_contracts: float | None = None     # 三大法人合計（口）
    pc_oi_ratio_pct: float | None = None          # put/call 未平倉比（%）


# ---------------- 第一層：各維度 ----------------

def alert_margin_surge(margin_lots_series: list[float | None]) -> Verdict:
    """融資餘額五日變化率。看的是墊高的速度，不是餘額水位。"""
    v = [float(x) for x in margin_lots_series if x is not None]
    if len(v) < MARGIN_MIN_POINTS or v[-MARGIN_MIN_POINTS] == 0:
        return False, INSUFFICIENT
    chg = (v[-1] / v[-MARGIN_MIN_POINTS] - 1.0) * 100.0
    if chg > MARGIN_SURGE_PCT:
        return True, f"融資餘額五日 {chg:+.2f}% > {MARGIN_SURGE_PCT}%"
    return False, f"融資餘額五日 {chg:+.2f}%"


def alert_foreign_futures(net_oi_contracts: list[float | None]) -> Verdict:
    """外資台指期淨未平倉的**方向翻轉**。

    一路淨空不算警示 —— 那是狀態不是事件。翻向才是。
    """
    v = [float(x) for x in net_oi_contracts if x is not None]
    if len(v) < 2:
        return False, INSUFFICIENT
    prev, last = v[-2], v[-1]
    if prev > 0 >= last:
        return True, f"外資台指期由淨多 {prev:+,.0f} 翻為淨空 {last:+,.0f} 口"
    if prev < 0 <= last:
        return True, f"外資台指期由淨空 {prev:+,.0f} 翻為淨多 {last:+,.0f} 口"
    side = "淨多" if last > 0 else "淨空" if last < 0 else "持平"
    return False, f"外資台指期維持{side} {last:+,.0f} 口"


def alert_pc_oi_ratio(ratio_pct: float | None) -> Verdict:
    """put/call 未平倉比。兩端都算警示 —— 極端偏向哪一邊都是不尋常。"""
    if ratio_pct is None:
        return False, INSUFFICIENT
    if ratio_pct > PC_OI_HIGH:
        return True, f"put/call 未平倉比 {ratio_pct:.1f}% > {PC_OI_HIGH:.0f}%"
    if ratio_pct < PC_OI_LOW:
        return True, f"put/call 未平倉比 {ratio_pct:.1f}% < {PC_OI_LOW:.0f}%"
    return False, f"put/call 未平倉比 {ratio_pct:.1f}%"


# ---------------- 第二層：合成 ----------------

@dataclass(frozen=True, slots=True)
class ChipScore:
    score: float | None
    valid: int
    alert_keys: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)


def score_chips(
    snap: ChipSnapshot,
    margin_series: list[float | None],
    fut_series: list[float | None],
) -> ChipScore:
    """未警示比例 × 100，跟 scoring_macro.score_layer 同一個算法。

    算不出來的維度**不計入分母** —— 這樣「三個維度中兩個警示」與「一個維度
    中一個警示」不會被壓成同一個數字。
    """
    verdicts = {
        "margin": alert_margin_surge(margin_series),
        "fut_foreign": alert_foreign_futures(fut_series),
        "pc_oi": alert_pc_oi_ratio(snap.pc_oi_ratio_pct),
    }
    usable = {k: v for k, v in verdicts.items() if v[1] != INSUFFICIENT}
    if not usable:
        return ChipScore(score=None, valid=0)
    hit = [k for k, (alert, _) in usable.items() if alert]
    return ChipScore(
        score=100.0 * (1.0 - len(hit) / len(usable)),
        valid=len(usable),
        alert_keys=hit,
        reasons={k: why for k, (_, why) in usable.items()},
    )


# ---------------- §8.2：同一個指標，換個標的就不能同樣解讀 ----------------

@dataclass(frozen=True, slots=True)
class ChipReading:
    applies: bool
    caveat: str


_ETF_CAVEAT = (
    "三大法人對 ETF 的買賣多半是套利與申贖，跟指數的籌碼面不同義 —— "
    "同一個數字換個標的就不能同樣解讀"
)
_INDEX_CAVEAT = "市場整體的籌碼水位，對應的是整個市場而不是單一標的"


def reading(symbol: str) -> ChipReading:
    """這個標的能不能套市場級籌碼面，以及要附上什麼但書。"""
    if not _is_tw(symbol):
        return ChipReading(
            applies=False,
            caveat=(
                f"{INSUFFICIENT} —— 三大法人、融資融券、台指期都是台股的資料，"
                f"套到美股標的上沒有意義"
            ),
        )
    if _is_index(symbol):
        return ChipReading(applies=True, caveat=_INDEX_CAVEAT)
    return ChipReading(applies=True, caveat=_ETF_CAVEAT)


def _is_tw(symbol: str) -> bool:
    """domain 層不 import config（那是外層）—— 判斷寫在這裡，規則一樣。"""
    return symbol.endswith((".TW", ".TWO")) or symbol == "^TWII"


def _is_index(symbol: str) -> bool:
    return symbol.startswith("^")
