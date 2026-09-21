"""Missing verdicts leave the denominator and visibly lower coverage."""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain.coverage import Coverage
from barometer.domain import macro_spec, scoring_index
from barometer.domain.scoring_macro import score_layer
from barometer.pipeline import run_macro
from barometer.pipeline.runlog import RunLog
from barometer.render.page import Row, Tab, render


def test_removing_two_alerting_items_renormalizes_without_lowering_score():
    full = score_layer({"a": False, "b": False, "c": True, "d": True})
    reduced = score_layer({"a": False, "b": False})
    assert reduced.score >= full.score
    assert reduced.score == 100
    coverage = Coverage(reduced.valid, 4)
    assert coverage.percent == 50
    assert coverage.degraded


def test_under_70_percent_adds_visible_badge_next_to_score():
    row = Row("index", "100.0", "2026-09-18", coverage=Coverage(3, 5))
    html = render([Tab("index", "Index", [row])], "probe")
    assert "低涵蓋・降級" in html
    assert "3/5 項（60%）" in html
    assert html.index("100.0") < html.index("低涵蓋・降級")


def test_macro_insufficient_verdict_is_not_counted_as_unalerted(monkeypatch, tmp_path):
    day = dt.date.today()
    vix = macro_spec.Indicator("vix", "VIX", "每日", "yfinance", "^VIX",
                               "{:.1f}", False, "world")
    cpi = macro_spec.Indicator("cpi", "CPI", "每月", "fred", "CPIAUCSL",
                               "{:.1f}", False, "world")
    monkeypatch.setattr(run_macro, "ALL", (vix, cpi))
    monkeypatch.setattr(run_macro, "SCORED", (vix, cpi))
    monkeypatch.setattr(run_macro, "WORLD", (vix, cpi))
    monkeypatch.setattr(run_macro, "TAIWAN", ())
    monkeypatch.setattr(run_macro.config, "db_path", lambda: tmp_path / "macro.db")
    monkeypatch.setattr(run_macro.config, "ensure_dirs", lambda: None)
    monkeypatch.setattr(RunLog, "append", lambda self: None)
    monkeypatch.setattr(run_macro, "_fetch_one",
                        lambda ind: [(day.isoformat(), 15.0 if ind.key == "vix" else 330.0)])
    _, output = run_macro.run(force=True)
    assert set(output["verdicts"]) == {"vix"}
    assert output["summary"]["world"] == pytest.approx(100)
    assert output["summary"]["world_coverage"].available == 1
    assert output["summary"]["world_coverage"].expected == 2


def test_index_coverage_tracks_available_technical_checks(monkeypatch):
    checks = {
        "a": lambda _: (False, "normal"),
        "b": lambda _: (False, "normal"),
        "c": lambda _: (False, "normal"),
        "d": lambda _: (False, scoring_index.INSUFFICIENT),
        "e": lambda _: (False, scoring_index.INSUFFICIENT),
    }
    monkeypatch.setattr(scoring_index, "TECHNICAL", checks)
    result = scoring_index.score_index("0050.TW", [100.0])
    assert result.score == 100
    assert result.coverage == Coverage(3, 5)
    assert result.coverage.degraded
