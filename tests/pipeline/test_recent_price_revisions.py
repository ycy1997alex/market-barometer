"""The last N trading sessions may be revised; older history is only flagged."""
from __future__ import annotations

import datetime as dt

from barometer import config
from barometer.domain.ports import PriceBar
from barometer.pipeline import fetch_prices
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


AS_OF = dt.datetime(2026, 9, 18, 18)
DAYS = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18)]


def bars(changed: dict[dt.date, float] | None = None):
    changed = changed or {}
    return [PriceBar("SPY", day, 100, 101, 99, changed.get(day, 100 + i),
                     1000, "yfinance", AS_OF) for i, day in enumerate(DAYS)]


def run_with(monkeypatch, prices, *, force=False):
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", lambda *a, **k: prices)
    return fetch_prices.run(["SPY"], "test_recent", run_date=DAYS[-1], force=force)


def test_noop_and_recent_vs_old_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    run_with(monkeypatch, bars())
    current = tmp_path / "price_current" / "SPY.csv"
    raw = config.price_raw_path(DAYS[-1].isoformat())
    before = current.read_bytes(), raw.stat().st_size
    with SqliteRepo(config.db_path()) as repo:
        old_stamp = repo.get_prices("SPY")[-1].as_of
    run_with(monkeypatch, bars())
    assert before == (current.read_bytes(), raw.stat().st_size)
    with SqliteRepo(config.db_path()) as repo:
        assert repo.get_prices("SPY")[-1].as_of == old_stamp

    recent, old = DAYS[-3], DAYS[-8]
    log = run_with(monkeypatch, bars({recent: 900, old: 800}), force=True)
    got = {b.date: b for b in csv_audit.read_current("SPY")}
    assert got[recent].close == 900
    assert got[old].close == 100 + DAYS.index(old)
    assert any("close" in note and str(recent) in note and "900" in note for note in log.notes)
    assert any("close" in note and str(old) in note and "800" in note for note in log.notes)
    with SqliteRepo(config.db_path()) as repo:
        conflicts = repo.get_conflicts(recent) + repo.get_conflicts(old)
    assert {(c["date"], c["field"]) for c in conflicts} == {(str(recent), "close"), (str(old), "close")}
    assert {(c["old_value"], c["new_value"], c["taken"]) for c in conflicts} == {
        (100 + DAYS.index(recent), 900, "yfinance_recent_update"),
        (100 + DAYS.index(old), 800, "stored_historical"),
    }


def test_configured_window_counts_sessions_over_holiday(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "PRICE_REVISABLE_SESSIONS", 3, raising=False)
    run_with(monkeypatch, bars())
    n, older = DAYS[-3], DAYS[-4]
    run_with(monkeypatch, bars({n: 500, older: 600}), force=True)
    got = {b.date: b.close for b in csv_audit.read_current("SPY")}
    assert got[n] == 500
    assert got[older] == 100 + DAYS.index(older)
