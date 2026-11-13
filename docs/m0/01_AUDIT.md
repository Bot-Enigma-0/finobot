# M0.1: Existing codebase audit

Audited commit: `5c60011` (branch `claude/friendly-euler-w0wty9`), 2026-11-11.
**No code was changed during the audit.**

## 1. Inventory

| File | Lines | What it does |
|---|---|---|
| `finobot/data.py` | 28 | `load_yahoo` (yfinance, `auto_adjust=True`, Close only), `load_csv`, `synthetic` (GBM prices) |
| `finobot/strategies.py` | 56 | Five single-asset, long-only target-weight functions: buy-and-hold, SMA crossover, RSI reversion, time-series momentum, Bollinger reversion |
| `finobot/backtest.py` | 78 | Single-asset loop backtester (proportional + fixed fees), `Result.metrics()` (CAGR, Sharpe, max DD), monthly DCA benchmark |
| `finobot/cli.py` | 50 | argparse CLI that runs every strategy on one ticker and prints a table |
| `finobot/trading212.py` | 84 | Trading 212 REST client: auth, 429 back-off, cash/positions/instruments/market order/cancel |
| `finobot/live.py` | 67 | Daily runner: Yahoo prices → strategy → one T212 market order (dry run by default) |
| `tests/test_backtest.py` | 33 | 4 tests: buy-and-hold tracking, look-ahead check, fees reduce return, DCA |
| `tests/test_trading212.py` | 35 | 3 tests with a mocked HTTP session |
| `requirements.txt` | 5 | Unpinned dependencies |
| `README.md` | — | Describes the prototype |
| `docs/DESIGN.md` | — | Previous design proposal (partly superseded by the new spec, see §4) |

Test status at the audited commit: 7/7 passing (from the last run in this session).

## 2. Findings by component

### `data.py`
- **Prices are adjusted at download time** (`auto_adjust=True`). Yahoo back-adjusts the
  whole history whenever a dividend or split happens, so a backtest that uses today's download
  sees adjustments that were not known on the simulated date. This is a **look-ahead risk** and
  conflicts with the point-in-time requirement.
- Downloads Close only: no OHLC, volume or corporate actions.
- No provenance (source, retrieval time, available-at time), validation, caching or storage.
  Every run downloads again.
- `synthetic()` (GBM generator) is useful as a deterministic test fixture.

### `strategies.py`
- The signal maths (SMA, RSI, momentum, Bollinger) is correct and short. One edge case:
  `rsi()` returns 100 when both average gain and average loss are 0 (flat prices). It should
  be undefined (NaN) or 50.
- Architecturally unsuitable: these are plain functions with no metadata (hypothesis,
  parameters, universe, horizon, cost assumptions), single-asset only, long-only `[0, 1]`
  weights, and pandas Series in/out. They can't express long/short, pairs or cross-sectional
  strategies.

### `backtest.py`
- The no-look-ahead approach is sound (`target.shift(1)`, so the signal at *t* trades at *t+1*),
  and there is a test for it.
- **Execution assumption is too optimistic for the new spec:** it fills at the next *close*
  with no spread or slippage model and no execution-price choice (open/close/VWAP).
- Single asset, long-only, no short positions, borrow or financing costs, no calendar, no
  corporate actions, no multi-currency.
- It only rebalances when the target weight changes, so portfolio drift isn't modelled. That's
  fine for 0/1 signals, but wrong for fractional weights.
- Metrics: Sharpe has no risk-free rate, there are no confidence intervals, and no Sortino,
  turnover or exposure.
- The DCA benchmark logic is correct and small.

### `cli.py`
- A thin wrapper around the above. It has no future value.

### `trading212.py`
- **Auth is consistent with the current docs:** the API key is the Basic-auth username and the
  secret the password. Demo and live base URLs are also correct. See `03_DATA_AND_BROKER_VERIFICATION.md`.
- The single-token legacy auth branch is probably obsolete.
- **Unsafe for live use under the new spec:** no order-state tracking, no reconciliation before
  a retry, no idempotency handling, and timeouts surface as raw exceptions. On the plus side it
  only retries on HTTP 429, where the request was rejected, so that path does not cause
  duplicate orders.
- Endpoint paths have not been tested against the real API.

### `live.py`
- **It conflicts with the architecture:** the strategy output goes straight to an order with
  no independent risk engine; position sizing uses a Yahoo price that may be in a different
  currency; FX fees are ignored; and there is no audit record.
- Safety defaults (practice account, dry run unless `--execute`) are good ideas to carry forward.

### Tests
- The look-ahead test idea ("a strategy that sees tomorrow must not get a perfect result")
  should be generalised into the new backtester's test suite.

### Repo hygiene
- No `pyproject.toml`, lock file, linting, type checking, CI or `.gitignore`.

## 3. Disposition of every component

| Component | Disposition | Destination / action | When |
|---|---|---|---|
| `data.synthetic` | **Refactor** | `tests/fixtures/synthetic.py`: multi-asset, OHLCV, with injectable splits/dividends/gaps for validation tests | M1 (T1.10) |
| `data.load_yahoo` | **Replace** | `YFinanceProvider` adapter: unadjusted OHLCV + actions, raw payload stored, flagged *unofficial* | M1 (T1.9) |
| `data.load_csv` | **Refactor** | `CsvProvider` (local files, e.g. purchased data later) | M1 (T1.10) |
| `strategies.*` indicator maths | **Refactor** | `features/indicators.py` (SMA, RSI with the flat-price fix, momentum, Bollinger z-score) | M2/M3 |
| `strategies.*` as strategies | **Replace** | New `Strategy` interface with a metadata spec; the old logic becomes reference strategies | M3 |
| `backtest.run` | **Replace** | Multi-asset event-driven engine | M2 |
| `backtest.Result.metrics` | **Refactor** | `research/metrics.py` (adds risk-free rate, Sortino, turnover, exposure, CIs) | M2 |
| `backtest.dca` | **Retain → move** | `benchmarks/dca.py` | M2 |
| `cli.py` | **Remove** | Superseded by the new `finobot` CLI | M1 (T1.0, moved to `legacy/`) |
| `trading212.py` | **Refactor (parked)** | `brokers/trading212/` adapter behind the `Broker` protocol; drop legacy auth; add reconciliation-before-retry | M8 |
| `live.py` | **Remove** | Replaced by the live runner + risk engine; keep its dry-run/practice defaults as requirements | M1 (T1.0, moved to `legacy/`) |
| `tests/test_backtest.py` | **Refactor** | Look-ahead and fee tests ported to the new engine | M2 |
| `tests/test_trading212.py` | **Refactor (parked)** | Ported with the adapter | M8 |
| `requirements.txt` | **Replace** | `pyproject.toml` + `uv.lock` | M1 (T1.0) |
| `README.md` | **Replace** | New README for the research platform | M1 (T1.0) |
| `docs/DESIGN.md` | **Retain as history** | Marked *superseded*; conflicts listed below | M0 (done) |

"Remove" means *moved to `legacy/`* (excluded from the package, tests and lint) in T1.0, not
deleted. It can be deleted once M2 and M8 have ported what they need.

## 4. Where `docs/DESIGN.md` conflicts with the new specification

| DESIGN.md said | New spec says | Resolution |
|---|---|---|
| Research universe of GBP LSE ETFs | Broad research universe; only live is narrow | New spec |
| Long-only pairs/stat-arb in research | Long/short in research, with realistic borrow modelling | New spec |
| SQLite for ops, Streamlit dashboard | PostgreSQL ops, FastAPI + Plotly | New spec |
| Daily decisions only | Multiple horizons, daily first, no HFT | New spec |
| Local LLMs by default | Hosted LLM allowed for public news only; LLMs never issue signals | New spec |
| Single always-on machine | Local research + cloud live service | New spec |

Still valid and carried forward: bitemporal storage, one code path for research and live, an
independent risk engine, no retry of uncertain orders, a locked hold-out, DSR/PBO, and the
feasibility analysis for £100.
