# M0.3: External data and brokerage verification

Checked on 2026-11-11.

**How this was checked:** this cloud sandbox cannot reach `docs.trading212.com` or provider sites
directly (DNS is blocked by the network policy), so verification used web search results that
quote the official pages. Each claim is labelled with how well it is confirmed:

- **OFFICIAL**: the official docs or provider page, quoted in search results.
- **3RD-PARTY**: consistent reports from reviews, client libraries or forums.
- **UNVERIFIED**: conflicting or not found. Must be checked directly before relying on it.

Items marked *Gate* must be re-checked against the live documentation before the milestone shown.

## 1. Trading 212 Public API

| Item | Finding | Confidence | Gate |
|---|---|---|---|
| Account types | Invest and Stocks ISA only | OFFICIAL | M8 |
| Status | Beta | OFFICIAL | M8 |
| Auth | HTTP Basic: API key = username, API secret = password; demo and live keys are separate | OFFICIAL | M7 |
| Base URLs | `https://demo.trading212.com/api/v0`, `https://live.trading212.com/api/v0` | OFFICIAL | M7 |
| Rate limits | Per **account** (not per key or IP), per endpoint; response headers show remaining requests and reset time; 429 when exceeded. Examples: instruments 1/50 s, exchanges 1/30 s, pending orders 1/5 s | OFFICIAL | M7 |
| Live order types | Docs say **market orders only** for live; limit/stop/stop-limit endpoints exist (practice). A forum thread from early 2026 asks when they will come to live | OFFICIAL (conflicting signals) | **M8** |
| Idempotency | Order placement is **not idempotent**: retries can duplicate orders | OFFICIAL + 3RD-PARTY | M7 |
| Pending orders cap | 50 per ticker per account | OFFICIAL | M8 |
| Instruments metadata | `GET /equity/metadata/instruments` and `/exchanges` (working schedules with OPEN/CLOSE events); refreshed every 10 min; T212-specific tickers (e.g. `AAPL_US_EQ`); ISIN in the response is UNVERIFIED | OFFICIAL / UNVERIFIED | M7 |
| **Price / market data** | **No historical or live price endpoint found** | UNVERIFIED (absence) | **M7** |
| Commission | £0 on stocks/ETFs (Invest) | 3RD-PARTY (consistent) | M9 |
| FX fee | 0.15% on conversion; a multi-currency account may avoid it when trading in the instrument currency | 3RD-PARTY | M9 |
| Minimum order | Fractional from £1/€1/$1 | 3RD-PARTY | M9 |

**What this means for the architecture**
1. **Trading 212 can't be a research data source**, and possibly not a live price source either.
   The live environment needs its *own* market-data provider for pre-trade price and spread checks.
   This is added to the M7 backlog.
2. **The risk engine must assume market orders only** (no broker-side stop or limit protection):
   pre-trade spread checks, small order sizes, and no trading near auctions.
3. **Non-idempotent submission** confirms the "reconcile, never blindly retry" design.
4. **Per-account rate limits** mean a single process must own all T212 calls (one rate-limiter
   instance), including any manual scripts.

## 2. Market data providers (for M1)

| Provider | Access | Coverage | History | Corporate actions | Free limits | Licence | Confidence |
|---|---|---|---|---|---|---|---|
| **Tiingo** | Official REST API, free key | US stocks and ETFs (EOD), IEX intraday, FX, crypto | 30+ years EOD | Unadjusted OHLCV **plus** `divCash` and `splitFactor` per day | Starter: **50 req/hour, 1,000/day**, 1 GB/month bandwidth; free tier labelled "internal use only" | Personal/internal use | OFFICIAL (limits); symbol caps UNVERIFIED |
| **yfinance** (Yahoo) | Unofficial scraper library | Global (incl. LSE), indices, FX, commodity futures | Decades | `actions=True` gives dividends and splits; `auto_adjust=False` gives raw prices | Unpublished; frequent `YFRateLimitError` reports, sometimes blocking for 24 h+ | yfinance README: **personal use only**; Yahoo ToS forbids automated scraping | 3RD-PARTY |
| **Stooq** | CSV endpoint | Global EOD | Long | None / adjusted | **Since ~March 2026 needs an API key obtained through a CAPTCHA**; daily quota | Unclear | 3RD-PARTY |
| Alpha Vantage | Official REST, free key | Global EOD, FX | 20+ years | Adjusted endpoint | ~25 req/day | Free tier personal | UNVERIFIED |

**M1 decision (default, see `05_DECISIONS.md`):**
- **Primary: Tiingo** for US stocks and ETFs. It is an official, documented API that provides
  unadjusted prices *and* the actions needed to build point-in-time adjustment ourselves.
  50 requests an hour is enough because one request returns a symbol's whole history:
  ~1,000 symbols a day, with incremental updates after that.
- **Secondary: yfinance** for non-US instruments (LSE, indices, commodity futures) and as a
  cross-check. Every row it produces is flagged `unofficial`, and nothing is redistributed.
- **Stooq: not used** (CAPTCHA key, unclear terms).

## 3. Where free data is not enough (no purchase yet)

| Need | Free option | Limitation | Paid options to evaluate later **[verify all prices]** |
|---|---|---|---|
| **Delisted securities** | Tiingo's supported-tickers list includes start/end dates **[verify it includes delisted]**; Yahoo usually drops delisted tickers | Incomplete; survivorship bias in stock-level research | Norgate Data (survivorship-free US incl. delisted), EODHD (delisted tickers), Sharadar (Nasdaq Data Link) |
| **Point-in-time index constituents** | None reliable. Wikipedia change logs (manual, error-prone) | Cross-sectional stock research on "S&P 500" is biased without it | Norgate (historical S&P/Russell membership); CRSP (academic only) |
| **Corporate actions** | Tiingo (US), Yahoo actions | Non-US coverage via Yahoo is unofficial; spin-offs/mergers poorly covered | EODHD, Norgate |
| **Historical fundamentals (point-in-time)** | **SEC EDGAR XBRL "company facts"**: free, official, with *filing dates*, so genuinely point-in-time for US filers since ~2009 | US only; needs normalisation across company tagging; no non-US | Sharadar SF1, EODHD fundamentals |
| **News with accurate publication timestamps** | GDELT (15-min, from 2015), SEC EDGAR filings (exact acceptance timestamps), central-bank RSS | Wire-quality financial news with exact timestamps is not free | Benzinga / Tiingo News (paid tier), RavenPack (institutional) |
| **Macro with revisions** | **ALFRED** (FRED vintages), ECB, ONS, Bank of England | UK revision history is weaker → archive our own snapshots from day one | Generally not needed |
| **Historical bid/ask spreads** | None for daily data. Estimate from OHLC (Corwin–Schultz, Abdi–Ranaldo); Tiingo IEX gives US top-of-book quotes going forward | Estimates are noisy; IEX is a single venue | Databento / Polygon historical quotes (pay-as-you-go), only if an intraday strategy needs it |
| **Borrow availability and fees (shorts)** | None historical. IBKR publishes a *current* shortable/borrow-fee file **[verify]** | No history → model borrow costs as scenarios (general collateral vs. hard-to-borrow, recall probability) and run a sensitivity analysis | Specialist data (S3, Markit), institutional-priced |
| **Intraday bars (2–5 years)** | Tiingo IEX intraday (US, single venue) **[verify history depth]**; Yahoo (only ~60 days for 1-min/5-min) | Not enough for robust intraday research | Databento, Polygon (~$30–200/month) |

**Conclusion:** daily research on **ETFs, indices and futures proxies** is well supported by free
data. **Single-stock cross-sectional research** (factor long/short, stat-arb on stocks) will be
survivorship-biased on free data. The platform will label those results as such, and the first
paid dataset worth evaluating is a survivorship-free US stock + constituents dataset (Norgate-type).
**Nothing will be purchased without your decision.**

## 4. Sources

- Trading 212 docs: [API overview](https://docs.trading212.com/api.md), [orders](https://docs.trading212.com/api/orders), [equity orders](https://docs.trading212.com/api/equity-orders), [key concepts](https://docs.trading212.com/api/section/general-information/key-concepts), [instruments metadata](https://docs.trading212.com/api/instruments-metadata.md), [exchanges](https://docs.trading212.com/api/instruments-metadata/exchanges.md), [community: API update thread](https://community.trading212.com/t/trading-212-api-update/87988), [community: price history question](https://community.trading212.com/t/trading-212-api-instrument-data-price-history-and-differences-between-demo-and-live/93392), [Go client (idempotency note)](https://pkg.go.dev/github.com/cyrbil/go-trading212)
- Trading 212 fees (third-party): [BrokerChooser](https://www.brokerchooser.com/broker-reviews/trading-212-review), [Stockbrokers.com UK](https://www.stockbrokers.com/uk/review/trading-212), [Investing in the Web](https://investingintheweb.com/reviews/trading-212-review/)
- Tiingo: [API documentation](https://api.tiingo.com/documentation), [IEX product/pricing](https://api.tiingo.com/products/iex-api)
- yfinance: [repository / README](https://github.com/ranaroussi/yfinance), [rate-limit issue #2422](https://github.com/ranaroussi/yfinance/issues/2422), [discussion #2431](https://github.com/ranaroussi/yfinance/discussions/2431)
- Stooq: [pandas-datareader issue #1012](https://github.com/pydata/pandas-datareader/issues/1012), [Stooq Q API spec](https://apis.io/apis/stooq/stooq-q-api/)
