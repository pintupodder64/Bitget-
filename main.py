"""
main.py — Entry point and main scan loop with WebSocket live updates.

Polls Bitget public API for each whitelisted symbol, runs the multi-factor
signal engine, stores everything to SQLite, and sends Telegram alerts.

Now includes WebSocket connection for real-time ticker updates to reduce
latency on outcome tracking.

Signals only — never places orders, never needs API key/secret.

Run:  python main.py
Stop: Ctrl-C or SIGTERM (both handled gracefully)
"""

import logging
import logging.handlers
import signal as signal_mod
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

import config
from config import (
    WHITELIST_SYMBOLS,
    TREND_TIMEFRAME, SIGNAL_TIMEFRAME, CANDLE_LIMIT,
    POLL_INTERVAL_SECONDS, MIN_24H_QUOTE_VOLUME_USDT,
    MIN_MINUTES_BETWEEN_REPEAT_SIGNAL, SCAN_ERROR_BACKOFF_SECONDS,
    LOG_FILE, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
)
from bitget_client import (
    get_candles, get_ticker, get_current_funding_rate, BitgetAPIError,
)
from bitget_websocket import init_websocket, stop_websocket, get_live_ticker
import telegram_commands
from indicators import candles_to_df, enrich, IndicatorError
from signal_engine import evaluate_symbol
from notifier import send_signal, send_status, fmt_price
import database as db
from outcome_tracker import check_open_signals, expire_old_signals


# ── Logging setup ───────────────────────────────────────────────────────────

def _setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=handlers,
    )

_setup_logging()
log = logging.getLogger("main")


# ── Shutdown flag ───────────────────────────────────────────────────────────

_shutdown = False

def _on_shutdown(signum, frame):
    global _shutdown
    log.info("Signal %s received — shutting down after current scan.", signum)
    _shutdown = True

signal_mod.signal(signal_mod.SIGTERM, _on_shutdown)
signal_mod.signal(signal_mod.SIGINT,  _on_shutdown)


# ── Cooldown tracker ──────────────────────────────────────────────────────────
# Keyed by (symbol, direction) → datetime of last sent signal.
# Prevents spamming the same pair/direction repeatedly.
_last_signal_at: dict[tuple, datetime] = {}


# ── Per-symbol scan ──────────────────────────────────────────────────────────

def _get_quote_volume(symbol: str) -> float | None:
    """
    Fetches 24h USDT volume from ticker. Tries live WebSocket first,
    falls back to REST API. Returns None on failure.
    """
    # Try WebSocket cached ticker first (lower latency)
    live_ticker = get_live_ticker(symbol)
    if live_ticker:
        try:
            vol = float(live_ticker.get("usdtVolume", 0))
            if vol > 0:
                return vol
        except (TypeError, ValueError):
            pass

    # Fall back to REST API
    try:
        ticker = get_ticker(symbol)
    except BitgetAPIError as e:
        log.warning("Ticker fetch failed for %s: %s", symbol, e)
        return None

    if not ticker:
        return None

    for key in ("usdtVolume", "quoteVolume", "volUsd"):
        raw = ticker.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def scan_symbol(symbol: str):
    """
    Complete scan cycle for one symbol:
    1. Liquidity gate
    2. Fetch market data
    3. Compute indicators
    4. Run signal engine
    5. Check cooldown
    6. Send alert
    """
    # ── Step 1: Liquidity gate ────────────────────────────────────────────────
    quote_vol = _get_quote_volume(symbol)

    if quote_vol is None:
        log.warning("%s skipped: could not fetch ticker volume", symbol)
        db.record_scan(symbol, passed_liquidity=False, skip_reason="ticker_fetch_failed")
        return

    if quote_vol < MIN_24H_QUOTE_VOLUME_USDT:
        log.info("%s skipped: 24h volume $%.0f < threshold $%.0f",
                 symbol, quote_vol, MIN_24H_QUOTE_VOLUME_USDT)
        db.record_scan(symbol, passed_liquidity=False,
                       quote_volume_24h=quote_vol, skip_reason="low_volume")
        return

    # ── Step 2: Fetch market data ─────────────────────────────────────────────
    try:
        raw_signal  = get_candles(symbol, SIGNAL_TIMEFRAME, CANDLE_LIMIT)
        raw_trend   = get_candles(symbol, TREND_TIMEFRAME,  CANDLE_LIMIT)
        funding_obj = get_current_funding_rate(symbol)
    except BitgetAPIError as e:
        log.warning("Market data fetch failed for %s: %s", symbol, e)
        db.record_scan(symbol, passed_liquidity=True, quote_volume_24h=quote_vol,
                       skip_reason=f"data_fetch_error: {e}")
        return

    if not raw_signal or not raw_trend:
        log.warning("%s skipped: empty candle data returned", symbol)
        db.record_scan(symbol, passed_liquidity=True, quote_volume_24h=quote_vol,
                       skip_reason="empty_candles")
        return

    try:
        funding_rate = float(funding_obj.get("fundingRate", 0)) if funding_obj else 0.0
    except (TypeError, ValueError):
        funding_rate = 0.0

    db.record_funding_rate(symbol, funding_rate)

    # ── Step 3: Compute indicators ────────────────────────────────────────────
    try:
        signal_df = enrich(candles_to_df(raw_signal))
        trend_df  = enrich(candles_to_df(raw_trend))
    except IndicatorError as e:
        log.warning("Indicator error for %s: %s", symbol, e)
        db.record_scan(symbol, passed_liquidity=True, quote_volume_24h=quote_vol,
                       skip_reason=f"indicator_error: {e}")
        return

    # Derive scan-level values for the DB record
    last_row = signal_df.iloc[-1]
    rsi_val  = float(last_row["rsi"]) if not pd.isna(last_row["rsi"]) else None
    tlast    = trend_df.iloc[-1]
    trend_dir = (
        "LONG"  if tlast["ema_fast"] > tlast["ema_slow"] else
        "SHORT" if tlast["ema_fast"] < tlast["ema_slow"] else None
    )

    # ── Step 4: Run signal engine ─────────────────────────────────────────────
    sig = evaluate_symbol(symbol, signal_df, trend_df, funding_rate)

    if sig is None:
        db.record_scan(
            symbol, passed_liquidity=True, quote_volume_24h=quote_vol,
            trend_direction=trend_dir, rsi=rsi_val, funding_rate=funding_rate,
            signal_generated=False, skip_reason="filters_not_aligned",
        )
        return

    # ── Step 5: Cooldown check ────────────────────────────────────────────────
    cooldown_key = (symbol, sig.direction)
    now = datetime.utcnow()
    last_sent = _last_signal_at.get(cooldown_key)

    if last_sent and (now - last_sent) < timedelta(minutes=MIN_MINUTES_BETWEEN_REPEAT_SIGNAL):
        remaining = MIN_MINUTES_BETWEEN_REPEAT_SIGNAL - int((now - last_sent).total_seconds() / 60)
        log.info("%s %s cooldown active — %smin remaining", symbol, sig.direction, remaining)
        db.record_scan(
            symbol, passed_liquidity=True, quote_volume_24h=quote_vol,
            trend_direction=trend_dir, rsi=rsi_val, funding_rate=funding_rate,
            signal_generated=False, skip_reason="cooldown_active",
        )
        return

    # ── Step 6: Send alert + persist ─────────────────────────────────────────
    log.info(
        "SIGNAL %s %s  entry=%s  SL=%s  TP=%s  RR=%.2f",
        sig.direction, symbol,
        fmt_price(sig.entry), fmt_price(sig.stop_loss), fmt_price(sig.take_profit),
        sig.reward_risk,
    )

    sent = send_signal(sig)
    db.record_signal(sig, telegram_sent=sent)
    db.record_scan(
        symbol, passed_liquidity=True, quote_volume_24h=quote_vol,
        trend_direction=trend_dir, rsi=rsi_val, funding_rate=funding_rate,
        signal_generated=True,
    )

    # Update cooldown regardless of whether Telegram succeeded —
    # the signal fired and we don't want to resend on every cycle
    # just because Telegram was temporarily down.
    _last_signal_at[cooldown_key] = now


# ── Main scan cycle ──────────────────────────────────────────────────────────

def run_once():
    """Scans all symbols then checks open signal outcomes."""
    for symbol in WHITELIST_SYMBOLS:
        if _shutdown:
            log.info("Shutdown requested — stopping scan early.")
            return
        try:
            scan_symbol(symbol)
        except Exception as exc:
            log.exception("Unhandled error scanning %s: %s", symbol, exc)
            db.record_event("ERROR", f"scan {symbol}: {exc}")

    if _shutdown:
        return

    try:
        check_open_signals()
    except Exception as exc:
        log.exception("Error in outcome tracker: %s", exc)
        db.record_event("ERROR", f"outcome_tracker: {exc}")

    try:
        expire_old_signals(max_open_hours=168)
    except Exception as exc:
        log.warning("Error expiring stale signals: %s", exc)

    try:
        db.checkpoint_wal()
    except Exception as exc:
        log.warning("WAL checkpoint failed: %s", exc)


def _sleep_interruptible(seconds: float):
    """
    Sleeps in 1-second increments so SIGTERM/SIGINT wakes us up promptly
    instead of blocking for the full poll interval (up to 15 minutes).
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not _shutdown:
        time.sleep(min(1.0, deadline - time.monotonic()))


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    # Validate config first — fail fast with clear messages
    try:
        config.validate()
    except config.ConfigError as exc:
        log.error("Startup aborted: %s", exc)
        sys.exit(1)

    # Init DB
    db.init_db()
    db.record_event("START", f"Watching: {', '.join(WHITELIST_SYMBOLS)}")

    # Start WebSocket for live updates
    try:
        init_websocket()
        log.info("WebSocket client initialized")
    except Exception as e:
        log.warning("Failed to start WebSocket (will use REST API): %s", e)

    # Start Telegram command listener (/start, /help, /status, /stats)
    try:
        telegram_commands.start()
    except Exception as e:
        log.warning("Failed to start Telegram command listener: %s", e)

    log.info("Bot started. Poll interval: %ss. Symbols: %s",
             POLL_INTERVAL_SECONDS, ", ".join(WHITELIST_SYMBOLS))
    
    # Send premium startup notification
    startup_msg = (
        f"✅ <b>Premium Signal Bot Online</b>\n\n"
        f"📊 <b>Market Scan Active</b>\n"
        f"<code>Pairs: {len(WHITELIST_SYMBOLS)} monitored</code>\n"
        f"<code>Update: Every {POLL_INTERVAL_SECONDS // 60}min</code>\n\n"
        f"⚡ Ready to detect trading setups!\n"
        f"<i>Awaiting market opportunities...</i>"
    )
    send_status(startup_msg, status_type="start")

    consecutive_errors = 0

    try:
        while not _shutdown:
            t_start = time.monotonic()
            try:
                run_once()
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                log.exception(
                    "Unhandled error in run_once (consecutive=%s): %s",
                    consecutive_errors, exc,
                )
                db.record_event("ERROR", f"run_once: {exc}")
                # Exponential-ish backoff capped at 10 minutes
                backoff = min(SCAN_ERROR_BACKOFF_SECONDS * consecutive_errors, 600)
                log.warning("Backing off %ss before next attempt.", backoff)
                _sleep_interruptible(backoff)
                continue

            elapsed    = time.monotonic() - t_start
            sleep_for  = max(5.0, POLL_INTERVAL_SECONDS - elapsed)
            log.info("Scan done in %.1fs — sleeping %.0fs.", elapsed, sleep_for)
            _sleep_interruptible(sleep_for)
    finally:
        # ── Graceful shutdown ─────────────────────────────────────────────────
        log.info("Shutting down cleanly...")
        stop_websocket()
        telegram_commands.stop()
        db.record_event("STOP", "Graceful shutdown")
        db.close_connection()
        
        # Send premium shutdown notification
        shutdown_msg = (
            f"⛔ <b>Signal Bot Offline</b>\n\n"
            f"<i>Graceful shutdown completed</i>\n"
            f"Thank you for trading responsibly!"
        )
        send_status(shutdown_msg, status_type="stop")
        
        log.info("Goodbye.")


if __name__ == "__main__":
    main()
