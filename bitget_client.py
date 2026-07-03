"""
bitget_client.py — Bitget public REST API wrapper (zero auth required).

Only reads public market data: candles, tickers, funding rates.
Never touches order placement. No API key or secret needed.

Design:
- Retries ONLY on transient errors (network failures, 5xx, 429 rate-limit).
- Permanent errors (bad symbol, wrong params) raise immediately — no wasted retries.
- Thread-safe rate limiting shared across all requests.
"""

import time
import logging
import threading

import requests

from config import (
    BITGET_BASE_URL, PRODUCT_TYPE,
    REQUEST_TIMEOUT_SECONDS, HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF_SECONDS, MIN_SECONDS_BETWEEN_REQUESTS,
)

log = logging.getLogger("bitget_client")

_session = requests.Session()
_session.headers.update({"User-Agent": "bitget-signal-bot/1.0"})

# ── Rate limiter ──────────────────────────────────────────────────────────────
_rate_lock = threading.Lock()
_last_request_time = [0.0]


def _throttle():
    """Ensure minimum gap between HTTP requests to avoid rate-limiting."""
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_time[0]
        gap = MIN_SECONDS_BETWEEN_REQUESTS - elapsed
        if gap > 0:
            time.sleep(gap)
        _last_request_time[0] = time.monotonic()


# Bitget API codes that are always permanent client errors — never retry these.
_PERMANENT_API_CODES = {
    "40009",  # missing / invalid parameter
    "40034",  # symbol does not exist
    "40308",  # invalid product type
    "40762",  # invalid granularity
    "40400",  # resource not found
}


class BitgetAPIError(Exception):
    def __init__(self, message, code=None, retryable=True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _get(path: str, params: dict):
    """Core HTTP GET with smart retry logic. Returns the 'data' field."""
    url = f"{BITGET_BASE_URL}{path}"

    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        _throttle()
        try:
            resp = _session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)

            # Handle Telegram-style rate limit header before parsing body
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 10))
                log.warning("Rate limited on %s — waiting %ss (attempt %s)", path, wait, attempt)
                time.sleep(wait)
                continue

            # 4xx (except 429) are permanent — bad request, wrong symbol, etc.
            if 400 <= resp.status_code < 500:
                raise BitgetAPIError(
                    f"HTTP {resp.status_code} on {path} — permanent client error.",
                    retryable=False,
                )

            resp.raise_for_status()
            body = resp.json()
            api_code = str(body.get("code", ""))

            if api_code != "00000":
                msg = body.get("msg", "unknown error")
                permanent = api_code in _PERMANENT_API_CODES
                raise BitgetAPIError(
                    f"Bitget API {api_code}: {msg} [{path}]",
                    code=api_code,
                    retryable=not permanent,
                )

            return body.get("data")

        except BitgetAPIError as exc:
            if not exc.retryable:
                log.error("Permanent API error on %s: %s", path, exc)
                raise
            log.warning("Retryable API error attempt %s/%s on %s: %s",
                        attempt, HTTP_MAX_RETRIES, path, exc)

        except requests.RequestException as exc:
            log.warning("Network error attempt %s/%s on %s: %s",
                        attempt, HTTP_MAX_RETRIES, path, exc)

        if attempt < HTTP_MAX_RETRIES:
            sleep = HTTP_RETRY_BACKOFF_SECONDS * attempt
            log.debug("Backing off %.1fs before retry", sleep)
            time.sleep(sleep)

    raise BitgetAPIError(
        f"Gave up on {path} after {HTTP_MAX_RETRIES} attempts.",
        retryable=False,
    )


# ── Public API functions ──────────────────────────────────────────────────────

def get_candles(symbol: str, granularity: str, limit: int = 200) -> list:
    """
    Returns OHLCV candles sorted oldest → newest.
    Each row: [ts_ms_str, open_str, high_str, low_str, close_str, base_vol_str, quote_vol_str]
    """
    if not symbol:
        raise ValueError("symbol must not be empty")
    if not 1 <= limit <= 1000:
        raise ValueError(f"limit must be 1–1000, got {limit}")

    data = _get(
        "/api/v2/mix/market/candles",
        {
            "symbol":      symbol,
            "granularity": granularity,
            "limit":       str(limit),
            "productType": PRODUCT_TYPE.lower(),
        },
    )
    if not data:
        return []
    data.sort(key=lambda c: int(c[0]))
    return data


def get_ticker(symbol: str) -> dict | None:
    """Returns 24h ticker dict for one symbol, or None if unavailable."""
    if not symbol:
        raise ValueError("symbol must not be empty")
    data = _get(
        "/api/v2/mix/market/ticker",
        {"symbol": symbol, "productType": PRODUCT_TYPE.lower()},
    )
    if isinstance(data, list):
        return data[0] if data else None
    return data or None


def get_current_funding_rate(symbol: str) -> dict | None:
    """Returns current funding rate dict for one symbol, or None."""
    if not symbol:
        raise ValueError("symbol must not be empty")
    data = _get(
        "/api/v2/mix/market/current-fund-rate",
        {"symbol": symbol, "productType": PRODUCT_TYPE.lower()},
    )
    if isinstance(data, list):
        return data[0] if data else None
    return data or None
