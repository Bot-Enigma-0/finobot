# M0.2: Target architecture

This document replaces `docs/DESIGN.md` as the architecture of record. Changes to it must be
made explicitly, with an entry in `05_DECISIONS.md`.

## 1. Shape

**One Python package (`finobot`), two deployables:**

| Deployable | Where | Entry point | Contains |
|---|---|---|---|
| **Research workbench** | Local machine | `finobot` CLI + notebooks | Data ingestion (batch), storage, features, strategies, backtester, validation, experiment registry, reports |
| **Live service** | Cloud VM, Docker | `finobot-live` (APScheduler loop + FastAPI) | Live data ingestion, feature/inference for *approved* strategy versions only, risk engine, execution, reconciliation, monitoring, alerts |

Both import the same `features`, `strategies`, `risk` and `execution` code. That is the "one code
path" requirement. The live service has **no** optimiser, search or training code paths.
Approved strategy versions arrive as immutable, versioned artifacts (§5).

No Kubernetes, Kafka, Spark or microservices. Each module boundary is a Python interface
(`Protocol`), so any module can later be moved behind a network boundary without changing callers.

## 2. Module map and dependency rule

```
                 core  (types, time, ids, config, logging, errors) ◀── everyone may import
                   ▲
   ┌───────────────┼──────────────────────────────────────────────────────────────┐
   │ data ──▶ features ──▶ strategies ──▶ backtest ──▶ research ──▶ portfolio      │  research side
   │  ▲                       ▲              ▲                                      │
   │ events (news/LLM) ───────┘              │                                      │
   └─────────────────────────────────────────┼──────────────────────────────────────┘
                                             │ same Strategy / CostModel interfaces
   ┌─────────────────────────────────────────┼──────────────────────────────────────┐
   │ live ──▶ strategies(approved) ──▶ RISK ──▶ execution ──▶ brokers/*             │  live side
   │   │                                   ▲                                         │
   │   └──▶ monitoring ────────────────────┘ (can halt)                             │
   └────────────────────────────────────────────────────────────────────────────────┘
```

Import rules, enforced by an `import-linter` contract in CI:
- `risk` imports only `core` (and read-only portfolio state types). **It never imports
  `strategies`, `research` or `events`.**
- `strategies` never imports `brokers`, `execution` or `live`.
- `events` (the LLM pipeline) outputs features only; nothing in `events` can construct an
  `Order`. LLM clients live in `events.llm` and are *not importable* from `risk`, `execution`
  or `live` (contract-enforced).
- `brokers/*` import only `core` and `execution.types`.

## 3. Data flow

### 3.1 Research (batch)

```
Provider APIs ──▶ [raw]   immutable payloads + sha256           data/raw/{provider}/{dataset}/...
                    │ parse
                    ▼
                 [normalized]  canonical schema + provenance     data/normalized/{dataset}/provider=…/year=…/*.parquet
                    │ validate (checks → flags + QualityReport)
                    ▼
                 [clean]  validated, versioned, append-only      data/clean/{dataset}/…
                    │ point-in-time adjustment (as_of), FX conversion
                    ▼
                 [derived] features keyed (instrument, decision_time)   data/derived/features/{feature_set}@{version}/…
                    │
   DuckDB views ◀───┘   snapshot manifest (dataset_version id) ──▶ experiment registry
                    ▼
   Strategy.generate(as_of view) ──▶ target positions ──▶ ExecutionSimulator(cost, spread, slippage, borrow) ──▶ Portfolio ledger
                    ▼
   research: splits / walk-forward / hold-out guard / DSR / PBO / bootstrap ──▶ reports + registry
```

### 3.2 Live (scheduled)

```
scheduler ─▶ live data provider ─▶ validate ─▶ clean ─▶ features (same code) ─▶ approved Strategy version
          ─▶ proposed target ─▶ RISK ENGINE (veto / resize) ─▶ order state machine ─▶ Broker adapter
          ─▶ reconcile (positions, cash, fills) ─▶ PostgreSQL ledger + audit ─▶ monitoring / alerts
```

## 4. Time model (the core defence against look-ahead)

Every stored record carries up to four timestamps, all **UTC, timezone-aware**:

| Field | Meaning | Example (daily bar) | Example (news) |
|---|---|---|---|
| `event_time` | When the thing happened | Session close 2024-03-01 21:00Z | When the explosion occurred |
| `published_at` | When the source made it public | Same as close (or the provider's stamp) | Article timestamp |
| `available_at` | Earliest time the *system could have used it*, in simulation | close + configured provider lag (e.g. +30 min) | `published_at` + ingestion lag |
| `retrieved_at` | When *our* system actually fetched this version | Ingestion run time | Ingestion run time |

**Rule:** every research read goes through `as_of(t)`, which returns, per key, the latest
version with `available_at <= t` **and** (for revisable data) the vintage known at `t`.
Re-downloads that change history create *new versions*. They never overwrite.

**Corporate actions:** store **unadjusted** prices plus an actions table. Adjusted series are
computed *as of the decision date* using only actions with `available_at <= t`. Provider-adjusted
prices are kept only for cross-checking.

## 5. Strategy lifecycle and promotion

```
DRAFT ─▶ RESEARCHED (in-sample) ─▶ VALIDATED (walk-forward OOS) ─▶ HOLDOUT_PASSED
      ─▶ PRACTICE_APPROVED ─▶ PRACTICE_PASSED ─▶ LIVE_APPROVED ─▶ (LIVE) ─▶ SUSPENDED / RETIRED
```

- Every transition is a recorded human approval in the registry, except automatic
  *suspension* by monitoring.
- A deployable artifact = strategy code version (git SHA) + parameter set + feature-set version
  + dataset version used for validation + risk profile, signed with a content hash. The live
  service loads only artifacts in `LIVE_APPROVED` / `PRACTICE_APPROVED` state.
- Retraining produces a **new** artifact that must go through the same states. Nothing is
  ever re-promoted automatically.

## 6. Dataset zones (supports the locked hold-out)

The time axis of each research universe is split into **development**, **validation** and
**final hold-out** zones, defined in config and recorded in the registry. The data access layer
takes a `zone_token`; reads that overlap the hold-out zone need a `FINAL_EVALUATION` token. Each
use is logged permanently and flips the hold-out's status to `USED`, and the change is visible
in every later report. (Mechanism built in M4; the M1 storage API takes the `as_of` / date-range
parameters it needs.)

## 7. Storage

| Store | Technology | Holds | Introduced |
|---|---|---|---|
| Raw | Files (JSON/CSV as received) + sha256 | Provider payloads | M1 |
| Normalized / Clean / Derived | Parquet, Hive-partitioned, append-only | Bars, actions, FX, fundamentals, macro, events, features | M1+ |
| Analytics | DuckDB (embedded, views over Parquet; lazy scans with Polars) | Queries, joins | M1 |
| Research catalog | Parquet tables under `data/catalog/` (ingest runs, snapshots, quality reports) → experiment registry | Provenance | M1 (catalog), M3 (registry) |
| Operational | **PostgreSQL** (SQLAlchemy + Alembic) | Orders, fills, positions ledger, risk verdicts, audit chain, approved artifacts, live monitoring | **M7** (see decision D3) |

**Out-of-core:** all reads return Polars `LazyFrame`s or DuckDB relations with predicate and
projection pushdown on partition columns. Nothing loads a whole dataset by default.

**Versioning:** a *dataset snapshot* is a manifest of file paths and sha256 hashes, with an id
equal to the hash of the manifest. Experiments reference snapshot ids. No DVC/LakeFS yet: the
manifest approach is enough for a single user and is easy to replace later.

**Storage estimate (initial universe):** daily bars for 500 instruments × 15 years ≈ 1.9M rows
≈ **< 200 MB** Parquet. 1-minute bars for 50 instruments × 5 years ≈ 25M rows ≈ **1–2 GB**. Raw
payloads are of similar size. The scale is laptop-sized; it will be re-estimated once the
universe is finalised.

## 8. Directory structure

```
finobot/                            repo root
├── pyproject.toml                  uv-managed; extras: [research] [ml] [nlp] [live] [dev]
├── uv.lock
├── .github/workflows/ci.yml        ruff, mypy, import-linter, pytest (offline)
├── configs/
│   ├── providers.yaml              rate limits, lags, base URLs (no secrets)
│   ├── universes/                  core_etfs.yaml, global_indices.yaml, pairs_candidates.yaml …
│   ├── costs/                      cost models per venue/broker (spread, FX, borrow scenarios)
│   ├── zones/                      dev/validation/holdout date ranges per universe
│   └── risk/                       live risk profiles (ceilings live in code)
├── data/                           (gitignored) raw/ normalized/ clean/ derived/ catalog/
├── src/finobot/
│   ├── core/                       time.py, ids.py, config.py, logging.py (redaction), errors.py, types.py
│   ├── data/
│   │   ├── instruments/            model.py, registry.py, symbology.py, universe.py
│   │   ├── calendars.py            exchange sessions (exchange_calendars)
│   │   ├── schemas.py              canonical Polars schemas: bars, actions, fx, …
│   │   ├── providers/              base.py (protocol, capabilities), http.py (rate limit/retry),
│   │   │                           tiingo.py, yfinance.py, csv.py, ecb_fx.py, (later: fred.py, edgar.py)
│   │   ├── store/                  layout.py, raw.py, parquet.py, catalog.py, snapshot.py, duck.py
│   │   ├── validation/             checks.py, report.py
│   │   ├── adjust.py               point-in-time corporate-action adjustment
│   │   ├── access.py               get_bars(..., as_of=…) etc. (the only research read API)
│   │   └── ingest.py               incremental, idempotent ingestion workflow
│   ├── features/                   indicators.py, registry.py, pipelines/
│   ├── strategies/                 base.py (Strategy, StrategySpec), registry.py, library/…
│   ├── backtest/                   engine.py, portfolio.py, execution_sim.py, costs.py, borrow.py
│   ├── research/                   splits.py, walkforward.py, zones.py, metrics.py, robustness/ (dsr, pbo,
│   │                               bootstrap, sensitivity), registry.py, reports/
│   ├── portfolio/                  construction.py, risk_budget.py, ensemble.py
│   ├── benchmarks/                 buy_hold.py, dca.py, sixty_forty.py
│   ├── events/                     sources/, extract/, llm/ (hosted client, cache), features.py
│   ├── risk/                       engine.py, limits.py (hard ceilings), killswitch.py
│   ├── execution/                  types.py (Order, Fill), state_machine.py, reconcile.py
│   ├── brokers/                    base.py (Broker protocol), sim.py, trading212/, alpaca/ (later)
│   ├── live/                       service.py, scheduler.py, artifacts.py
│   ├── monitoring/                 drift.py, alerts.py, health.py
│   ├── api/                        FastAPI app (read-only dashboards, kill switch)
│   └── cli/                        typer app: data, research, live sub-commands
├── tests/
│   ├── unit/ … integration/ … acceptance/m1/
│   ├── fixtures/                   synthetic.py, recorded provider responses (cassettes)
│   └── conftest.py                 network disabled by default; `-m network` to opt in
├── legacy/                         prototype code moved here in T1.0 (not packaged, not linted)
└── docs/
    ├── m0/                         this audit and plan
    ├── adr/                        architecture decision records
    └── datasets/                   one page per dataset: source, licence, lags, known issues
```

## 9. Dependencies

Python **≥ 3.12** (tested on 3.13). Exact versions are pinned in `uv.lock`.

| Group | Packages | Needed from |
|---|---|---|
| core | `polars`, `pyarrow`, `pandas`, `numpy`, `scipy`, `duckdb`, `pydantic`, `pydantic-settings`, `pyyaml`, `httpx`, `tenacity`, `structlog`, `exchange_calendars`, `typer` | M1 |
| providers (optional) | `yfinance` | M1 |
| dev | `pytest`, `pytest-cov`, `hypothesis`, `respx` (HTTP mocking), `ruff`, `mypy`, `import-linter`, `pre-commit` | M1 |
| research | `statsmodels`, `arch`, `scikit-learn`, `plotly`, `optuna` (Bayesian search, M5) | M2–M5 |
| ml | `lightgbm`, `xgboost`, `torch` (M10) | M5+ |
| nlp | `transformers`, `sentence-transformers`, `spacy`, hosted-LLM SDK | M6 |
| live | `fastapi`, `uvicorn`, `apscheduler`, `sqlalchemy`, `psycopg`, `alembic` | M7 |

Not adopted: MLflow (the experiment registry will be a small custom DuckDB/Parquet registry in
M3, because the spec's reproducibility needs, such as zone tokens and hold-out usage, are
specific); vectorbt/backtrader (they may be used *only* as cross-check oracles in tests).

## 10. Cross-cutting rules

- **Secrets:** loaded only from environment variables (or a `.env` excluded by `.gitignore`)
  through `core.config.Secrets` (`SecretStr`). The logging pipeline redacts registered secret
  values and `Authorization` headers; a test asserts this. Secrets are never put in configs,
  raw payload files (request headers aren't stored) or LLM prompts.
- **Determinism:** every run records git SHA, a dirty-tree flag, config hash, dataset snapshot id
  and random seed.
- **Timezones:** naive datetimes are rejected at module boundaries (validation error).
- **Network in tests:** disabled by default; provider tests replay recorded responses.
