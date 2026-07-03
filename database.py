"""
database.py — SQLite persistence layer.

Tables:
  scans           — every symbol scanned each cycle (signal or not) + reason
  signals         — full snapshot of every generated signal
  signal_outcomes — TP_HIT / SL_HIT / EXPIRED outcome per signal
  funding_rates   — historical funding rate log per symbol
  bot_events      — START / STOP / ERROR operational events

Design:
  - Thread-local connections (safe for single-process long-running VPS use)
  - WAL mode + periodic checkpoint to prevent unbounded -wal file growth
  - Busy timeout so concurrent reads/writes from sqlite3 CLI don't deadlock
  - All writes are wrapped in a context-manager that commits or rolls back
"""

import sqlite3
import logging
import threading
from contextlib import contextmanager
from datetime import datetime

from config import DB_PATH, DB_BUSY_TIMEOUT_SECONDS

log = logging.getLogger("database")

_local = threading.local()
_DB_BUSY_TIMEOUT_MS = DB_BUSY_TIMEOUT_SECONDS * 1000

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS scans (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at       TEXT    NOT NULL,
    symbol           TEXT    NOT NULL,
    passed_liquidity INTEGER NOT NULL,           -- 1 = yes, 0 = no
    quote_volume_24h REAL,
    trend_direction  TEXT,                       -- LONG / SHORT / NULL
    rsi              REAL,
    funding_rate     REAL,
    signal_generated INTEGER NOT NULL DEFAULT 0, -- 1 = signal fired
    skip_reason      TEXT                        -- reason no signal was generated
);
CREATE INDEX IF NOT EXISTS idx_scans_symbol_time ON scans(symbol, scanned_at);

CREATE TABLE IF NOT EXISTS signals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at         TEXT    NOT NULL,
    symbol             TEXT    NOT NULL,
    direction          TEXT    NOT NULL,          -- LONG / SHORT
    entry              REAL    NOT NULL,
    stop_loss          REAL    NOT NULL,
    take_profit        REAL    NOT NULL,
    reward_risk        REAL    NOT NULL,
    rsi                REAL,
    atr                REAL,
    funding_rate       REAL,
    suggested_leverage INTEGER,
    confidence_notes   TEXT,                      -- newline-separated list
    telegram_sent      INTEGER NOT NULL DEFAULT 0,
    telegram_message_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals(symbol, created_at);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id      INTEGER NOT NULL UNIQUE,
    status         TEXT    NOT NULL DEFAULT 'OPEN',  -- OPEN / TP_HIT / SL_HIT / EXPIRED
    closed_at      TEXT,
    closing_price  REAL,
    pnl_r_multiple REAL,   -- profit/loss in units of initial risk (1R = 1× risk taken)
    FOREIGN KEY(signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS funding_rates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    funding_rate REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_funding_symbol_time ON funding_rates(symbol, recorded_at);

CREATE TABLE IF NOT EXISTS bot_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    event_type  TEXT NOT NULL,   -- START / STOP / ERROR / INFO
    message     TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    """Returns this thread's SQLite connection, creating it if needed."""
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={_DB_BUSY_TIMEOUT_MS};")
        _local.conn = conn
    return _local.conn


@contextmanager
def _cursor():
    """Context manager: yields a cursor, commits on success, rolls back on error."""
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db():
    """Creates all tables if they don't exist. Safe to call on every startup."""
    conn = _get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    log.info("Database ready at %s", DB_PATH)


# ── WAL maintenance ───────────────────────────────────────────────────────────

def checkpoint_wal():
    """
    Folds the WAL file back into the main DB file.
    Must be called periodically — WAL mode never auto-truncates under
    continuous write load, causing the -wal file to grow unbounded.
    Call once per scan cycle.
    """
    conn = _get_conn()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except sqlite3.Error as e:
        log.warning("WAL checkpoint failed (non-fatal): %s", e)


def close_connection():
    """
    Checkpoints WAL then closes this thread's connection.
    Call on graceful shutdown so the -wal file is merged before exit.
    """
    if hasattr(_local, "conn"):
        try:
            checkpoint_wal()
            _local.conn.close()
        except sqlite3.Error as e:
            log.warning("Error closing DB connection: %s", e)
        finally:
            del _local.conn


# ── Scans ─────────────────────────────────────────────────────────────────────

def record_scan(
    symbol: str,
    passed_liquidity: bool,
    quote_volume_24h: float = None,
    trend_direction: str = None,
    rsi: float = None,
    funding_rate: float = None,
    signal_generated: bool = False,
    skip_reason: str = None,
):
    with _cursor() as cur:
        cur.execute(
            """INSERT INTO scans
               (scanned_at, symbol, passed_liquidity, quote_volume_24h,
                trend_direction, rsi, funding_rate, signal_generated, skip_reason)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                _now(), symbol, int(passed_liquidity), quote_volume_24h,
                trend_direction, rsi, funding_rate, int(signal_generated), skip_reason,
            ),
        )


# ── Signals ───────────────────────────────────────────────────────────────────

def record_signal(signal, telegram_sent: bool = False, telegram_message_id: str = None) -> int:
    """
    Inserts a signal row + a matching OPEN outcome row atomically.
    Returns the new signal id.
    """
    with _cursor() as cur:
        cur.execute(
            """INSERT INTO signals
               (created_at, symbol, direction, entry, stop_loss, take_profit,
                reward_risk, rsi, atr, funding_rate, suggested_leverage,
                confidence_notes, telegram_sent, telegram_message_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _now(),
                signal.symbol, signal.direction,
                signal.entry, signal.stop_loss, signal.take_profit,
                signal.reward_risk,
                getattr(signal, "rsi", None),
                getattr(signal, "atr", None),
                signal.funding_rate, signal.suggested_leverage,
                "\n".join(signal.confidence_notes),
                int(telegram_sent), telegram_message_id,
            ),
        )
        signal_id = cur.lastrowid
        cur.execute(
            "INSERT INTO signal_outcomes (signal_id, status) VALUES (?, 'OPEN')",
            (signal_id,),
        )
        return signal_id


def get_open_signals() -> list:
    """Returns all signals whose outcome is still OPEN."""
    with _cursor() as cur:
        cur.execute(
            """SELECT s.*, o.id AS outcome_id, o.status, o.closed_at,
                      o.closing_price, o.pnl_r_multiple
               FROM signals s
               JOIN signal_outcomes o ON o.signal_id = s.id
               WHERE o.status = 'OPEN'
               ORDER BY s.created_at""",
        )
        return cur.fetchall()


def close_signal_outcome(
    signal_id: int,
    status: str,
    closing_price: float,
    pnl_r_multiple: float,
):
    """Marks a signal outcome as TP_HIT, SL_HIT, or EXPIRED."""
    with _cursor() as cur:
        cur.execute(
            """UPDATE signal_outcomes
               SET status=?, closed_at=?, closing_price=?, pnl_r_multiple=?
               WHERE signal_id=?""",
            (status, _now(), closing_price, pnl_r_multiple, signal_id),
        )


def get_recent_signals(limit: int = 20, symbol: str = None) -> list:
    with _cursor() as cur:
        if symbol:
            cur.execute(
                """SELECT s.*, o.status, o.pnl_r_multiple
                   FROM signals s
                   JOIN signal_outcomes o ON o.signal_id = s.id
                   WHERE s.symbol = ?
                   ORDER BY s.created_at DESC LIMIT ?""",
                (symbol, limit),
            )
        else:
            cur.execute(
                """SELECT s.*, o.status, o.pnl_r_multiple
                   FROM signals s
                   JOIN signal_outcomes o ON o.signal_id = s.id
                   ORDER BY s.created_at DESC LIMIT ?""",
                (limit,),
            )
        return cur.fetchall()


def get_performance_summary() -> list:
    """Returns win rate + avg R-multiple across all closed signals."""
    with _cursor() as cur:
        cur.execute(
            """SELECT status,
                      COUNT(*)            AS cnt,
                      AVG(pnl_r_multiple) AS avg_r,
                      SUM(pnl_r_multiple) AS total_r
               FROM signal_outcomes
               WHERE status != 'OPEN'
               GROUP BY status""",
        )
        return cur.fetchall()


def get_signals_by_symbol_summary() -> list:
    """Per-symbol signal count and win rate — useful for reviewing pair quality."""
    with _cursor() as cur:
        cur.execute(
            """SELECT s.symbol,
                      COUNT(*) AS total,
                      SUM(CASE WHEN o.status='TP_HIT' THEN 1 ELSE 0 END) AS tp_count,
                      SUM(CASE WHEN o.status='SL_HIT' THEN 1 ELSE 0 END) AS sl_count,
                      AVG(o.pnl_r_multiple) AS avg_r
               FROM signals s
               JOIN signal_outcomes o ON o.signal_id = s.id
               WHERE o.status != 'OPEN'
               GROUP BY s.symbol
               ORDER BY total DESC""",
        )
        return cur.fetchall()


# ── Funding rates ─────────────────────────────────────────────────────────────

def record_funding_rate(symbol: str, funding_rate: float):
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO funding_rates (recorded_at, symbol, funding_rate) VALUES (?,?,?)",
            (_now(), symbol, funding_rate),
        )


# ── Bot events ────────────────────────────────────────────────────────────────

def record_event(event_type: str, message: str = ""):
    with _cursor() as cur:
        cur.execute(
            "INSERT INTO bot_events (occurred_at, event_type, message) VALUES (?,?,?)",
            (_now(), event_type, message),
        )
