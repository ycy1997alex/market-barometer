"""第八批 8-2：美股市場廣度（11 檔 SPDR 類股 ETF 站上 200MA 的比例）。

⚠️ 這是 **proxy，不是真的 advance/decline** —— 文件、頁面、判定文字都要照實說。
⚠️ 缺一檔時比例用剩下的算，而且**分母要標出來**：7/10 與 7/11 不是同一件事。
"""
from __future__ import annotations

from barometer.domain import breadth
from barometer.domain import macro_spec as spec
from barometer.domain import scoring_macro as sm


def _series(values: list[float]) -> list[tuple[str, float]]:
    return [(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", v) for i, v in enumerate(values)]


def _rising(n: int) -> list[float]:
    return [100.0 + i for i in range(n)]


def _falling(n: int) -> list[float]:
    return [300.0 - i for i in range(n)]


def test_all_above_their_average_is_one_hundred_percent():
    closes = {f"XL{i}": _series(_rising(205)) for i in range(4)}
    ratio, cover = breadth.breadth_series(closes, window=200, days=2)
    assert [value for _, value in ratio] == [100.0, 100.0]
    assert [value for _, value in cover] == [4.0, 4.0]


def test_ratio_uses_only_the_symbols_that_have_a_full_window():
    closes = {"UP1": _series(_rising(205)), "UP2": _series(_rising(205)),
              "DOWN": _series(_falling(205)), "SHORT": _series(_rising(50))}
    ratio, cover = breadth.breadth_series(closes, window=200, days=1)
    # SHORT 沒有 200 根，不進分子也不進分母
    assert ratio[-1][1] == 200.0 / 3
    assert cover[-1][1] == 3.0


def test_a_day_nobody_can_be_measured_is_dropped_not_zero():
    closes = {"SHORT": _series(_rising(50))}
    ratio, cover = breadth.breadth_series(closes, window=200, days=3)
    assert ratio == [] and cover == []


def test_dates_come_from_the_symbols_and_stay_sorted():
    closes = {"A": _series(_rising(203)), "B": _series(_rising(203))}
    ratio, _ = breadth.breadth_series(closes, window=200, days=3)
    labels = [label for label, _ in ratio]
    assert labels == sorted(labels) and len(labels) == 3


# ---------------- 判定 ----------------

def test_weak_breadth_is_an_alert_and_says_it_is_a_proxy():
    hit, text = sm.alert_breadth_us(_series([70.0, 60.0, 40.0]))
    assert hit
    assert "代理指標" in text and "門檻" in text


def test_broad_participation_is_not_an_alert():
    hit, text = sm.alert_breadth_us(_series([70.0, 75.0, 80.0]))
    assert not hit
    assert "代理指標" in text


def test_no_data_is_insufficient():
    assert sm.alert_breadth_us([])[1] == sm.INSUFFICIENT


# ---------------- 接線 ----------------

def test_breadth_is_scored_and_its_denominator_is_shown_separately():
    assert spec.BY_KEY["breadth_us"].scored
    assert "代理" in spec.BY_KEY["breadth_us"].name or "代理" in spec.BY_KEY["breadth_us"].note
    cover = spec.BY_KEY["breadth_us_cover"]
    assert cover.layer == "observe"        # 分母是給人看的，不是另一個分數
    assert "breadth_us" in sm.ALERT_FUNCS


# ---------------- 分母的凍結例外 ----------------

def test_a_constant_denominator_is_healthy_not_frozen():
    """11 檔每天都算得出來 → 分母天天是 11。那是好的那一種情況，不是死掉的來源。

    ⚠️ 例外只給這一個 key，而且只免掉「連續六筆同值」那一條；
    日期過期（OVERDUE）照樣會被擋下來。
    """
    import datetime as dt

    from barometer.domain import freshness

    today = dt.date(2026, 9, 22)
    flat = [11.0] * 6
    assert freshness.assess_source_series(
        "每日", today, today, flat, key="breadth_us_cover").usable
    assert not freshness.assess_source_series(
        "每日", today, today, flat, key="vix").usable
    stale = freshness.assess_source_series(
        "每日", dt.date(2026, 8, 1), today, flat, key="breadth_us_cover")
    assert not stale.usable
