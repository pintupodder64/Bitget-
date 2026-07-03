"""
config.py — All settings for the Bitget Futures Signal Bot.
Every value reads from environment variables with sensible defaults.
Call validate() at startup to catch misconfigurations early.
"""

import os
import logging

log = logging.getLogger("config")


class ConfigError(Exception):
    pass


def _env_str(name, default=""):
    return os.environ.get(name, default)

def _env_int(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        raise ConfigError(f"Env var {name}={val!r} must be an integer.")

def _env_float(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        raise ConfigError(f"Env var {name}={val!r} must be a float.")


# ── Telegram ────────────────────────────────────────────────────────────[...]
TELEGRAM_BOT_TOKEN = _env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = _env_str("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED   = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ── Bitget API Authentication (optional) ────────────────────────────────────
# Leave empty to run in signals-only mode (no orders placed)
BITGET_API_KEY     = _env_str("BITGET_API_KEY", "")
BITGET_API_SECRET  = _env_str("BITGET_API_SECRET", "")
BITGET_PASSPHRASE  = _env_str("BITGET_PASSPHRASE", "")
BITGET_AUTH_ENABLED = bool(BITGET_API_KEY and BITGET_API_SECRET and BITGET_PASSPHRASE)

# ── Bitget public REST ────────────────────────────────────────────────────────
BITGET_BASE_URL              = _env_str("BITGET_BASE_URL", "https://api.bitget.com")
PRODUCT_TYPE                 = "USDT-FUTURES"
REQUEST_TIMEOUT_SECONDS      = _env_int("REQUEST_TIMEOUT_SECONDS", 10)
HTTP_MAX_RETRIES             = _env_int("HTTP_MAX_RETRIES", 3)
HTTP_RETRY_BACKOFF_SECONDS   = _env_float("HTTP_RETRY_BACKOFF_SECONDS", 1.5)
MIN_SECONDS_BETWEEN_REQUESTS = _env_float("MIN_SECONDS_BETWEEN_REQUESTS", 0.2)

# ── Symbol whitelist ──────────────────────────────────────────────────────────
WHITELIST_SYMBOLS = [
    s.strip().upper()
    for s in _env_str(
        "WHITELIST_SYMBOLS",
        "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,"
        "DOGEUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,LTCUSDT",
    ).split(",")
    if s.strip()
]

# ── Liquidity gate ──────────────────────────────────────────────────────────[...]
MIN_24H_QUOTE_VOLUME_USDT = _env_float("MIN_24H_QUOTE_VOLUME_USDT", 20_000_000)

# ── Timeframes ────────────────────────────────────────────────────────[...]
TREND_TIMEFRAME  = _env_str("TREND_TIMEFRAME",  "4H")
SIGNAL_TIMEFRAME = _env_str("SIGNAL_TIMEFRAME", "1H")
CANDLE_LIMIT     = _env_int("CANDLE_LIMIT", 200)

VALID_GRANULARITIES = {
    "1m","3m","5m","15m","30m","1H","4H","6H","12H","1D","3D","1W","1M",
}

# ── Indicators ────────────────────────────────────────────────────────[...]
EMA_FAST                = _env_int("EMA_FAST", 20)
EMA_SLOW                = _env_int("EMA_SLOW", 50)
RSI_PERIOD              = _env_int("RSI_PERIOD", 14)
RSI_OVERBOUGHT          = _env_float("RSI_OVERBOUGHT", 70.0)
RSI_OVERSOLD            = _env_float("RSI_OVERSOLD", 30.0)
ATR_PERIOD              = _env_int("ATR_PERIOD", 14)
BREAKOUT_LOOKBACK       = _env_int("BREAKOUT_LOOKBACK", 20)
VOLUME_SPIKE_MULTIPLIER = _env_float("VOLUME_SPIKE_MULTIPLIER", 1.5)

# ── Funding rate filter ───────────────────────────────────────────────────────
MAX_ABS_FUNDING_RATE = _env_float("MAX_ABS_FUNDING_RATE", 0.0008)

# ── Risk management (signal output only — no orders placed) ──────────────────
ATR_STOP_MULTIPLIER    = _env_float("ATR_STOP_MULTIPLIER", 1.5)
ATR_TARGET_MULTIPLIER  = _env_float("ATR_TARGET_MULTIPLIER", 2.5)
ACCOUNT_RISK_PERCENT   = _env_float("ACCOUNT_RISK_PERCENT", 1.0)
MAX_LEVERAGE_SUGGESTED = _env_int("MAX_LEVERAGE_SUGGESTED", 5)

# ── Order Management (when BITGET_AUTH_ENABLED = true) ──────────────────────
ENABLE_AUTO_ORDERS     = _env_str("ENABLE_AUTO_ORDERS", "false").lower() in ("true", "1", "yes")
AUTO_ORDER_TYPE        = _env_str("AUTO_ORDER_TYPE", "limit")  # "limit" or "market"
AUTO_ORDER_LEVERAGE    = _env_int("AUTO_ORDER_LEVERAGE", 3)
AUTO_ORDER_MARGIN_MODE = _env_str("AUTO_ORDER_MARGIN_MODE", "isolated")  # "isolated" or "crossed"
POSITION_SIZE_PERCENT  = _env_float("POSITION_SIZE_PERCENT", 2.0)  # % of account balance per position

# ── Polling & cooldowns ───────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS             = _env_int("POLL_INTERVAL_SECONDS", 900)
MIN_MINUTES_BETWEEN_REPEAT_SIGNAL = _env_int("MIN_MINUTES_BETWEEN_REPEAT_SIGNAL", 240)
SCAN_ERROR_BACKOFF_SECONDS        = _env_int("SCAN_ERROR_BACKOFF_SECONDS", 30)

# ── Database ────────────────────────────────────────────────────────[...]
DB_PATH                 = _env_str("DB_PATH", "signal_bot.db")
DB_BUSY_TIMEOUT_SECONDS = _env_int("DB_BUSY_TIMEOUT_SECONDS", 30)

# ── Logging ─────────────────────────────────────────────────────────[...]
LOG_FILE         = _env_str("LOG_FILE", "signal_bot.log")
LOG_LEVEL        = _env_str("LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES    = _env_int("LOG_MAX_BYTES", 10 * 1024 * 1024)
LOG_BACKUP_COUNT = _env_int("LOG_BACKUP_COUNT", 5)


def validate():
    """
    Raises ConfigError listing all problems found.
    Call this once at startup before doing anything else.
    """
    errors = []

    if not WHITELIST_SYMBOLS:
        errors.append("WHITELIST_SYMBOLS is empty — no pairs to scan.")

    if TREND_TIMEFRAME not in VALID_GRANULARITIES:
        errors.append(f"TREND_TIMEFRAME={TREND_TIMEFRAME!r} not valid. Choose from {VALID_GRANULARITIES}.")
    if SIGNAL_TIMEFRAME not in VALID_GRANULARITIES:
        errors.append(f"SIGNAL_TIMEFRAME={SIGNAL_TIMEFRAME!r} not valid.")

    if EMA_FAST >= EMA_SLOW:
        errors.append(f"EMA_FAST ({EMA_FAST}) must be < EMA_SLOW ({EMA_SLOW}).")

    if not (0 < RSI_OVERSOLD < RSI_OVERBOUGHT < 100):
        errors.append(
            f"RSI thresholds invalid: OVERSOLD={RSI_OVERSOLD}, OVERBOUGHT={RSI_OVERBOUGHT}. "
            "Must satisfy 0 < OVERSOLD < OVERBOUGHT < 100."
        )

    min_candles = max(EMA_SLOW, RSI_PERIOD, ATR_PERIOD, BREAKOUT_LOOKBACK) + 30
    if CANDLE_LIMIT < min_candles:
        errors.append(
            f"CANDLE_LIMIT={CANDLE_LIMIT} too small; need >= {min_candles} for indicator warmup."
        )

    if ATR_STOP_MULTIPLIER <= 0:
        errors.append("ATR_STOP_MULTIPLIER must be > 0.")
    if ATR_TARGET_MULTIPLIER <= 0:
        errors.append("ATR_TARGET_MULTIPLIER must be > 0.")
    if ATR_TARGET_MULTIPLIER <= ATR_STOP_MULTIPLIER:
        errors.append(
            f"ATR_TARGET_MULTIPLIER ({ATR_TARGET_MULTIPLIER}) should be > "
            f"ATR_STOP_MULTIPLIER ({ATR_STOP_MULTIPLIER}) for positive reward:risk."
        )

    if not (1 <= MAX_LEVERAGE_SUGGESTED <= 125):
        errors.append(f"MAX_LEVERAGE_SUGGESTED={MAX_LEVERAGE_SUGGESTED} must be 1–125.")

    if not (0 < ACCOUNT_RISK_PERCENT <= 10):
        errors.append(
            f"ACCOUNT_RISK_PERCENT={ACCOUNT_RISK_PERCENT} outside 0–10%. "
            "Keep it small — this is per-trade risk."
        )

    if POLL_INTERVAL_SECONDS < 60:
        errors.append(
            f"POLL_INTERVAL_SECONDS={POLL_INTERVAL_SECONDS} too aggressive; minimum 60s."
        )

    # Authentication validation (optional)
    if BITGET_AUTH_ENABLED:
        if not (1 <= AUTO_ORDER_LEVERAGE <= 20):
            errors.append(
                f"AUTO_ORDER_LEVERAGE={AUTO_ORDER_LEVERAGE} must be 1-20."
            )
        if AUTO_ORDER_MARGIN_MODE not in ("isolated", "crossed"):
            errors.append(
                f"AUTO_ORDER_MARGIN_MODE={AUTO_ORDER_MARGIN_MODE!r} must be 'isolated' or 'crossed'."
            )
        if not (0.1 <= POSITION_SIZE_PERCENT <= 10):
            errors.append(
                f"POSITION_SIZE_PERCENT={POSITION_SIZE_PERCENT} should be 0.1-10%."
            )
        if ENABLE_AUTO_ORDERS and AUTO_ORDER_TYPE not in ("limit", "market"):
            errors.append(
                f"AUTO_ORDER_TYPE={AUTO_ORDER_TYPE!r} must be 'limit' or 'market'."
            )

    if not TELEGRAM_ENABLED:
        log.warning(
            "Telegram not configured. Signals will be logged only — "
            "set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable alerts."
        )

    if errors:
        for e in errors:
            log.error("Config error: %s", e)
        raise ConfigError(f"{len(errors)} config error(s). See log above.")

    # Log configuration status
    log.info("Config OK. Watching: %s", ", ".join(WHITELIST_SYMBOLS))
    if BITGET_AUTH_ENABLED:
        log.info(
            "Bitget authentication configured. Auto-orders: %s (leverage %sx, margin: %s)",
            "ENABLED" if ENABLE_AUTO_ORDERS else "disabled",
            AUTO_ORDER_LEVERAGE,
            AUTO_ORDER_MARGIN_MODE,
        )
    else:
        log.info("Running in signals-only mode (no Bitget auth configured)")
