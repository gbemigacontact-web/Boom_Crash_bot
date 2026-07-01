"""
telegram_notifier.py
Envoi des signaux formatés vers Telegram.
"""

import logging
import os
import requests
from analysis_engine import Direction, Signal

logger = logging.getLogger("telegram_notifier")
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def format_signal_message(signal: Signal) -> str:
    direction_label = "ACHAT (BUY)" if signal.direction == Direction.BULLISH else "VENTE (SELL)"
    direction_emoji = "🟢" if signal.direction == Direction.BULLISH else "🔴"

    risk = abs(signal.entry_price - signal.stop_loss)
    reward = abs(signal.take_profit - signal.entry_price)
    rr_ratio = reward / risk if risk > 0 else 0
    confirmations_text = "\n".join(f"  • {c}" for c in signal.confirmations)

    return (
        f"{direction_emoji} <b>SIGNAL {direction_label}</b>\n"
        f"<b>Instrument :</b> {signal.instrument}\n"
        f"<b>Scénario :</b> {signal.scenario.value}\n"
        f"<b>Confiance :</b> {signal.confidence_score}/6 confirmations\n\n"
        f"<b>Entrée :</b> {signal.entry_price:.4f}\n"
        f"<b>Stop Loss :</b> {signal.stop_loss:.4f}\n"
        f"<b>Take Profit :</b> {signal.take_profit:.4f}\n"
        f"<b>Ratio R:R :</b> 1:{rr_ratio:.1f}\n\n"
        f"<b>Confirmations validées :</b>\n{confirmations_text}\n\n"
        f"<i>{signal.notes}</i>\n\n"
        f"⚠️ <i>Signal automatique — vérifier avant d'exécuter.</i>"
    )


def send_telegram_message(message: str) -> bool:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        return False
    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=bot_token),
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=15,
        )
        response.raise_for_status()
        logger.info("Message Telegram envoyé.")
        return True
    except requests.RequestException as e:
        logger.error(f"Échec Telegram: {e}")
        return False


def send_signals(signals: list) -> None:
    if not signals:
        logger.info("Aucun signal valide ce scan.")
        return
    for signal in signals:
        send_telegram_message(format_signal_message(signal))


def send_run_summary(total_instruments: int, signals_count: int) -> None:
    message = (
        f"🔍 <b>Scan terminé</b>\n"
        f"Instruments analysés : {total_instruments}\n"
        f"Signaux détectés : {signals_count}"
    )
    send_telegram_message(message)
