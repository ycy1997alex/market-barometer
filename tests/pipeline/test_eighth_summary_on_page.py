"""第八批 8-9：總結句要真的出現在頁面上，而且必須通過 lint。"""
from __future__ import annotations

import datetime as dt

from barometer.pipeline import build_page
from barometer.render import lint, page
from barometer.storage.sqlite_repo import SqliteRepo


def _seed(tmp_path) -> None:
    """種兩條真的算得出判定的序列：一條會警示、一條不會。"""
    today = dt.date.today()
    with SqliteRepo(tmp_path / "market.db") as repo:
        repo.init_schema()
        repo.put_macro("vix", [(today.isoformat(), 42.0)],
                       fetched_at=dt.datetime.now(), data_date=today, source="yfinance")
        repo.put_macro("t10y2y", [(today.isoformat(), 0.55)],
                       fetched_at=dt.datetime.now(), data_date=today, source="fred")


def test_world_tab_intro_leads_with_the_arithmetic_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    _seed(tmp_path)

    world = next(tab for tab in build_page.build_tabs() if tab.key == "world")

    assert world.intro.startswith("世界層 2 項中有 1 項警示：VIX 恐慌指數。")


def test_an_empty_layer_says_so_instead_of_dividing(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    world = next(tab for tab in build_page.build_tabs() if tab.key == "world")
    assert world.intro.startswith("世界層沒有任何可用指標。")


def test_the_rendered_page_passes_the_extended_lint(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKDATA_ROOT", str(tmp_path))
    _seed(tmp_path)

    html = page.render(build_page.build_tabs(), title="市場氣壓計", enforce_lint=True)

    assert not lint.lint(html)
