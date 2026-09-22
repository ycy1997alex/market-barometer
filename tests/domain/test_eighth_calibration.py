"""第八批 8-12：警示門檻的實證校準（頻率統計）。

§7.2 的目標：單一指標一年亮燈 **5~15 次**，而不是 200 次或 0 次。

⚠️ 這是**頻率統計**，不是「準不準」。§8 的界線：不得用「與未來報酬的相關性」
回頭調參數 —— 這裡只數亮燈次數，沒有任何報酬欄位進得來。
⚠️ 兩把尺各做一次：barometer 的警示比例尺在這裡，research 的 ±100 加權尺另算。
"""
from __future__ import annotations

import datetime as dt

from barometer.domain import macro_replay


def _daily(start: dt.date, n: int, value_of):
    return [((start + dt.timedelta(days=i)).isoformat(), value_of(i)) for i in range(n)]


def test_counts_alert_days_per_indicator_and_normalises_per_year():
    start = dt.date(2026, 1, 1)
    # VIX 一路 40（永遠亮燈）、10Y-2Y 一路 +1（永遠不亮）
    series = {"vix": _daily(start, 200, lambda i: 40.0),
              "t10y2y": _daily(start, 200, lambda i: 1.0)}

    stats = macro_replay.alert_frequency(series, start, start + dt.timedelta(days=199))

    assert stats["vix"].evaluated == 200
    assert stats["vix"].hits == 200
    assert stats["vix"].per_year > 300          # 一年 365 天都亮
    assert stats["t10y2y"].hits == 0
    assert stats["t10y2y"].per_year == 0.0


def test_indicators_that_cannot_be_evaluated_are_absent_not_zero():
    start = dt.date(2026, 1, 1)
    series = {"vix": _daily(start, 30, lambda i: 20.0)}

    stats = macro_replay.alert_frequency(series, start, start + dt.timedelta(days=29))

    assert "vix" in stats
    assert "cpi" not in stats, "沒有資料的指標不該以 0 次亮燈的樣子出現在報告裡"


def test_a_series_excluded_from_the_replay_never_appears():
    """8-6 的原油曲線不進回測，也就不該出現在校準報告裡。"""
    start = dt.date(2026, 1, 1)
    series = {"vix": _daily(start, 30, lambda i: 20.0),
              "oil_curve": _daily(start, 30, lambda i: -12.0)}

    stats = macro_replay.alert_frequency(series, start, start + dt.timedelta(days=29))

    assert "oil_curve" not in stats


def test_the_report_has_no_return_or_performance_column():
    """§8 的界線寫成測試：報告裡不得出現任何報酬欄位。"""
    import ast
    from pathlib import Path

    source = Path(macro_replay.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not any(word in name for name in names
                   for word in ("return", "profit", "performance", "sharpe"))


def test_episodes_count_transitions_not_days():
    """「一年亮燈 5~15 次」數的是**次**：連續亮 30 天是一次，不是 30 次。"""
    start = dt.date(2026, 1, 1)
    # 前 10 天亮、接著 10 天暗、再 10 天亮 → 兩次
    series = {"vix": _daily(start, 30, lambda i: 40.0 if i < 10 or i >= 20 else 12.0)}

    stats = macro_replay.alert_frequency(series, start, start + dt.timedelta(days=29))

    assert stats["vix"].hits == 20          # 亮著的天數
    assert stats["vix"].episodes == 2       # 亮燈的次數
    assert stats["vix"].episodes_per_year > stats["vix"].episodes
