"""Run one strategy step against Trading 212 (practice account by default).

    export T212_API_KEY=...   # and T212_API_SECRET=... if your key has one
    python -m finobot.live --t212 AAPL_US_EQ --yahoo AAPL --strategy sma_crossover --budget 50          # dry run
    python -m finobot.live --t212 AAPL_US_EQ --yahoo AAPL --strategy sma_crossover --budget 50 --execute

Run it once a day (e.g. cron, after the market closes). It works out the target position from
daily prices and places one market order to move the holding towards it.
"""
from __future__ import annotations
import argparse
from datetime import date, timedelta
from . import data
from .strategies import STRATEGIES
from .trading212 import Trading212

MIN_TRADE_VALUE = 1.0  # skip tiny rebalances that would just cost spread


def plan(target_weight: float, budget: float, price: float, held_qty: float, free_cash: float) -> float:
    """Quantity to trade (+buy / -sell) to hold `target_weight * budget` worth of the instrument."""
    want_qty = target_weight * budget / price
    delta = want_qty - held_qty
    if delta > 0:
        delta = min(delta, free_cash / price * 0.99)  # never spend more than available cash
    if abs(delta * price) < MIN_TRADE_VALUE:
        return 0.0
    return delta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--t212", required=True, help="Trading 212 ticker, e.g. AAPL_US_EQ or VUSAl_EQ")
    ap.add_argument("--yahoo", required=True, help="Yahoo ticker for price history, e.g. AAPL or VUSA.L")
    ap.add_argument("--strategy", default="sma_crossover", choices=STRATEGIES)
    ap.add_argument("--budget", type=float, default=50.0, help="Max money this bot may allocate")
    ap.add_argument("--execute", action="store_true", help="Actually place the order (otherwise dry run)")
    ap.add_argument("--live", action="store_true", help="Use the REAL-money account instead of practice")
    a = ap.parse_args(argv)

    if a.live and input("LIVE account, real money. Type 'yes' to continue: ") != "yes":
        return

    prices = data.load_yahoo(a.yahoo, str(date.today() - timedelta(days=500)))
    weight = float(STRATEGIES[a.strategy](prices).iloc[-1])

    t212 = Trading212(live=a.live)
    cash = t212.cash()
    pos = t212.position(a.t212)
    held = pos["quantity"] if pos else 0.0
    price = pos["currentPrice"] if pos else float(prices.iloc[-1])  # Yahoo price fallback (may differ by FX)

    qty = plan(weight, a.budget, price, held, cash["free"])
    env = "LIVE" if a.live else "PRACTICE"
    print(f"[{env}] {a.strategy}: target weight={weight:.0%}, held={held}, price~{price:.2f}, "
          f"free cash={cash['free']:.2f} -> order qty {qty:+.6f}")

    if qty == 0:
        print("Nothing to do.")
    elif a.execute:
        print("Order placed:", t212.market_order(a.t212, qty))
    else:
        print("Dry run: add --execute to place the order.")


if __name__ == "__main__":
    main()
