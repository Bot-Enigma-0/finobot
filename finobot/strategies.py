"""Strategies return a target position series in [0, 1] (fraction of capital invested).

Signals are computed on day t's close and executed on day t+1 by the backtester,
so there is no look-ahead bias.
"""
from __future__ import annotations
import pandas as pd


def buy_and_hold(prices: pd.Series) -> pd.Series:
    return pd.Series(1.0, index=prices.index)


def sma_crossover(prices: pd.Series, fast: int = 50, slow: int = 200) -> pd.Series:
    f, s = prices.rolling(fast).mean(), prices.rolling(slow).mean()
    return (f > s).astype(float)


def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100)


def rsi_mean_reversion(prices: pd.Series, period: int = 14, low: float = 30, high: float = 70) -> pd.Series:
    """Buy when oversold (RSI < low), sell when overbought (RSI > high), hold otherwise."""
    r = rsi(prices, period)
    pos = pd.Series(float("nan"), index=prices.index)
    pos[r < low] = 1.0
    pos[r > high] = 0.0
    return pos.ffill().fillna(0.0)


def momentum(prices: pd.Series, lookback: int = 126) -> pd.Series:
    """Time-series momentum: invested when trailing return over `lookback` days is positive."""
    return (prices.pct_change(lookback) > 0).astype(float)


def bollinger_reversion(prices: pd.Series, window: int = 20, k: float = 2.0) -> pd.Series:
    mid = prices.rolling(window).mean()
    sd = prices.rolling(window).std()
    pos = pd.Series(float("nan"), index=prices.index)
    pos[prices < mid - k * sd] = 1.0
    pos[prices > mid] = 0.0
    return pos.ffill().fillna(0.0)


STRATEGIES = {
    "buy_and_hold": buy_and_hold,
    "sma_crossover": sma_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
    "momentum": momentum,
    "bollinger_reversion": bollinger_reversion,
}
