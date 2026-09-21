"""A Yahoo daily bar during the US trading session is not a completed daily close."""
import datetime as dt

from barometer.domain.ports import PriceBar
from barometer.domain.windows import latest_complete_us_date
from barometer.pipeline import fetch_prices
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


def bar(day):
    return PriceBar("SPY", day, 100, 101, 99, 100, 1000, "yfinance",
                    dt.datetime(2026, 9, 21, 21, 53))


def test_new_york_close_cutoff_handles_dst():
    assert latest_complete_us_date(dt.datetime(2026, 9, 21, 13, 53, tzinfo=dt.timezone.utc)) == dt.date(2026, 9, 20)
    assert latest_complete_us_date(dt.datetime(2026, 9, 21, 20, 31, tzinfo=dt.timezone.utc)) == dt.date(2026, 9, 21)
    assert latest_complete_us_date(dt.datetime(2026, 1, 5, 20, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 1, 4)


def test_pipeline_drops_us_intraday_bar_from_both_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    monkeypatch.setattr(fetch_prices.windows, "latest_complete_us_date", lambda: dt.date(2026, 9, 18))
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily",
                        lambda *a, **k: [bar(dt.date(2026, 9, 18)), bar(dt.date(2026, 9, 21))])
    log = fetch_prices.run(["SPY"], "test_intraday", run_date=dt.date(2026, 9, 21))
    assert [b.date for b in csv_audit.read_current("SPY")] == [dt.date(2026, 9, 18)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        assert [b.date for b in repo.get_adjusted_prices("SPY")] == [dt.date(2026, 9, 18)]
    assert log.counts["incomplete_sessions"] == 1
