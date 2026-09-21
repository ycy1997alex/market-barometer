"""A step change is a split only with a verified TWSE notice; never auto repair."""
import datetime as dt

from barometer.datasources import twse_src
from barometer.domain.ports import PriceBar
from barometer.pipeline import fetch_prices
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


AS_OF = dt.datetime(2026, 9, 21, 16)
DAYS = [dt.date(2025, 6, d) for d in (6, 9, 10, 18, 19)]


def series(pre_close):
    closes = [pre_close] * 3 + [47.5, 48.0]
    return [PriceBar("0050.TW", day, value, value, value, value, 1000,
                     "yfinance", AS_OF) for day, value in zip(DAYS, closes)]


def test_official_notice_confirms_step_and_blocks_rewrite(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    original = series(188)
    csv_audit.write_current("0050.TW", original)
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_prices(original)
    fetched = series(47)
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", lambda *a, **k: fetched)
    monkeypatch.setattr(fetch_prices.twse_src, "fetch_stock_day_all", lambda _: {})
    notice = twse_src.official_split_notice("0050.TW", dt.date(2025, 6, 18))
    assert notice is not None and notice.ratio == 4
    assert "twse.com.tw" in notice.url
    log = fetch_prices.run(["0050.TW"], "test_split", run_date=DAYS[-1])
    assert csv_audit.read_current("0050.TW") == original
    with SqliteRepo(tmp_path / "market.db") as repo:
        events = repo.conn.execute("SELECT * FROM adjustment_event").fetchall()
        assert len(events) == 1
        assert events[0]["event_date"] == "2025-06-18"
        assert events[0]["ratio"] == 4
        assert not repo.get_conflicts(DAYS[0])
    assert log.counts["split_notices"] == 1
    assert (tmp_path / "ALERT.md").exists()


def test_no_notice_leaves_fixed_ratio_as_unconfirmed_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    old = [PriceBar("SPY", b.date, b.open, b.high, b.low, b.close,
                    b.volume_shares, b.source, b.as_of) for b in series(188)]
    csv_audit.write_current("SPY", old)
    new = [PriceBar("SPY", b.date, b.open, b.high, b.low, b.close,
                    b.volume_shares, b.source, b.as_of) for b in series(47)]
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", lambda *a, **k: new)
    log = fetch_prices.run(["SPY"], "test_split", run_date=DAYS[-1])
    assert log.counts.get("split_notices") is None
    assert csv_audit.read_current("SPY") == old
    assert any("待查" in note for note in log.notes)
