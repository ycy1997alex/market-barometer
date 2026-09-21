"""TTL metadata wraps price_current; it must not create another price data cache."""
import datetime as dt
import json

from barometer.datasources.cached import CachedSource
from barometer.pipeline import fetch_prices
from barometer.domain.ports import PriceBar


NOW = dt.datetime(2026, 9, 21, 16, tzinfo=dt.timezone.utc)


def bar(day, close):
    return PriceBar("SPY", day, close, close, close, close, 1000,
                    "yfinance", NOW.replace(tzinfo=None))


def test_ttl_force_tail_overlap_and_version(tmp_path):
    previous = [bar(dt.date(2026, 9, 18), 100)]
    calls = []

    def fetch(symbol, **kw):
        calls.append(kw)
        return previous

    cache = CachedSource(tmp_path, fetch, lambda _: previous, lambda _: previous,
                         ttl_seconds=3600, clock=lambda: NOW)
    cache.mark_checked("SPY")
    result = cache.get("SPY", period="1y")
    assert result.from_cache and calls == []
    cache.get("SPY", period="1y", force=True)
    assert calls[0]["start"] == dt.date(2026, 9, 11)
    assert calls[1]["start"] == dt.date(2026, 9, 11)

    meta = tmp_path / "price_current" / ".cache_meta.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["SPY"]["version"] = "0.0.0"
    meta.write_text(json.dumps(data), encoding="utf-8")
    calls.clear()
    cache.get("SPY", period="1y")
    assert len(calls) == 2
    assert all("start" not in call for call in calls)


def test_changed_adjusted_overlap_triggers_full_adjusted_refresh(tmp_path):
    previous = [bar(dt.date(2026, 9, 18), 100)]
    calls = []

    def fetch(symbol, **kw):
        calls.append(kw)
        if kw.get("auto_adjust") and "start" in kw:
            return [bar(previous[0].date, 99)]
        return previous

    cache = CachedSource(tmp_path, fetch, lambda _: previous, lambda _: previous,
                         ttl_seconds=0, clock=lambda: NOW)
    cache.mark_checked("SPY")
    cache.get("SPY", period="1y")
    assert len(calls) == 3
    assert calls[2]["auto_adjust"] is True and "start" not in calls[2]


def test_price_pipeline_reuses_current_store_within_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    fetched = []
    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily",
                        lambda symbol, **kw: fetched.append(kw) or [bar(dt.date(2026, 9, 18), 100)])
    fetch_prices.run(["SPY"], "test_cache", run_date=dt.date(2026, 9, 18))
    assert len(fetched) == 2
    fetch_prices.run(["SPY"], "test_cache", run_date=dt.date(2026, 9, 18))
    assert len(fetched) == 2
    fetch_prices.run(["SPY"], "test_cache", run_date=dt.date(2026, 9, 18), force=True)
    assert len(fetched) == 4
