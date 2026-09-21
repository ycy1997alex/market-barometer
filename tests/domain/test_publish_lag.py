"""Release lag checks for historical macro replay."""
import datetime as dt

from barometer.domain.macro_spec import PUBLISH_LAG_DAYS, available_series


def test_plan_lags_are_centralized():
    assert PUBLISH_LAG_DAYS["CPIAUCSL"] == 45
    assert PUBLISH_LAG_DAYS["UNRATE"] == 35
    assert PUBLISH_LAG_DAYS["PAYEMS"] == 35
    assert PUBLISH_LAG_DAYS["ICSA"] == 5
    assert PUBLISH_LAG_DAYS["WALCL"] == 8
    assert PUBLISH_LAG_DAYS["T10Y2Y"] == 1


def test_replay_cannot_read_row_before_its_release_date():
    rows = [("2020-01-01", 1.0), ("2020-02-01", 9.0)]
    assert available_series(rows, "CPIAUCSL", dt.date(2020, 3, 15)) == rows[:1]
    assert available_series(rows, "CPIAUCSL", dt.date(2020, 3, 17)) == rows


def test_daily_series_excludes_same_day_fred_row():
    rows = [("2022-09-01", -0.2), ("2022-09-02", -0.3)]
    assert available_series(rows, "T10Y2Y", dt.date(2022, 9, 2)) == rows[:1]


def test_unlisted_lag_fails_closed():
    try:
        available_series([("2022-09-01", 1.0)], "UNKNOWN", dt.date(2022, 9, 2))
    except KeyError:
        pass
    else:
        raise AssertionError("unknown release timing must not use an implicit zero lag")


def test_month_and_quarter_labels_use_period_start_before_lag():
    assert available_series([("2026-07", 1.0)], "6099", dt.date(2026, 8, 14)) == []
    assert available_series([("2026-07", 1.0)], "6099", dt.date(2026, 8, 15))
    assert available_series([("2026Q2", 2.0)], "6799", dt.date(2026, 6, 29)) == []
    assert available_series([("2026Q2", 2.0)], "6799", dt.date(2026, 6, 30))
