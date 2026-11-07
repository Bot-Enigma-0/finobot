"""Minimal Trading 212 public API client (Invest / ISA accounts, equities only).

Defaults to the PRACTICE (demo) environment. Generate an API key in the app:
Settings -> API (Beta), while switched to your Practice account.

Credentials come from environment variables, never from code:
    T212_API_KEY       required
    T212_API_SECRET    optional; newer keys are issued as key+secret pairs (HTTP Basic auth).
                       Older keys are a single token sent as-is in the Authorization header.

Endpoint paths follow the public v0 API. Check them against https://docs.trading212.com/api
if anything returns 404, since the API is still in beta.
"""
from __future__ import annotations
import base64
import os
import time
import requests

DEMO_URL = "https://demo.trading212.com/api/v0"
LIVE_URL = "https://live.trading212.com/api/v0"


class Trading212Error(RuntimeError):
    pass


class Trading212:
    def __init__(self, api_key: str | None = None, api_secret: str | None = None,
                 live: bool = False, session: requests.Session | None = None, max_retries: int = 3):
        key = api_key or os.environ.get("T212_API_KEY")
        secret = api_secret if api_secret is not None else os.environ.get("T212_API_SECRET")
        if not key:
            raise Trading212Error("Set T212_API_KEY (and T212_API_SECRET if your key has one)")
        auth = "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode() if secret else key
        self.base = LIVE_URL if live else DEMO_URL
        self.live = live
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": auth, "Content-Type": "application/json"})
        self.max_retries = max_retries

    def _req(self, method: str, path: str, **kw):
        for attempt in range(self.max_retries + 1):
            r = self.s.request(method, self.base + path, timeout=15, **kw)
            if r.status_code == 429 and attempt < self.max_retries:  # rate limited: endpoints are strict
                wait = float(r.headers.get("x-ratelimit-reset-in", r.headers.get("Retry-After", 5)))
                time.sleep(min(max(wait, 1), 60))
                continue
            if not r.ok:
                raise Trading212Error(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
            return r.json() if r.content else None
        raise Trading212Error(f"{method} {path}: rate limited")

    # --- account ---
    def cash(self) -> dict:
        """{'free', 'total', 'invested', 'ppl', ...} in account currency."""
        return self._req("GET", "/equity/account/cash")

    def account_info(self) -> dict:
        return self._req("GET", "/equity/account/info")

    def positions(self) -> list[dict]:
        """List of {'ticker', 'quantity', 'averagePrice', 'currentPrice', 'ppl', ...}."""
        return self._req("GET", "/equity/portfolio")

    def position(self, ticker: str) -> dict | None:
        return next((p for p in self.positions() if p["ticker"] == ticker), None)

    # --- instruments ---
    def instruments(self) -> list[dict]:
        """All tradable instruments. Heavily rate limited, so cache the result."""
        return self._req("GET", "/equity/metadata/instruments")

    # --- orders ---
    def market_order(self, ticker: str, quantity: float) -> dict:
        """Positive quantity buys, negative sells. Fractional quantities are allowed for most stocks."""
        return self._req("POST", "/equity/orders/market",
                         json={"ticker": ticker, "quantity": round(quantity, 6)})

    def open_orders(self) -> list[dict]:
        return self._req("GET", "/equity/orders")

    def cancel_order(self, order_id: int) -> None:
        self._req("DELETE", f"/equity/orders/{order_id}")
