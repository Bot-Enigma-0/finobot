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

## Next steps
Paper-trade before going live (e.g. Alpaca or Trading 212 practice accounts), then wire
up a broker API behind the same strategy interface.
