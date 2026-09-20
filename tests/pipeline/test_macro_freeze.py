"""Every macro source uses the shared freeze gate before scoring."""

import datetime as dt

import pytest

from barometer.domain import macro_spec
from barometer.pipeline import run_macro
from barometer.pipeline import build_page
from barometer.pipeline.runlog import RunLog
from barometer.storage.sqlite_repo import SqliteRepo


@pytest.fixture
def isolated_macro(monkeypatch, tmp_path):
    path = tmp_path / "macro.db"
    monkeypatch.setattr(run_macro.config, "db_path", lambda: path)
    monkeypatch.setattr(run_macro.config, "ensure_dirs", lambda: None)
    monkeypatch.setattr(RunLog, "append", lambda self: None)
    monkeypatch.setattr(run_macro, "SCORED", ())
    monkeypatch.setattr(run_macro, "WORLD", ())
    monkeypatch.setattr(run_macro, "TAIWAN", ())
    return path


@pytest.mark.parametrize("source", sorted({ind.source for ind in macro_spec.ALL}))
def test_each_datasource_freeze_is_marked_missing_not_scored(monkeypatch, isolated_macro, source):
    ind = macro_spec.Indicator("probe", "probe", "每日", source, "probe", "{:.1f}", False, "observe")
    monkeypatch.setattr(run_macro, "ALL", (ind,))
    frozen_date = dt.date.today() - dt.timedelta(days=70)
    monkeypatch.setattr(run_macro, "_fetch_one", lambda _: [(frozen_date.isoformat(), 21.0)])

    _, output = run_macro.run(force=True)

    assert output["results"]["probe"]["status"] == "missing"
    assert output["results"]["probe"]["series"] == []
    assert "凍結" in output["results"]["probe"]["note"]
    assert output["verdicts"] == {}


def test_frozen_primary_downgrades_to_fresh_cached_series(monkeypatch, isolated_macro):
    ind = macro_spec.Indicator("probe", "probe", "每日", "yfinance", "probe", "{:.1f}", False, "observe")
    monkeypatch.setattr(run_macro, "ALL", (ind,))
    yesterday = dt.date.today() - dt.timedelta(days=1)
    frozen_date = dt.date.today() - dt.timedelta(days=70)
    with SqliteRepo(isolated_macro) as repo:
        repo.init_schema()
        repo.put_macro("probe", [(yesterday.isoformat(), 25.0)],
                       fetched_at=dt.datetime.now() - dt.timedelta(days=1), data_date=yesterday)
    monkeypatch.setattr(run_macro, "_fetch_one", lambda _: [(frozen_date.isoformat(), 21.0)])

    _, output = run_macro.run(force=True)

    row = output["results"]["probe"]
    assert row["status"] == "stale"
    assert row["series"] == [(yesterday.isoformat(), 25.0)]
    assert "凍結" in row["note"] and "降級" in row["note"]


def test_page_marks_frozen_cached_value_missing(monkeypatch, isolated_macro):
    ind = macro_spec.Indicator("probe", "probe", "每日", "yfinance", "probe", "{:.1f}", False, "observe")
    frozen_date = dt.date.today() - dt.timedelta(days=70)
    with SqliteRepo(isolated_macro) as repo:
        repo.init_schema()
        repo.put_macro("probe", [(frozen_date.isoformat(), 21.0)],
                       fetched_at=dt.datetime.now(), data_date=frozen_date)
        row = build_page._macro_rows(repo, (ind,))[0]

    assert row.value is None
    assert "凍結" in row.note
