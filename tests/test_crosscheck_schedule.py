"""The TW crosscheck must never compare 0050 across its 2025 split."""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

from barometer.domain.ports import PriceBar
from barometer.pipeline.runlog import read_runs


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("crosscheck_tw", ROOT / "tools" / "crosscheck_tw.py")
assert SPEC and SPEC.loader
crosscheck_tw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(crosscheck_tw)


def test_0050_window_starts_at_first_post_split_trading_day():
    end = dt.date(2025, 6, 25)
    assert crosscheck_tw.comparison_start("0050.TW", end, 30) == dt.date(2025, 6, 18)


def test_0050_before_resumption_has_no_valid_comparison_window():
    assert crosscheck_tw.comparison_start("0050.TW", dt.date(2025, 6, 10), 30) is None


def test_other_symbols_keep_normal_lookback():
    assert crosscheck_tw.comparison_start("006208.TW", dt.date(2025, 6, 25), 30) == dt.date(2025, 5, 26)


def test_crosscheck_is_declared_in_scheduler():
    script = (ROOT / "tools" / "register_tasks.ps1").read_text(encoding="utf-8-sig")
    assert 'Name = "Barometer-Crosscheck-TW"' in script
    assert 'Script = "crosscheck_tw.ps1"' in script


def test_scheduled_wrapper_changes_out_of_system32_before_shioaji():
    script = (ROOT / "tools" / "crosscheck_tw.ps1").read_text(encoding="utf-8-sig")
    assert 'Set-Location -LiteralPath (Join-Path $env:STOCKDATA_ROOT "runlog")' in script
    assert script.index("Set-Location") < script.index("& $Python")


def test_frozen_shioaji_history_never_reaches_crosscheck(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    monkeypatch.setattr(crosscheck_tw.secrets_store, "has_shioaji", lambda: True)
    monkeypatch.setattr(crosscheck_tw.config, "TW_SYMBOLS", ("0050.TW",))
    old_day = dt.date.today() - dt.timedelta(days=70)
    bar = PriceBar("0050.TW", old_day, 47, 47, 47, 47, 1000,
                   "shioaji", dt.datetime.now())
    monkeypatch.setattr(crosscheck_tw.shioaji_src, "fetch_daily", lambda *a, **k: ([bar], {}))

    def fail_if_reached(*args):
        raise AssertionError("frozen Shioaji series reached crosscheck")

    monkeypatch.setattr(crosscheck_tw.csv_audit, "read_current", fail_if_reached)
    crosscheck_tw.main()
    runs = [row for row in read_runs(dt.date.today().strftime("%Y-%m"))
            if row["task"] == "crosscheck_tw"]
    assert runs and any("凍結" in note for note in runs[-1]["notes"])
