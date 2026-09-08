"""EIA 原油庫存（作者 2026-09-07 要求保留：戰爭期間這是重要指標）。

**走免金鑰的每週石油狀況報告（WPSR）Table 1**，不是需要金鑰的 EIA API v2。
FRED 上只有 1930 年代的 NBER 舊序列，沒有現行的週度庫存，所以繞回 EIA 自己
的公開 CSV。

這支 CSV 的形狀跟其他來源都不一樣：它不是一條時間序列，是**一張比較表**。
一列裡同時有本週、上週、週變化、去年同期、年變化。所以解析出來的是一個
「快照」而不是序列，顯示層要知道這件事。

單位是**百萬桶**（million barrels）。系統裡第五種單位。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from barometer.datasources import eia_src
from barometer.datasources.base import FetchError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture() -> str:
    return (FIXTURES / "eia_wpsr_table1.csv").read_text(encoding="utf-8")


def test_parses_the_crude_oil_row():
    s = eia_src.parse_wpsr(_fixture())
    assert s.stocks_mbbl == pytest.approx(711.064)
    assert s.prior_week_mbbl == pytest.approx(718.636)
    assert s.wow_change_mbbl == pytest.approx(-7.572)
    assert s.wow_change_pct == pytest.approx(-1.1)


def test_parses_the_year_ago_comparison():
    s = eia_src.parse_wpsr(_fixture())
    assert s.year_ago_mbbl == pytest.approx(825.417)
    assert s.yoy_change_pct == pytest.approx(-13.9)


def test_reads_the_data_date_from_the_header():
    """資料日期在表頭欄位名裡（`8/28/26`），不是在任何一格資料裡。"""
    s = eia_src.parse_wpsr(_fixture())
    assert s.data_date == dt.date(2026, 8, 28)


def test_unit_is_million_barrels():
    """系統裡第五種單位。股、張、口、%，現在再加百萬桶。"""
    assert eia_src.parse_wpsr(_fixture()).unit == "百萬桶"


def test_it_is_a_snapshot_not_a_series():
    """WPSR 給的是一張比較表，不是時間序列。

    硬把它攤成序列會產生一條只有三個點、而且日期不連續的假序列。
    所以回的是一個明確的快照型別。
    """
    s = eia_src.parse_wpsr(_fixture())
    assert not hasattr(s, "series")
    assert s.is_snapshot is True


def test_missing_crude_row_is_an_error_not_a_zero():
    with pytest.raises(FetchError):
        eia_src.parse_wpsr("STUB_1,8/28/26\nGasoline,200.0\n")


def test_empty_response_is_an_error():
    with pytest.raises(FetchError):
        eia_src.parse_wpsr("")


def test_as_series_gives_two_dated_points_for_display():
    """顯示層還是需要「畫得出來的東西」。

    只給上週與本週兩個點，日期都是真的，**不補中間**。
    """
    s = eia_src.parse_wpsr(_fixture())
    pts = s.as_series()
    assert len(pts) == 2
    assert pts[0][0] == "2026-08-21" and pts[1][0] == "2026-08-28"
    assert pts[1][1] == pytest.approx(711.064)
