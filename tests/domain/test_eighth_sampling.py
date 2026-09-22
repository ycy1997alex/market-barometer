"""第八批 8-10：分數折線圖的混合取樣（§5.3）。

**週頻涵蓋完整一年 + 近 5 個交易日日頻。** 折線圖佔體積的大宗，一整年日頻
是 250 點、混合取樣約 55 點，而長期分數看的是 6~24 個月 —— 砍成三個月等於
把這張圖最有用的那一段丟掉。

⚠️ **兩段解析度不同，圖上要標出來**，否則近端的鋸齒會被誤讀成波動突然變大。
⚠️ **缺料是斷點**，不是把兩邊接起來。
"""
from __future__ import annotations

import datetime as dt

from barometer.domain import sampling


def _daily(start: dt.date, values: list[float | None]):
    return [((start + dt.timedelta(days=i)).isoformat(), v)
            for i, v in enumerate(values) if v is not None]


def test_recent_days_stay_daily_and_are_marked_as_such():
    end = dt.date(2026, 9, 22)
    rows = _daily(end - dt.timedelta(days=29), [50.0 + i for i in range(30)])

    got = sampling.mixed_sample(rows, today=end)

    tail = [p for p in got if p.resolution == sampling.DAILY]
    assert len(tail) == 5
    assert [p.label for p in tail] == [r[0] for r in rows[-5:]]


def test_older_points_collapse_to_one_per_week():
    end = dt.date(2026, 9, 22)
    rows = _daily(end - dt.timedelta(days=200), [float(i) for i in range(201)])

    got = sampling.mixed_sample(rows, today=end)
    weekly = [p for p in got if p.resolution == sampling.WEEKLY]

    assert 25 <= len(weekly) <= 32          # 約 200 天 ÷ 7
    assert all(a.label < b.label for a, b in zip(weekly, weekly[1:]))


def test_a_full_year_is_covered_not_just_three_months():
    end = dt.date(2026, 9, 22)
    rows = _daily(end - dt.timedelta(days=400), [float(i) for i in range(401)])

    got = sampling.mixed_sample(rows, today=end)
    oldest = dt.date.fromisoformat(got[0].label)

    assert (end - oldest).days >= 350
    assert (end - oldest).days <= 372        # 不要超過一年太多
    assert len(got) <= 70                    # §5.3 的體積前提：約 55 點


def test_gaps_are_kept_as_breaks_not_bridged():
    end = dt.date(2026, 9, 22)
    rows = (_daily(end - dt.timedelta(days=60), [float(i) for i in range(20)])
            + _daily(end - dt.timedelta(days=10), [float(i) for i in range(11)]))

    got = sampling.mixed_sample(rows, today=end)

    assert any(p.gap_before for p in got), "中間整整一個月沒有資料，圖上必須斷開"
    assert not got[0].gap_before


def test_an_empty_history_samples_to_nothing():
    assert sampling.mixed_sample([], today=dt.date(2026, 9, 22)) == []


def test_the_two_resolutions_are_distinguishable_in_the_svg():
    from barometer.render import svg

    end = dt.date(2026, 9, 22)
    rows = _daily(end - dt.timedelta(days=120), [50.0 + (i % 7) for i in range(121)])
    markup = svg.score_chart(sampling.mixed_sample(rows, today=end), label="世界層分數")

    assert markup.startswith("<svg")
    assert 'class="line weekly"' in markup and 'class="line daily"' in markup
    assert "解析度" in markup            # 圖上標出兩段解析度


def test_a_break_starts_a_new_path_instead_of_a_straight_line():
    from barometer.render import svg

    end = dt.date(2026, 9, 22)
    rows = (_daily(end - dt.timedelta(days=90), [float(i) for i in range(20)])
            + _daily(end - dt.timedelta(days=6), [float(i) for i in range(7)]))
    markup = svg.score_chart(sampling.mixed_sample(rows, today=end), label="世界層分數")

    assert markup.count("<path") >= 2
