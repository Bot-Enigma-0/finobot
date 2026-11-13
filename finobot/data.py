"""Price data loading: Yahoo Finance, local CSV, or synthetic (offline)."""
from __future__ import annotations
import numpy as np
import pandas as pd


def load_yahoo(ticker: str, start: str, end: str | None = None) -> pd.Series:
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # multi-index columns in newer yfinance
        close = close.iloc[:, 0]
    return close.dropna().rename(ticker)


def load_csv(path: str, date_col: str = "Date", price_col: str = "Close") -> pd.Series:
    df = pd.read_csv(path, parse_dates=[date_col], index_col=date_col)
    return df[price_col].dropna().sort_index()


def synthetic(days: int = 1500, seed: int = 0, drift: float = 0.0003, vol: float = 0.012) -> pd.Series:
    """Geometric Brownian motion prices — useful for offline tests."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, days)
    idx = pd.bdate_range("2018-01-01", periods=days)
    return pd.Series(100 * np.exp(np.cumsum(rets)), index=idx, name="SYN")
