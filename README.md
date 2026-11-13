# finobot

A small, backtesting-first playground for comparing classic algorithmic trading
strategies against simple investing baselines (buy-and-hold, monthly DCA).

## Quick start
```bash
pip install -r requirements.txt
python -m finobot.cli --ticker VUSA.L --start 2015-01-01 --capital 50
python -m finobot.cli --ticker BTC-GBP --start 2019-01-01 --fee-pct 0.005
python -m finobot.cli --synthetic          # offline random data
python -m finobot.cli --csv my_prices.csv  # Date,Close columns
pytest -q
```

## Strategies (`finobot/strategies.py`)
| name | idea |
|---|---|
| buy_and_hold | baseline |
| monthly_dca | spread capital evenly over months (your "investor" baseline) |
| sma_crossover | trend: long when 50-day SMA > 200-day SMA |
| momentum | long when trailing 6-month return > 0 |
| rsi_mean_reversion | buy RSI<30, sell RSI>70 |
| bollinger_reversion | buy below lower band, sell at the mean |

Add your own: write `fn(prices) -> Series of 0..1 positions` and register it in `STRATEGIES`.

## Notes on realism
- Signals use day *t* close and execute on *t+1* (no look-ahead; there's a test for it).
- **Fees matter enormously at £50.** A £1 flat fee is 2% per trade — try `--fee-fixed 1`.
  Use a zero-commission / fractional-share broker, and remember the spread (`--fee-pct`).
- A good backtest does not predict future returns. Watch out for overfitting parameters.

## Trading 212 (practice account)
1. In the Trading 212 app, switch to **Practice**, then go to Settings -> API (Beta) and generate a key.
   Give it only the permissions you need (account, portfolio, orders).
2. Export the credentials (never commit them):
   ```bash
   export T212_API_KEY=...
   export T212_API_SECRET=...   # if your key came with a secret
   ```
3. Do a dry run, then place a real practice order:
   ```bash
   python -m finobot.live --t212 AAPL_US_EQ --yahoo AAPL --strategy sma_crossover --budget 50
   python -m finobot.live --t212 AAPL_US_EQ --yahoo AAPL --strategy sma_crossover --budget 50 --execute
   ```
4. Schedule it to run once a day (cron or Task Scheduler).

Notes:
- It uses the practice server by default. `--live` uses real money and asks you to confirm.
- Trading 212 tickers look like `AAPL_US_EQ` (US) or `VUSAl_EQ` (London). `Trading212().instruments()` lists them all.
- The API is beta and strictly rate limited. The client retries after a 429 response.
- The order is sized from the Trading 212 price when you already hold the stock, otherwise
  from the Yahoo price, which can be in a different currency. The cash cap stops it overspending.
