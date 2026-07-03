"""
signal_engine.py — Multi-factor signal generation with professional formatting.

A signal only fires when ALL confirmation layers agree:
  1. Higher-timeframe trend (4H EMA crossover)
  2. Lower-timeframe alignment (1H EMA crossover matches trend)
  3. RSI not extended (not chasing an already-exhausted move)
  4. Breakout of recent high/low on a volume spike
  5. Funding rate within safe range (not an overcrowded trade)

Every signal carries:
  - Multiple take profit levels (TP1, TP2, TP3)
  - ATR-based SL/TP levels
  - Position sizing recommendations
  - Leverage suggestions
  - Detailed risk metrics

No orders are placed — this is a signal/alert system only.
"""

import logging
from typing import Optional

import pandas as pd

from config import (
    EMA_FAST, EMA_SLOW,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
    VOLUME_SPIKE_MULTIPLIER,
    MAX_ABS_FUNDING_RATE,
    ATR_STOP_MULTIPLIER,
    ACCOUNT_RISK_PERCENT,
)
from signal_formatter import build_professional_signal, ProfessionalSignal

log = logging.getLogger("signal_engine")

# Minimum number of candles required before we trust indicator values.
# Below this the EWM warmup period means readings are unreliable.
MIN_CANDLES_REQUIRED = 60


def _higher_tf_trend(trend_df: pd.DataFrame) -> Optional[str]:
    """
    Determines dominant trend direction from the higher timeframe (e.g. 4H).
    Returns 'LONG', 'SHORT', or None if EMAs are flat/equal.
    """
    last = trend_df.iloc[-1]
    ema_fast = last["ema_fast"]
    ema_slow = last["ema_slow"]
    if pd.isna(ema_fast) or pd.isna(ema_slow):
        return None
    if ema_fast > ema_slow:
        return "LONG"
    if ema_fast < ema_slow:
        return "SHORT"
    return None


def _calculate_breakout_strength(
    close: float,
    recent_high: float,
    recent_low: float,
    curr_volume: float,
    avg_volume: float,
) -> float:
    """
    Calculate breakout strength (0.0-1.0) based on proximity to extreme
    and volume confirmation.
    
    Returns:
        Strength score 0.0-1.0
    """
    if avg_volume <= 0:
        return 0.0
    
    price_range = recent_high - recent_low
    if price_range <= 0:
        return 0.0
    
    # How far into the range is the close? (0.0 = recent_low, 1.0 = recent_high)
    price_position = (close - recent_low) / price_range
    price_position = max(0.0, min(1.0, price_position))
    
    # Volume confirmation (ratio capped at 2.0)
    volume_ratio = min(curr_volume / avg_volume if avg_volume > 0 else 1.0, 2.0)
    volume_strength = (volume_ratio - 1.0) / 1.0  # Normalize to 0.0-1.0
    
    # Combined strength
    strength = (price_position + volume_strength) / 2.0
    return strength


def evaluate_symbol(
    symbol: str,
    signal_df: pd.DataFrame,
    trend_df: pd.DataFrame,
    funding_rate: float,
    account_balance: float = 10000,
) -> Optional[ProfessionalSignal]:
    """
    Runs all signal filters for one symbol and generates a professional signal.

    Args:
        symbol:       Trading pair, e.g. "BTCUSDT"
        signal_df:    Enriched lower-TF candle DataFrame (e.g. 1H)
        trend_df:     Enriched higher-TF candle DataFrame (e.g. 4H)
        funding_rate: Current perpetual funding rate (decimal, e.g. 0.0001)
        account_balance: Account size for position sizing

    Returns:
        ProfessionalSignal if all filters pass, else None.
    """
    # ── Warmup guard ─────────────────────────────────────────────────────────
    if len(signal_df) < MIN_CANDLES_REQUIRED or len(trend_df) < MIN_CANDLES_REQUIRED:
        log.debug("%s skipped: not enough candles for warmup (%s signal, %s trend)",
                  symbol, len(signal_df), len(trend_df))
        return None

    # ── Filter 1: Higher timeframe trend ─────────────────────────────────────
    trend = _higher_tf_trend(trend_df)
    if trend is None:
        log.debug("%s skipped: higher-TF trend is flat/undefined", symbol)
        return None

    last = signal_df.iloc[-1]

    # ── Filter 2: Lower timeframe EMA alignment ───────────────────────────────
    ema_fast = last["ema_fast"]
    ema_slow = last["ema_slow"]

    if pd.isna(ema_fast) or pd.isna(ema_slow):
        return None

    lf_direction = "LONG" if ema_fast > ema_slow else ("SHORT" if ema_fast < ema_slow else None)
    if lf_direction != trend:
        log.debug("%s skipped: 1H EMA direction (%s) conflicts with 4H trend (%s)",
                  symbol, lf_direction, trend)
        return None

    # ── Filter 3: RSI not extended ────────────────────────────────────────────
    rsi = last["rsi"]
    if pd.isna(rsi):
        return None

    if trend == "LONG" and rsi >= RSI_OVERBOUGHT:
        log.debug("%s skipped: RSI=%.1f overbought for LONG", symbol, rsi)
        return None
    if trend == "SHORT" and rsi <= RSI_OVERSOLD:
        log.debug("%s skipped: RSI=%.1f oversold for SHORT", symbol, rsi)
        return None

    # ── Filter 4: Breakout + volume spike ────────────────────────────────────
    close        = last["close"]
    recent_high  = last["recent_high"]
    recent_low   = last["recent_low"]
    avg_volume   = last["avg_volume"]
    curr_volume  = last["quote_vol"]

    if pd.isna(recent_high) or pd.isna(recent_low) or pd.isna(avg_volume) or avg_volume <= 0:
        log.debug("%s skipped: breakout reference values not yet available", symbol)
        return None

    volume_spike = curr_volume > avg_volume * VOLUME_SPIKE_MULTIPLIER

    if trend == "LONG":
        breakout = close > recent_high
        if not (breakout and volume_spike):
            log.debug(
                "%s LONG: breakout=%s (close=%.6f > high=%.6f), vol_spike=%s (%.0f vs avg %.0f)",
                symbol, breakout, close, recent_high, volume_spike, curr_volume, avg_volume,
            )
            return None
    else:  # SHORT
        breakout = close < recent_low
        if not (breakout and volume_spike):
            log.debug(
                "%s SHORT: breakout=%s (close=%.6f < low=%.6f), vol_spike=%s (%.0f vs avg %.0f)",
                symbol, breakout, close, recent_low, volume_spike, curr_volume, avg_volume,
            )
            return None

    # Calculate breakout strength
    breakout_strength = _calculate_breakout_strength(
        close, recent_high, recent_low, curr_volume, avg_volume
    )

    # ── Filter 5: Funding rate ────────────────────────────────────────────────
    if abs(funding_rate) > MAX_ABS_FUNDING_RATE:
        log.info("%s skipped: funding rate %.4f%% exceeds cap %.4f%%",
                 symbol, funding_rate * 100, MAX_ABS_FUNDING_RATE * 100)
        return None

    funding_favorable = abs(funding_rate) < MAX_ABS_FUNDING_RATE
    if trend == "LONG":
        funding_favorable = funding_favorable and funding_rate >= 0
    else:
        funding_favorable = funding_favorable and funding_rate <= 0

    # ── ATR-based SL ─────────────────────────────────────────────────────────
    atr = last["atr"]
    if pd.isna(atr) or atr <= 0:
        log.debug("%s skipped: ATR is NaN or zero", symbol)
        return None

    entry = close
    if trend == "LONG":
        stop_loss = entry - atr * ATR_STOP_MULTIPLIER
    else:
        stop_loss = entry + atr * ATR_STOP_MULTIPLIER

    # ── Build professional signal ────────────────────────────────────────────
    professional_signal = build_professional_signal(
        symbol=symbol,
        direction=trend,
        entry=entry,
        stop_loss=stop_loss,
        atr=atr,
        rsi=float(rsi),
        ema_direction=trend,
        volume_spike=volume_spike,
        funding_rate=funding_rate,
        funding_threshold=MAX_ABS_FUNDING_RATE,
        breakout_strength=breakout_strength,
        account_balance=account_balance,
    )

    log.info(
        "SIGNAL %s %s  entry=%s  SL=%s  TP1=%s  TP2=%s  TP3=%s  confidence=%.0f%%",
        professional_signal.direction, symbol,
        professional_signal.entry,
        professional_signal.stop_loss,
        professional_signal.tp_levels[0].price if len(professional_signal.tp_levels) > 0 else "N/A",
        professional_signal.tp_levels[1].price if len(professional_signal.tp_levels) > 1 else "N/A",
        professional_signal.tp_levels[2].price if len(professional_signal.tp_levels) > 2 else "N/A",
        professional_signal.confidence_score,
    )

    return professional_signal
