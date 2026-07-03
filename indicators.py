"""
indicators.py — Technical indicator calculations.

Pure pandas/numpy, zero exchange logic. Stateless functions that accept
and return DataFrames — easy to unit-test independently of the bot.
"""

import pandas as pd
import numpy as np

from config import (
    EMA_FAST, EMA_SLOW, RSI_PERIOD,
    ATR_PERIOD, BREAKOUT_LOOKBACK,
)


class IndicatorError(Exception):
    pass


def candles_to_df(raw_candles: list) -> pd.DataFrame:
    """
    Converts raw Bitget candle list to a typed DataFrame indexed by UTC datetime.

    raw_candles: list of [ts_ms, open, high, low, close, base_vol, quote_vol]
                 (all values as strings, sorted oldest → newest)
    """
    if not raw_candles:
        raise IndicatorError("candles_to_df received an empty candle list.")

    df = pd.DataFrame(
        raw_candles,
        columns=["ts", "open", "high", "low", "close", "base_vol", "quote_vol"],
    )

    # Cast numeric columns — coerce invalid values to NaN instead of crashing
    for col in ("open", "high", "low", "close", "base_vol", "quote_vol"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["ts"] = pd.to_datetime(df["ts"].astype(np.int64), unit="ms", utc=True)
    df = df.set_index("ts").sort_index()

    # Drop rows where OHLC is entirely unusable
    df = df.dropna(subset=["open", "high", "low", "close"])

    if df.empty:
        raise IndicatorError("No valid candles remain after cleaning NaNs.")

    return df


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average using Wilder-style smoothing (adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    """
    Wilder RSI. Uses EWM with com=period-1 so it matches most trading
    platforms. NaN warmup rows are filled with 50 (neutral) — the warmup
    guard in signal_engine ensures we never act on those values.
    """
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range using Wilder EWM smoothing."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"]  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds all indicator columns to df and returns it.

    Note: breakout levels and avg_volume use shift(1) so the current
    candle's own values are excluded from the reference window — this
    avoids look-ahead bias where a breakout would be compared to itself.
    """
    df = df.copy()  # never mutate the caller's DataFrame
    df["ema_fast"]    = _ema(df["close"], EMA_FAST)
    df["ema_slow"]    = _ema(df["close"], EMA_SLOW)
    df["rsi"]         = _rsi(df["close"], RSI_PERIOD)
    df["atr"]         = _atr(df, ATR_PERIOD)
    df["avg_volume"]  = df["quote_vol"].shift(1).rolling(BREAKOUT_LOOKBACK).mean()
    df["recent_high"] = df["high"].shift(1).rolling(BREAKOUT_LOOKBACK).max()
    df["recent_low"]  = df["low"].shift(1).rolling(BREAKOUT_LOOKBACK).min()
    return df
