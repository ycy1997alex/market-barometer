"""第八批 8-10：分數折線圖要真的畫在頁面上。"""
from __future__ import annotations

import datetime as dt

from barometer.pipeline import build_page
from barometer.render import page
from barometer.storage.sqlite_repo import SqliteRepo


def _seed_scores(tmp_path, days: int = 200) -> None:
    today = dt.date.today()
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        for i in range(days):
            day = today - dt.timedelta(days=days - 1 - i)
            repo.put_score(scope="macro_world", symbol="-", as_of=day,
                           score=60.0 + (i % 11), subscores={}, price_version="macro")


def test_world_tab_carries_a_mixed_resolution_score_chart(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    _seed_scores(tmp_path)

    world = next(tab for tab in build_page.build_tabs() if tab.key == "world")

    assert world.chart.startswith("<svg")
    assert "解析度" in world.chart


def test_the_chart_reaches_the_rendered_html(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    _seed_scores(tmp_path)

    html = page.render(build_page.build_tabs(), title="市場氣壓計", enforce_lint=True)

    assert 'class="score-chart"' in html
    assert 'class="line weekly"' in html and 'class="line daily"' in html


def test_no_history_means_no_chart_not_an_empty_box(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    world = next(tab for tab in build_page.build_tabs() if tab.key == "world")
    assert world.chart == ""
