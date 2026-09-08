"""明文頁面產出（ToDo §9 Day 25 第 3 項、Day 27 第 3 項）。

核心驗收只有一句，但它是整個頻率混雜問題的結論：

  > **頁面上沒有單一的「網站最後更新時間」，每條序列各自標自己的資料日期。**

理由是實測出來的：21 項指標抓下來，資料日期共 8 種 —— 央行停在 2024-03-22、
國發會是 2026-07、CPI 是 2026-07-01、台灣 GDP 是 2026Q2、利差是昨天。
印一個「最後更新：今天」等於宣稱這 21 個數字都是今天的，那是假的。

其餘的測試守 §2.1（輸出不得含行動字眼）與跳脫。
"""
from __future__ import annotations

import re

import pytest

from barometer.render import lint, page


def _row(**kw):
    base = dict(label="美國 CPI", value="330.1", data_date="2026-07-01",
                freq="每月", series=[("2026-06-01", 329.0), ("2026-07-01", 330.1)])
    base.update(kw)
    return page.Row(**base)


def _tabs():
    return [
        page.Tab(key="world", title="世界總體經濟", rows=[
            _row(),
            _row(label="美債 10Y-2Y 利差", value="+0.41%",
                 data_date="2026-09-05", freq="每日"),
        ]),
        page.Tab(key="tw", title="台灣總體經濟", rows=[
            _row(label="台灣央行重貼現率", value="2.00%",
                 data_date="2024-03-22", freq="不定期",
                 note="最近一次調整距今 898 天"),
        ]),
    ]


# ---------------- 頻率混雜：這一條是這支檔案存在的理由 ----------------

def test_fetch_time_is_shown_and_labelled_as_a_run_time():
    """頁面要顯示「最後一次抓取」的時間（作者 2026-09-07 要求）。

    這跟原本「不要有單一更新時間」的顧慮並不衝突，前提是**講清楚它是什麼**：
    它是**管線最後一次執行**的時間，不是任何一條序列的資料日期。

    兩者差很多。管線 18:23 跑過，不代表美國 CPI 是 18:23 的數字 ——
    CPI 停在 7 月，而且下次要等下個月。把執行時間印成「資料更新時間」
    就等於宣稱那 21 條序列都是剛才更新的。
    """
    html = page.render(_tabs(), title="market-barometer",
                       last_run_at="2026-09-07 18:23")
    assert "2026-09-07 18:23" in html
    assert "最後一次抓取" in html
    # 必須同時把「這不是資料日期」講出來
    assert "不是" in html and "資料日期" in html


def test_fetch_time_is_not_labelled_as_a_data_date():
    """不能用會讓人以為所有資料都是那個時間的說法。"""
    html = page.render(_tabs(), title="market-barometer",
                       last_run_at="2026-09-07 18:23")
    for misleading in ("資料更新時間：", "資料日期：2026-09-07 18:23"):
        assert misleading not in html, misleading


def test_page_without_a_run_time_omits_the_line_entirely():
    """沒有執行紀錄的時候不要瞎編一個 —— 寧可不顯示。"""
    html = page.render(_tabs(), title="market-barometer")
    assert "最後一次抓取" not in html


def test_per_row_data_dates_survive_the_fetch_time_line():
    """加了執行時間之後，每一列還是要有自己的資料日期。"""
    html = page.render(_tabs(), title="market-barometer",
                       last_run_at="2026-09-07 18:23")
    for d in ("2026-07-01", "2026-09-05", "2024-03-22"):
        assert d in html


def test_every_row_carries_its_own_data_date():
    html = page.render(_tabs(), title="market-barometer")
    for d in ("2026-07-01", "2026-09-05", "2024-03-22"):
        assert d in html


def test_rows_with_different_dates_are_not_collapsed():
    """三條序列三個日期，頁面上就要看得到三個 —— 不許取最大值當代表。"""
    html = page.render(_tabs(), title="market-barometer")
    dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", html))
    assert {"2026-07-01", "2026-09-05", "2024-03-22"} <= dates


def test_monthly_series_is_drawn_stepped_not_continuous():
    """月頻拉成連續線 = 宣稱中間那些日子有值。畫法由頻率決定（§9 Day 25 第 4 項）。"""
    html = page.render(_tabs(), title="market-barometer")
    assert 'class="line step"' in html


def test_daily_series_is_drawn_continuous():
    html = page.render(
        [page.Tab(key="w", title="世界", rows=[_row(freq="每日")])],
        title="t",
    )
    assert 'class="line step"' not in html


# ---------------- §2.1：輸出層擋住行動字眼 ----------------

def test_rendered_page_passes_the_action_word_lint():
    html = page.render(_tabs(), title="market-barometer")
    assert lint.lint(html) == []


def test_render_refuses_content_that_would_fail_the_lint():
    """命中就讓發布失敗，不是印個警告就放行（§2.1）。"""
    bad = [page.Tab(key="w", title="世界", rows=[
        _row(note="分數低於 40 應減碼")
    ])]
    with pytest.raises(lint.OutputLintError):
        page.render(bad, title="market-barometer", enforce_lint=True)


def test_lint_is_not_enforced_for_the_private_site():
    """stock-research 那一側可以有建議 —— 同一支 render 兩種用法（§2.1）。"""
    tabs = [page.Tab(key="tw", title="台股權值股", rows=[
        _row(label="2330.TW", note="短線建議：加碼")
    ])]
    html = page.render(tabs, title="stock-research", enforce_lint=False)
    assert "短線建議" in html


# ---------------- 一般 ----------------

def test_tabs_all_appear():
    html = page.render(_tabs(), title="market-barometer")
    assert "世界總體經濟" in html and "台灣總體經濟" in html


def test_values_are_html_escaped():
    tabs = [page.Tab(key="w", title="世界", rows=[
        _row(label="<script>alert(1)</script>", value="&<>")
    ])]
    html = page.render(tabs, title="t")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_page_is_self_contained_with_no_external_requests():
    """明文最後會被塞進 <iframe srcdoc>，外部相依只會變成破圖（§3.4 render/）。"""
    html = page.render(_tabs(), title="market-barometer")
    assert "http://" not in html
    assert "https://" not in html
    assert "<img" not in html


def test_missing_value_renders_a_dash_not_zero():
    html = page.render(
        [page.Tab(key="w", title="世界", rows=[_row(value=None, series=[])])],
        title="t",
    )
    assert "—" in html
    assert ">0<" not in html
