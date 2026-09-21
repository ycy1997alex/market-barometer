"""Content checks are read-only, explicit and human-reviewable."""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from barometer.domain.coverage import Coverage
from barometer.pipeline.content_check import capture_tabs, compare_snapshots, format_report
from barometer.render.page import Row, Tab


def _tabs(value="100.0", coverage=Coverage(10, 10), source="fred"):
    return [Tab("world", "世界", [Row("CPI", value, "2026-07-01", source=source,
                                      fetched_at="2026-09-20 09:00")],
                coverage=coverage)]


def test_large_value_change_and_coverage_drop_are_review_items():
    yesterday = capture_tabs(_tabs(), dt.datetime(2026, 9, 20, 9))
    today = capture_tabs(_tabs("1000.0", Coverage(7, 10)),
                         dt.datetime(2026, 9, 21, 9))
    issues = compare_snapshots(yesterday, today)
    assert {issue.kind for issue in issues} == {"value_jump", "coverage_drop"}
    report = format_report(yesterday, today, issues)
    assert "100.0" in report and "1000.0" in report
    assert "100%" in report and "70%" in report
    assert "需人工確認" in report
    assert yesterday["tabs"]["world"]["rows"]["CPI"]["value"] == "100.0"


def test_boundary_is_strictly_more_than_twenty_percentage_points():
    old = capture_tabs(_tabs(), dt.datetime(2026, 9, 20))
    exact = capture_tabs(_tabs(coverage=Coverage(8, 10)), dt.datetime(2026, 9, 21))
    assert not any(issue.kind == "coverage_drop" for issue in compare_snapshots(old, exact))
    fractional = capture_tabs(_tabs(coverage=Coverage(796, 1000)),
                              dt.datetime(2026, 9, 21))
    assert any(issue.kind == "coverage_drop" for issue in compare_snapshots(old, fractional))


def test_source_change_is_visible_even_without_value_jump():
    old = capture_tabs(_tabs(), dt.datetime(2026, 9, 20))
    new = capture_tabs(_tabs(source="cached_fred"), dt.datetime(2026, 9, 21))
    assert any(issue.kind == "source_change" for issue in compare_snapshots(old, new))


def test_cli_reports_anomalies_but_exits_successfully(tmp_path):
    old = capture_tabs(_tabs(), dt.datetime(2026, 9, 20))
    new = capture_tabs(_tabs("1000.0", Coverage(7, 10)), dt.datetime(2026, 9, 21))
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps(old), encoding="utf-8")
    after.write_text(json.dumps(new), encoding="utf-8")
    repo = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.pop("PYTHONIOENCODING", None)
    result = subprocess.run(
        [sys.executable, str(repo / "tools" / "verify_content.py"),
         "--previous", str(before), "--current", str(after)],
        capture_output=True, text=True, encoding="utf-8", cwd=repo,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert "需人工確認" in result.stdout
    assert "1000.0" in result.stdout
