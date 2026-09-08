"""期交所：台指期未平倉與 put/call ratio（ToDo §9 Day 26 第 2 項、§8.2）。

驗收句同上一支：「單位標對，且非交易日拿到空 CSV 時當『這天還沒有』而不是 0」。

期交所的「沒資料」跟 TWSE 又不一樣 —— 它回**只有表頭、沒有任何列**的 CSV。
兩家的空回應長得完全不同，處置卻相同：一律當「這天還沒有」。

單位提醒：期貨的未平倉是**口**，不是張也不是股。整套系統裡第三種單位，
所以 dataclass 的欄位名一律帶 `_lots_oi`／`_contracts` 字尾把它釘死。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from barometer.datasources import taifex_src

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------- put / call ratio ----------------

def test_parses_pc_ratio_rows_newest_first():
    rows = taifex_src.parse_pc_ratio(
        _fixture("taifex_pcratio_20260901_0904.csv")
    )
    assert len(rows) == 4
    latest = rows[0]
    assert latest["date"] == dt.date(2026, 9, 4)
    assert latest["put_volume"] == pytest.approx(356_219)
    assert latest["call_volume"] == pytest.approx(361_817)
    assert latest["pc_volume_ratio_pct"] == pytest.approx(98.45)
    assert latest["put_oi"] == pytest.approx(48_162)
    assert latest["call_oi"] == pytest.approx(48_258)
    assert latest["pc_oi_ratio_pct"] == pytest.approx(99.80)


def test_pc_ratio_header_only_is_not_published_yet():
    """期交所的空回應是「只有表頭」—— 不是 ratio = 0。"""
    with pytest.raises(taifex_src.NotPublishedYet):
        taifex_src.parse_pc_ratio(_fixture("taifex_pcratio_empty.csv"))


# ---------------- 三大法人台指期未平倉 ----------------

def test_parses_fut_oi_by_investor_type():
    r = taifex_src.parse_fut_oi(_fixture("taifex_futcontracts_20260904.csv"))

    assert r.date == dt.date(2026, 9, 4)
    assert r.product == "臺股期貨"
    assert set(r.by_investor) == {"自營商", "投信", "外資及陸資"}

    foreign = r.by_investor["外資及陸資"]
    # 多空未平倉口數淨額 = -82,389 口（淨空）
    assert foreign["net_oi_contracts"] == pytest.approx(-82_389)
    assert foreign["long_oi_contracts"] == pytest.approx(8_153)
    assert foreign["short_oi_contracts"] == pytest.approx(90_542)

    # 投信是淨多
    assert r.by_investor["投信"]["net_oi_contracts"] == pytest.approx(76_174)


def test_fut_oi_total_net_is_the_sum_of_three_investor_types():
    r = taifex_src.parse_fut_oi(_fixture("taifex_futcontracts_20260904.csv"))
    assert r.total_net_oi_contracts == pytest.approx(-697 + 76_174 - 82_389)


def test_fut_oi_header_only_is_not_published_yet():
    with pytest.raises(taifex_src.NotPublishedYet):
        taifex_src.parse_fut_oi(
            "日期,商品名稱,身份別,多方交易口數\n"
        )


def test_fut_oi_unit_is_contracts_not_lots_or_shares():
    """單位是口。整套系統有股／張／口三種單位，欄位名要自己說清楚。"""
    r = taifex_src.parse_fut_oi(_fixture("taifex_futcontracts_20260904.csv"))
    assert r.unit == "口"
    for stats in r.by_investor.values():
        assert all(k.endswith("_contracts") for k in stats)
