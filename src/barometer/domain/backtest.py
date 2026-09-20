"""Pure Python historical replay of close-time signals and next-open fills.

The caller supplies a scorer that receives an immutable tuple ending at the
signal day's close. This keeps the strategy independent of data adapters and
prevents the scorer from seeing tomorrow's bar.
"""
from __future__ import annotations

import datetime as dt
import math
import threading
from dataclasses import dataclass, field
from typing import Callable, Sequence

from barometer.domain.ports import PriceBar

FEE_RATE = 0.001425
TAX_RATE = 0.003

_HORIZON_LABELS = {"total": "總評", "short": "短期", "mid": "中期", "long": "長期"}
_BUCKETS = (
    (80, math.inf, "≥80"), (60, 80, "60~80"), (40, 60, "40~60"),
    (20, 40, "20~40"), (-20, 20, "-20~20"), (-40, -20, "-40~-20"),
    (-60, -40, "-60~-40"), (-math.inf, -60, "≤-60"),
)


@dataclass(frozen=True, slots=True)
class BacktestParams:
    start: str = ""
    end: str = ""
    horizon: str = "total"
    buy_threshold: float = 60.0
    exit_threshold: float = -20.0
    market: str = "tw"
    warmup_bars: int = 0

    def __post_init__(self) -> None:
        if self.market not in {"tw", "us"}:
            raise ValueError("market must be 'tw' or 'us'")
        if self.buy_threshold <= self.exit_threshold:
            raise ValueError("buy_threshold must exceed exit_threshold")
        if self.warmup_bars < 0:
            raise ValueError("warmup_bars must be nonnegative")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must not exceed end")

    @property
    def fee_rate(self) -> float:
        return FEE_RATE if self.market == "tw" else 0.0

    @property
    def tax_rate(self) -> float:
        return TAX_RATE if self.market == "tw" else 0.0


@dataclass(slots=True)
class Trade:
    entry_date: str
    entry_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    ret_pct: float = 0.0
    holding_days: int = 0
    reason: str = ""


@dataclass(slots=True)
class BacktestResult:
    symbol: str
    name: str
    horizon_label: str
    params: BacktestParams
    trades: list[Trade] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    bh_equity: list[float] = field(default_factory=list)
    scores: list[float | None] = field(default_factory=list)
    in_position: list[bool] = field(default_factory=list)
    stats: dict[str, str] = field(default_factory=dict)
    bucket_stats: list[dict] = field(default_factory=list)


def _max_drawdown(values: Sequence[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1)
    return worst * 100


def _validate_bars(bars: Sequence[PriceBar]) -> None:
    if len(bars) < 2:
        raise ValueError("backtest needs at least two price bars")
    symbol = bars[0].symbol
    previous: dt.date | None = None
    for bar in bars:
        if bar.symbol != symbol:
            raise ValueError("all price bars must share a symbol")
        if previous is not None and bar.date <= previous:
            raise ValueError("price bars must have strictly increasing dates")
        for field_name in ("open", "close"):
            value = getattr(bar, field_name)
            if value is None or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{bar.date}: invalid {field_name} price")
        previous = bar.date


def run_backtest(
    bars: Sequence[PriceBar], params: BacktestParams,
    score_fn: Callable[[tuple[PriceBar, ...]], float | None],
    symbol: str = "", name: str = "",
    progress: Callable[[int, int, str], None] | None = None,
    cancel: threading.Event | None = None,
) -> BacktestResult:
    """Replay signals using only historical prefixes, with full cash accounting.

    ``end`` is the last signal date; its order fills on the next available bar.
    Any remaining position is marked and simulated as closed at that bar's close.
    The score callback must use only its supplied prefix and no external future data.
    """
    bars = tuple(bars)
    _validate_bars(bars)
    symbol = symbol or bars[0].symbol
    if symbol != bars[0].symbol:
        raise ValueError("symbol does not match price bars")
    start = dt.date.fromisoformat(params.start) if params.start else dt.date.min
    end = dt.date.fromisoformat(params.end) if params.end else dt.date.max
    signal_indices = [i for i in range(params.warmup_bars, len(bars) - 1)
                      if start <= bars[i].date <= end]
    if not signal_indices:
        raise ValueError("no evaluable signal dates with a following price bar")

    first, last = signal_indices[0], signal_indices[-1]
    result = BacktestResult(symbol, name or symbol,
                            _HORIZON_LABELS.get(params.horizon, params.horizon), params)
    cash, units = 1.0, 0.0
    pending: str | None = None
    current: Trade | None = None
    entry_effective = 0.0
    entry_index = -1
    scored: list[tuple[int, float]] = []
    total = len(signal_indices)

    for i in range(first, last + 2):
        if cancel is not None and cancel.is_set():
            raise InterruptedError("backtest cancelled")
        bar = bars[i]
        if pending == "buy":
            entry_effective = bar.open * (1 + params.fee_rate)
            units = cash / entry_effective
            cash = 0.0
            entry_index = i
            current = Trade(bar.date.isoformat(), bar.open)
            result.trades.append(current)
        elif pending == "sell":
            assert current is not None
            cash = units * bar.open * (1 - params.fee_rate - params.tax_rate)
            units = 0.0
            current.exit_date = bar.date.isoformat()
            current.exit_price = bar.open
            current.ret_pct = (bar.open * (1 - params.fee_rate - params.tax_rate)
                               / entry_effective - 1) * 100
            current.holding_days = i - entry_index
            current.reason = "exit threshold"
            current = None
        pending = None

        score: float | None = None
        if i <= last:
            score = score_fn(bars[:i + 1])
            if score is not None:
                if not math.isfinite(score):
                    raise ValueError(f"{bar.date}: nonfinite score")
                scored.append((i, score))
                if units == 0 and score >= params.buy_threshold:
                    pending = "buy"
                elif units > 0 and score <= params.exit_threshold:
                    pending = "sell"
            if progress and (i - first) % 5 == 0:
                progress(i - first, total, f"評分 {bar.date}")

        # Final mark uses the same simulated liquidation as the trade ledger.
        if i == last + 1 and units > 0:
            assert current is not None
            cash = units * bar.close * (1 - params.fee_rate - params.tax_rate)
            units = 0.0
            current.exit_date = bar.date.isoformat()
            current.exit_price = bar.close
            current.ret_pct = (bar.close * (1 - params.fee_rate - params.tax_rate)
                               / entry_effective - 1) * 100
            current.holding_days = i - entry_index
            current.reason = "end of backtest"

        result.dates.append(bar.date.isoformat())
        result.equity.append(cash + units * bar.close)
        result.scores.append(score)
        result.in_position.append(units > 0)

    base = bars[first].close * (1 + params.fee_rate)
    result.bh_equity = [bars[i].close / base for i in range(first, last + 2)]
    result.bh_equity[-1] *= 1 - params.fee_rate - params.tax_rate
    trades = result.trades
    winners = sum(t.ret_pct > 0 for t in trades)
    years = max(len(result.dates) / (244 if params.market == "tw" else 252), 1e-9)
    result.stats = {
        "回測區間": f"{result.dates[0]} ～ {result.dates[-1]}（{len(result.dates)} 個交易日）",
        "策略報酬": f"{(result.equity[-1] - 1) * 100:+.1f}%",
        "買進持有報酬": f"{(result.bh_equity[-1] - 1) * 100:+.1f}%",
        "策略年化報酬": f"{(result.equity[-1] ** (1 / years) - 1) * 100:+.1f}%",
        "交易次數": f"{len(trades)} 次（勝 {winners}）",
        "勝率": f"{winners / len(trades) * 100:.0f}%" if trades else "—",
        "平均單筆報酬": f"{sum(t.ret_pct for t in trades) / len(trades):+.1f}%" if trades else "—",
        "平均持有天數": f"{sum(t.holding_days for t in trades) / len(trades):.0f} 日" if trades else "—",
        "策略最大回撤": f"{_max_drawdown(result.equity):.1f}%",
        "買進持有最大回撤": f"{_max_drawdown(result.bh_equity):.1f}%",
        "持有時間比例": f"{sum(result.in_position) / len(result.in_position) * 100:.0f}%",
    }
    for lo, hi, label in _BUCKETS:
        returns = [(bars[i + 20].close / bars[i].close - 1) * 100
                   for i, score in scored if lo <= score < hi and i + 20 < len(bars)]
        if returns:
            result.bucket_stats.append({
                "bucket": label, "days": len(returns),
                "avg_fwd20": sum(returns) / len(returns),
                "win_rate": sum(value > 0 for value in returns) / len(returns) * 100,
            })
    if progress:
        progress(total, total, "回測完成")
    return result
