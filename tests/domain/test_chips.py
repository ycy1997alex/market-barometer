"""市場級籌碼面（ToDo §8.2、§9 Day 26 第 2 項）。

§8.2 的那句話是這支測試的核心：

  > **籌碼面在 ETF 上要換個讀法**：三大法人對 ETF 的買賣多半是套利與申贖，
  > 跟個股的意義不同。

所以 `reading()` 不是裝飾用的說明字串 —— 它是這個模組唯一防止「同一個數字
被套到不該套的標的上」的東西，要寫成測試。

單位在這裡最容易出事：T86 買賣超是**股**、融資融券是**張**、台指期未平倉是
**口**。三種單位同時出現在一個 snapshot 裡，所以每個欄位名都自己帶單位。
"""
from __future__ import annotations

import pytest

from barometer.domain import chips


# ---------------- 融資餘額 ----------------

def test_margin_surge_is_an_alert():
    """融資餘額五日快速墊高 → 散戶槓桿升高，記警示。"""
    series = [8_000_000, 8_100_000, 8_300_000, 8_600_000, 8_900_000, 9_200_000]
    alert, why = chips.alert_margin_surge(series)
    assert alert is True
    assert "%" in why


def test_margin_flat_is_not_an_alert():
    series = [8_000_000] * 6
    alert, _ = chips.alert_margin_surge(series)
    assert alert is False


def test_margin_needs_six_points():
    alert, why = chips.alert_margin_surge([8_000_000, 8_100_000])
    assert alert is False
    assert why == chips.INSUFFICIENT


# ---------------- 台指期未平倉 ----------------

def test_foreign_futures_flipping_to_net_short_is_an_alert():
    """外資淨未平倉由多翻空 —— 翻向本身是事件，不是水位高低。"""
    alert, why = chips.alert_foreign_futures([12_000, 8_000, 3_000, -82_389])
    assert alert is True
    assert "翻" in why


def test_foreign_futures_staying_net_short_is_not_a_new_alert():
    """一直是淨空不算「翻空」—— 不然它會天天亮燈，燈就沒有意義了。

    這跟 §10 央行重貼現率那個坑是同一種錯：拿「值」去比，會永遠亮燈。
    """
    alert, _ = chips.alert_foreign_futures([-70_000, -75_000, -80_000, -82_389])
    assert alert is False


def test_foreign_futures_needs_two_points():
    alert, why = chips.alert_foreign_futures([-82_389])
    assert alert is False
    assert why == chips.INSUFFICIENT


# ---------------- put / call ratio ----------------

def test_pc_oi_ratio_extremes_alert_at_both_ends():
    high_alert, _ = chips.alert_pc_oi_ratio(190.0)
    low_alert, _ = chips.alert_pc_oi_ratio(45.0)
    assert high_alert is True
    assert low_alert is True


def test_pc_oi_ratio_near_parity_is_not_an_alert():
    alert, why = chips.alert_pc_oi_ratio(99.8)
    assert alert is False
    assert "99.8" in why


def test_pc_oi_ratio_missing_is_insufficient_not_zero():
    alert, why = chips.alert_pc_oi_ratio(None)
    assert alert is False
    assert why == chips.INSUFFICIENT


# ---------------- §8.2 讀法：指數 vs ETF ----------------

def test_index_reading_is_the_plain_one():
    note = chips.reading("^TWII")
    assert note.applies is True
    assert "套利" not in note.caveat


def test_etf_reading_must_carry_the_arbitrage_caveat():
    note = chips.reading("0050.TW")
    assert note.applies is True
    assert "套利" in note.caveat and "申贖" in note.caveat


def test_us_symbols_have_no_taiwan_chip_data():
    """三大法人、融資融券、台指期都是台股的東西，套到美股標的上沒有意義。"""
    note = chips.reading("SPY")
    assert note.applies is False
    assert chips.INSUFFICIENT in note.caveat


# ---------------- snapshot 的單位紀律 ----------------

def test_snapshot_field_names_carry_their_unit():
    snap = chips.ChipSnapshot(
        foreign_net_shares=1_234_000,
        margin_lots=8_919_251,
        fut_foreign_net_oi_contracts=-82_389,
        pc_oi_ratio_pct=99.8,
    )
    names = [f for f in snap.__dataclass_fields__ if f != "date"]
    assert all(
        n.endswith(("_shares", "_lots", "_contracts", "_pct")) for n in names
    ), names


def test_score_chips_counts_only_the_dimensions_it_could_compute():
    snap = chips.ChipSnapshot(
        margin_lots=8_919_251,
        fut_foreign_net_oi_contracts=-82_389,
        pc_oi_ratio_pct=99.8,
    )
    layer = chips.score_chips(
        snap,
        margin_series=[8_000_000] * 6,
        fut_series=[-70_000, -75_000, -80_000, -82_389],
    )
    assert layer.valid == 3
    assert layer.score == pytest.approx(100.0)


def test_score_chips_is_none_when_nothing_is_available():
    layer = chips.score_chips(chips.ChipSnapshot(), margin_series=[], fut_series=[])
    assert layer.score is None
    assert layer.valid == 0
