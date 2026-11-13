import pandas as pd
from finobot import data, backtest
from finobot.strategies import STRATEGIES


def test_buy_and_hold_tracks_price_without_fees():
    p = data.synthetic(500)
    r = backtest.run(p, STRATEGIES["buy_and_hold"](p), 50, fee_pct=0)
    # invested from day 1 (signal day 0 executed day 1)
    assert abs(r.equity.iloc[-1] / 50 - p.iloc[-1] / p.iloc[1]) < 1e-9


def test_no_lookahead():
    # A strategy that "knows" tomorrow's return must not profit once shifted correctly:
    p = data.synthetic(1000, seed=3)
    cheat = (p.shift(-1) > p).astype(float).fillna(0)
    honest = backtest.run(p, cheat, 50, fee_pct=0).equity.iloc[-1]
    perfect = 50 * (1 + p.pct_change().clip(lower=0)).prod()
    assert honest < perfect / 2


def test_all_strategies_run_and_fees_reduce_return():
    p = data.synthetic(800)
    for name, fn in STRATEGIES.items():
        free = backtest.run(p, fn(p), 50, fee_pct=0).equity.iloc[-1]
        paid = backtest.run(p, fn(p), 50, fee_pct=0.01).equity.iloc[-1]
        assert paid <= free + 1e-9, name


def test_dca():
    p = pd.Series(100.0, index=pd.bdate_range("2020-01-01", periods=300))
    r = backtest.dca(p, 50, fee_pct=0)
    assert abs(r.equity.iloc[-1] - 50) < 1e-9
