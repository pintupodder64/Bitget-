"""
outcome_tracker.py — Retroactive TP/SL outcome tracking.

Checks every OPEN signal against the current ticker price and closes it
when price reaches the TP or SL level. This builds a real win-rate
track record rather than just a log of alerts sent.

Known limitation:
    Polling-based tracking (e.g. every 15 min) cannot see intra-poll
    price action. If price gapped through BOTH TP and SL since the last
    check, we conservatively assume the SL was hit first — this may
    understate actual win rate but will never overstate it.
"""

import logging

from bitget_client import get_ticker, BitgetAPIError
from database import get_open_signals, close_signal_outcome

log = logging.getLogger("outcome_tracker")


def _get_price(symbol: str) -> float | None:
    """
    Fetches last trade price. Returns None on any error.

    Note: uses explicit key lookup with a fallback chain. Avoids the
    common bug of `ticker.get("lastPr") or ticker.get("last")` — if
    lastPr is the string "0" (falsy), the `or` silently skips it.
    """
    try:
        ticker = get_ticker(symbol)
    except BitgetAPIError as e:
        log.warning("Price fetch failed for %s: %s", symbol, e)
        return None

    if not ticker:
        return None

    for key in ("lastPr", "last", "close"):
        raw = ticker.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue

    log.warning("Could not extract price from ticker for %s: %s", symbol, ticker)
    return None


def check_open_signals():
    """
    Iterates all OPEN signals and closes any that have hit their TP or SL.
    Safe to call every scan cycle — skips symbols where price fetch fails.
    """
    open_signals = get_open_signals()
    if not open_signals:
        return

    # Cache prices so we don't hit the API twice for the same symbol
    # if multiple open signals exist for it (e.g. LONG and SHORT from
    # different timestamps).
    price_cache: dict[str, float | None] = {}

    for row in open_signals:
        symbol    = row["symbol"]
        direction = row["direction"]
        entry     = float(row["entry"])
        sl        = float(row["stop_loss"])
        tp        = float(row["take_profit"])
        sig_id    = row["id"]

        if symbol not in price_cache:
            price_cache[symbol] = _get_price(symbol)

        price = price_cache[symbol]
        if price is None:
            continue

        risk = abs(entry - sl)
        if risk <= 0:
            log.warning(
                "Signal #%s (%s) has zero risk distance — skipping outcome check.",
                sig_id, symbol,
            )
            continue

        # Determine which levels were hit
        if direction == "LONG":
            sl_hit = price <= sl
            tp_hit = price >= tp
        else:  # SHORT
            sl_hit = price >= sl
            tp_hit = price <= tp

        if not sl_hit and not tp_hit:
            continue  # still open, nothing to do

        # If both are technically triggered (price gapped through both levels
        # between polls), conservatively assume SL was hit first.
        if sl_hit:
            status        = "SL_HIT"
            closing_price = sl
        else:
            status        = "TP_HIT"
            closing_price = tp

        if direction == "LONG":
            pnl_r = (closing_price - entry) / risk
        else:
            pnl_r = (entry - closing_price) / risk

        close_signal_outcome(sig_id, status, closing_price, pnl_r)
        log.info(
            "Closed #%s %s %s — %s at %.8f (%.2fR)  [live price: %.8f]",
            sig_id, symbol, direction, status, closing_price, pnl_r, price,
        )


def expire_old_signals(max_open_hours: int = 168):
    """
    Marks signals as EXPIRED if they have been OPEN for longer than
    max_open_hours (default 7 days). Prevents stale open signals from
    cluttering the DB if price never reached either level.
    """
    from datetime import datetime, timedelta
    from database import _cursor, _now

    cutoff = (datetime.utcnow() - timedelta(hours=max_open_hours)).isoformat(timespec="seconds")

    with _cursor() as cur:
        cur.execute(
            """UPDATE signal_outcomes
               SET status='EXPIRED', closed_at=?, pnl_r_multiple=0
               WHERE status='OPEN'
               AND signal_id IN (
                   SELECT id FROM signals WHERE created_at < ?
               )""",
            (_now(), cutoff),
        )
        if cur.rowcount:
            log.info("Expired %s stale open signal(s) older than %sh", cur.rowcount, max_open_hours)
