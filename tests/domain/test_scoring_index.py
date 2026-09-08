"""大盤與 ETF 評分（ToDo §8.2、§9 Day 26 第 3 項）。

驗收句有兩段，這裡只測得了純函式那一段（真實五日資料那段在 tools/ 那邊跑）：

    「權重加總 = 1.0 的測試」→ 已由 tests/domain/test_weighting.py 守著
    「三組對照差值有數字」   → tools/compare_groups.py

這支測的是評分本身的形狀，重點有四個：

1. **跟 scoring_macro 同一個結構** —— 第一層各維度各自判警示、第二層算未警示
   比例。不另外發明一套，兩層總經與大盤才比得起來。
2. **兩端都算警示**：RSI 70 以上與 30 以下都是警示。分數不是「越高越好」的
   方向盤，是「有幾個維度落在不尋常的地方」的量測。
3. **輸出不得含建議欄位**（§2.1）—— 這條寫成測試，不寫成註解。
4. **ETF 的籌碼面要換個讀法**（§8.2）—— 不是不給，是給的時候要標明它跟指數
   不同義，三大法人對 ETF 的買賣多半是套利與申贖。
"""
from __future__ import annotations

import math

import pytest

from barometer.domain import scoring_index as si


def _rising(n: int, start: float = 100.0, step: float = 0.5) -> list[float]:
    return [start + step * i for i in range(n)]


def _falling(n: int, start: float = 200.0, step: float = 0.5) -> list[float]:
    return [start - step * i for i in range(n)]


def _flat(n: int, value: float = 100.0) -> list[float]:
    return [value] * n


# ---------------- 第一層：各維度 ----------------

def test_ma_stack_multi_head_is_not_an_alert():
    ok, why = si.alert_ma_stack(_rising(90))
    assert ok is False
    assert "多頭排列" in why


def test_ma_stack_bear_arrangement_is_an_alert():
    alert, why = si.alert_ma_stack(_falling(90))
    assert alert is True
    assert "空頭排列" in why


def test_ma_stack_needs_60_bars():
    alert, why = si.alert_ma_stack(_rising(30))
    assert alert is False
    assert why == si.INSUFFICIENT


def test_rsi_alerts_at_both_ends():
    """兩端都是警示 —— 過熱與過冷都算「落在不尋常的地方」。"""
    hot_alert, hot_why = si.alert_rsi(_rising(60))
    cold_alert, cold_why = si.alert_rsi(_falling(60))
    assert hot_alert is True and "70" in hot_why
    assert cold_alert is True and "30" in cold_why


def test_rsi_mid_range_is_not_an_alert():
    # 漲跌交錯 → RSI 貼近 50
    closes = [100 + (1 if i % 2 else -1) for i in range(60)]
    alert, _ = si.alert_rsi(closes)
    assert alert is False


def test_bollinger_outside_band_is_an_alert():
    # 走平一段之後突然跳一根 → 一定衝出上軌
    closes = _flat(40) + [130.0]
    alert, why = si.alert_bollinger(closes)
    assert alert is True
    assert "帶外" in why


def test_bollinger_inside_band_is_not_an_alert():
    closes = [100 + math.sin(i / 3) for i in range(60)]
    alert, _ = si.alert_bollinger(closes)
    assert alert is False


def test_volatility_alert_is_relative_not_an_absolute_number():
    """波動度門檻刻意是「近期 vs 長期」的倍數，不是寫死的 30%。

    台股與美股的常態波動度本來就不同，寫死一個絕對值等於偷偷假設兩個市場
    一樣。用自己的長期水準當分母，這把尺才對兩邊都成立。
    """
    # 波動度基線要一整年才算得出來（si.LOOKBACK_FULL）
    calm = _flat(si.LOOKBACK_FULL, 100.0)
    # 前面平靜、最後 20 根劇烈震盪
    spiky = calm + [100 + (8 if i % 2 else -8) for i in range(si.VOL_RECENT)]
    alert, why = si.alert_volatility(spiky)
    assert alert is True
    assert "倍" in why


def test_volatility_needs_a_long_baseline():
    alert, why = si.alert_volatility(_rising(30))
    assert alert is False
    assert why == si.INSUFFICIENT


def test_drawdown_alert_past_threshold():
    closes = _rising(250) + [_rising(250)[-1] * 0.85]
    alert, why = si.alert_drawdown(closes)
    assert alert is True
    assert "%" in why


def test_drawdown_at_the_high_is_not_an_alert():
    alert, why = si.alert_drawdown(_rising(250))
    assert alert is False


# ---------------- 第二層：合成 ----------------

def test_score_is_percentage_of_dimensions_not_alerting():
    score = si.score_index("^TWII", _rising(300))
    assert score.score is not None
    assert 0.0 <= score.score <= 100.0
    # 五個技術面維度都算得出來
    assert score.valid == len(si.TECHNICAL)


def test_score_is_none_when_nothing_can_be_computed():
    score = si.score_index("^TWII", [100.0, 101.0])
    assert score.score is None
    assert score.valid == 0


def test_score_output_carries_no_advice_field():
    """§2.1 紅線：這裡不得出現任何把分數翻成動作的欄位。"""
    payload = si.score_index("0050.TW", _rising(300)).to_dict()
    banned = {
        "advice", "action", "signal", "suggestion", "recommendation",
        "建議", "操作", "短線建議", "中線建議", "長線建議",
    }
    assert not (banned & set(payload)), payload.keys()


def test_score_dict_has_subscores_for_every_dimension():
    payload = si.score_index("^GSPC", _rising(300)).to_dict()
    assert set(payload["subscores"]) == set(si.TECHNICAL)
    assert all(v in (0.0, 1.0) for v in payload["subscores"].values())


# ---------------- ETF 特有 ----------------

def test_tracking_error_is_computable_and_signed():
    index = _rising(120, 100.0, 1.0)
    etf = _rising(120, 50.0, 0.52)  # 追得比指數快一點
    te = si.tracking_error(etf, index)
    assert te is not None
    assert te > 0


def test_tracking_error_needs_equal_length_series():
    assert si.tracking_error(_rising(50), _rising(60)) is None


def test_etf_only_metrics_report_insufficient_rather_than_guessing():
    """內扣費用、折溢價、成分股調整這三項現有資料算不出來。

    **回「資料不足」，不准硬掰一個數字。** 這跟 SPCX 中長期評分的處置一致
    （§10）—— 算不出來就說算不出來，是這套東西誠實度的一部分。
    """
    gaps = si.etf_data_gaps("0050.TW")
    assert set(gaps) >= {"內扣費用", "折溢價", "成分股調整"}
    assert all(v == si.INSUFFICIENT for v in gaps.values())


def test_index_symbols_have_no_etf_gaps():
    assert si.etf_data_gaps("^TWII") == {}


# ---------------- 視窗長度：同一把尺在兩個市場要量到同樣多東西 ----------------

def test_taiwan_year_length_still_yields_all_five_dimensions():
    """台股一年只有 243~244 根，美股 252 根。

    把 52 週的視窗寫死成 250 根，台股就會**永遠**少算波動度與回撤兩個維度 ——
    分數還是算得出來（分母只有 3），看起來完全正常，但台股的分數與美股的分數
    量的根本不是同一組東西，兩邊放在同一頁上比就是錯的。

    這個 bug 是拿真實資料跑出來才看見的：^TWII 只有 3 個維度、^GSPC 有 5 個。
    """
    tw_year = _rising(243)   # 台股實際筆數
    us_year = _rising(252)   # 美股實際筆數
    assert si.score_index("^TWII", tw_year).valid == len(si.TECHNICAL)
    assert si.score_index("^GSPC", us_year).valid == len(si.TECHNICAL)


def test_short_window_degrades_and_says_so():
    """不足 52 週時降級成「這段序列以來」，而且**要在理由裡講出來**。

    跟 SPCX 的處置一致（§10）：「52 週高點回撤」退化成「上市以來高點」時
    必須標明降級，不能假裝它還是 52 週。
    """
    closes = _rising(si.LOOKBACK_MIN + 5)
    _, why = si.alert_drawdown(closes)
    assert "降級" in why
    _, vol_why = si.alert_volatility(closes)
    assert "降級" in vol_why


def test_full_window_does_not_claim_degradation():
    _, why = si.alert_drawdown(_rising(si.LOOKBACK_FULL + 10))
    assert "降級" not in why


def test_below_the_floor_is_still_insufficient():
    """SPCX 那種只有 59 根的，仍然是資料不足 —— 降級有底線，不是無限退讓。"""
    alert, why = si.alert_drawdown(_rising(59))
    assert alert is False
    assert why == si.INSUFFICIENT
    alert, why = si.alert_volatility(_rising(59))
    assert alert is False
    assert why == si.INSUFFICIENT
