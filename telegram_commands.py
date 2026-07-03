"""
telegram_commands.py — Telegram command listener (long-polling).

This is the missing piece: notifier.py only ever *sends* messages, nothing
in the original codebase ever listened for incoming ones. That's why
/start, /help, /stats did nothing — the bot never read updates from Telegram.

Runs in its own daemon thread using getUpdates long-polling (no webhook
server needed, works fine on Railway's worker/no-open-port setup).

Commands:
  /start   — confirms the bot is alive
  /help    — lists commands
  /status  — uptime + symbols being watched
  /stats   — quick performance summary from the DB
"""

import logging
import threading
import time

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED, WHITELIST_SYMBOLS

log = logging.getLogger("telegram_commands")

_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
_POLL_TIMEOUT = 25  # seconds — long-poll wait, Telegram holds the connection open


def _send(chat_id, text: str):
    try:
        requests.post(
            f"{_API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except requests.RequestException as e:
        log.warning("Failed to send command reply: %s", e)


def _handle_command(chat_id, text: str, bot_start_time: float):
    cmd = text.strip().split()[0].lower().split("@")[0]  # strip /cmd@BotName args

    if cmd == "/start":
        _send(
            chat_id,
            "✅ <b>Bitget Signal Bot is online.</b>\n\n"
            "I scan the market automatically and push signals here — "
            "you don't need to send commands for that.\n\n"
            "Type /help to see what I can tell you.",
        )

    elif cmd == "/help":
        _send(
            chat_id,
            "<b>Available commands</b>\n"
            "/start — check the bot is alive\n"
            "/status — uptime + watched pairs\n"
            "/stats — recent signal performance",
        )

    elif cmd == "/status":
        uptime_min = int((time.time() - bot_start_time) / 60)
        _send(
            chat_id,
            f"<b>🤖 Bot Status</b>\n"
            f"<code>Uptime: {uptime_min} min</code>\n"
            f"<code>Watching: {', '.join(WHITELIST_SYMBOLS)}</code>",
        )

    elif cmd == "/stats":
        try:
            import database as db
            rows = db.get_performance_summary()
            if not rows:
                _send(chat_id, "📊 No closed signals yet — check back later.")
                return
            lines = ["<b>📊 Performance Summary</b>", ""]
            for r in rows:
                lines.append(f"{r['status']}: {r['cnt']} (avg {r['avg_r']:.2f}R)")
            _send(chat_id, "\n".join(lines))
        except Exception as e:
            log.warning("Error building /stats reply: %s", e)
            _send(chat_id, "⚠️ Couldn't load stats right now — check logs.")


def _poll_loop(stop_event: threading.Event):
    if not TELEGRAM_ENABLED:
        log.info("Telegram not configured — command listener not started.")
        return

    bot_start_time = time.time()
    offset = None
    log.info("Telegram command listener started (long-polling).")

    while not stop_event.is_set():
        try:
            params = {"timeout": _POLL_TIMEOUT}
            if offset is not None:
                params["offset"] = offset

            resp = requests.get(f"{_API_BASE}/getUpdates", params=params,
                                 timeout=_POLL_TIMEOUT + 10)
            resp.raise_for_status()
            body = resp.json()

            if not body.get("ok"):
                log.warning("getUpdates returned not-ok: %s", body)
                time.sleep(5)
                continue

            for update in body.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                text = message.get("text", "")
                chat_id = message.get("chat", {}).get("id")
                if not text.startswith("/") or chat_id is None:
                    continue
                _handle_command(chat_id, text, bot_start_time)

        except requests.RequestException as e:
            log.warning("Telegram polling error: %s — retrying in 5s", e)
            time.sleep(5)
        except Exception as e:
            log.exception("Unexpected error in command listener: %s", e)
            time.sleep(5)

    log.info("Telegram command listener stopped.")


_stop_event = threading.Event()
_thread = None


def start():
    """Start the command listener in a daemon thread. Safe to call once."""
    global _thread
    if _thread is not None:
        log.warning("Command listener already started")
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_poll_loop, args=(_stop_event,), daemon=True)
    _thread.start()


def stop():
    """Signal the command listener to stop and wait briefly for it to exit."""
    global _thread
    _stop_event.set()
    if _thread:
        _thread.join(timeout=5)
        _thread = None
