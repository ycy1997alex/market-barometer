"""`summarize_window` 不滿五天時要**大聲失敗**（2026-09-08）。

同一個缺陷在桌面 Presenter 那側是「不准炸」（`tests/app/test_dashboard_presenter.py`
的回歸測試守著），在這裡是**「必須炸」** —— 兩邊刻意相反：

  - **UI**：使用者切到大盤分頁，畫面不該因為某一檔歷史不夠就整頁掛掉。
    那一側回 None，備註寫「資料不足（3/5 天）」。
  - **管線**：批次跑完之後安靜產出一份少了幾檔的結果，比直接失敗糟得多。
    沒有人會去比對「今天怎麼少了兩檔」。

所以這裡要的不是「不要炸」，而是**炸得看得懂**：訊息要講出是哪一檔、
只有幾天、那幾天是哪幾天。原本的訊息只有「五日平均需要恰好 5 個點，
收到 3 個」—— 15 檔跑到一半炸掉，這句話不會告訴你是哪一檔。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.domain import scoring_index
from barometer.pipeline import run_scores


def _scored(symbol: str, n: int) -> list[tuple[dt.date, scoring_index.IndexScore]]:
    days = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)][:n]
    return [
        (
            day,
            scoring_index.IndexScore(symbol=symbol, score=80.0, valid=5,
                                     subscores={}, reasons=[]),
        )
        for day in days
    ]


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_short_window_raises(n):
    with pytest.raises(ValueError):
        run_scores.summarize_window(_scored("^TWII", n))


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_error_names_the_symbol(n):
    """15 檔跑到一半炸掉，訊息一定要說出是哪一檔。"""
    with pytest.raises(ValueError, match="0050.TW"):
        run_scores.summarize_window(_scored("0050.TW", n))


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_error_states_how_many_days(n):
    with pytest.raises(ValueError) as exc:
        run_scores.summarize_window(_scored("^GSPC", n))
    assert f"{n}/5" in str(exc.value)


def test_error_lists_the_dates():
    """「只有 3 天」還不夠 —— 是哪 3 天決定了它是新標的還是抓取漏了。"""
    with pytest.raises(ValueError) as exc:
        run_scores.summarize_window(_scored("SPY", 3))
    msg = str(exc.value)
    assert "2026-09-01" in msg and "2026-09-03" in msg


def test_empty_window_raises_too():
    """一天都沒有的時候不能死在 IndexError —— 那句話同樣看不懂。"""
    with pytest.raises(ValueError, match="0/5"):
        run_scores.summarize_window([])


def test_exactly_five_days_still_works():
    """修完之後正常路徑不能跟著壞掉。"""
    summary = run_scores.summarize_window(_scored("^TWII", 5))
    assert summary["weighted_average"] == pytest.approx(80.0)
    assert summary["simple_average"] == pytest.approx(80.0)
    assert len(summary["dates"]) == 5
