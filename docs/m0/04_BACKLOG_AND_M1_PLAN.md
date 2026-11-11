# M0.4: Implementation backlog and detailed M1 plan

## 1. Prioritised backlog (milestone level)

| Pri | Milestone | Depends on | Key risks | Exit gate |
|---|---|---|---|---|
| 1 | **M1 Data foundation** | M0 approval | Provider ToS / rate limits; point-in-time corporate actions | M1 acceptance tests (§3) |
| 2 | **M2 Backtesting foundation** | M1 (`get_bars`, calendars, FX) | Execution realism; accounting bugs | Accounting invariants, look-ahead tests, oracle cross-check |
| 3 | **M3 Initial strategy library** | M2 | Overfitting starts here → registry from day one | Each strategy has a spec, tests, registered experiments |
| 4 | **M4 Validation and robustness** | M3 | Hold-out leakage through human iteration | Zone guard tests; DSR/PBO validated against published examples |
| 5 | **M5 Discovery and portfolio construction** | M4 | Search-space explosion | Every trial recorded; selection on OOS only |
| 6 | **M6 News and events** | M1 (storage), M4 (to measure value) | Timestamp accuracy; LLM cost and reproducibility | Incremental OOS value shown, or features rejected |
| 7 | **M7 Practice trading** | M2, M4 (≥1 VALIDATED strategy), Postgres | T212 API limits; live price source | Reconciliation tests; 4+ weeks unattended |
| 8 | **M8 Live broker integration** | M7 | Market-only orders; non-idempotent API | Technical review; live disabled by default |
| 9 | **M9 £100 pilot** | M8 + your explicit approval | — | — |
| 10 | **M10 Advanced research** | M4/M5 baselines | — | Beats a simpler baseline out of sample |

Items added to later milestones by M0's findings:
- **M7:** a live market-data provider (T212 seems to have no price endpoint); one shared
  T212 rate limiter per account.
- **M2:** borrow-cost *scenarios* (no free historical borrow data); spread estimators (Corwin–Schultz).
- **M3/M5:** a "survivorship-biased" label on any result that uses a current-constituents stock universe.

## 2. M1 implementation backlog

Conventions: every task ends with green `ruff`, `mypy --strict` (on `src/`) and `pytest`; each
task is one small PR-sized commit. **S** ≈ < half a day, **M** ≈ 1 day, **L** ≈ 2 days.

### Phase A: scaffolding and core

| ID | Task | Depends | Size | Deliverable | Done when |
|---|---|---|---|---|---|
| **T1.0** | Restructure repo: `src/` layout, `pyproject.toml` (uv), `.gitignore`, move prototype to `legacy/`, new README stub, CI workflow (ruff, mypy, import-linter, pytest offline) | — | M | Buildable package, CI | `uv sync && pytest` passes; `legacy/` excluded; CI green |
| **T1.1** | `core.time`: UTC helpers, `ensure_utc()`, rejection of naive datetimes, session-date ↔ timestamp helpers | T1.0 | S | `core/time.py` + tests | Property tests: round trips, DST boundaries |
| **T1.2** | `core.config`: pydantic-settings loader (YAML + env), `Secrets` with `SecretStr`, config hashing | T1.0 | S | `core/config.py` | Hash stable across key order; secrets never in `repr`/hash |
| **T1.3** | `core.logging`: structlog JSON, run context (run_id, git SHA), **secret-redaction processor** | T1.2 | S | `core/logging.py` | Test: log a dict with a secret value and an `Authorization` header, assert both are redacted |
| **T1.4** | `core.ids` + `core.errors`: ULID-based ids, error hierarchy (`DataError`, `ValidationError`, `ProviderError`, `RateLimited`, `LookAheadError`) | T1.0 | S | | |

### Phase B: instruments, universes, calendars

| ID | Task | Depends | Size | Done when |
|---|---|---|---|---|
| **T1.5** | `Instrument` model: internal `instrument_id`, asset class, exchange MIC, currency, country, calendar code, listing/delisting dates, optional ISIN/FIGI | T1.4 | S | Pydantic model with validation tests |
| **T1.6** | Symbology: per-provider symbol mapping (`SPY` ↔ Tiingo `spy` ↔ Yahoo `SPY`; `VUSA.L` …), stored in `configs/universes/*.yaml` → instrument registry Parquet | T1.5 | M | Lookup in both directions; unknown symbol → explicit error |
| **T1.7** | Universe config + resolver: static lists and filters (asset class, currency, exchange); `resolve(universe, as_of)` honours listing/delisting dates | T1.6 | M | Resolver test: an instrument listed in 2015 isn't returned for 2012 |
| **T1.8** | Calendars: `exchange_calendars` wrapper (XNYS, XLON, …); session list, close times in UTC, early closes | T1.1 | S | Known holidays/half days tested |
| **T1.9** | Default research universes: `core_etfs` (~30 liquid US cross-asset ETFs), `uk_etfs` (~10), `global_indices`, `pairs_candidates` (~20 stocks in economically linked pairs). Survivorship caveat documented | T1.7 | S | YAML files + `docs/datasets/universes.md` |

### Phase C: schemas, storage, provenance

| ID | Task | Depends | Size | Done when |
|---|---|---|---|---|
| **T1.10** | Canonical schemas (`data/schemas.py`): `bars_daily` (instrument_id, session_date, open/high/low/close **unadjusted**, volume, currency, + `event_time`, `available_at`, `retrieved_at`, `source`, `ingest_run_id`, `raw_ref`, `quality_flags`), `corporate_actions` (ex_date, type, split_ratio, cash_amount, currency, + provenance), `fx_daily` | T1.5 | M | Schema checks reject wrong dtypes or naive timestamps |
| **T1.11** | Raw store: write payload bytes immutably to `data/raw/{provider}/{dataset}/{symbol}/{retrieved_at}_{sha8}.json`; sha256 in the catalog; refuses overwrite | T1.4 | S | Overwrite attempt raises; hash verify utility |
| **T1.12** | Parquet store: Hive-partitioned append-only writes (`dataset=/provider=/year=`), atomic write (temp file + rename), version rows keyed by `(instrument_id, session_date, source, retrieved_at)` | T1.10 | M | Concurrent/crash test: partial file never visible |
| **T1.13** | Catalog: `ingest_runs` (run_id, git SHA, dirty flag, config hash, provider, params, timestamps, row counts, status, error) and `raw_files` tables | T1.11 | S | Every normalised row joins back to a run and a raw file |
| **T1.14** | Dataset snapshots: `snapshot create <dataset>` → manifest (paths + sha256) → `dataset_version` id; `snapshot verify` | T1.12 | S | Same content → same id; any byte change → verification fails |
| **T1.15** | DuckDB access layer: views over clean Parquet; `get_bars(instruments, start, end, as_of, adjust="none"|"split"|"total_return", currency=None) -> pl.LazyFrame` | T1.12 | M | Predicate pushdown confirmed with `explain`; returns a LazyFrame |
| **T1.16** | **As-of semantics:** latest version per key with `available_at <= as_of`; default `as_of` = now (research must pass it explicitly in the backtester) | T1.15 | M | Revision test (acceptance AT-8) |

### Phase D: providers and ingestion

| ID | Task | Depends | Size | Done when |
|---|---|---|---|---|
| **T1.17** | Provider protocol: `capabilities()`, `fetch_raw(request) -> RawPayload`, `parse(raw) -> NormalizedBatch`; parsing is pure, so it can be tested on stored payloads | T1.10 | S | Protocol + an in-memory fake provider |
| **T1.18** | HTTP layer: httpx client, **token-bucket rate limiter** from `providers.yaml` (Tiingo 50/h, 1,000/day), tenacity retry for idempotent GETs only (429/5xx/timeouts), daily-quota awareness, request headers never persisted | T1.17, T1.3 | M | Tests with respx: back-off honoured; quota exhaustion → `RateLimited` without hammering |
| **T1.19** | Synthetic + CSV providers (ported from prototype `data.synthetic`/`load_csv`): multi-asset OHLCV with injectable splits, dividends, gaps, duplicates and bad ticks | T1.17 | S | Used by validation tests |
| **T1.20** | **Tiingo provider:** daily prices (unadjusted OHLCV, `divCash`, `splitFactor`), ticker metadata (start/end dates); available_at = session close + configured lag | T1.18 | M | Parser tests on recorded responses; one `-m network` smoke test |
| **T1.21** | **yfinance provider:** `auto_adjust=False`, `actions=True`; every row flagged `UNOFFICIAL_SOURCE`; library and version recorded | T1.18 | M | Parser tests on stored frames; network smoke test |
| **T1.22** | **ECB FX provider:** official euro reference rates (daily), plus derived GBP/USD cross rates, flagged `DERIVED` | T1.18 | S | Cross-rate maths test; published-time lag (~16:00 CET) applied |
| **T1.23** | Ingestion workflow (`data/ingest.py`): plan (what's missing per instrument/date range from the catalog) → fetch raw → parse → validate → write normalised → publish clean; **incremental, idempotent, resumable**; per-instrument failures isolated | T1.13–T1.22, T1.27 | L | AT-1, AT-2, AT-10 |
| **T1.24** | CLI (`typer`): `finobot data ingest --universe core_etfs --provider tiingo --start 2010-01-01`, `data status`, `data quality-report`, `data snapshot create/verify` | T1.23 | S | Help text; exit codes; dry-run flag |

### Phase E: validation, corporate actions, quality reporting

| ID | Task | Depends | Size | Done when |
|---|---|---|---|---|
| **T1.25** | Validation checks, each a pure function `frame -> flags`, severity ERROR/WARN: schema/dtype; naive or non-UTC timestamps; **duplicate keys**; **missing sessions vs. calendar**; OHLC consistency (`low ≤ open,close ≤ high`, all > 0); negative/zero volume runs; **stale prices** (n identical closes); **extreme returns** (robust z-score) *unless* explained by a corporate action; future-dated rows (`event_time > retrieved_at`) | T1.10, T1.8 | L | One unit test per check, each with a synthetic injected defect |
| **T1.26** | Cross-provider comparison: for instruments ingested from ≥2 providers, compare unadjusted closes and action dates; report divergences above tolerance | T1.25 | S | Injected divergence detected |
| **T1.27** | Clean-layer publication policy: ERROR rows are quarantined (kept, not published); WARN rows published with flags; **no forward-fill or interpolation in storage** | T1.25 | S | Quarantine test |
| **T1.28** | **Point-in-time adjustment (`data/adjust.py`):** split and total-return adjustment factors computed only from actions with `available_at <= as_of` | T1.15, T1.20 | M | AT-9; matches provider-adjusted close within tolerance when `as_of` = today |
| **T1.29** | Quality report: per-dataset JSON + Markdown (coverage per instrument, first/last date, missing sessions, flags by type, quarantined rows, cross-provider divergences, provider ToS flags) | T1.25, T1.26 | M | Report generated for the default universe |
| **T1.30** | Documentation: `docs/datasets/*.md` (one per dataset: source, licence, lags, known issues), `docs/data_layer.md` (as-of semantics, how to add a provider) | all | S | Reviewed by you |

### Critical path

```
T1.0 → T1.1/T1.2/T1.4 → T1.5 → T1.10 → T1.11/T1.12 → T1.13 → T1.15 → T1.16
                                   └─→ T1.17 → T1.18 → T1.20/T1.21/T1.22 ─┐
       T1.8 → T1.25 → T1.27 ────────────────────────────────────────────────┴→ T1.23 → T1.24 → T1.28 → T1.29
```

Estimated effort: **~15–20 working days**, done in that order, reporting after each task.

## 3. M1 acceptance tests

All run offline in CI against synthetic data and recorded provider responses, except where
marked `network` (run manually or locally with API keys).

| ID | Acceptance test | Maps to your criterion |
|---|---|---|
| **AT-1** | Given `configs/universes/test_universe.yaml` (5 instruments), `finobot data ingest` produces clean `bars_daily` + `corporate_actions` for every instrument, with a catalog run record of status `SUCCESS` | Configure a universe and ingest |
| **AT-2** | Running the same ingest twice: the second run makes **zero** provider requests for already-covered ranges (counted via a respx mock) and leaves the snapshot id unchanged | Reuse without re-downloading |
| **AT-3** | Extending the end date only fetches the missing date range | Incremental ingestion |
| **AT-4** | An injected duplicate (instrument, session_date) row is reported as ERROR and quarantined | Duplicates detectable |
| **AT-5** | An injected missing trading session (vs. the XNYS calendar) is reported; holidays are *not* reported as missing | Missing values detectable |
| **AT-6** | A naive datetime or a non-UTC timestamp is rejected at the schema boundary; `event_time > retrieved_at` is flagged | Timestamp problems detectable |
| **AT-7** | A 2:1 split shows a −50% unadjusted move: **not** flagged when the split action is present, **flagged** when it's absent | Corporate-action aware validation |
| **AT-8** | A bar revised by a later ingest is invisible to `get_bars(as_of=before_revision)` and visible after it | Point-in-time correctness |
| **AT-9** | `get_bars(adjust="total_return", as_of=t)` is unchanged by adding a dividend dated after `t` (adjustment uses no future actions) | No look-ahead in adjustment |
| **AT-10** | Every clean row can be traced to `ingest_run_id` → raw file whose sha256 verifies; tampering with a raw file makes `snapshot verify` fail | Provenance |
| **AT-11** | `get_bars` over a synthetic 20M-row dataset completes with peak RSS below a set bound (e.g. 1.5 GB) using lazy scans (`slow` marker) | Not loading everything into memory |
| **AT-12** | A provider returning HTTP 429 causes back-off within configured limits; daily-quota exhaustion stops cleanly with a resumable state, and the next run resumes | Robust repeatable workflow |
| **AT-13** | No secret value or `Authorization` header appears in logs, raw payloads, catalog tables or exceptions (configured with a canary secret) | Credential safety |
| **AT-14** | `quality-report` lists coverage, flags, quarantined rows and cross-provider divergences for the test universe | Data quality reports |
| **AT-15** (`network`) | Real ingest of `core_etfs` 2010→today from Tiingo (and `uk_etfs` from yfinance) completes within free-tier limits; quality report reviewed by you | Historical dataset exists |
