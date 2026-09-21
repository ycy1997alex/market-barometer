"""Yahoo price histories also pass the shared freeze screen."""

import datetime as dt

import pytest

from barometer.domain.ports import PriceBar
from barometer.pipeline import build_page, fetch_prices, run_scores
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


RUN_DAY = dt.date(2026, 9, 18)


def bar(day: dt.date, close: float) -> PriceBar:
    return PriceBar(
        symbol="0050.TW", date=day, open=close, high=close, low=close,
        close=close, volume_shares=1000.0, source="yfinance",
        as_of=dt.datetime(2026, 9, 18, 18),
    )


def test_old_yahoo_series_is_marked_and_not_written(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    old = [bar(dt.date(2026, 7, 15), 47.0)]
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", lambda *a, **k: old)

    log = fetch_prices.run(["0050.TW"], "test_price_freeze", run_date=RUN_DAY)

    assert log.counts.get("frozen") == 1
    assert any("凍結" in note for note in log.notes)
    assert csv_audit.read_current("0050.TW") == []
    assert build_page._index_rows(["0050.TW"])[0].value is None


def test_frozen_yahoo_downgrades_to_fresh_local_history(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    recent = [bar(RUN_DAY - dt.timedelta(days=day), 50 + day) for day in range(5)]
    csv_audit.write_current("0050.TW", recent)
    monkeypatch.setattr(
        fetch_prices.yfinance_src, "fetch_daily",
        lambda *a, **k: [bar(dt.date(2026, 7, 15), 47.0)],
    )

    log = fetch_prices.run(["0050.TW"], "test_price_freeze", run_date=RUN_DAY)

    assert any("降級" in note for note in log.notes)
    assert csv_audit.read_current("0050.TW") == sorted(recent, key=lambda b: b.date)


def test_page_does_not_score_a_locally_frozen_price_series(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    first = dt.date(2026, 5, 1)
    old = [bar(first + dt.timedelta(days=day), 40 + day * 0.1) for day in range(60)]
    csv_audit.write_current("0050.TW", old)

    row = build_page._index_rows(["0050.TW"])[0]

    assert row.value is None
    assert "凍結" in row.note


def test_score_pipeline_rejects_frozen_history_before_writing(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    first = dt.date(2026, 5, 1)
    old = [bar(first + dt.timedelta(days=day), 40 + day * 0.1) for day in range(60)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(old)

    with pytest.raises(ValueError, match="凍結"):
        run_scores.run(["0050.TW"], task="test_price_freeze")

    with SqliteRepo(tmp_path / "market.db") as repo:
        assert repo.get_scores("index", "0050.TW") == []
