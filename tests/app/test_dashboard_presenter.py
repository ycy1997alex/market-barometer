"""桌面程式的 Presenter（ToDo §9 Day 27 第 1 項）。

驗收句：**「手動按鈕會打網路、開分頁不會打網路（只讀快取）；兩者行為明確不同」**。

這一條非測不可，因為它從畫面上看不出來 —— 兩個動作都是「畫面刷新了」，
使用者分不出哪一次偷偷打了網路。既有專案就是這樣一路多打的。

Presenter 拿的是 Port（MacroRepository）與一個可注入的 refresher，
所以整組測試離線、幾毫秒跑完，一次網路都不用打 —— 這正是 §3.2 想要的好處。
"""
from __future__ import annotations

import datetime as dt

import pytest

from barometer.app.presenters.dashboard import DashboardPresenter
from barometer.storage.memory_repo import InMemoryRepo


class CountingRefresher:
    """假的 refresher，只數自己被叫了幾次。"""

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.last_force = None

    def __call__(self, force: bool = False) -> None:
        self.calls += 1
        self.last_force = force
        if self.fail:
            raise RuntimeError("資料源掛了")


@pytest.fixture
def repo():
    r = InMemoryRepo()
    r.put_macro("vix", [("2026-09-04", 14.53), ("2026-09-05", 14.10)],
                fetched_at=dt.datetime(2026, 9, 6, 19, 0),
                data_date=dt.date(2026, 9, 5))
    r.put_macro("cpi", [("2026-06-01", 329.0), ("2026-07-01", 330.1)],
                fetched_at=dt.datetime(2026, 9, 6, 19, 0),
                data_date=dt.date(2026, 7, 1))
    return r


@pytest.fixture
def refresher():
    return CountingRefresher()


@pytest.fixture
def presenter(repo, refresher):
    return DashboardPresenter(repo, refresher)


# ---------------- 驗收：兩種更新機制行為明確不同 ----------------

def test_loading_a_tab_never_touches_the_network(presenter, refresher):
    presenter.load("world")
    presenter.load("tw")
    presenter.load("world")
    assert refresher.calls == 0


def test_manual_refresh_touches_the_network_exactly_once(presenter, refresher):
    presenter.refresh()
    assert refresher.calls == 1


def test_refresh_then_load_does_not_fetch_again(presenter, refresher):
    presenter.refresh()
    presenter.load("world")
    assert refresher.calls == 1


# ---------------- 快取讀出來的東西 ----------------

def test_cached_rows_carry_their_own_data_date(presenter):
    rows = {r.key: r for r in presenter.load("world")}
    assert rows["vix"].data_date == "2026-09-05"
    assert rows["cpi"].data_date == "2026-07-01"


def test_rows_with_no_cache_say_so_instead_of_showing_zero(presenter):
    rows = {r.key: r for r in presenter.load("world")}
    assert rows["dxy"].value is None
    assert "尚未抓取" in rows["dxy"].note


def test_status_line_reports_per_series_dates_not_one_timestamp(presenter):
    """§9 Day 25 第 3 項在桌面端同樣成立：沒有單一的「最後更新」。"""
    status = presenter.status()
    assert "最後更新" not in status
    assert "2026-09-05" in status and "2026-07-01" in status


def test_failed_refresh_keeps_the_cached_view(presenter, refresher):
    """單一資料源失敗不得清空畫面 —— 舊值留著並標明失敗（§7.3 最後一段）。"""
    refresher.fail = True
    before = presenter.load("world")
    result = presenter.refresh()
    assert result.ok is False
    assert "資料源掛了" in result.message
    assert len(presenter.load("world")) == len(before)


def test_presenter_works_without_any_refresher():
    """沒有注入 refresher 就是純唯讀模式 —— 不是壞掉，是刻意的。"""
    p = DashboardPresenter(InMemoryRepo(), None)
    assert p.load("world")
    result = p.refresh()
    assert result.ok is False
    assert "唯讀" in result.message


# ---------------- 兩種更新機制（作者 2026-09-07 要求） ----------------

class ModeRefresher:
    """記下每次被呼叫時 force 是什麼。"""

    def __init__(self) -> None:
        self.calls: list[bool] = []

    def __call__(self, force: bool = False) -> None:
        self.calls.append(force)


def _all_fresh_repo(today: dt.date) -> InMemoryRepo:
    """每一條序列都剛更新過的 repo。

    **沒抓過的序列本來就算到期**（`data_date is None` → 一定要抓），
    所以要測「沒有東西到期」，得先把每一條都餵成新鮮的。
    第一版測試漏了這件事，前提根本不成立。
    """
    from barometer.domain import macro_spec

    r = InMemoryRepo()
    for ind in macro_spec.ALL:
        r.put_macro(ind.key, [(today.isoformat(), 1.0)],
                    fetched_at=dt.datetime.combine(today, dt.time(19, 0)),
                    data_date=today)
    return r


def test_auto_refresh_skips_when_nothing_is_due():
    """全部都在預期時間內 → 不打網路。這是「到期才自動更新」的重點。"""
    today = dt.date(2026, 9, 5)
    r = ModeRefresher()
    p = DashboardPresenter(_all_fresh_repo(today), r, today=today)
    result = p.auto_refresh()
    assert r.calls == []
    assert result.ok is False
    assert "沒有" in result.message


def test_auto_refresh_fetches_when_something_is_due(repo):
    """日頻的 vix 停在 9/5，到了 9/8 就該有新的。"""
    r = ModeRefresher()
    p = DashboardPresenter(repo, r, today=dt.date(2026, 9, 8))
    result = p.auto_refresh()
    assert r.calls == [False]     # 自動更新不強制，讓 TTL 擋掉還新鮮的
    assert result.ok is True


def test_force_refresh_always_fetches_even_when_nothing_is_due():
    """就算沒有任何序列到期，「強制重抓」還是要真的去掃一次。"""
    today = dt.date(2026, 9, 5)
    r = ModeRefresher()
    p = DashboardPresenter(_all_fresh_repo(today), r, today=today)
    result = p.force_refresh()
    assert r.calls == [True]      # 強制重抓要真的重新掃一次
    assert result.ok is True


def test_due_keys_names_which_series_need_fetching(repo):
    p = DashboardPresenter(repo, None, today=dt.date(2026, 9, 8))
    due = p.due_keys()
    assert "vix" in due           # 日頻，停在 9/5，早就該有新的
    assert "cpi" in due           # 月頻，停在 7/1，下一筆 8/1 也過了
    # 剛更新過的就不該在裡面
    fresh = DashboardPresenter(_all_fresh_repo(dt.date(2026, 9, 8)), None,
                               today=dt.date(2026, 9, 8))
    assert fresh.due_keys() == []


def test_next_due_summary_is_human_readable():
    p = DashboardPresenter(_all_fresh_repo(dt.date(2026, 9, 5)), None,
                           today=dt.date(2026, 9, 5))
    text = p.due_summary()
    assert "到期" in text or "沒有" in text


def test_force_refresh_reports_failure_without_clearing_the_view(repo):
    def boom(force: bool = False):
        raise RuntimeError("資料源掛了")

    p = DashboardPresenter(repo, boom, today=dt.date(2026, 9, 5))
    before = p.load("world")
    result = p.force_refresh()
    assert result.ok is False
    assert "資料源掛了" in result.message
    assert len(p.load("world")) == len(before)


# ---------------- 大盤與 ETF 分頁（作者 2026-09-07 要求加進桌面程式） ----------------

def _repo_with_scores() -> InMemoryRepo:
    """五個交易日的評分，最後一天有一個警示維度。"""
    r = InMemoryRepo()
    days = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)]
    for sym in ("^TWII", "0050.TW", "006208.TW", "^GSPC", "SPY", "VOO"):
        for i, day in enumerate(days):
            subs = {"ma_stack": 1.0, "rsi": 1.0, "bollinger": 1.0,
                    "volatility": 1.0, "drawdown": 1.0}
            if i == len(days) - 1:
                subs["rsi"] = 0.0          # 最後一天 RSI 警示
            r.put_score(scope="index", symbol=sym, as_of=day,
                        score=100.0 * sum(subs.values()) / len(subs),
                        subscores=subs, price_version="v1")
    return r


def test_index_tabs_exist_for_both_markets():
    p = DashboardPresenter(_repo_with_scores(), None)
    assert [r.key for r in p.load("tw_index")] == ["^TWII", "0050.TW", "006208.TW"]
    assert [r.key for r in p.load("us_index")] == ["^GSPC", "SPY", "VOO"]


def test_index_row_shows_the_latest_score_and_its_own_date():
    p = DashboardPresenter(_repo_with_scores(), None)
    row = {r.key: r for r in p.load("tw_index")}["0050.TW"]
    assert row.value == "80.0"                  # 5 個維度中 1 個警示
    assert row.data_date == "2026-09-07"


def test_index_row_names_the_alerting_dimension():
    """畫面上要顯示看得懂的名字，不是 subscores 的 key。"""
    p = DashboardPresenter(_repo_with_scores(), None)
    row = {r.key: r for r in p.load("tw_index")}["^TWII"]
    assert "RSI" in row.note
    assert "ma_stack" not in row.note


def test_index_row_carries_the_five_day_weighted_average():
    """§8.1 的 10/15/20/25/30，跟網頁與個股共用同一組權重。"""
    p = DashboardPresenter(_repo_with_scores(), None)
    row = {r.key: r for r in p.load("us_index")}["SPY"]
    assert "五日加權" in (row.note + (row.value or ""))


def test_symbol_without_scores_says_so_instead_of_showing_zero():
    p = DashboardPresenter(InMemoryRepo(), None)
    row = {r.key: r for r in p.load("tw_index")}["^TWII"]
    assert row.value is None
    assert "尚未" in row.note or "沒有" in row.note


def test_index_tabs_never_touch_the_network(refresher):
    p = DashboardPresenter(_repo_with_scores(), refresher)
    p.load("tw_index")
    p.load("us_index")
    assert refresher.calls == 0


def test_index_rows_carry_no_advice_field():
    """§2.1：桌面端同樣不得把分數翻成動作。"""
    p = DashboardPresenter(_repo_with_scores(), None)
    for r in p.load("tw_index") + p.load("us_index"):
        blob = f"{r.label}{r.value}{r.note}"
        for word in ("買進", "賣出", "加碼", "減碼", "進場", "出場", "建議"):
            assert word not in blob, (r.key, word)


# ---------------- 不滿五天（回歸測試，2026-09-08） ----------------
#
# `weighting.weighted_average` 對長度不是 5 的輸入會丟 ValueError，而
# `_load_index` 直接把 `history[-5:]` 餵進去。管線剛開始跑、或某個標的
# 新加進清單的時候，歷史就是不滿五天 —— **那是常態，不是異常**，
# 但整個大盤分頁會直接炸掉。
#
# 上面每一個既有測試都剛好餵滿五天，所以從來沒碰到。

def _repo_with_n_days(n: int) -> InMemoryRepo:
    r = InMemoryRepo()
    days = [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)][:n]
    for i, day in enumerate(days):
        subs = {"ma_stack": 1.0, "rsi": 1.0, "bollinger": 1.0,
                "volatility": 1.0, "drawdown": 1.0}
        r.put_score(scope="index", symbol="^TWII", as_of=day, score=80.0,
                    subscores=subs, price_version="v1")
    return r


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_index_tab_survives_fewer_than_five_days(n):
    """不滿五天不得讓整個分頁爆掉。"""
    p = DashboardPresenter(_repo_with_n_days(n), None)
    rows = p.load("tw_index")          # 這一行原本會丟 ValueError
    assert len(rows) == 3


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_short_history_says_insufficient_not_a_number(n):
    """算不出來就說算不出來，**不准拿三天硬算成「五日加權」**。"""
    p = DashboardPresenter(_repo_with_n_days(n), None)
    row = {r.key: r for r in p.load("tw_index")}["^TWII"]

    assert row.value == "80.0"          # 當天分數照顯示
    assert "資料不足" in row.note
    assert f"{n}/5" in row.note         # 講清楚是幾天，不要只說「不足」


def test_exactly_five_days_still_computes():
    """修完之後，滿五天的那條路不能跟著壞掉。"""
    p = DashboardPresenter(_repo_with_n_days(5), None)
    row = {r.key: r for r in p.load("tw_index")}["^TWII"]
    assert "五日加權 80.0" in row.note


def test_more_than_five_days_uses_only_the_latest_five():
    r = InMemoryRepo()
    subs = {"ma_stack": 1.0, "rsi": 1.0, "bollinger": 1.0,
            "volatility": 1.0, "drawdown": 1.0}
    # 前三天 0 分、後五天 80 分：只取最後五天的話，加權剛好是 80
    for i, day in enumerate([dt.date(2026, 8, d) for d in (25, 26, 27)]):
        r.put_score(scope="index", symbol="^TWII", as_of=day, score=0.0,
                    subscores=subs, price_version="v1")
    for day in [dt.date(2026, 9, d) for d in (1, 2, 3, 4, 7)]:
        r.put_score(scope="index", symbol="^TWII", as_of=day, score=80.0,
                    subscores=subs, price_version="v1")

    row = {x.key: x for x in DashboardPresenter(r, None).load("tw_index")}["^TWII"]
    assert "五日加權 80.0" in row.note
