# Autonomous Quantitative Trading and Research System: Design Proposal

Status: **draft for review. No implementation yet.**
Date: 2026-11-07

Provider facts (prices, limits, availability) were checked with a quick web search on this date
where cited. Everything marked **[verify]** could not be confirmed and must be checked before
it is relied on. Provider terms change often, so treat this document's numbers as starting points.

---

## 0. Executive summary and feasibility verdict

**The verdict first, because it shapes everything else.**

1. **With £100, this project can be a sound research platform. It cannot be a meaningful
   profit engine.** A strategy with a genuinely excellent 5% annual edge over the benchmark
   earns about £5 a year. One badly-timed trade, a 0.15% FX fee on every trade, or the spread
   on a thin ETF can cancel that. The value is in the *research system*: rigorous answers to
   "does this signal have predictive value after costs?", which also apply to your manual investing.

2. **You cannot tell skill from luck with £100 of live trading in any reasonable timeframe.**
   The standard error of an annualised Sharpe ratio is roughly √((1 + SR²/2) / years). After
   one year of live trading a true Sharpe of 0.5 is indistinguishable from 0 (±1.0). Even ten
   years only narrows it to about ±0.33. **Statistical evidence has to come from backtests,
   walk-forward tests and paper trading. Live trading at £100 only proves the plumbing
   works** (orders, fills, costs, reconciliation, risk controls).

3. **Several requested strategies conflict with the constraints.** Pairs trading and
   statistical arbitrage are long/short by construction, but short selling is banned. They can
   only survive as *long-only relative-value rotations* (hold the cheap leg, or nothing), which
   is a weaker and different strategy. This is stated plainly rather than hidden.

4. **"Real-time" must mean "as fresh as the decision frequency needs".** Free and cheap data is
   delayed (often 15 minutes or end-of-day). Trading 212's live API only accepts market orders.
   Retail latency is uncompetitive. **The system should therefore make decisions daily or
   weekly**, where retail participants are not structurally disadvantaged. Intraday or
   high-frequency approaches are out of scope at this budget.

5. **The most likely honest finding is that most strategies do not beat a passive benchmark
   after costs.** The system should be designed so that finding is *cheap to reach and easy to
   trust*. A system that confirms "buy a global index fund" with rigour is a success, not a failure.

**Recommendation:** go ahead, with the scope adjustments in §0.1, and treat milestone exit
criteria (§9) as genuine go/no-go gates.

### 0.1 Proposed scope adjustments

| Requested | Proposed | Why |
|---|---|---|
| Real-time trading | Daily (post-close) decisions, intraday monitoring for risk only | Data latency, market-only orders, costs |
| Individual stocks + broad universe | A whitelist of ~10–25 liquid **GBP-denominated LSE-listed ETFs** (equity regions, gilts, gold, commodities), with individual stocks for research only | No FX fee, tighter spreads, less idiosyncratic risk, fractional shares cover the small capital |
| Pairs / stat-arb | Long-only relative-value rotation, plus the full long/short version in **research only** | Short selling banned |
| RNN / transformer / RL | Research-only stretch goals, admitted to production only if they beat simpler models out of sample | Low signal-to-noise in daily returns, high overfitting risk |
| Order-book data | Use spread estimates and broker quotes; no full order book | Retail-affordable LSE level-2 data effectively does not exist |

---

## 1. System architecture

### 1.1 Principles

- **Point-in-time correctness everywhere.** Every observation records *when the event happened*
  and *when the system could have known it*. Models only see data that was available at decision
  time. This is the main defence against look-ahead bias, and it is designed into the storage
  layer rather than left to discipline.
- **One code path for research and production.** The backtester, the paper trader and the live
  trader call the same feature, model, decision and risk code. Only the clock and the broker
  adapter differ. Most "worked in backtest, failed live" bugs come from two separate code paths.
- **The risk engine is a separate authority.** It is a separate module with its own configuration
  and hard-coded ceilings. It has the final say on every order and cannot be bypassed by the
  decision engine.
- **NO TRADE is the default.** Every layer fails closed: missing data, stale data, model errors,
  broker errors or low confidence all lead to no action.
- **Everything is recorded.** Every decision is reproducible from the stored inputs, model
  version and configuration hash.

### 1.2 Component diagram

```
                ┌──────────────────────────── Scheduler / Orchestrator ────────────────────────────┐
                │  (daily cycle, intraday risk checks, retries, health checks, recovery on restart) │
                └──────────────────────────────────────────────────────────────────────────────────┘
                         │                │                 │                │               │
   ┌─────────────┐  ┌────▼─────┐   ┌──────▼──────┐   ┌──────▼──────┐   ┌─────▼──────┐  ┌─────▼──────┐
   │ Data sources│─▶│ Ingestion│──▶│ Storage     │──▶│ Features    │──▶│ Models     │─▶│ Decision   │
   │ (APIs, RSS) │  │ adapters │   │ (bitemporal)│   │ (PIT joins) │   │ (signals + │  │ engine     │
   └─────────────┘  └──────────┘   └──────▲──────┘   └──────▲──────┘   │ forecasts) │  │ (combine,  │
                                          │                 │          └─────▲──────┘  │ cost-aware)│
                         ┌────────────────┴───┐             │                │         └─────┬──────┘
                         │ News & event       │─────────────┘                │               │ proposed
                         │ intelligence (NLP) │  structured event features   │               │ orders
                         └────────────────────┘                              │         ┌─────▼──────┐
                                                                             │         │ RISK ENGINE│
   ┌───────────────────┐   ┌──────────────────────────┐                      │         │ (veto,     │
   │ Research harness  │──▶│ Experiment tracking      │──────────────────────┘         │ sizing,    │
   │ (backtest, WF,    │   │ (model registry, configs)│  only promoted models          │ kill switch│
   │ Monte Carlo)      │   └──────────────────────────┘                                └─────┬──────┘
   └───────────────────┘                                                                     │ approved
                                                                                     ┌───────▼───────┐
   ┌───────────────────┐        ┌───────────────────────────────┐                    │ Execution     │
   │ Dashboard /       │◀───────│ Audit log (append-only,       │◀───────────────────│ (broker-      │
   │ reports           │        │ hash-chained) + ops database  │                    │ independent)  │
   └───────────────────┘        └───────────────────────────────┘                    └───────┬───────┘
                                                                                             │
                                                                       ┌─────────────────────┼─────────────┐
                                                                       │ Trading212 │ Alpaca(paper) │ Sim  │
                                                                       └───────────────────────────────────┘
```

### 1.3 Run modes

| Mode | Clock | Broker adapter | Money |
|---|---|---|---|
| `backtest` | historical, simulated | `SimBroker` (cost and slippage model) | none |
| `paper` | real time | `SimBroker` on live data, or the T212 Practice account | none |
| `live` | real time | `Trading212Broker` (live) | ≤ £100 |

`live` needs **all** of these: a config flag, an environment variable, a confirmation file
written by a CLI command you run yourself, and passing pre-flight checks. Any one missing means
the system runs as `paper`.

### 1.4 Why this shape (and not something more ambitious)

- **A modular monolith, not microservices.** One Python package with clear module boundaries,
  run as one or two processes (the main loop, plus an optional dashboard). Microservices add
  deployment, networking and consistency problems that don't pay off for one user and £100. The
  module boundaries keep the option of splitting services out later.
- **Event-driven inside, scheduled outside.** A daily cycle is easy to reason about, test and
  replay. An internal event bus (simple in-process publish/subscribe) keeps components
  decoupled without needing Kafka.

---

## 2. Subsystem breakdown

Each subsystem lists its responsibilities, interfaces, key design decisions and how it fails.

### 2.1 Data ingestion

- **Responsibilities:** pull from each source on a schedule, normalise to a common `Observation`
  schema, attach quality flags, write to raw storage. Never transform away the raw payload.
- **Interface:** `SourceAdapter.fetch(since) -> Iterable[Observation]`. One adapter per provider.
  Adapters are stateless; progress pointers live in the ops database.
- **Observation schema (all data, not just prices):**

  | field | meaning |
  |---|---|
  | `event_time` | when the thing happened (bar close, article published, data release) |
  | `available_at` | when *we* could first have known it (ingest time, or the provider's publication time plus known delay) |
  | `source`, `source_id` | provider and its native identifier |
  | `entity` | instrument / country / commodity / series identifier |
  | `field`, `value`, `unit`, `currency` | the payload |
  | `vintage` | for revisable data (GDP, employment): which release this value comes from |
  | `quality` | `REALTIME`, `DELAYED(n min)`, `EOD`, `REVISED`, `ESTIMATED`, `UNVERIFIED`, `STALE`, `SUSPECT` |
  | `raw_ref` | pointer to the stored raw payload |

- **Quality checks:** staleness against the expected update frequency; price-jump and
  zero-volume detection; cross-source agreement where two sources exist; corporate-action
  detection (splits and dividends cause false "jumps").
- **Failure behaviour:** retries with exponential backoff and jitter; a circuit breaker per
  source; marks data `STALE` instead of forward-filling silently. The decision engine treats
  stale required inputs as "no evidence", which means NO TRADE.

### 2.2 Data storage

See §7.

### 2.3 Feature engineering

- **Point-in-time joins only:** each feature at decision time *t* uses
  `WHERE available_at <= t`, and uses the latest *vintage* known at *t* for macro series
  (for example, the GDP estimate published at the time, not the later revision).
- **Feature families:** returns over several horizons; realised and GARCH volatility;
  rolling correlations and betas; volume and estimated spreads (Corwin–Schultz or Roll
  estimators from daily high/low/close); macro surprises (actual minus consensus, where consensus
  is available) and changes; regime probabilities; event features from §2.5.
- **Feature registry:** each feature has a name, version, input list and code hash, so a
  stored decision records exactly which feature definitions produced it.
- **Leakage tests:** an automated test perturbs future data and asserts that features at *t*
  don't change.

### 2.4 Quantitative models

- **Common interface:**
  `Model.predict(features_at_t) -> Forecast(mean, std or quantiles, horizon, model_id, version)`.
  Every model outputs a **predictive distribution of the forward excess return** over a stated
  horizon, not a raw score. That makes models comparable and combinable, and gives meaningful
  confidence (§2.6).
- Rule-based strategies (momentum, mean reversion) are wrapped by fitting a *calibration
  model*: a historical mapping from signal value to the distribution of forward returns, fitted
  only on past data.
- Strategy details are in §3.

### 2.5 News and event intelligence

A pipeline that turns unstructured text into *structured, de-duplicated, point-in-time event
features*. It never trades by itself.

| Step | Approach | Notes |
|---|---|---|
| 1. Retrieve | RSS feeds, GDELT, SEC EDGAR, central bank feeds, provider news APIs | Store the full text where licensing allows, otherwise the headline, summary and URL |
| 2. Classify events | Zero-shot or few-shot classification into a fixed taxonomy (earnings, guidance, M&A, rate decision, sanctions, conflict, election, natural disaster, supply disruption, …). Start with FinBERT or a small local model; optionally use an LLM | The taxonomy is fixed and versioned so features stay stable |
| 3. Extract entities | NER plus linking to IDs: companies → tickers/ISINs, countries → ISO codes, commodities → a fixed list | Linking errors are a major error source; measure them |
| 4. Credibility and novelty | Source tier (primary filing > wire service > major outlet > aggregator > social media); novelty = 1 − max similarity to events in the previous N days | |
| 5. Map to instruments | Exposure map: entity → instruments, via sector/region ETF holdings and commodity sensitivities | Kept as a reviewable table, not a black box |
| 6. Find comparable events | Embedding search over the historical event store, filtered by event type | |
| 7. Historical reactions | Event-study method: abnormal returns versus a market model, over [−1, +5] days, with confidence intervals | Shows whether this *type* of event historically moved prices, not causation |
| 8. Features out | Per instrument and day: event counts by type, sentiment, novelty-weighted intensity, historical-reaction priors | |

**Design rules from your brief:**
- **Deduplication:** articles are clustered into *events* (embedding similarity + shared
  entities + time window). Features are computed per event, not per article, so 40 articles
  about one rate decision count once.
- **Already priced in:** the main event feature is the *surprise* (actual vs. expected, or
  novelty), and we record the price move between `event_time` and `available_at`. If the
  market moved before we could act, the expected remaining edge is reduced accordingly.
- **Correlation vs. causation:** the event study measures association. The system makes no
  causal claims. The model is only credited with predictive value if out-of-sample tests show it.
- **LLM use and secrets:** if an external LLM API is used, only *public text* (news) is sent.
  Never credentials, account balances or positions. All LLM outputs are cached with model
  version, so results stay reproducible.

**Expectation management:** academic evidence suggests news sentiment has small, short-lived
predictive power, mostly for individual stocks and mostly within a day. For a daily ETF strategy
the most useful outputs are probably **risk features** ("high event intensity: widen
uncertainty / reduce size") rather than directional signals. This is a hypothesis to test.

### 2.6 Decision engine

Combines forecasts into BUY / SELL / HOLD / NO TRADE, per instrument, per cycle.

1. **Combine forecasts.** Stacking or Bayesian model averaging, with weights from each model's
   *out-of-sample log predictive score* over a trailing window (never in-sample fit). This
   naturally down-weights models that stop working. Disagreement between models increases the
   variance of the combined forecast: under model averaging, the combined variance =
   average within-model variance + variance *between* models.
2. **Adjust for regime and volatility.** The HMM regime probability and the GARCH volatility
   forecast scale the predictive variance and can enter as features.
3. **Subtract costs.** Net expected return = combined mean − expected round-trip cost (spread +
   FX + slippage + commission) ÷ expected holding period.
4. **Probabilistic decision rule.** For a candidate change in position Δw:
   - compute **P(net return over horizon > 0)** from the combined predictive distribution;
   - act only if P > p_min (e.g. 0.60) **and** the expected utility gain (mean − λ·variance)
     exceeds a cost hurdle;
   - otherwise **NO TRADE** (when flat) or **HOLD** (when invested).
5. **Size the position:** fractional Kelly (≤ 0.25 Kelly) on the net forecast, capped by risk
   limits. Kelly with estimated parameters is dangerous at full size; a quarter or less is standard.
6. **Explain the decision:** each decision stores a breakdown: per-model forecasts, weights,
   costs, regime, triggering events, and which threshold allowed or blocked it.

**Making "probabilistic confidence" honest:** predictive distributions must be *calibrated*.
The research harness checks calibration (probability integral transform histograms, reliability
diagrams, Brier score for P(r > 0)) and can apply conformal prediction for guaranteed-coverage
intervals. If a model says "70%", it must be right about 70% of the time out of sample, or it
isn't used.

### 2.7 Risk engine

See §8. In short: a separate module that receives proposed orders, applies a fixed sequence of
checks against live broker state, and returns `APPROVE(order')` (possibly reduced) or
`REJECT(reason)`. It can also act on its own: if the kill switch is set or a loss limit is hit,
it blocks all buys and can propose exits.

### 2.8 Execution and broker integration

- **Broker-independent interface:**

  ```
  class Broker(Protocol):
      def account() -> AccountState            # cash, buying power, currency
      def positions() -> list[Position]
      def instrument(symbol) -> InstrumentInfo # tradable?, min qty, fractional?, currency, hours
      def quote(symbol) -> Quote | None        # bid/ask if available
      def submit(order: OrderRequest) -> OrderAck
      def order_status(broker_order_id) -> OrderState
      def cancel(broker_order_id) -> None
      def fills(since) -> list[Fill]
  ```
  Adapters: `SimBroker`, `Trading212Broker` (practice and live), and optionally
  `AlpacaBroker` (paper) for testing order-type logic the T212 live API doesn't offer.

- **Order state machine:** `PROPOSED → RISK_APPROVED → SUBMITTED → ACKED →
  {FILLED | PARTIALLY_FILLED | REJECTED | CANCELLED | EXPIRED | UNKNOWN}`. Every transition is
  written to the audit log *before* the next action.
- **Duplicate-order protection.** Trading 212's order endpoint is **not idempotent** in the
  current beta ([T212 docs](https://docs.trading212.com/api/orders)), so a naive retry after a
  timeout could buy twice. Rule: after any ambiguous outcome (timeout, 5xx), the order goes to
  `UNKNOWN`, **no retry**, and the system reconciles by polling orders and positions. It only
  resubmits once it has positively confirmed the original did not execute.
- **Reconciliation:** at startup and every cycle, broker positions and cash are compared with the
  internal ledger. Any mismatch beyond a tolerance halts trading and raises an alert.
- **Credentials:** environment variables or the OS keychain only; loaded through a single
  `secrets` module. The logging layer has a redaction filter (known secret values and
  `Authorization` headers are scrubbed); a test asserts no secret appears in log output.

### 2.9 Research harness

See §9 (roadmap) and the evaluation methodology in §3.4.

### 2.10 Monitoring, reporting and audit

- **Audit log:** append-only table; each record holds the hash of the previous record (a hash
  chain), so tampering or loss is detectable. It records data snapshots referenced by decisions,
  forecasts, decisions, risk verdicts, orders, fills, config changes and kill-switch events.
- **Dashboard:** Streamlit, read-only, local-only by default. Pages: portfolio and cash; open
  orders; recent transactions; market conditions (regime, volatility, correlations); forecasts
  and signals per instrument with explanations; risk usage (exposure versus limits, daily P&L
  versus the loss limit); strategy performance versus benchmarks, live and backtest side by side.
- **Alerts:** email or a push service (e.g. ntfy, Telegram bot) for: kill switch, loss limit,
  reconciliation mismatch, stale data, repeated broker errors, missed run.
- **Health:** heartbeat file plus `/health` check; the scheduler detects missed runs.

---

## 3. Recommended strategies and theoretical foundations

### 3.1 The benchmarks to beat (implemented first)

| Benchmark | Why |
|---|---|
| Buy-and-hold global equity ETF (e.g. a FTSE All-World or MSCI World UCITS ETF in GBP) | The realistic alternative use of the money |
| 60/40 equity/gilt ETF portfolio, rebalanced monthly | Multi-asset passive baseline |
| Monthly investing (DCA) in the same | Mirrors typical manual investing |
| Cash (SONIA / money-market rate) | Risk-free hurdle |
| Random-entry strategy with the same turnover | Separates "signal" from "exposure plus costs" |

### 3.2 Core strategies (production candidates)

| Strategy | Foundation | Implementation notes | Prior expectation |
|---|---|---|---|
| **Time-series momentum / trend** | Moskowitz, Ooi & Pedersen (2012); Hurst, Ooi & Pedersen (2017): persistent multi-month trends across asset classes, linked to under-reaction and herding | 1–12-month lookbacks, volatility-scaled; long-only means "invested or cash" | The best-documented candidate; mainly reduces drawdowns rather than raising returns |
| **Cross-sectional momentum / relative strength across ETFs** | Jegadeesh & Titman (1993); Asness, Moskowitz & Pedersen (2013) | Rank the ETF universe by 6–12-month return (skipping the last month); hold the top-k | Moderate; prone to sharp momentum crashes |
| **Volatility targeting** | Moreira & Muir (2017); volatility clustering (Mandelbrot; Engle 1982) | Size ∝ target vol / forecast vol. Not a return forecast, but a strong risk tool | Reliable risk benefit; the return benefit is debated |
| **GARCH-family volatility forecasting** | Bollerslev (1986); GJR-GARCH (Glosten, Jagannathan & Runkle 1993) for asymmetry; HAR-RV (Corsi 2009) as a strong simple competitor | Feeds sizing, risk limits and the variance of forecasts; benchmark GARCH against EWMA and HAR | GARCH often barely beats EWMA; test it |
| **Regime detection (HMM)** | Hamilton (1989) regime switching; Gaussian HMM with 2–3 states on returns and volatility | Use *filtered* (not smoothed) probabilities only. Smoothed probabilities use future data, a classic leakage bug | Useful as a risk overlay; weak as a direct signal |
| **Factor tilts (long-only)** | Fama & French (1993, 2015); Carhart (1997); AQR "value and momentum everywhere" | Implemented through factor ETFs (value, momentum, quality, minimum volatility) and rotation between them | Factor premia are real but noisy and can underperform for long periods |
| **Short-horizon mean reversion** | Lehmann (1990); Lo & MacKinlay (1990); liquidity-provision explanation | RSI / Bollinger / z-score on ETFs at 1–10-day horizons | **Likely killed by costs** at retail spreads; included because it's a requested and instructive negative control |

### 3.3 Research-track strategies (they must earn promotion)

| Strategy | Foundation | Constraint issue / note |
|---|---|---|
| **Pairs trading / statistical arbitrage** | Gatev, Goetzmann & Rouwenhorst (2006); cointegration (Engle & Granger 1987; Johansen 1991); Ornstein–Uhlenbeck spread models; Kalman-filter hedge ratios | **Needs short selling.** Research: full long/short version (as a reference). Production candidate: long-only "hold the cheap leg vs. cash/neutral asset" rotation. Expect most of the edge to disappear. Documented returns have also decayed since the 1990s |
| **Event-driven** | Post-earnings announcement drift (Bernard & Thomas 1989); event-study methodology (MacKinlay 1997); macro-announcement effects (Savor & Wilson 2013) | Mostly a single-stock effect; for ETFs it likely shows up through macro announcements and as a risk feature |
| **Sentiment-driven** | Tetlock (2007); Loughran & McDonald (2011) finance dictionary; FinBERT (Araci 2019) | Small, fast-decaying effects; likely useful as a risk/uncertainty input |
| **Gradient-boosted trees (LightGBM / XGBoost)** | Gu, Kelly & Xiu (2020): ML for return prediction with many weak signals | Use for combining features into a forecast. Requires **purged, embargoed walk-forward CV** (López de Prado 2018). Use quantile or distributional objectives (e.g. NGBoost) for uncertainty |
| **Bayesian models** | Bayesian shrinkage of expected returns (Black–Litterman 1992; James–Stein); Bayesian structural time series; PyMC hierarchical models | Main role: shrink noisy return estimates towards zero and produce honest predictive distributions |
| **RNNs / temporal transformers** | LSTM (Hochreiter & Schmidhuber 1997); Temporal Fusion Transformer (Lim et al. 2021) | Daily data for 20 ETFs over 20 years ≈ 100k noisy observations: little data for deep models. **Low priority**; promoted only if it beats LightGBM *and* the benchmarks out of sample |
| **Reinforcement learning** | Moody & Saffell (2001); deep RL portfolio papers | **Not justified initially.** RL needs a reliable simulator, which in finance is just the backtest, so it overfits backtest noise efficiently. Revisit only as an execution/sizing policy once everything else works |

### 3.4 Evaluation methodology (applies to every strategy)

- **Walk-forward:** expanding or rolling training windows, refitted on a schedule; predictions
  only ever on later data. Purging plus an embargo around the train/test boundary when labels
  overlap (e.g. 20-day forward returns).
- **Hold-out:** the most recent ~2 years are **locked away** until a strategy is final, then
  tested exactly once. This is enforced in code: the harness refuses to load the hold-out unless
  given an explicit "final evaluation" token, and it records each use.
- **Multiple-testing correction:** every configuration ever tried is logged. Report the
  **Deflated Sharpe Ratio** (Bailey & López de Prado 2014) and the probability of backtest
  overfitting (PBO, via combinatorially symmetric cross-validation). Trying 200 variations and
  reporting the best is the most common way to fool yourself.
- **Sensitivity analysis:** performance surfaces over parameters; a strategy whose result depends
  on one exact lookback is rejected. Prefer robust plateaus over sharp peaks.
- **Monte Carlo:** block bootstrap of returns (preserves autocorrelation and volatility
  clustering) to produce confidence bands for every metric; randomised cost and slippage draws.
- **Cost model:** spread (estimated per instrument and time), 0.15% FX conversion on
  non-GBP instruments at Trading 212 **[verify current rate]**, UK stamp duty (0.5% on UK
  individual shares; ETFs are generally exempt **[verify per instrument]**), slippage as a
  function of volatility, and execution at the *next* available price after the decision.
- **Metrics:** total and annualised return, volatility, Sharpe, Sortino, Calmar, max drawdown and
  duration, win rate, profit factor, average win/loss, turnover, exposure (time in market),
  information ratio and alpha/beta versus benchmarks, plus confidence intervals for all of them.
- **Biases:**
  - *Look-ahead:* point-in-time storage (§7) plus leakage tests.
  - *Survivorship:* the ETF universe is chosen by *rules applied as of each date* (e.g. existed
    and had ≥ £X average volume at that time); delisted ETFs are tracked. Single-stock research
    needs survivorship-free data, which is usually paid (see §4).
  - *Data snooping:* experiment log, hold-out, Deflated Sharpe.
  - *Selection bias in the universe:* universe rules are fixed before testing.

---

## 4. Data providers and APIs

Rated for this project: reliability (Rel), update frequency, history, licensing, cost, latency.
**All prices are approximate and must be re-checked [verify]**: these markets change pricing often.

### 4.1 Market data

| Provider | Coverage | Frequency / latency | History | Cost | Licensing / caveats | Verdict |
|---|---|---|---|---|---|---|
| **yfinance** (unofficial Yahoo scraper) | Global incl. LSE, FX, indices, futures proxies | ~15-min delayed intraday; EOD | Decades (adjusted) | Free | Unofficial, breaks without warning, Yahoo ToS limits use to personal use; adjusted prices are revised retroactively | Prototyping only; never the only source |
| **Tiingo** | US stocks/ETFs EOD, IEX intraday, crypto, news | EOD; IEX real-time (US) | 30+ yrs EOD | Free tier; ~$30/mo personal **[verify]** | Personal-use licence | Good secondary EOD source; weak on LSE |
| **EODHD** | Global EOD incl. LSE, fundamentals, delisted tickers | EOD; delayed intraday | 30+ yrs | ~€20–100/mo by plan **[verify]** | Personal-use tiers | **Recommended paid option** for LSE coverage *and* delisted data (survivorship) |
| **Alpha Vantage** | Global EOD, FX, some macro, news sentiment | EOD / delayed | 20+ yrs | Free (~25 requests/day **[verify]**); paid ~$50+/mo | | Backup / news sentiment experiments |
| **Polygon.io** | US stocks/options/FX/crypto, very good quality | Real-time (paid) | 20 yrs | Free (delayed, limited); ~$30–200/mo **[verify]** | US-centric | Only if the universe moves to US instruments |
| **Broker quotes (T212 / Alpaca)** | Tradable instruments | Live | None / little | Free | The T212 API focuses on account and orders; its market-data offering is limited **[verify]** | Use for pre-trade spread checks if available |
| **Stooq** | Global EOD CSV | EOD | Long | Free | Unofficial bulk downloads | Cross-check source |

**Bid-ask and order book:** affordable LSE level-2 data effectively doesn't exist for retail.
Proposal: estimate spreads from daily OHLC (Corwin–Schultz), cross-check against broker
quotes at trade time, and enforce a maximum-spread rule in the risk engine.

### 4.2 Macroeconomic data (mostly free, official)

| Source | Content | Notes |
|---|---|---|
| **FRED / ALFRED** (St. Louis Fed) | 800k+ series incl. US rates, CPI, employment; **ALFRED gives historical vintages** | Free API key; ALFRED vintages are essential for point-in-time macro |
| **ONS API** | UK CPI, GDP, labour market | Free; vintages less convenient, so archive our own snapshots |
| **Bank of England Database** | Bank Rate, gilt yields, SONIA, FX | Free |
| **ECB Data Portal**, **Eurostat** | Euro-area data | Free |
| **IMF / World Bank / OECD APIs** | Cross-country, lower frequency | Free |
| **EIA** (US Energy Information Administration) | Oil, gas, power inventories and supply | Free key; weekly releases matter for energy |
| **Economic calendar / consensus forecasts** | Needed for "surprise" features | Usually paid (e.g. Trading Economics ~$$$) **[verify]**; a free fallback is to treat changes vs. the previous release as the surprise (weaker) |

### 4.3 News, filings and sentiment

| Source | Content | Frequency | Cost | Caveats |
|---|---|---|---|---|
| **GDELT 2.0** | Global news events, tone, themes, countries, ~15-min updates | 15 min | Free | Noisy, machine-coded; great for geopolitics and event intensity |
| **SEC EDGAR** | US filings (8-K, 10-Q, …) | Real-time | Free (≤10 req/s, User-Agent required) | US issuers only |
| **LSE RNS** (Regulatory News Service) | UK company announcements | Real-time | Official feeds are paid; free web viewing; re-distribution restricted **[verify]** | Important for UK stocks; less so for ETFs |
| **Central banks** (BoE, Fed, ECB) | Statements, minutes, speeches via RSS | As released | Free | High value, low volume. A good first NLP target |
| **Finnhub** | Company news, sentiment, calendar | Near real-time | Free tier (~60 req/min **[verify]**), paid tiers | Good for prototyping |
| **NewsAPI** | Aggregated headlines | Free dev tier delayed ~24h; business tier expensive (~$449/mo **[verify]**) | | Free tier not usable for live features |
| **Marketaux / Alpha Vantage News** | News with entity tags and sentiment | Near real-time | Free tiers + paid | Their sentiment is a black box. Use it as a feature only after validation |
| **Publisher RSS** (Reuters, BBC Business, FT headlines, etc.) | Headlines and summaries | Real-time | Free | Full-text licensing restrictions; store headlines and links |

### 4.4 Political and geopolitical

| Source | Content | Cost | Caveats |
|---|---|---|---|
| **GDELT** | Conflict, protest, diplomacy event codes | Free | As above |
| **ACLED** | Curated conflict events | Free for non-commercial research with registration | Weekly-ish updates; licence terms restrict use **[verify]** |
| **UK OFSI / US OFAC / EU sanctions lists** | Sanctions designations | Free | Official, structured |
| **Election calendars** (Electoral Commission, IFES ElectionGuide) | Scheduled elections | Free | Scheduled events can enter the model as known in advance |
| **Prediction markets** (e.g. Polymarket, Kalshi) | Market-implied probabilities | Free read APIs | Legal/availability varies by jurisdiction; read-only use for features **[verify]** |
| **WTO / UK Trade Tariff API** | Trade measures and tariffs | Free | Low frequency |

### 4.5 Environmental

| Source | Content | Cost | Caveats |
|---|---|---|---|
| **Open-Meteo** | Global weather forecasts and history | Free for non-commercial use | Easy API; forecast archives available |
| **NOAA (NCEI, CPC)** | US weather, ENSO, drought monitor | Free | |
| **Copernicus (ERA5, C3S)** | Reanalysis and seasonal forecasts | Free with registration | Large files; batch only |
| **GDACS / USGS earthquakes / NASA FIRMS** | Disasters, earthquakes, wildfires | Free, near real-time | Good for event intensity |
| **USDA (WASDE, crop progress), FAO** | Agriculture supply/demand | Free | Scheduled monthly/weekly releases |
| **National Grid ESO / ENTSO-E / EIA** | Energy supply and demand | Free (ENTSO-E needs a token) | |

**Honest assessment:** the evidence that weather and geopolitical data improve *daily
broad-ETF* forecasts is thin. They are most plausibly useful for commodity ETFs (energy,
agriculture) and as uncertainty/risk features. They should be built *after* the core pipeline is
proven, and kept only if they show out-of-sample value (§9, M6).

---

## 5. Brokerage API comparison

| | **Trading 212** | **Interactive Brokers (IBKR)** | **Alpaca** |
|---|---|---|---|
| UK retail availability | Yes (FCA) | Yes (IBKR UK, FCA) | UK entity since the 2026 WealthKernel acquisition, but retail self-directed access for UK residents is **unclear / invite-only [verify]** ([Alpaca](https://alpaca.markets/blog/alpaca-enters-uk-and-eu-market-through-wealthkernel-acquisition/), [eligibility](https://alpaca.markets/learn/account-eligibility/)) |
| API maturity | **Beta**, REST | Mature (TWS API, Client Portal REST, FIX) | Mature, developer-first REST + WebSocket |
| Paper / practice | Practice account with the same API | Paper account | Free paper accounts (widely available) |
| Order types via API | **Live: market orders only** per current docs ([T212 docs](https://docs.trading212.com/api/orders)); more on practice | Everything | Market, limit, stop, bracket, etc. (US) |
| Idempotency | **Not idempotent** in beta, so duplicate risk on retry | Client order IDs | Client order IDs |
| Rate limits | Strict, per account and endpoint (e.g. pending orders 1 per 5 s) ([T212 docs](https://docs.trading212.com/api.md)) | Moderate pacing rules | Generous (~200 req/min) |
| Fractional shares | Yes | Yes (not in the ISA, per one review) ([BrokerChooser](https://brokerchooser.com/broker-reviews/interactive-brokers-review/interactive-brokers-uk)) | Yes (US) |
| Costs at £100 scale | Zero commission; **0.15% FX fee** on non-GBP; spread | UK shares ~£3 per trade minimum (fixed pricing); US shares ~$1 minimum ([IBKR fees](https://www.interactivebrokers.co.uk/en/index.php?f=49807)): **a £3 fee on a £20 trade is 15%** | Commission-free US stocks; FX costs for GBP funding |
| Account types | Invest and Stocks ISA only via API | Wide | Wide (US) |
| Market data | Limited **[verify]** | Rich (subscriptions extra) | Good free IEX feed (US) |

**Recommendation:**
1. **Trading 212 as the only live broker**, because zero commission is decisive at £100.
   Design around its limits: market orders only, so the risk engine needs pre-trade spread
   checks and a size cap per order, and trading should avoid the open/close auctions and
   illiquid periods. Non-idempotent orders, so the reconciliation-first retry policy from §2.8.
   Strict rate limits, so batching and caching.
2. **Alpaca paper** as a secondary *development* adapter, to prove the broker abstraction really
   is broker-independent and to test order types T212 doesn't support.
3. **IBKR: not now.** It is the best API, but minimum commissions make it unsuitable below
   roughly £5–10k. Worth revisiting if the capital ever grows, and the abstraction keeps that
   option open.
4. **Use a Stocks ISA or a General Investment Account?** Running this in an ISA uses ISA allowance
   and mixes the experiment with tax-advantaged savings. A **separate Invest account** keeps the
   experiment ring-fenced. Gains may need reporting for CGT (unlikely to matter at this size, but
   the audit log provides the records). **This is not tax advice.**

---

## 6. Technology stack

| Concern | Choice | Reason |
|---|---|---|
| Language / packaging | Python 3.12+, `uv`, `pyproject.toml`, locked dependencies | Reproducible environments |
| Dataframes | pandas (ecosystem), Polars where speed matters | |
| Numerics / stats | NumPy, SciPy, statsmodels | Cointegration, regressions, tests |
| Volatility | `arch` | GARCH family, bootstrap |
| Regimes | `hmmlearn` (or statsmodels Markov switching) | |
| ML | scikit-learn, LightGBM, XGBoost; NGBoost or quantile objectives for uncertainty | |
| Probabilistic | PyMC (Bayesian), MAPIE (conformal prediction) | Calibrated uncertainty |
| Deep learning (research only) | PyTorch (+ pytorch-forecasting for TFT) | Isolated optional dependency group |
| NLP | Hugging Face `transformers` (FinBERT), `sentence-transformers` (dedup, similarity), spaCy (NER) | Local models by default; no data leaves the machine |
| Storage | **DuckDB + Parquet** (research/analytics), **SQLite** (ops state + audit) → PostgreSQL if needed | Zero-ops, fast, single-user |
| Config | pydantic-settings + YAML; config hash stored with every decision | Validated, versioned config |
| HTTP / resilience | httpx, tenacity (retries), per-source circuit breakers | |
| Scheduling | APScheduler (in-process), or systemd timers / cron | Simple and reliable |
| Experiment tracking | MLflow (local) | Model registry, parameters, metrics |
| Dashboard | Streamlit (+ Plotly) | Fast to build, read-only |
| Logging | structlog (JSON), secret-redaction processor | |
| Quality | pytest, hypothesis (property tests), ruff, mypy, pre-commit, GitHub Actions CI | |
| Deployment | Docker; run on a small always-on machine (Raspberry Pi 5 / cheap VPS ~£5/mo) | Continuous running; VPS costs are ~5% of capital a month, so a home machine is preferable |

**Build versus buy for the backtester:** existing frameworks (vectorbt, backtrader, zipline-
reloaded, NautilusTrader) were considered. Recommendation: a **small in-house event-driven
backtester** that reuses the production decision/risk/execution code (the "one code path"
principle), cross-validated against vectorbt on simple strategies to catch bugs.
NautilusTrader is the strongest alternative if the project grows towards intraday.

---

## 7. Data storage and processing strategy

### 7.1 Layers

```
raw/      immutable original payloads (JSON/CSV/HTML), partitioned by source/date. Never modified.
bronze/   parsed into the Observation schema (Parquet), with available_at and quality flags.
silver/   cleaned, deduplicated, corporate-action-adjusted, bitemporal tables (Parquet + DuckDB views).
gold/     feature tables keyed by (instrument, decision_time), point-in-time correct.
ops.db    SQLite: orders, fills, positions ledger, decisions, risk verdicts, audit chain, source cursors.
```

### 7.2 Bitemporal design

- Each record has **valid time** (`event_time`) and **knowledge time** (`available_at`, plus
  `vintage` for revised series).
- Query rule: `as_of(t)` returns, for each key, the latest record with `available_at <= t`.
  Backtests and live runs both use `as_of`, so both see the same information they would have
  had at the time.
- **Prices:** store *unadjusted* prices plus a corporate-action table; compute adjusted series
  as-of each date. Using today's back-adjusted Yahoo series in a backtest is a subtle look-ahead.

### 7.3 Processing

- Ingestion is incremental with cursors and idempotent upserts keyed by
  `(source, source_id, vintage)`, so re-running a day is safe.
- Daily batch: ingest → validate → silver → features → forecasts → decision → risk → execution
  → reconcile → report. Each stage writes a completion marker, so a crash resumes at the failed
  stage (no repeated orders, no skipped stages).
- **Reproducibility:** each decision stores its data snapshot ID, feature versions, model
  version and config hash, so `replay(decision_id)` regenerates it exactly.
- **Retention:** raw data is kept indefinitely (it's small); where provider licences forbid
  storing full text, keep derived features plus a URL.
- Expected size: daily data for ~25 ETFs + macro + news headlines ≈ well under 10 GB for years.
  No distributed processing is needed.

---

## 8. Risk management framework

### 8.1 Authority and independence

- `risk/` is a separate package with **no imports from strategy or model code**. The decision
  engine depends on it, not the other way round.
- **Two layers of limits:** a YAML config (adjustable) *and* hard-coded ceilings (only changed by
  a code change + review). Config can only tighten limits relative to the ceilings, never loosen
  them.
- Every order passes `RiskEngine.check(order, live_account_state)`, which returns a verdict and
  reasons. The execution layer *refuses* any order without a valid, unexpired risk approval
  token bound to that exact order.

### 8.2 Hard constraints (ceilings)

| Rule | Ceiling |
|---|---|
| Total capital the system may deploy | £100 (counts deposits in, not P&L; gains don't raise the cap automatically) |
| Leverage / margin / borrowing | Forbidden: buy notional ≤ settled free cash − fee buffer |
| Short selling | Forbidden: sell quantity ≤ held quantity |
| Instruments | Whitelist of plain equities/ETFs only; no options, futures, CFDs, leveraged or inverse ETPs |
| Deposits / withdrawals | Not implemented at all. No code path exists |
| Account type | Must match the configured ring-fenced account ID |

### 8.3 Configurable limits (initial proposals)

| Limit | Initial value | Purpose |
|---|---|---|
| Max position size | 40% of the system's equity | Concentration |
| Max gross exposure | 100% (i.e. no leverage); default target ≤ 90% so some cash remains | |
| Max number of positions | 5 | Practicality at £100 |
| Min order value | £5 | Avoid orders where spread and rounding dominate |
| Max order value | £50 | Limit per-order damage |
| Max orders per day | 5 | Runaway-loop protection |
| Max spread at execution | 0.5% (ETFs) | Market-only orders need a spread guard |
| Max cost-to-expected-edge ratio | 0.5 | Don't trade when costs eat most of the forecast edge |
| Daily loss limit | 3% of equity → block new buys for the day | |
| Weekly / total drawdown limits | 7% weekly → pause 1 week; 20% from peak → **stop, needs manual reset** | |
| Volatility kill | If portfolio forecast vol > X, scale down positions | |
| Data freshness | Required inputs older than their freshness limit → NO TRADE | |
| Trading window | Not in the first/last 15 min of the session; no trading on half days | Auctions and wide spreads |

### 8.4 Emergency controls

- **Kill switch:** created by a CLI command, a file flag, or the dashboard button; checked before
  every order. States: `HALT_NEW` (no new buys) and `FLATTEN` (sell everything at market, once,
  subject to spread checks). Clearing it needs a deliberate manual command.
- **Automatic halts:** reconciliation mismatch, repeated broker errors, clock skew, unexpected
  positions (anything not created by the system), and orders in `UNKNOWN` state.
- **Dead-man check:** if the system hasn't completed a healthy cycle in N hours, it stops placing
  new orders when it restarts, until reconciliation passes.

### 8.5 Costs counted in risk

Spread, FX conversion (0.15% on T212 for non-GBP **[verify]**), stamp duty where applicable,
slippage, and the opportunity cost of fees relative to the expected edge. The risk engine
rejects trades whose expected net edge after costs is negative, even if the decision engine
proposed them, as a second safety net.

### 8.6 Model risk

- Each model has a performance monitor (rolling out-of-sample log score, calibration). If it
  degrades beyond a threshold, its weight falls to zero automatically (and is logged).
- New models enter in *shadow mode* (forecasts recorded but not traded) for a minimum period
  before they get any weight.

---

## 9. Development roadmap

Each milestone has **exit criteria**. If they aren't met, the project doesn't proceed to the
next milestone; it changes course instead.

| # | Milestone | Content | Exit criteria |
|---|---|---|---|
| **M0** | Foundations (1–2 wks) | Repo restructure, packaging, CI, config, secrets handling + redaction, logging, audit-log skeleton, ops DB. The existing prototype code is retired or folded in | CI green; secret-leak test passes; audit chain verifies |
| **M1** | Market data + storage (2 wks) | Bitemporal storage, 2 price sources (yfinance + EODHD/Stooq cross-check), corporate actions, quality flags, ETF universe definition | 20 yrs of PIT data for the universe; cross-source discrepancies < threshold; leakage tests pass |
| **M2** | Research harness (2–3 wks) | Event-driven backtester, cost model, walk-forward + purging, metrics with bootstrap CIs, Monte Carlo, experiment log, locked hold-out, benchmarks | Benchmarks reproduce published ETF returns within tolerance; backtester matches vectorbt on simple cases |
| **M3** | Core quant strategies (3 wks) | TS momentum, cross-sectional momentum, vol targeting, GARCH/EWMA/HAR, HMM regimes, mean reversion, factor tilts; calibrated forecast wrappers | A report per strategy with Deflated Sharpe and PBO; **go/no-go: does anything beat benchmarks out of sample after costs with acceptable PBO?** |
| **M4** | Decision + risk engines + SimBroker paper trading (2–3 wks) | Forecast combination, probabilistic rule, sizing, full risk engine, kill switch, order state machine, daily scheduler, crash recovery | Fault-injection tests (killed mid-cycle, API timeouts, duplicate-order scenarios) all fail safe; 4 weeks of unattended paper running |
| **M5** | Broker integration (2 wks) | Trading 212 adapter (practice), reconciliation, rate-limit handling; Alpaca paper adapter | ≥ 4 weeks on the T212 Practice account with zero reconciliation errors; same results from both adapters |
| **M6** | Macro + news + event intelligence (4–6 wks) | Macro with vintages, GDELT, central-bank feeds, event taxonomy, dedup, entity linking, event studies, features | Labelled evaluation set (~300 hand-checked events): classification F1, linking accuracy, dedup precision reported; **features add measurable out-of-sample value, or are kept as risk-only / dropped** |
| **M7** | ML layer (3–4 wks) | LightGBM/XGBoost with distributional outputs, Bayesian shrinkage, conformal calibration; optional deep-learning research | Must beat the best M3 model *and* benchmarks on log score and net Sharpe, out of sample, with correction for the number of trials; otherwise not promoted |
| **M8** | Dashboard + monitoring (2 wks, can overlap) | Streamlit dashboard, alerts, decision explanations, performance reports | All §10-requested views present; alerts tested |
| **M9** | Live pilot (£100) | Enable live only after M4–M5 exit criteria and your explicit activation; start with a fraction (e.g. £25) | 3 months without control failures; live costs and slippage match the model within tolerance |
| **M10** | Ongoing research | Environmental data, pairs research, RL experiments, alternative brokers | Each item through the same promotion gates |

Realistic total to M9: **4–6 months part-time.**

---

## 10. Challenges and open questions

### 10.1 Technical

- **Point-in-time data is hard to get for free:** vintages for UK macro, survivorship-free
  instrument histories, historical news exactly as published. Some will need paid data or our own
  archiving from day one (the archive becomes more valuable over time).
- **Unofficial data sources** (yfinance) break without notice.
- **Trading 212 API beta risks:** market-only live orders, non-idempotent submission, strict
  limits, possible breaking changes, limited market data.
- **Entity linking and deduplication** in news are error-prone and need labelled evaluation data,
  which you will have to create by hand.
- **Running continuously** on home hardware (power, network, updates) needs restart-safe design.
- **Reproducibility of LLM/NLP outputs:** hosted model versions change, so cache every output
  and pin local models.

### 10.2 Financial / methodological

- **Low signal-to-noise:** daily return predictability is tiny; most apparent edges are noise
  or overfitting. Expect most hypotheses to fail. That is the normal outcome of research.
- **Costs at small size:** spread and FX dominate. A 0.3% round trip, 20 times a year, is 6% a
  year, more than most plausible edges.
- **Insufficient statistical power for live results** (see §0).
- **Non-stationarity:** relationships change (regime shifts, crowding, published anomalies
  decaying after publication; McLean & Pontiff 2016).
- **Constraint conflicts:** long-only rules out true pairs/stat-arb.
- **Benchmark difficulty:** low-cost global index funds are a strong benchmark.
- **Tax:** CGT reporting obligations; ISA vs. GIA choice. Get proper advice if unsure.

### 10.3 Operational

- **Your time:** labelling data, reviewing reports, handling halts. Plan for this.
- **Security:** API keys with the narrowest permissions; IP restriction if T212 supports it
  **[verify]**; the dashboard not exposed to the internet.
- **Discipline:** not overriding the risk engine after losses; not changing parameters after
  looking at the hold-out.
- **Broker account risk:** automated trading must comply with the broker's terms of use.

### 10.4 Research questions and assumptions to test

1. Does long-only time-series momentum on a GBP ETF universe beat buy-and-hold *risk-adjusted*,
   after T212 costs, out of sample? (Primary hypothesis.)
2. Do GARCH/HAR volatility forecasts beat EWMA for position sizing?
3. Do HMM regime probabilities improve drawdowns without hurting returns?
4. Do macro surprise features add predictive value at a daily/weekly horizon?
5. Does news/event intensity predict *volatility* better than it predicts *returns*?
6. Does LightGBM beat a linear model with the same features once the number of trials is accounted for?
7. Are model forecasts *calibrated* out of sample, and does conformal adjustment fix it?
8. How large are real T212 spreads and slippage versus the cost model? (Measured in the practice
   account and the pilot.)
9. What decision frequency (daily vs. weekly vs. monthly) maximises net-of-cost performance?
10. Does long-only pairs rotation retain any of the long/short edge?

---

## 11. Decisions needed from you before implementation

1. **Universe:** do you accept the GBP-denominated ETF focus (with single stocks for research
   only)?
2. **Decision frequency:** daily (recommended) or weekly?
3. **Data budget:** £0 (free sources only) or ~£15–25/month (e.g. EODHD) for better LSE coverage
   and survivorship-free data? Note that a data subscription for a year exceeds the trading capital.
4. **LLM use for news:** local models only (private, free, weaker) or a hosted LLM API for
   event classification (better, costs a little, sends public news text only)?
5. **Account:** a separate Trading 212 Invest account (recommended) or the ISA?
6. **Hardware:** home machine (Raspberry Pi / always-on PC) or a cloud VPS?
7. **The existing prototype code:** fold the useful parts into M0/M2, or delete it?

---

### Sources consulted (2026-11-07)

- Trading 212 API docs: [orders](https://docs.trading212.com/api/orders), [overview](https://docs.trading212.com/api.md), [legacy portal](https://t212public-api-docs.redoc.ly)
- Alpaca: [UK/EU via WealthKernel](https://alpaca.markets/blog/alpaca-enters-uk-and-eu-market-through-wealthkernel-acquisition/), [EEA passporting](https://alpaca.markets/blog/alpaca-completes-eea-passporting-to-29-countries-expanding-access-to-regulated-investment-services-across-europe/), [eligibility](https://alpaca.markets/learn/account-eligibility/)
- IBKR UK: [commissions](https://www.interactivebrokers.co.uk/en/index.php?f=49807), [minimums](https://www.interactivebrokers.co.uk/en/index.php?f=38234), [BrokerChooser review](https://brokerchooser.com/broker-reviews/interactive-brokers-review/interactive-brokers-uk)
- Academic references are cited inline by author and year; full bibliography to be added in M0.
