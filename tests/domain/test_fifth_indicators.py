"""Hand-checkable batch-five indicator boundaries and values."""

import ast
from pathlib import Path

import pytest

from barometer.domain import indicators as ind


def test_wilder_ema_and_roc_have_explicit_warmup():
    assert ind.wilder_ema([1, 2, 3, 4], 2) == pytest.approx([None, 1.5, 2.25, 3.125])
    values = ind.roc([10, 11, 12], 2)
    assert values[:2] == [None, None]
    assert values[-1] == pytest.approx(20.0)


def test_stochastic_constant_halfway_and_macd_flat():
    k, d = ind.stochastic_kd([10] * 12, [0] * 12, [5] * 12)
    assert k[:8] == [None] * 8
    assert k[-1] == pytest.approx(50)
    assert d[-1] == pytest.approx(50)
    dif, signal, hist = ind.macd([10] * 40)
    assert dif[-1] == pytest.approx(0)
    assert signal[-1] == pytest.approx(0)
    assert hist[-1] == pytest.approx(0)


def test_dmi_obv_cross_and_slope():
    highs = [float(11 + i) for i in range(40)]
    lows = [float(9 + i) for i in range(40)]
    closes = [float(10 + i) for i in range(40)]
    plus, minus, adx = ind.dmi_adx(highs, lows, closes)
    assert plus[-1] > 0 and minus[-1] == pytest.approx(0)
    assert adx[-1] == pytest.approx(100)
    assert ind.obv([10, 11, 10], [100, 200, 50]) == [0.0, 200.0, 150.0]
    assert ind.ma_slope([10, 11, 12], 2) == pytest.approx(20)
    assert ind.crossed_within([-1, -1, 1], [0, 0, 0], 2, "up")
    assert not ind.crossed_within([-1, -1, 1], [0, 0, 0], 2, "down")


def test_domain_indicators_do_not_import_dataframe_libraries():
    tree = ast.parse(Path(ind.__file__).read_text(encoding="utf-8"))
    names = {alias.name.split(".")[0] for node in ast.walk(tree)
             if isinstance(node, (ast.Import, ast.ImportFrom))
             for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])}
    assert not names & {"pandas", "numpy"}
