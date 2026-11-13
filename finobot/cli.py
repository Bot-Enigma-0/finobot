"""Compare strategies:  python -m finobot.cli --ticker VUSA.L --start 2015-01-01"""
from __future__ import annotations
import argparse
import pandas as pd
from . import data, backtest
from .strategies import STRATEGIES


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest and compare trading strategies")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--ticker", default="SPY", help="Yahoo ticker, e.g. SPY, VUSA.L, BTC-GBP")
    src.add_argument("--csv", help="CSV file with Date and Close columns")
    src.add_argument("--synthetic", action="store_true", help="Use random offline data")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--capital", type=float, default=50.0)
    ap.add_argument("--fee-pct", type=float, default=0.001, help="Proportional cost per trade")
    ap.add_argument("--fee-fixed", type=float, default=0.0, help="Flat fee per trade")
    ap.add_argument("--plot", help="Save equity curves to this PNG (needs matplotlib)")
    a = ap.parse_args(argv)

    if a.synthetic:
        prices = data.synthetic()
    elif a.csv:
        prices = data.load_csv(a.csv)
    else:
        prices = data.load_yahoo(a.ticker, a.start, a.end)

    results = [backtest.run(prices, fn(prices), a.capital, a.fee_pct, a.fee_fixed, name)
               for name, fn in STRATEGIES.items()]
    results.append(backtest.dca(prices, a.capital, a.fee_pct, a.fee_fixed))

    table = pd.DataFrame([r.metrics() for r in results]).set_index("strategy")
    print(f"\n{prices.name}  {prices.index[0].date()} -> {prices.index[-1].date()}  "
          f"capital={a.capital}  fee={a.fee_pct:.2%} + {a.fee_fixed}/trade\n")
    print(table.sort_values("sharpe", ascending=False).to_string())

    if a.plot:
        import matplotlib.pyplot as plt
        pd.DataFrame({r.name: r.equity for r in results}).plot(figsize=(11, 6), logy=True)
        plt.title(f"Equity curves — {prices.name}")
        plt.ylabel("Equity")
        plt.tight_layout()
        plt.savefig(a.plot, dpi=120)
        print(f"\nSaved plot to {a.plot}")


if __name__ == "__main__":
    main()
