"""
bitget_websocket.py — Bitget WebSocket public feed for real-time market data.

Subscribes to public channels:
  - ticker — price updates
  - candle (1H) — 1-hour candle updates
  - fundingRate — funding rate changes (futures only)

Uses thread-safe dict cache of latest tickers.
Automatic reconnect with exponential backoff on connection loss.
Zero auth required — public market data only.

Design:
  - Long-lived connection in a daemon thread
  - Thread-safe dict cache of latest tickers
  - Graceful shutdown hook
  - Application-level ping/pong heartbeat handling
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import websocket

from config import (
    WHITELIST_SYMBOLS,
    PRODUCT_TYPE,
)

log = logging.getLogger("bitget_websocket")

# Bitget public WebSocket endpoint (v2 unified for both Spot and Futures)
# Use instType in subscription to distinguish: "SPOT" or "USDT-FUTURES"
BITGET_WS_URL = "wss://ws.bitget.com/v2/ws/public"

# Reconnect parameters
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds
BACKOFF_MULTIPLIER = 2.0


class BitgetWebSocketClient:
    """
    Manages a WebSocket connection to Bitget public feeds.
    Runs in a daemon thread; call start() to begin, stop() to shutdown.
    """

    def __init__(self, symbols: list, on_ticker: Optional[Callable] = None):
        """
        Args:
            symbols: List of symbols to subscribe (e.g. ['BTCUSDT', 'ETHUSDT'])
            on_ticker: Optional callback(symbol, ticker_data) for new tickers
        """
        self.symbols = symbols
        self.on_ticker = on_ticker
        self.ws = None
        self._shutdown = False
        self._thread = None
        self._lock = threading.Lock()
        self._ticker_cache = {}  # {symbol: {data}}
        self._backoff = INITIAL_BACKOFF

    def start(self):
        """Start the WebSocket connection in a daemon thread."""
        if self._thread is not None:
            log.warning("WebSocket already started")
            return
        self._shutdown = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("WebSocket client started for symbols: %s", ", ".join(self.symbols))

    def stop(self):
        """Gracefully shut down the WebSocket connection."""
        self._shutdown = True
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                log.debug("Error closing WebSocket: %s", e)
        if self._thread:
            self._thread.join(timeout=5)
        log.info("WebSocket client stopped")

    def get_ticker(self, symbol: str) -> dict | None:
        """Returns latest cached ticker for symbol, or None if not yet received."""
        with self._lock:
            return self._ticker_cache.get(symbol)

    def _run(self):
        """Main WebSocket loop with auto-reconnect."""
        while not self._shutdown:
            try:
                self._connect_and_listen()
            except Exception as e:
                log.error("WebSocket error: %s", e)
                if not self._shutdown:
                    log.info("Reconnecting in %.1fs...", self._backoff)
                    time.sleep(self._backoff)
                    self._backoff = min(self._backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)

    def _connect_and_listen(self):
        """Establish WebSocket connection and listen for messages."""
        # Always use v2 unified public endpoint; PRODUCT_TYPE controls instType in subs
        ws_url = BITGET_WS_URL

        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        # Run until shutdown or error. ping_interval helps keep connection alive at TCP level.
        # We also handle application-level "ping"/"pong" strings per Bitget docs.
        self.ws.run_forever(
            ping_interval=25,
            ping_timeout=10,
            ping_payload="",
        )

    def _on_open(self, ws):
        """Called when WebSocket connection is established. Subscribe here."""
        log.info("WebSocket connection opened to %s", BITGET_WS_URL)
        self._backoff = INITIAL_BACKOFF  # reset backoff on successful connect
        self._subscribe()

    def _subscribe(self):
        """Send batched subscription requests for ticker, candle1H, and fundingRate channels."""
        if not self.ws:
            log.warning("Cannot subscribe: WebSocket not initialized")
            return

        # Prepare batched args (much more efficient than one message per symbol)
        ticker_args = []
        candle_args = []
        funding_args = []

        for symbol in self.symbols:
            ticker_args.append({
                "instType": PRODUCT_TYPE,
                "channel": "ticker",
                "instId": symbol,
            })
            candle_args.append({
                "instType": PRODUCT_TYPE,
                "channel": "candle1H",
                "instId": symbol,
            })
            if PRODUCT_TYPE == "USDT-FUTURES":
                funding_args.append({
                    "instType": PRODUCT_TYPE,
                    "channel": "fundingRate",
                    "instId": symbol,
                })

        # Send batched subscribes (max ~3 messages instead of 3*N)
        if ticker_args:
            self._safe_send({"op": "subscribe", "args": ticker_args}, "ticker")

        if candle_args:
            self._safe_send({"op": "subscribe", "args": candle_args}, "candle1H")

        if funding_args:
            self._safe_send({"op": "subscribe", "args": funding_args}, "fundingRate")

    def _safe_send(self, msg: dict, desc: str):
        """Helper to safely send a subscription message."""
        try:
            self.ws.send(json.dumps(msg))
            log.debug("Subscribed to %s (%d symbols)", desc, len(msg.get("args", [])))
        except Exception as e:
            log.warning("Failed to subscribe to %s: %s", desc, e)

    def _on_message(self, ws, message: str):
        """Process incoming WebSocket message (handles both JSON and plain ping/pong)."""
        message = message.strip()

        # Application-level heartbeat per Bitget docs (string "ping"/"pong")
        if message == "pong":
            log.debug("Received pong heartbeat from server")
            return
        if message == "ping":
            try:
                ws.send("pong")
                log.debug("Responded to server ping with pong")
            except Exception as e:
                log.warning("Failed to send pong response: %s", e)
            return

        # Parse JSON messages
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            log.warning("Invalid JSON from WebSocket: %s", e)
            return

        if not isinstance(data, dict):
            log.debug("Ignoring non-object WebSocket message: %s", data)
            return

        if "data" not in data:
            # Could be subscribe success {"event":"subscribe", "arg":...} or error — ignore for now
            if data.get("event") == "error":
                log.warning("WebSocket error event: %s", data)
            return

        event_data = data.get("data", [])
        arg = data.get("arg", {})
        channel = arg.get("channel")
        symbol = arg.get("instId")

        if not event_data or not symbol:
            return

        # Handle ticker updates
        if channel == "ticker":
            self._handle_ticker(symbol, event_data[0])

        # Handle candle updates
        elif channel == "candle1H":
            self._handle_candle(symbol, event_data[0])

        # Handle funding rate updates
        elif channel == "fundingRate":
            self._handle_funding_rate(symbol, event_data[0])

    def _handle_ticker(self, symbol: str, ticker_data):
        """Cache ticker and call callback if provided."""
        if not isinstance(ticker_data, dict):
            log.debug("Unexpected ticker payload for %s: %s", symbol, ticker_data)
            return
        with self._lock:
            self._ticker_cache[symbol] = {
                "lastPr": ticker_data.get("lastPr"),
                "high24h": ticker_data.get("high24h"),
                "low24h": ticker_data.get("low24h"),
                "usdtVolume": ticker_data.get("usdtVolume"),
                "timestamp": datetime.utcnow().isoformat(),
            }

        if self.on_ticker:
            try:
                self.on_ticker(symbol, self._ticker_cache[symbol])
            except Exception as e:
                log.warning("Error in on_ticker callback: %s", e)

        log.debug("Ticker %s: %s", symbol, ticker_data.get("lastPr"))

    def _handle_candle(self, symbol: str, candle_data):
        """Log candle update (for debugging; main loop uses REST API for candles).

        Bitget sends candle data as a positional list, not a dict:
        [timestamp, open, high, low, close, baseVolume, quoteVolume, usdtVolume]
        """
        if not isinstance(candle_data, (list, tuple)) or len(candle_data) < 6:
            log.debug("Unexpected candle payload for %s: %s", symbol, candle_data)
            return

        close = candle_data[4]
        volume = candle_data[5]
        log.debug("Candle 1H %s: close=%s, vol=%s", symbol, close, volume)

    def _handle_funding_rate(self, symbol: str, rate_data):
        """Log funding rate update."""
        if not isinstance(rate_data, dict):
            log.debug("Unexpected funding rate payload for %s: %s", symbol, rate_data)
            return
        try:
            rate = float(rate_data.get("fundingRate", 0)) * 100
        except (TypeError, ValueError):
            rate = 0.0
        log.debug("Funding rate %s: %.4f%%", symbol, rate)

    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        log.error("WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close. Triggers reconnect in _run loop."""
        log.warning("WebSocket closed: status=%s msg=%s", close_status_code, close_msg)
        # Backoff will be applied in the reconnect loop; reset here for clean reconnects
        self._backoff = INITIAL_BACKOFF


# Global WebSocket client instance
_ws_client = None


def init_websocket(on_ticker: Optional[Callable] = None):
    """Initialize and start the global WebSocket client."""
    global _ws_client
    if _ws_client is not None:
        log.warning("WebSocket already initialized")
        return _ws_client
    _ws_client = BitgetWebSocketClient(WHITELIST_SYMBOLS, on_ticker=on_ticker)
    _ws_client.start()
    return _ws_client


def stop_websocket():
    """Stop the global WebSocket client."""
    global _ws_client
    if _ws_client:
        _ws_client.stop()
        _ws_client = None


def get_live_ticker(symbol: str) -> dict | None:
    """Retrieve latest cached ticker from WebSocket."""
    if _ws_client is None:
        return None
    return _ws_client.get_ticker(symbol)
