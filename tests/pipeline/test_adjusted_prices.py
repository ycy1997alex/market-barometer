"""Batch 4: total-return bars feed indicators; current bars remain the audit/display basis."""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

import pytest

from barometer.domain.ports import PriceBar
from barometer.pipeline import fetch_prices, run_scores
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


DAY = dt.date(2025, 7, 21)
AS_OF = dt.datetime(2026, 9, 21, 14)


def bar(day: dt.date, close: float, source: str = "yfinance") -> PriceBar:
    return PriceBar("0050.TW", day, close, close, close, close, 1000, source, AS_OF)


def test_dividend_return_and_pipeline_separation(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    before = dt.date(2025, 7, 18)
    current = [bar(before, 51.45), bar(DAY, 50.90)]
    adjusted = [bar(before, 51.09), bar(DAY, 50.90)]
    requests = []

    def fetch(symbol, **kwargs):
        requests.append(kwargs.get("auto_adjust", False))
        return adjusted if kwargs.get("auto_adjust") else current

    monkeypatch.setattr(fetch_prices.yfinance_src, "fetch_daily", fetch)
    monkeypatch.setattr(fetch_prices.twse_src, "fetch_stock_day_all", lambda _: {})
    fetch_prices.run(["0050.TW"], "test_adjusted", run_date=DAY)

    with SqliteRepo(tmp_path / "market.db") as repo:
        got_adjusted = repo.get_adjusted_prices("0050.TW")
    got_current = csv_audit.read_current("0050.TW")
    raw = csv_audit.read_raw(DAY)
    assert requests == [False, True]
    assert [b.close for b in got_adjusted] == [51.09, 50.90]
    assert [b.close for b in got_current] == [51.45, 50.90]
    assert all(float(b["close"]) != 51.09 for b in raw)
    difference = (50.90 / 51.09 - 1) - (50.90 / 51.45 - 1)
    assert difference == pytest.approx(0.36 / 51.45, abs=0.001)


def test_score_loader_uses_adjusted_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    adjusted = [bar(dt.date(2026, 9, 18), 42.0)]
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(adjusted)
    monkeypatch.setattr(run_scores.csv_audit, "read_current", lambda _: (_ for _ in ()).throw(AssertionError("current used for scoring")))
    seen = []
    monkeypatch.setattr(run_scores, "score_series", lambda symbol, bars, window: seen.extend(bars) or [])
    monkeypatch.setattr(run_scores, "summarize_window", lambda _: {"weighted_average": None})
    monkeypatch.setattr(run_scores, "WINDOW", 0)
    run_scores.run(["0050.TW"], run_date=dt.date(2026, 9, 18), window=0)
    assert seen == adjusted


def test_no_production_adapter_uses_adj_close_alone():
    root = Path(__file__).resolve().parents[2] / "src" / "barometer"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Constant) and node.value == "Adj Close"
            for node in ast.walk(tree)
        ), path
