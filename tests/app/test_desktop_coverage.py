"""Desktop score and status expose coverage without recomputing stored scores."""
import datetime as dt

from barometer.app.presenters.dashboard import DashboardPresenter
from barometer.storage.memory_repo import InMemoryRepo


def test_index_score_note_marks_three_of_five_as_degraded():
    repo = InMemoryRepo()
    repo.put_score("index", "0050.TW", dt.date(2026, 9, 18), 100.0,
                   {"ma_stack": 1.0, "rsi": 1.0, "bollinger": 1.0}, "v1")
    row = next(r for r in DashboardPresenter(repo).load("tw_index")
               if r.key == "0050.TW")
    assert row.value == "100.0"
    assert "技術面 3/5 項（60%）" in row.note
    assert "低涵蓋・降級" in row.note


def test_status_shows_macro_layer_coverage_separately():
    repo = InMemoryRepo()
    today = dt.date(2026, 9, 18)
    repo.put_macro("vix", [(today.isoformat(), 15.0)],
                   fetched_at=dt.datetime(2026, 9, 18, 18), data_date=today,
                   source="yfinance")
    status = DashboardPresenter(repo, today=today).status()
    assert "世界層 1/11 項" in status
    assert "台灣層 0/6 項" in status
    assert "低涵蓋" in status
    assert status.index("低涵蓋") < status.index("資料日期")
