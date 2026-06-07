"""
DefiLlamaClient: thin HTTP wrapper around DefiLlama's public REST APIs.

No API key required. Rate limiting: 0.5 s between calls.
Responses are cached in-session so repeated calls for the same endpoint
don't hit the network twice.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_BASE   = "https://api.llama.fi"
_STABLE = "https://stablecoins.llama.fi"

_RATE_LIMIT_DELAY = 0.5   # seconds between requests


class DefiLlamaApiError(Exception):
    pass


class DefiLlamaClient:
    def __init__(self, rate_limit_delay: float = _RATE_LIMIT_DELAY):
        self._delay = rate_limit_delay
        self._cache: dict[str, Any] = {}
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._last_call: float = 0.0

    # ── Public helpers ───────────────────────────────────────────────────────────

    def dex_overview(self) -> dict:
        """GET /overview/dexs — all DEX protocols with 24h volume and change fields."""
        return self._get(
            _BASE,
            "/overview/dexs",
            params={"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"},
        )

    def protocols(self) -> list[dict]:
        """GET /protocols — full protocol list with TVL and chain breakdown."""
        result = self._get(_BASE, "/protocols")
        return result if isinstance(result, list) else []

    def protocol(self, slug: str) -> dict:
        """GET /protocol/{slug} — historical TVL for a single protocol."""
        return self._get(_BASE, f"/protocol/{slug}")

    def stablecoins(self, include_prices: bool = True) -> dict:
        """GET /stablecoins?includePrices=true"""
        return self._get(
            _STABLE,
            "/stablecoins",
            params={"includePrices": "true" if include_prices else "false"},
        )

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _get(self, base: str, path: str, params: dict | None = None) -> Any:
        cache_key = base + path + str(sorted((params or {}).items()))
        if cache_key in self._cache:
            return self._cache[cache_key]

        elapsed = time.time() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        url = base + path
        logger.debug("GET %s  params=%s", url, params)
        resp = self._session.get(url, params=params, timeout=30)
        self._last_call = time.time()

        if not resp.ok:
            raise DefiLlamaApiError(
                f"HTTP {resp.status_code} for {url}: {resp.text[:200]}"
            )

        data = resp.json()
        self._cache[cache_key] = data
        return data
