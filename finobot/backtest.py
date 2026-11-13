"""Vectorised backtester with fees, plus a monthly DCA benchmark."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class Result:
    name: str
    equity: pd.Series
    trades: int
    fees_paid: float

    def metrics(self) -> dict:
        eq = self.equity
        rets = eq.pct_change().dropna()
        years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
        cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
        sharpe = rets.mean() / rets.std() * np.sqrt(TRADING_DAYS) if rets.std() > 0 else 0.0
        max_dd = (eq / eq.cummax() - 1).min()
        return {
            "strategy": self.name,
            "final": round(eq.iloc[-1], 2),
            "total_return_%": round((eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2),
            "CAGR_%": round(cagr * 100, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown_%": round(max_dd * 100, 2),
            "trades": self.trades,
            "fees": round(self.fees_paid, 2),
        }


def run(prices: pd.Series, target: pd.Series, capital: float = 50.0,
        fee_pct: float = 0.001, fee_fixed: float = 0.0, name: str = "strategy") -> Result:
    """Simulate holding `target` fraction of equity, trading at next day's close.

    fee_pct: proportional cost per trade (spread + commission), e.g. 0.001 = 0.1%.
    fee_fixed: flat fee per trade in account currency (matters a lot at £50!).
    """
    pos = target.reindex(prices.index).fillna(0.0).clip(0, 1).shift(1).fillna(0.0)
    cash, units, fees, trades = capital, 0.0, 0.0, 0
    equity = np.empty(len(prices))
    for i, (p, w) in enumerate(zip(prices.values, pos.values)):
        value = cash + units * p
        desired_units = w * value / p
        delta = desired_units - units
        if abs(delta * p) > 1e-6 and (i == 0 or w != pos.values[i - 1]):
            cost = abs(delta * p) * fee_pct + fee_fixed
            cash -= delta * p + cost
            units = desired_units
            fees += cost
            trades += 1
        equity[i] = cash + units * p
    return Result(name, pd.Series(equity, index=prices.index), trades, fees)


def dca(prices: pd.Series, capital: float = 50.0, fee_pct: float = 0.001,
        fee_fixed: float = 0.0, name: str = "monthly_dca") -> Result:
    """Invest `capital` in equal chunks on the first trading day of each month.

    Equity includes not-yet-invested cash so it's comparable to the other strategies.
    """
    months = prices.groupby(prices.index.to_period("M")).head(1).index
    chunk = capital / len(months)
    buy_days = set(months)
    cash, units, fees = capital, 0.0, 0.0
    equity = np.empty(len(prices))
    for i, (d, p) in enumerate(prices.items()):
        if d in buy_days:
            cost = chunk * fee_pct + fee_fixed
            units += (chunk - cost) / p
            cash -= chunk
            fees += cost
        equity[i] = cash + units * p
    return Result(name, pd.Series(equity, index=prices.index), len(months), fees)
