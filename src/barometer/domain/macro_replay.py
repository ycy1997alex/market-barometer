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
        rows = series_by_key.get(ind.key, [])
        lag = PUBLISH_LAG_DAYS[ind.sid]
        dated = sorted((dt.date.fromisoformat(label) + dt.timedelta(days=lag),
                        (label, value)) for label, value in rows)
        prepared[ind.key] = ([item[0] for item in dated], [item[1] for item in dated])
    return prepared


def _score(prepared, as_of: dt.date) -> LayerScore:
    alerts = {}
    for ind in WORLD:
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
