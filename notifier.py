"""
notifier.py — Telegram notification system with professional signal formatting.

Sends:
  - Professional multi-TP signals with risk metrics
  - Trade outcome notifications (TP hit, SL hit, expired)
  - Performance summaries
  - Bot status messages

Uses Telegram Bot API with retry logic and error handling.
"""

import logging
import time
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED
from signal_formatter import ProfessionalSignal, format_professional_signal_text

log = logging.getLogger("notifier")

_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # seconds, multiplied by attempt number


def fmt_price(value: float) -> str:
    """Format price with appropriate decimals."""
    if value is None:
        return "N/A"
    if value >= 1000:
        return f"${value:,.2f}"
    elif value >= 1:
        return f"${value:.4f}"
    else:
        return f"${value:.8g}"


def _send_raw(text: str, parse_mode: str = "HTML") -> bool:
    """
    Send raw message to Telegram.
    
    Args:
        text: Message text (HTML or plain)
        parse_mode: "HTML" or "Markdown"
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_ENABLED:
        log.warning("Telegram not enabled, skipping notification")
        return False
    
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
            }
            resp = requests.post(_API_URL, json=payload, timeout=10)
            
            if resp.status_code == 200:
                log.debug("Telegram message sent (attempt %s)", attempt)
                return True
            else:
                log.warning(
                    "Telegram API error (attempt %s/%s): %s — %s",
                    attempt, _MAX_RETRIES, resp.status_code, resp.text,
                )
        except requests.RequestException as e:
            log.warning("Network error sending Telegram message (attempt %s/%s): %s",
                        attempt, _MAX_RETRIES, e)
        
        if attempt < _MAX_RETRIES:
            sleep_time = _RETRY_BACKOFF * attempt
            log.debug("Retrying Telegram send in %.1fs", sleep_time)
            time.sleep(sleep_time)
    
    log.error("Failed to send Telegram message after %s attempts", _MAX_RETRIES)
    return False


def send_professional_signal(signal: ProfessionalSignal) -> bool:
    """
    Send professional signal with multiple TPs and risk metrics.
    
    Args:
        signal: ProfessionalSignal object
    
    Returns:
        True if sent successfully
    """
    if not signal:
        return False
    
    message = format_professional_signal_text(signal)
    success = _send_raw(message, parse_mode="HTML")
    
    if success:
        log.info("Professional signal sent for %s %s", signal.direction, signal.symbol)
    else:
        log.error("Failed to send professional signal for %s", signal.symbol)
    
    return success


def send_trade_outcome(
    symbol: str,
    direction: str,
    entry: float,
    exit_price: float,
    tp_or_sl: str,
    pnl_r: float,
) -> bool:
    """
    Send trade outcome notification (TP HIT, SL HIT, or EXPIRED).
    
    Args:
        symbol: Trading pair
        direction: "LONG" or "SHORT"
        entry: Entry price
        exit_price: Exit price
        tp_or_sl: "TP_HIT", "SL_HIT", or "EXPIRED"
        pnl_r: P&L in risk units
    
    Returns:
        True if sent successfully
    """
    direction_label = "📈 LONG" if direction == "LONG" else "📉 SHORT"
    
    if tp_or_sl == "TP_HIT":
        outcome_emoji = "✅"
        outcome_label = "PROFIT - TP HIT!"
        outcome_color = "🟢"
    elif tp_or_sl == "SL_HIT":
        outcome_emoji = "❌"
        outcome_label = "LOSS - SL HIT"
        outcome_color = "🔴"
    else:  # EXPIRED
        outcome_emoji = "⏰"
        outcome_label = "EXPIRED"
        outcome_color = "⚪"
    
    pnl_label = f"+{pnl_r:.2f}R" if pnl_r >= 0 else f"{pnl_r:.2f}R"
    
    message = (
        f"<b>{outcome_emoji} TRADE CLOSED {outcome_color}</b>\n\n"
        f"<b>{direction_label} {symbol}</b>\n"
        f"<code>Entry  : {fmt_price(entry)}</code>\n"
        f"<code>Exit   : {fmt_price(exit_price)}</code>\n"
        f"<code>Result : {pnl_label}</code>\n\n"
        f"<b>{outcome_label}</b>"
    )
    
    return _send_raw(message, parse_mode="HTML")


def send_performance_summary(summary_data: dict) -> bool:
    """
    Send performance summary statistics.
    
    Args:
        summary_data: Dict with keys: total, tp_count, sl_count, avg_r, total_r, win_rate
    
    Returns:
        True if sent successfully
    """
    total = summary_data.get("total", 0)
    tp_count = summary_data.get("tp_count", 0)
    sl_count = summary_data.get("sl_count", 0)
    avg_r = summary_data.get("avg_r", 0)
    total_r = summary_data.get("total_r", 0)
    win_rate = summary_data.get("win_rate", 0)
    
    message = (
        f"<b>📊 PERFORMANCE SUMMARY</b>\n\n"
        f"<code>Closed Trades: {total}</code>\n"
        f"<code>✅ TP Hits   : {tp_count}</code>\n"
        f"<code>❌ SL Hits   : {sl_count}</code>\n"
        f"<code>Win Rate    : {win_rate:.1f}%</code>\n\n"
        f"<code>Avg Win     : +{avg_r:.2f}R</code>\n"
        f"<code>Net Result  : {total_r:+.2f}R</code>\n\n"
        f"<b>Keep up the discipline! 🚀</b>"
    )
    
    return _send_raw(message, parse_mode="HTML")


def send_status_message(message_text: str, status_type: str = "info") -> bool:
    """
    Send bot status message (startup, error, etc).
    
    Args:
        message_text: Message content
        status_type: "start", "stop", "error", "info", "warning"
    
    Returns:
        True if sent successfully
    """
    if status_type == "start":
        emoji = "✅"
        title = "BOT STARTED"
    elif status_type == "stop":
        emoji = "⛔"
        title = "BOT STOPPED"
    elif status_type == "error":
        emoji = "⚠️"
        title = "ERROR"
    elif status_type == "warning":
        emoji = "🚨"
        title = "WARNING"
    else:
        emoji = "ℹ️"
        title = "INFO"
    
    message = (
        f"<b>{emoji} {title}</b>\n\n"
        f"{message_text}"
    )
    
    return _send_raw(message, parse_mode="HTML")


def send_startup_notification(config_info: str) -> bool:
    """
    Send bot startup notification with configuration summary.
    
    Args:
        config_info: Configuration summary text
    
    Returns:
        True if sent successfully
    """
    message = (
        f"<b>✅ BITGET SIGNAL BOT ONLINE</b>\n\n"
        f"<b>🤖 Bot Status</b>\n"
        f"<code>Status: Ready to scan</code>\n"
        f"<code>Mode: Futures (USDT-FUTURES)</code>\n\n"
        f"<b>⚙️  Configuration</b>\n"
        f"{config_info}\n\n"
        f"<b>📡 Awaiting market opportunities...</b>\n"
        f"<i>Signals will appear here as they're detected</i>"
    )
    
    return _send_raw(message, parse_mode="HTML")


def send_error_notification(error_message: str, context: str = "") -> bool:
    """
    Send error notification.
    
    Args:
        error_message: Error description
        context: Additional context (e.g., symbol, function name)
    
    Returns:
        True if sent successfully
    """
    context_str = f"\n<code>Context: {context}</code>" if context else ""
    
    message = (
        f"<b>⚠️  BOT ERROR</b>\n\n"
        f"<code>Error: {error_message}</code>{context_str}\n\n"
        f"<i>Check logs for details. The bot will attempt to recover.</i>"
    )
    
    return _send_raw(message, parse_mode="HTML")


# Convenience function for backward compatibility
def send_signal(signal: ProfessionalSignal) -> bool:
    """Legacy function name — calls send_professional_signal."""
    return send_professional_signal(signal)


def send_status(text: str, status_type: str = "info") -> bool:
    """Legacy function name — calls send_status_message."""
    return send_status_message(text, status_type)
