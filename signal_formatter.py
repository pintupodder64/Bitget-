"""
signal_formatter.py — Professional signal formatting with multiple TPs and detailed risk metrics.

Generates institutional-grade trading signals with:
  - Multiple take profit levels (TP1, TP2, TP3)
  - Detailed entry/SL/TP pricing
  - Risk-reward ratios per level
  - Position sizing & leverage recommendations
  - Confidence scoring with market context
  - Professional formatting for Telegram

Designed for top coins (BTC, ETH, SOL, etc.) with precise risk management.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List

import pandas as pd

from config import (
    ATR_STOP_MULTIPLIER, ATR_TARGET_MULTIPLIER,
    ACCOUNT_RISK_PERCENT, MAX_LEVERAGE_SUGGESTED,
)

log = logging.getLogger("signal_formatter")


@dataclass
class ProfitLevel:
    """Single take profit level with associated metrics."""
    level: int              # 1, 2, 3, etc.
    price: float
    target_percent: float   # % of position to take at this level
    reward_risk: float      # R:R ratio at this level
    confidence: str         # "High", "Medium", "Low"


@dataclass
class ProfessionalSignal:
    """Complete professional trading signal with all details."""
    symbol: str
    direction: str          # "LONG" or "SHORT"
    
    # Price levels
    entry: float
    stop_loss: float
    
    # Multiple take profit levels
    tp_levels: List[ProfitLevel] = field(default_factory=list)
    
    # Risk metrics
    risk_amount: float = 0.0        # $ risk per 1% account
    atr: float = 0.0
    funding_rate: float = 0.0
    
    # Position sizing
    suggested_position_size: float = 0.0    # % of account
    suggested_leverage: int = 1
    max_loss_percent: float = 0.0           # Max loss if SL hit
    
    # Market context
    rsi: float = 50.0
    ema_trend: str = "NEUTRAL"
    volume_status: str = "Normal"
    
    # Confidence & notes
    confidence_score: float = 65.0  # 0-100
    confidence_notes: List[str] = field(default_factory=list)
    
    # Additional context
    market_cap_rank: Optional[int] = None
    liquidity_rating: str = "High"


def calculate_position_size(
    entry: float,
    stop_loss: float,
    account_balance: float,
    risk_percent: float = ACCOUNT_RISK_PERCENT,
) -> float:
    """
    Calculate position size based on risk management.
    
    Args:
        entry: Entry price
        stop_loss: Stop loss price
        account_balance: Total account balance
        risk_percent: % of account to risk on this trade
    
    Returns:
        Position size in base currency units
    """
    risk_amount = account_balance * (risk_percent / 100)
    price_distance = abs(entry - stop_loss)
    
    if price_distance <= 0:
        return 0
    
    position_size = risk_amount / price_distance
    return position_size


def calculate_tp_levels(
    entry: float,
    stop_loss: float,
    direction: str,
    atr: float,
    num_levels: int = 3,
) -> List[ProfitLevel]:
    """
    Calculate multiple take profit levels with decreasing target percentages.
    
    TP1: Closest, highest confidence, 30% position taken
    TP2: Medium, 40% position taken
    TP3: Furthest, 30% position taken
    
    Args:
        entry: Entry price
        stop_loss: Stop loss price
        direction: "LONG" or "SHORT"
        atr: Average True Range
        num_levels: Number of TP levels (typically 3)
    
    Returns:
        List of ProfitLevel objects
    """
    risk_distance = abs(entry - stop_loss)
    
    if direction == "LONG":
        # TP1: 1.5x ATR above entry (closest, high probability)
        tp1_price = entry + (atr * 1.5)
        tp1_rr = (tp1_price - entry) / risk_distance
        
        # TP2: 2.5x ATR above entry (medium, moderate probability)
        tp2_price = entry + (atr * 2.5)
        tp2_rr = (tp2_price - entry) / risk_distance
        
        # TP3: 4.0x ATR above entry (furthest, lower probability)
        tp3_price = entry + (atr * 4.0)
        tp3_rr = (tp3_price - entry) / risk_distance
    else:  # SHORT
        # TP1: 1.5x ATR below entry
        tp1_price = entry - (atr * 1.5)
        tp1_rr = (entry - tp1_price) / risk_distance
        
        # TP2: 2.5x ATR below entry
        tp2_price = entry - (atr * 2.5)
        tp2_rr = (entry - tp2_price) / risk_distance
        
        # TP3: 4.0x ATR below entry
        tp3_price = entry - (atr * 4.0)
        tp3_rr = (entry - tp3_price) / risk_distance
    
    tp_levels = [
        ProfitLevel(level=1, price=tp1_price, target_percent=30.0, reward_risk=tp1_rr, confidence="High"),
        ProfitLevel(level=2, price=tp2_price, target_percent=40.0, reward_risk=tp2_rr, confidence="Medium"),
        ProfitLevel(level=3, price=tp3_price, target_percent=30.0, reward_risk=tp3_rr, confidence="Low"),
    ]
    
    return tp_levels


def calculate_confidence_score(
    rsi: float,
    ema_direction: str,
    volume_spike: bool,
    funding_favorable: bool,
    breakout_strength: float,
) -> tuple:
    """
    Calculate overall confidence score (0-100) and emoji.
    
    Args:
        rsi: RSI value (0-100)
        ema_direction: "LONG", "SHORT", or "NEUTRAL"
        volume_spike: True if volume is elevated
        funding_favorable: True if funding rate favors the direction
        breakout_strength: 0.0-1.0 (higher = stronger breakout)
    
    Returns:
        (confidence_score, emoji, description)
    """
    score = 50  # Base score
    
    # RSI contribution (max +15)
    if 45 <= rsi <= 55:
        score += 15  # Perfect neutral, lots of room to move
    elif 40 <= rsi <= 60:
        score += 10
    elif 35 <= rsi <= 65:
        score += 5
    
    # EMA alignment (max +20)
    if ema_direction in ("LONG", "SHORT"):
        score += 20
    
    # Volume spike (max +15)
    if volume_spike:
        score += 15
    
    # Funding rate (max +10)
    if funding_favorable:
        score += 10
    
    # Breakout strength (max +25)
    score += int(breakout_strength * 25)
    
    score = min(score, 99)  # Cap at 99%
    
    if score >= 85:
        return score, "🔥", "Excellent setup - strong confluence"
    elif score >= 75:
        return score, "⚡", "Strong setup - high conviction"
    elif score >= 65:
        return score, "✨", "Good setup - worth considering"
    elif score >= 55:
        return score, "👍", "Moderate setup - proceed with caution"
    else:
        return score, "⚠️", "Weak setup - low confidence"


def build_professional_signal(
    symbol: str,
    direction: str,
    entry: float,
    stop_loss: float,
    atr: float,
    rsi: float,
    ema_direction: str,
    volume_spike: bool,
    funding_rate: float,
    funding_threshold: float = 0.0008,
    breakout_strength: float = 0.7,
    account_balance: float = 10000,  # Default for demo
) -> ProfessionalSignal:
    """
    Build a complete professional signal with all metrics.
    
    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        direction: "LONG" or "SHORT"
        entry: Entry price
        stop_loss: Stop loss price
        atr: Average True Range
        rsi: RSI value
        ema_direction: "LONG", "SHORT", or "NEUTRAL"
        volume_spike: Whether volume is elevated
        funding_rate: Current funding rate (decimal)
        funding_threshold: Max favorable funding rate
        breakout_strength: 0.0-1.0 strength of breakout
        account_balance: Account balance for position sizing
    
    Returns:
        ProfessionalSignal object
    """
    risk_distance = abs(entry - stop_loss)
    
    # Calculate TP levels
    tp_levels = calculate_tp_levels(entry, stop_loss, direction, atr, num_levels=3)
    
    # Position sizing
    position_size = calculate_position_size(entry, stop_loss, account_balance, ACCOUNT_RISK_PERCENT)
    position_size_percent = (position_size * entry / account_balance) * 100 if account_balance else 0
    
    # Leverage calculation
    max_loss_percent = (risk_distance / entry) * 100
    suggested_leverage = min(int(ACCOUNT_RISK_PERCENT / max_loss_percent) if max_loss_percent > 0 else 1, MAX_LEVERAGE_SUGGESTED)
    
    # Confidence
    funding_favorable = abs(funding_rate) < funding_threshold
    confidence_score, confidence_emoji, confidence_desc = calculate_confidence_score(
        rsi, ema_direction, volume_spike, funding_favorable, breakout_strength
    )
    
    # Build confidence notes
    notes = [confidence_desc]
    
    if ema_direction in ("LONG", "SHORT"):
        notes.append(f"EMA trend aligned ({ema_direction})")
    
    if volume_spike:
        notes.append("Strong volume confirmation")
    
    if abs(funding_rate) < funding_threshold:
        funding_pct = funding_rate * 100
        direction_text = "positive (favors long)" if funding_rate > 0 else "negative (favors short)"
        notes.append(f"Funding rate {funding_pct:.3f}% ({direction_text})")
    
    if 45 <= rsi <= 55:
        notes.append("RSI neutral - room to move")
    elif rsi > 65:
        notes.append("RSI elevated - watch for pullback")
    elif rsi < 35:
        notes.append("RSI depressed - watch for bounce")
    
    return ProfessionalSignal(
        symbol=symbol,
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        tp_levels=tp_levels,
        risk_amount=risk_distance,
        atr=atr,
        funding_rate=funding_rate,
        suggested_position_size=position_size_percent,
        suggested_leverage=suggested_leverage,
        max_loss_percent=max_loss_percent,
        rsi=rsi,
        ema_trend=ema_direction,
        volume_status="Elevated" if volume_spike else "Normal",
        confidence_score=confidence_score,
        confidence_notes=notes,
        liquidity_rating="High" if volume_spike else "Normal",
    )


def format_professional_signal_text(signal: ProfessionalSignal) -> str:
    """
    Format signal as professional text for Telegram.
    
    Returns:
        HTML-formatted signal text
    """
    direction_emoji = "📈" if signal.direction == "LONG" else "📉"
    direction_label = "LONG 🟢" if signal.direction == "LONG" else "SHORT 🔴"
    
    # Header
    header = (
        f"<b>╔═══════════════════════════════════╗</b>\n"
        f"<b>║  {direction_emoji} {direction_label:20s} ║</b>\n"
        f"<b>║  {signal.symbol:30s} ║</b>\n"
        f"<b>║  Confidence: {signal.confidence_score:.0f}%           ║</b>\n"
        f"<b>╚═══════════════════════════════════╝</b>"
    )
    
    # Entry & Stop Loss
    entry_section = (
        f"\n\n<b>💰 PRICE LEVELS</b>\n"
        f"<code>Entry Point : ${signal.entry:.8g}</code>\n"
        f"<code>Stop Loss   : ${signal.stop_loss:.8g}</code>\n"
        f"<code>Risk Amount : ${signal.risk_amount:.8g}</code>"
    )
    
    # Take Profit Levels
    tp_section = "<b>\n🎯 TAKE PROFIT LEVELS</b>\n"
    for tp in signal.tp_levels:
        tp_section += (
            f"<code>TP{tp.level}: ${tp.price:.8g} ({tp.target_percent:.0f}%) → "
            f"+{tp.reward_risk:.2f}R [{tp.confidence}]</code>\n"
        )
    
    # Risk Metrics
    risk_section = (
        f"\n<b>⚖️  RISK METRICS</b>\n"
        f"<code>Position Size: {signal.suggested_position_size:.2f}% of account</code>\n"
        f"<code>Max Loss: {signal.max_loss_percent:.2f}% if SL hit</code>\n"
        f"<code>ATR: {signal.atr:.8g}</code>\n"
        f"<code>Leverage: {signal.suggested_leverage}x (suggested)</code>"
    )
    
    # Market Context
    funding_emoji = "📈" if signal.funding_rate > 0 else ("📉" if signal.funding_rate < 0 else "➡️")
    market_section = (
        f"\n\n<b>🌍 MARKET CONTEXT</b>\n"
        f"<code>RSI: {signal.rsi:.1f}</code>\n"
        f"<code>EMA Trend: {signal.ema_trend}</code>\n"
        f"<code>Volume: {signal.volume_status}</code>\n"
        f"<code>Funding: {funding_emoji} {signal.funding_rate * 100:.3f}%</code>"
    )
    
    # Confidence Notes
    notes_section = f"\n\n<b>✅ SIGNAL ANALYSIS</b>\n"
    for note in signal.confidence_notes:
        notes_section += f"<code>• {note}</code>\n"
    
    # Risk Disclaimer
    disclaimer = (
        f"\n<b>⚠️  IMPORTANT</b>\n"
        f"<i>• Signals are educational analysis only</i>\n"
        f"• Trade at your own risk\n"
        f"• Always use stop losses\n"
        f"• Never risk more than 1-2% per trade\n"
        f"• Leverage = high risk of liquidation\n\n"
        f"<b>Good luck! 🚀</b>"
    )
    
    return header + entry_section + tp_section + risk_section + market_section + notes_section + disclaimer

