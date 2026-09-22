"""World macro score replay using the publication assumptions in macro_spec.

This is an engineering history view. Today's revised source values are not
historical vintages, so the result must not be described as a vintage backtest.
"""
from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from dataclasses import dataclass

from barometer.domain.macro_spec import PUBLISH_LAG_DAYS, WORLD
from barometer.domain.scoring_macro import ALERT_FUNCS, INSUFFICIENT, LayerScore, score_layer


@dataclass(frozen=True, slots=True)
class ReplayPoint:
    date: dt.date
    score: float | None
    valid: int


def _prepare(series_by_key: dict[str, list[tuple[str, float]]]):
    prepared = {}
    for ind in WORLD:
        if not ind.backtest:
            continue  # 8-6：距到期月數不同，前後不可比 —— 重放時當缺料
        rows = series_by_key.get(ind.key, [])
        lag = PUBLISH_LAG_DAYS[ind.sid]
        dated = sorted((dt.date.fromisoformat(label) + dt.timedelta(days=lag),
                        (label, value)) for label, value in rows)
        prepared[ind.key] = ([item[0] for item in dated], [item[1] for item in dated])
    return prepared


def _score(prepared, as_of: dt.date) -> LayerScore:
    alerts = {}
    for ind in WORLD:
        if ind.key not in prepared:
            continue
        dates, rows = prepared[ind.key]
        visible = rows[:bisect_right(dates, as_of)]
        # Current FRED pipeline keeps 30 observations; replay uses the same
        # bounded lookback for FRED series, and 6 months for daily prices.
        visible = visible[-130:] if ind.source == "yfinance" else visible[-30:]
        if not visible:
            continue
        hit, reason = ALERT_FUNCS[ind.key](visible)
        if reason != INSUFFICIENT:
            alerts[ind.key] = hit
    return score_layer(alerts)


def score_world_on(
    series_by_key: dict[str, list[tuple[str, float]]], as_of: dt.date,
) -> LayerScore:
    return _score(_prepare(series_by_key), as_of)


@dataclass(frozen=True, slots=True)
class TriggerStats:
    """一個指標在一段歷史裡亮了幾次燈。**只有次數，沒有報酬。**"""

    evaluated: int
    hits: int
    episodes: int = 0

    @property
    def per_year(self) -> float:
        """亮著的**天數**換算成一年。"""
        if self.evaluated == 0:
            return 0.0
        return self.hits / self.evaluated * 365.0

    @property
    def episodes_per_year(self) -> float:
        """亮燈的**次數**換算成一年 —— §7.2 的 5~15 次講的是這個。

        連續亮 30 天是一次，不是 30 次。拿天數去對 5~15 這個區間，
        會把一個長期偏高的指標誤判成「觸發太頻繁」。
        """
        if self.evaluated == 0:
            return 0.0
        return self.episodes / self.evaluated * 365.0


def alert_frequency(
    series_by_key: dict[str, list[tuple[str, float]]],
    start: dt.date, end: dt.date,
) -> dict[str, TriggerStats]:
    """逐日重放，數每個指標亮燈的天數（§7.2 的門檻校準用）。

    ⚠️ 這是**頻率統計**，不是準確率。§8 的界線：不得拿「與未來報酬的相關性」
    回頭調參數 —— 所以這裡連報酬欄位都沒有，想那樣用也拿不到數字。

    算不出判定的指標**不會出現在結果裡**，不是以 0 次亮燈的樣子混進報告
    （那會讓一條根本沒資料的序列看起來像「從來不亮」）。
    """
    if start > end:
        raise ValueError("start must not exceed end")
    prepared = _prepare(series_by_key)
    days = sorted({day for key in prepared
                   for day in (dt.date.fromisoformat(label)
                               for label, _ in series_by_key.get(key, []))
                   if start <= day <= end})
    evaluated: dict[str, int] = {}
    hits: dict[str, int] = {}
    episodes: dict[str, int] = {}
    previous: dict[str, bool] = {}
    for day in days:
        for ind in WORLD:
            if ind.key not in prepared:
                continue
            dates, rows = prepared[ind.key]
            visible = rows[:bisect_right(dates, day)]
            visible = visible[-130:] if ind.source == "yfinance" else visible[-30:]
            if not visible:
                continue
            hit, reason = ALERT_FUNCS[ind.key](visible)
            if reason == INSUFFICIENT:
                continue
            evaluated[ind.key] = evaluated.get(ind.key, 0) + 1
            hits[ind.key] = hits.get(ind.key, 0) + (1 if hit else 0)
            if hit and not previous.get(ind.key, False):
                episodes[ind.key] = episodes.get(ind.key, 0) + 1
            previous[ind.key] = hit
    return {key: TriggerStats(count, hits.get(key, 0), episodes.get(key, 0))
            for key, count in evaluated.items()}


def replay_world(
    series_by_key: dict[str, list[tuple[str, float]]],
    start: dt.date, end: dt.date,
) -> list[ReplayPoint]:
    """Evaluate on actual VIX trading dates, never on future-dated rows."""
    if start > end:
        raise ValueError("start must not exceed end")
    trading_dates = sorted({dt.date.fromisoformat(label)
                            for label, _ in series_by_key.get("vix", [])
                            if start <= dt.date.fromisoformat(label) <= end})
    prepared = _prepare(series_by_key)
    points = []
    for day in trading_dates:
        layer = _score(prepared, day)
        points.append(ReplayPoint(day, layer.score, layer.valid))
    return points
