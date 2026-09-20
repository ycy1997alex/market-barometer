"""Acceptance tests for the pandas-free historical replay engine."""
from __future__ import annotations

import datetime as dt
import math

import pytest

from barometer.domain.backtest import BacktestParams, run_backtest
from barometer.domain.ports import PriceBar
from barometer.storage.backtest_cache import BacktestHistoryCache


def bars(opens, closes, symbol="0050.TW"):
    as_of = dt.datetime(2026, 1, 1)
    return [
        PriceBar(symbol, dt.date(2026, 1, 1) + dt.timedelta(days=i),
                 opening, max(opening, close), min(opening, close), close,
                 1000.0, "fixture", as_of)
        for i, (opening, close) in enumerate(zip(opens, closes))
    ]


def test_signal_sees_only_through_t_close_and_executes_at_next_open():
    history = bars([100, 111, 121, 131], [100, 110, 120, 130])
    seen = []

    def score(prefix):
        seen.append(tuple(bar.date for bar in prefix))
        return 70 if len(prefix) == 1 else -30

    result = run_backtest(history, BacktestParams(market="us"), score)
    assert seen == [(history[0].date,),
                    (history[0].date, history[1].date),
                    (history[0].date, history[1].date, history[2].date)]
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert (trade.entry_date, trade.entry_price) == ("2026-01-02", 111)
    assert (trade.exit_date, trade.exit_price) == ("2026-01-03", 121)
    assert result.equity[-1] == pytest.approx(121 / 111)


@pytest.mark.parametrize("market,expected", [
    ("tw", (1 - 0.001425 - 0.003) / (1 + 0.001425)),
    ("us", 1.0),
])
def test_market_costs_apply_to_each_side(market, expected):
    history = bars([100] * 4, [100] * 4)
    result = run_backtest(history, BacktestParams(market=market),
                          lambda prefix: 70 if len(prefix) == 1 else -30)
    assert result.equity[-1] == pytest.approx(expected)
    assert result.trades[0].ret_pct == pytest.approx((expected - 1) * 100)


def test_terminal_nav_matches_closed_trade_compounding():
    history = bars([100, 110, 120, 130, 140, 150, 160],
                   [100, 112, 118, 132, 138, 155, 165])
    signals = {1: 70, 2: -30, 3: 70, 4: -30, 5: 70, 6: 70}
    result = run_backtest(history, BacktestParams(market="tw"),
                          lambda prefix: signals[len(prefix)])
    assert len(result.trades) == 3
    compounded = math.prod(1 + trade.ret_pct / 100 for trade in result.trades)
    assert abs(result.equity[-1] - compounded) / compounded < 0.005
    assert all(trade.exit_date for trade in result.trades)


def test_invalid_thresholds_and_missing_prices_are_rejected():
    history = bars([100] * 3, [100] * 3)
    with pytest.raises(ValueError, match="threshold"):
        run_backtest(history, BacktestParams(buy_threshold=10, exit_threshold=10),
                     lambda _: 70)
    missing = list(history)
    missing[1] = PriceBar("0050.TW", missing[1].date, None, 100, 100, 100,
                          1000, "fixture", missing[1].as_of)
    with pytest.raises(ValueError, match="open"):
        run_backtest(missing, BacktestParams(), lambda _: 70)


def test_history_is_fetched_once_into_separate_cache_then_replayed_offline(tmp_path):
    cache = BacktestHistoryCache(tmp_path)
    history = bars([100, 101, 102], [100, 101, 102])
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return history

    assert cache.prepare("0050.TW", fetch) == history
    assert calls == ["0050.TW"]
    assert (tmp_path / "backtest_history" / "0050.TW.csv").exists()
    assert cache.prepare("0050.TW", lambda _: pytest.fail("network called")) == history
    assert cache.load("0050.TW") == history
    assert calls == ["0050.TW"]


def test_cache_discards_sunday_source_rows(tmp_path):
    cache = BacktestHistoryCache(tmp_path)
    friday = bars([100], [100])[0]
    sunday = PriceBar(friday.symbol, dt.date(2026, 9, 20), 100, 120, 90,
                      100, 50000, "fixture", friday.as_of)
    assert cache.prepare(friday.symbol, lambda _: [friday, sunday]) == [friday]
    assert cache.load(friday.symbol) == [friday]
