"""Historical scoring uses observation rows only after their assumed release."""
import datetime as dt

from barometer.domain.macro_replay import score_world_on


def test_score_does_not_see_future_vix_or_unreleased_cpi():
    series = {
        "vix": [("2020-03-01", 20.0), ("2020-03-02", 50.0)],
        "cpi": [(f"{year}-{month:02d}-01", 100.0)
                for year in (2018, 2019) for month in range(1, 13)]
               + [("2020-01-01", 100.0), ("2020-02-01", 150.0)],
    }
    before = score_world_on(series, dt.date(2020, 3, 1))
    assert before.valid == 2
    assert before.alert_keys == []
    assert before.score == 100.0

    after = score_world_on(series, dt.date(2020, 3, 2))
    assert after.valid == 2
    assert after.alert_keys == ["vix"]
    assert after.score == 50.0


def test_unknown_timing_is_excluded_instead_of_assumed_available():
    score = score_world_on({"unknown": [("2020-01-01", 9.0)]}, dt.date(2020, 3, 1))
    assert score.valid == 0
    assert score.score is None
