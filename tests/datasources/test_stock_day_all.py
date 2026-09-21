"""Official latest listed close supplements Yahoo without claiming OTC coverage."""
from __future__ import annotations

import datetime as dt
import math

import pytest

from barometer.datasources import twse_src
from barometer.domain.ports import PriceBar
from barometer.pipeline import fetch_prices
from barometer.storage import csv_audit

AS_OF = dt.datetime(2026, 9, 20, 18)
FRIDAY = dt.date(2026, 9, 18)


def row(code="0050", close="109.85", date="1150918"):
    return {"Date": date, "Code": code, "Name": "fixture",
            "TradeVolume": "79,772,537", "OpeningPrice": "109.60",
            "HighestPrice": "109.95", "LowestPrice": "108.85",
            "ClosingPrice": close}


def yahoo(day=FRIDAY - dt.timedelta(days=1), close=108.05, stale=False):
    return PriceBar("0050.TW", day, close, close, close, close,
                    1_000_000, "yfinance", AS_OF, stale)


def test_parse_official_roc_date_price_and_actual_source():
    prices = twse_src.parse_stock_day_all([row()], as_of=AS_OF)
    bar = prices["0050.TW"]
    assert bar.date == FRIDAY
    assert bar.close == pytest.approx(109.85)
    assert bar.volume_shares == 79_772_537
    assert bar.source == "twse_stock_day_all"
    assert bar.as_of == AS_OF


def test_missing_yahoo_close_is_supplemented_and_matches_shioaji():
    official = twse_src.parse_stock_day_all([row()], as_of=AS_OF)
    bars, status = twse_src.supplement_latest_close("0050.TW", [yahoo()], official)
    assert status == "supplemented"
    assert bars[-1].date == FRIDAY
    assert bars[-1].close - 109.85 == pytest.approx(0.0, abs=0.005)


def test_stale_or_nan_last_yahoo_row_does_not_count_as_fresh():
    official = twse_src.parse_stock_day_all([row()], as_of=AS_OF)
    for last in (yahoo(FRIDAY, close=108.05, stale=True),
                 yahoo(FRIDAY, close=math.nan)):
        bars, status = twse_src.supplement_latest_close("0050.TW", [last], official)
        assert status == "supplemented"
        assert bars[-1].close == pytest.approx(109.85)
        assert bars[-1].source == "twse_stock_day_all"


def test_official_nan_is_not_accepted_as_fresh():
    official = twse_src.parse_stock_day_all([row(close="NaN")], as_of=AS_OF)
    bars, status = twse_src.supplement_latest_close("0050.TW", [yahoo()], official)
    assert status == "unavailable"
    assert bars == [yahoo()]


def test_otc_is_explicitly_uncovered_and_yahoo_current_is_preserved():
    bars, status = twse_src.supplement_latest_close(
        "8299.TWO", [yahoo()], twse_src.parse_stock_day_all([row()], as_of=AS_OF))
    assert status == "otc_uncovered"
    assert bars == [yahoo()]
    fresh = yahoo(FRIDAY, close=109.85)
    kept, status = twse_src.supplement_latest_close(
        "0050.TW", [fresh], twse_src.parse_stock_day_all([row()], as_of=AS_OF))
    assert status == "already_fresh"
    assert kept == [fresh]


def test_price_pipeline_uses_one_market_fetch_for_two_listed_symbols(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    requested = []
    official = twse_src.parse_stock_day_all(
        [row("0050", "109.85"), row("006208", "251.20")], as_of=AS_OF)
    monkeypatch.setattr(fetch_prices.twse_src, "fetch_stock_day_all",
                        lambda run_date: requested.append(run_date) or official)

    def yf(symbol, **kwargs):
        previous = yahoo()
        return [PriceBar(symbol, previous.date, previous.open, previous.high,
                         previous.low, previous.close, previous.volume_shares,
                         previous.source, previous.as_of)]

    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", yf)
    log = fetch_prices.run(["0050.TW", "006208.TW"], "test_stock_day_all",
                           run_date=FRIDAY)
    assert requested == [FRIDAY]
    assert log.counts.get("twse_supplemented") == 2
    assert csv_audit.read_current("0050.TW")[-1] == official["0050.TW"]
    assert csv_audit.read_current("006208.TW")[-1] == official["006208.TW"]


def test_pipeline_replaces_stale_latest_close_with_official(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    official = twse_src.parse_stock_day_all([row()], as_of=AS_OF)
    monkeypatch.setattr(fetch_prices.twse_src, "fetch_stock_day_all", lambda _: official)
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily",
                        lambda *a, **k: [yahoo(), yahoo(FRIDAY, 108.05, stale=True)])
    fetch_prices.run(["0050.TW"], "test_stock_day_all", run_date=FRIDAY)
    assert csv_audit.read_current("0050.TW")[-1].close == pytest.approx(109.85)
    assert csv_audit.read_current("0050.TW")[-1].source == "twse_stock_day_all"


def test_pipeline_rejects_synthetic_sunday_before_choosing_latest(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    official = twse_src.parse_stock_day_all([row()], as_of=AS_OF)
    monkeypatch.setattr(fetch_prices.twse_src, "fetch_stock_day_all", lambda _: official)
    sunday = yahoo(dt.date(2026, 9, 20), close=109.85)
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily",
                        lambda *a, **k: [yahoo(), sunday])
    log = fetch_prices.run(["0050.TW"], "test_stock_day_all",
                           run_date=dt.date(2026, 9, 20))
    saved = csv_audit.read_current("0050.TW")
    assert saved[-1].date == FRIDAY
    assert saved[-1].source == "twse_stock_day_all"
    assert not any(bar.date.weekday() == 6 for bar in saved)
    assert log.counts.get("invalid_sessions") == 1
