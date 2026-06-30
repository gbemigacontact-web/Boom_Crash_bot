"""
main.py
Point d'entrée principal du bot Boom & Crash.
Orchestration : récupération des données → analyse → notification.
Appelé par GitHub Actions 6x/jour.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

from analysis_engine import analyze_all_instruments
from deriv_client import fetch_market_data, INSTRUMENTS
from telegram_notifier import send_signals, send_run_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


async def run():
    logger.info(f"=== Démarrage du scan — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")

    # 1. Récupération des données depuis l'API Deriv
    try:
        market_data = await fetch_market_data()
        logger.info(f"Données récupérées pour {len(market_data)} instruments.")
    except Exception as e:
        logger.error(f"Erreur critique lors de la récupération des données: {e}")
        sys.exit(1)

    # 2. Analyse multi-timeframe et détection des signaux
    signals = analyze_all_instruments(market_data)
    logger.info(f"Analyse terminée — {len(signals)} signal(s) valide(s) détecté(s).")

    # 3. Envoi des signaux sur Telegram
    send_signals(signals)

    # 4. Résumé de run (toujours envoyé pour confirmer que le bot tourne)
    send_run_summary(total_instruments=len(INSTRUMENTS), signals_count=len(signals))

    logger.info("=== Scan terminé ===")


if __name__ == "__main__":
    asyncio.run(run())
