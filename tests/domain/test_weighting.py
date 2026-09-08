"""§8.1 五日加權：D-4 10% / D-3 15% / D-2 20% / D-1 25% / D-0 30%。

驗收（Day 26 第 3 項）：「權重加總 = 1.0 的測試」。
domain 層純函式，測試不得碰網路或檔案（§3.3）。
"""
import pytest

from barometer.domain.weighting import (
    FIVE_DAY_WEIGHTS,
    simple_average,
    weighted_average,
    smooth,
)


def test_weights_sum_to_one():
    assert sum(FIVE_DAY_WEIGHTS) == pytest.approx(1.0)


def test_weights_are_the_documented_ladder():
    # 順序是由舊到新：D-4 … D-0
    assert FIVE_DAY_WEIGHTS == (0.10, 0.15, 0.20, 0.25, 0.30)


def test_weighted_average_favours_the_latest_day():
    # 只有最後一天是 100，其餘 0 → 加權平均恰好等於最後一天的權重 ×100
    assert weighted_average([0, 0, 0, 0, 100]) == pytest.approx(30.0)
    # 反過來，只有最舊一天是 100
    assert weighted_average([100, 0, 0, 0, 0]) == pytest.approx(10.0)


def test_weighted_and_simple_agree_when_flat():
    flat = [62, 62, 62, 62, 62]
    assert weighted_average(flat) == pytest.approx(62.0)
    assert simple_average(flat) == pytest.approx(62.0)


def test_weighted_average_rejects_wrong_length():
    # 五日加權就是五個點；長度不對是呼叫端的錯，不要默默補零
    with pytest.raises(ValueError):
        weighted_average([1, 2, 3])


def test_averages_ignore_none_but_report_insufficient():
    # 五個交易日裡有洞（休市、stale）→ 不硬算，回傳 None
    assert weighted_average([62, None, 64, 65, 66]) is None
    assert simple_average([62, None, 64, 65, 66]) is None


def test_smooth_returns_same_length_and_tracks_level():
    series = [50, 60, 70, 80, 90]
    out = smooth(series, window=3)
    assert len(out) == len(series)
    # 前兩點窗口不足 → None，不要用半個窗口硬算
    assert out[0] is None and out[1] is None
    assert out[2] == pytest.approx(60.0)
    assert out[4] == pytest.approx(80.0)
