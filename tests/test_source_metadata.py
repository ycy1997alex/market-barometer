"""Every displayed value identifies its actual source, data date, and fetch time."""
from __future__ import annotations

import datetime as dt
import re

from barometer.domain.macro_spec import Indicator
from barometer.domain.ports import PriceBar
from barometer.pipeline import build_page
from barometer.render.page import Row, Tab, render
from barometer.storage import csv_audit
from barometer.storage.sqlite_repo import SqliteRepo


def test_render_has_three_nonempty_provenance_cells():
    row = Row("probe", "12.3", "2026-09-18", source="twse_stock_day_all",
              fetched_at="2026-09-20 18:00")
    html = render([Tab("tw", "Taiwan", [row])], "probe")
    assert "<th>來源</th>" in html
    assert "<th>資料日期" in html
    assert "<th>取得時間</th>" in html
    cells = re.findall(r"<td[^>]*>(.*?)</td>", html)
    assert any("twse_stock_day_all" in cell for cell in cells)
    assert any("2026-09-18" in cell for cell in cells)
    assert any("2026-09-20 18:00" in cell for cell in cells)


def test_macro_fallback_labels_cached_actual_source_not_configured_primary(tmp_path):
    day = dt.date.today() - dt.timedelta(days=1)
    fetched = dt.datetime.combine(day, dt.time(18))
    with SqliteRepo(tmp_path / "macro.db") as repo:
        repo.init_schema()
        repo.put_macro("probe", [(day.isoformat(), 12.3)], fetched_at=fetched,
                       data_date=day, source="cached_yfinance")
        configured = Indicator("probe", "probe", "每日", "fred", "probe",
                               "{:.1f}", False, "observe")
        row = build_page._macro_rows(repo, (configured,))[0]
    assert row.value == "12.3"
    assert row.source == "cached_yfinance"
    assert row.data_date == day.isoformat()
    assert row.fetched_at.startswith(day.isoformat())


def test_price_score_row_uses_actual_latest_price_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    today = dt.date.today()
    as_of = dt.datetime.combine(today, dt.time(18))
    bars = [PriceBar("0050.TW", today - dt.timedelta(days=69 - i),
                     100 + i, 101 + i, 99 + i, 100 + i, 1000,
                     "yfinance" if i < 69 else "twse_stock_day_all", as_of)
            for i in range(70)]
    monkeypatch.setattr(csv_audit, "read_current", lambda _: bars)
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.upsert_adjusted_prices(bars)
    row = build_page._index_rows(["0050.TW"])[0]
    assert row.source == "twse_stock_day_all"
    assert row.data_date == today.isoformat()
    assert row.fetched_at.startswith(today.isoformat())
