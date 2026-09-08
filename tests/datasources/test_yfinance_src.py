"""§4.3 缺值處理 + §1 第 10 條 單位。

Day 24 第 6 項驗收：「0050 那根 NaN 沒有讓整批中止，該格標了 stale」。
datasources 層測試用錄下來的回應，不打真的 API（§3.3）。
這裡直接餵 DataFrame —— yfinance 回的就是 DataFrame，中間沒有別的東西。
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from barometer.datasources.yfinance_src import bars_from_frame
from barometer.datasources.base import FetchError

AS_OF = dt.datetime(2026, 9, 6, 18, 0)


def frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("date"))
    return df


class TestNaNHandling:
    def test_close_nan_carries_forward_previous_and_marks_stale(self):
        """0050.TW 實測：Open/High/Low/Volume 都在，就 Close 缺（§10）。"""
        df = frame([
            {"date": "2026-09-03", "Open": 105.0, "High": 106.0, "Low": 104.0,
             "Close": 105.5, "Volume": 12_000_000},
            {"date": "2026-09-04", "Open": 106.0, "High": 107.0, "Low": 105.0,
             "Close": float("nan"), "Volume": 11_000_000},
        ])
        bars = bars_from_frame("0050.TW", df, as_of=AS_OF)

        assert len(bars) == 2, "缺值不得讓整批中止"
        assert bars[1].close == pytest.approx(105.5), "保留前一日值"
        assert bars[1].stale is True, "該格要標 stale"
        assert bars[0].stale is False

    def test_all_nan_row_is_marked_stale_not_dropped(self):
        """auto_adjust=True 時整列 OHLC 全變 NaN —— 那一列仍要留下痕跡。"""
        df = frame([
            {"date": "2026-09-03", "Open": 105.0, "High": 106.0, "Low": 104.0,
             "Close": 105.5, "Volume": 12_000_000},
            {"date": "2026-09-04", "Open": float("nan"), "High": float("nan"),
             "Low": float("nan"), "Close": float("nan"), "Volume": float("nan")},
        ])
        bars = bars_from_frame("0050.TW", df, as_of=AS_OF)
        assert len(bars) == 2
        assert bars[1].stale is True
        assert bars[1].close == pytest.approx(105.5)

    def test_leading_nan_has_nothing_to_carry_forward(self):
        """第一根就缺 → 沒有前一日可以保留，close 是 None 而不是瞎猜。"""
        df = frame([
            {"date": "2026-09-03", "Open": float("nan"), "High": float("nan"),
             "Low": float("nan"), "Close": float("nan"), "Volume": float("nan")},
        ])
        bars = bars_from_frame("0050.TW", df, as_of=AS_OF)
        assert bars[0].close is None
        assert bars[0].stale is True

    def test_clean_frame_has_no_stale_rows(self):
        df = frame([
            {"date": "2026-09-03", "Open": 105.0, "High": 106.0, "Low": 104.0,
             "Close": 105.5, "Volume": 12_000_000},
            {"date": "2026-09-04", "Open": 106.0, "High": 107.0, "Low": 105.0,
             "Close": 106.2, "Volume": 11_000_000},
        ])
        bars = bars_from_frame("0050.TW", df, as_of=AS_OF)
        assert not any(b.stale for b in bars)
        assert bars[-1].close == pytest.approx(106.2)


class TestUnits:
    def test_volume_is_stored_in_shares_for_tw(self):
        """§1 第 10 條：內部一律存股，不存張。"""
        df = frame([{"date": "2026-09-04", "Open": 106.0, "High": 107.0,
                     "Low": 105.0, "Close": 106.2, "Volume": 11_000_000}])
        bars = bars_from_frame("0050.TW", df, as_of=AS_OF)
        assert bars[0].volume_shares == pytest.approx(11_000_000)

    def test_display_layer_converts_tw_to_lots(self):
        from barometer.config import display_volume

        value, unit = display_volume("0050.TW", 11_000_000)
        assert value == pytest.approx(11_000)
        assert unit == "張"

    def test_display_layer_keeps_us_in_shares(self):
        from barometer.config import display_volume

        value, unit = display_volume("SPY", 11_000_000)
        assert value == pytest.approx(11_000_000)
        assert unit == "股"

    def test_index_symbol_counts_as_tw(self):
        from barometer.config import display_volume

        assert display_volume("^TWII", 1000)[1] == "張"


class TestEmptyFrame:
    def test_empty_frame_raises_fetch_error(self):
        """空 DataFrame 是抓取失敗，不是「這天成交量 0」（§10 T86 那一條的同理）。"""
        with pytest.raises(FetchError):
            bars_from_frame("0050.TW", pd.DataFrame(), as_of=AS_OF)

    def test_missing_close_column_raises(self):
        df = frame([{"date": "2026-09-04", "Open": 1.0, "High": 1.0, "Low": 1.0,
                     "Volume": 1.0}])
        with pytest.raises(FetchError):
            bars_from_frame("0050.TW", df, as_of=AS_OF)


class TestSourceTag:
    def test_source_is_recorded(self):
        df = frame([{"date": "2026-09-04", "Open": 106.0, "High": 107.0,
                     "Low": 105.0, "Close": 106.2, "Volume": 11_000_000}])
        bars = bars_from_frame("0050.TW", df, as_of=AS_OF)
        assert bars[0].source == "yfinance"
