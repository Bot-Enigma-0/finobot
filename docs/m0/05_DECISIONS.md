# M0.5: Decisions and assumptions

## A. Critical decisions needing your input (they block parts of M1)

| ID | Decision | Why it matters | Default if you don't say otherwise |
|---|---|---|---|
| **D1** | **Create a free Tiingo account and API key?** | It's the only free, *official* daily source with unadjusted prices + dividends + splits, which point-in-time adjustment needs. Without it, M1 relies on yfinance (unofficial, personal-use only, unstable) | Build both adapters; AT-15 waits for the key. Personal research use only, no redistribution |
| **D2** | **Where should real-data ingestion run?** This cloud sandbox can't reach Tiingo, Yahoo, ECB or Trading 212 docs (network policy). Options: (a) you run `finobot data ingest` on your local machine (matches the agreed local-research split); (b) I request that this environment's network allowlist add `api.tiingo.com`, `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `data-api.ecb.europa.eu`, `docs.trading212.com` | Affects whether I can run AT-15 and check docs directly | **(a)**: all development and CI is offline with recorded responses; you run the network acceptance test locally. Say if you want (b) |
| **D3** | **PostgreSQL from M7 rather than M1** | Research provenance (ingest runs, snapshots, later the experiment registry) is single-user and lives next to the Parquet data; a local Postgres server adds setup without benefit until live trading records exist. The spec listed Postgres for "operational information, trading records and metadata" | Research metadata in the DuckDB/Parquet catalog; Postgres introduced in M7 for all operational and trading records. **This is a deliberate reading of the spec, so I'm flagging it rather than doing it silently** |

## B. Assumptions made (no input needed unless you disagree)

| ID | Assumption |
|---|---|
| A1 | Package name stays `finobot`; `src/` layout; Python ≥ 3.12 |
| A2 | Polars is the main internal dataframe library; pandas only at library boundaries (yfinance, statsmodels) |
| A3 | `uv` for environment and locking; GitHub Actions CI, offline tests only |
| A4 | Initial research universes: ~30 liquid US cross-asset ETFs (equity regions, sectors, treasuries, credit, gold, commodities, REITs), ~10 UK-listed ETFs, major indices, ~20 stocks in economically linked pairs. **Known survivorship bias** (chosen today), documented and flagged in every report |
| A5 | Default availability lag for daily bars: session close + 30 min (configurable per provider). Signals made "at close" can only trade at the *next* available execution opportunity (enforced in M2) |
| A6 | ECB reference rates as the official FX source (published ~16:00 CET, so an `available_at` lag applies); GBP/USD derived via EUR crosses and flagged |
| A7 | yfinance data is used for personal research only, never redistributed, and its rows carry an `UNOFFICIAL_SOURCE` flag |
| A8 | Dataset versioning by content-hash manifests (no DVC/LakeFS) |
| A9 | Experiment registry built in-house in M3 (no MLflow), because hold-out usage tracking and zone tokens are specific requirements |
| A10 | The prototype is moved to `legacy/` in T1.0 (not deleted) |
| A11 | Intraday data is out of scope for M1; the schema and partitioning leave room for `bars_1m` |
| A12 | The new architecture docs in `docs/m0/` supersede `docs/DESIGN.md`, which is kept for history |

## C. Verification still outstanding (not blocking M1)

- Trading 212: whether limit/stop orders work on **live**; whether any price or quote endpoint
  exists; ISIN in instruments metadata; official fee page (0.15% FX, £1 fractional minimum).
  Gate: M7/M8.
- Tiingo: free-tier unique-symbol caps; whether supported tickers include delisted symbols;
  exact licence text. Gate: AT-15.
- IBKR shortable/borrow-fee file as a *current* borrow-cost reference. Gate: M2 cost scenarios.
