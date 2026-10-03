"""render() 的可選擴充點：分頁分組、自訂分頁內容、額外 CSS／JS（2026-10-03）。

stock-research 那一側的個股頁需要自己的版面（每檔一列＋展開明細），
但標頭、「最後一次抓取」、導覽、頁尾免責仍然要由這一支產生 ——
兩個站共用同一副骨架，各自決定分頁裡面放什麼。

**這幾個參數全部是 opt-in。** market-barometer 自己一個都不傳，
產出必須跟加入擴充點之前逐字相同 —— 用 golden 檔守著，不是靠自律。
golden 是在動 render() 之前用舊版產生的；哪天真的要改這一側的版面，
重新產生 golden 並在 commit 裡寫明原因。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from barometer.domain.coverage import Coverage
from barometer.render import lint, page

GOLDEN = Path(__file__).parent / "golden" / "page_render_default.html"


def _golden_tabs() -> list[page.Tab]:
    return [
        page.Tab(key="world", title="世界總體經濟", intro="月頻與日頻混在同一頁。",
                 chart='<svg class="score-chart"></svg>', sortable=True, rows=[
            page.Row(label="美國 CPI", value="330.1", data_date="2026-07-01", freq="每月",
                     series=[("2026-05-01", 328.2), ("2026-06-01", 329.0), ("2026-07-01", 330.1)],
                     note="年增 2.9%", change="較上月 +0.3%", source="FRED CPIAUCSL",
                     fetched_at="2026-09-07 18:23", coverage=Coverage(3, 3),
                     fundamental_coverage=Coverage(0, 0)),
            page.Row(label="美債 10Y-2Y 利差", value="+0.41%", data_date="2026-09-05",
                     series=[("2026-09-03", 0.38), ("2026-09-04", None), ("2026-09-05", 0.41)],
                     coverage=Coverage(1, 3), coverage_name="技術面"),
            page.Row(label="<b>未接入</b>", value=None, data_date=None, series=[]),
        ]),
        page.Tab(key="tw", title="台灣總體經濟", rows=[
            page.Row(label="台灣央行重貼現率", value="2.00%", data_date="2024-03-22",
                     freq="不定期", note="最近一次調整距今 898 天"),
        ]),
    ]


def _golden_page() -> str:
    return page.render(_golden_tabs(), title="market-barometer",
                       tagline="總經與大盤的本機氣壓計", last_run_at="2026-09-07 18:23")


def _section(html: str, key: str) -> str:
    start = html.index(f'<section data-tab="{key}"')
    return html[start:html.index("</section>", start)]


def _grouped_tabs() -> list[page.Tab]:
    return [
        page.Tab(key="tw", title="台股權值股", group="評分", body='<div class="custom">台股</div>'),
        page.Tab(key="us", title="美股權值股", group="評分", body='<div class="custom">美股</div>'),
        page.Tab(key="pe", title="估值", group="基本面", body='<div class="custom">估值</div>'),
    ]


# ---------------- 不傳新參數 = 逐字不變 ----------------

def test_default_render_is_byte_identical_to_the_golden_page():
    """market-barometer 自己不用任何擴充點，明文不得因為加了擴充點而改變。"""
    assert _golden_page() == GOLDEN.read_text(encoding="utf-8")


# ---------------- 自訂分頁內容 ----------------

def test_tab_body_replaces_the_default_table():
    html = page.render([page.Tab(key="x", title="X", intro="這一頁的說明",
                                 body='<div class="custom">自訂內容</div>')], title="t")
    section = _section(html, "x")
    assert '<div class="custom">自訂內容</div>' in section
    assert "<table" not in section
    assert "這一頁的說明" in section


def test_tab_body_is_inserted_verbatim_while_titles_stay_escaped():
    """內容由呼叫端畫好、由呼叫端負責跳脫；標題與說明仍由這一支跳脫。"""
    html = page.render([page.Tab(key="x", title="<i>標題</i>", intro="<u>說明</u>",
                                 body="<b>粗體</b>")], title="t")
    assert "<b>粗體</b>" in html
    assert "<i>標題</i>" not in html and "&lt;i&gt;標題&lt;/i&gt;" in html
    assert "<u>說明</u>" not in html


def test_lint_still_scans_custom_bodies():
    """自訂內容繞不過 §2.1 的行動字眼掃描。"""
    with pytest.raises(lint.OutputLintError):
        page.render([page.Tab(key="x", title="X", body="<p>分數低於 40 應減碼</p>")],
                    title="t", enforce_lint=True)


# ---------------- 分頁分組 ----------------

def test_grouped_nav_shows_groups_and_only_the_first_groups_subtabs():
    html = page.render(_grouped_tabs(), title="t")
    assert '<nav class="grouped"' in html
    assert html.count('data-group="評分"') == 2      # 群組按鈕 + 它的子分頁列
    assert html.count('data-group="基本面"') == 2
    assert '<div class="subtabs" data-group="評分">' in html
    assert '<div class="subtabs" data-group="基本面" hidden>' in html
    assert '<button data-tab="tw" aria-selected="true">' in html
    assert '<button data-tab="pe" aria-selected="true">' in html   # 每組記得自己的第一個
    assert '<section data-tab="tw">' in html
    assert '<section data-tab="us" hidden>' in html
    assert '<section data-tab="pe" hidden>' in html


def test_grouped_nav_does_not_reuse_the_flat_nav_handler():
    """平鋪版的處理器綁在所有 `nav button` 上；分組版的群組按鈕沒有 data-tab，
    被它綁到會把每一個分頁都藏起來。"""
    html = page.render(_grouped_tabs(), title="t")
    assert "querySelectorAll('nav button')" not in html
    assert "nav.grouped" in html


def test_grouped_page_keeps_the_fetch_line_and_footer():
    html = page.render(_grouped_tabs(), title="t", last_run_at="2026-10-02 21:45",
                       footer_notes=("<strong>本頁不構成投資建議。</strong>",))
    assert "最後一次抓取" in html and "2026-10-02 21:45" in html
    assert "<strong>本頁不構成投資建議。</strong>" in html


def test_group_titles_are_escaped():
    html = page.render([page.Tab(key="x", title="X", group="<s>組</s>", body="")], title="t")
    assert "<s>組</s>" not in html


# ---------------- 額外 CSS／JS ----------------

def test_extra_style_and_script_come_after_the_shared_ones():
    html = page.render(_grouped_tabs(), title="t",
                       extra_style=".custom{color:red}", extra_script="window.custom=1;")
    style = html[html.index("<style>"):html.index("</style>")]
    script = html[html.rindex("<script>"):html.rindex("</script>")]
    assert style.index(":root{") < style.index(".custom{color:red}")
    assert script.index("section[data-tab]") < script.index("window.custom=1;")
