"""
deriv_client.py
Client WebSocket pour l'API Deriv - récupération des données OHLC
pour les indices synthétiques Boom & Crash.

IMPORTANT : Les synthetic indices de Deriv (Boom/Crash) sont accessibles
en lecture SANS authentification. Le token n'est requis que pour trader.
On utilise l'app_id public 1089 (fourni par Deriv pour les tests/lecture).
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import websockets

logger = logging.getLogger("deriv_client")

DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id={app_id}"

TIMEFRAME_GRANULARITY = {
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
}

CANDLE_COUNT = {
    "M5": 200,
    "M15": 200,
    "M30": 150,
    "H1": 150,
    "H4": 100,
}

# Symboles officiels Deriv pour Boom & Crash synthetic indices
INSTRUMENTS = {
    "Boom 500":   "BOOM500",
    "Boom 900":   "BOOM900",
    "Boom 1000":  "BOOM1000",
    "Crash 500":  "CRASH500",
    "Crash 900":  "CRASH900",
    "Crash 1000": "CRASH1000",
}


class DerivClient:
    """
    Client WebSocket Deriv sans authentification.
    La lecture des prix synthétiques est publique sur Deriv —
    aucun token requis pour ticks_history.
    """

    def __init__(self, app_id: str = "1089"):
        self.app_id = app_id
        self.ws = None

    async def connect(self):
        url = DERIV_WS_URL.format(app_id=self.app_id)
        self.ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
        )
        logger.info(f"Connecté à l'API Deriv (app_id={self.app_id}) — mode lecture publique.")

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def get_candles(self, symbol: str, timeframe: str) -> list[dict]:
        """
        Récupère l'historique OHLC via ticks_history (style=candles).
        Aucune authentification requise pour les synthetic indices.
        """
        granularity = TIMEFRAME_GRANULARITY[timeframe]
        count = CANDLE_COUNT[timeframe]

        request = {
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "start": 1,
            "style": "candles",
            "granularity": granularity,
        }

        await self.ws.send(json.dumps(request))
        response = json.loads(await self.ws.recv())

        if "error" in response:
            raise RuntimeError(
                f"Erreur API Deriv pour {symbol} {timeframe}: {response['error']['message']}"
            )

        candles = response.get("candles", [])
        parsed = [
            {
                "time": datetime.fromtimestamp(c["epoch"], tz=timezone.utc),
                "open":  float(c["open"]),
                "high":  float(c["high"]),
                "low":   float(c["low"]),
                "close": float(c["close"]),
            }
            for c in candles
        ]
        logger.info(f"{symbol} {timeframe}: {len(parsed)} bougies récupérées.")
        return parsed

    async def get_all_timeframes(self, symbol: str) -> dict[str, list[dict]]:
        """Récupère les 5 timeframes pour un symbole donné."""
        result = {}
        for tf in ["H4", "H1", "M30", "M15", "M5"]:
            try:
                result[tf] = await self.get_candles(symbol, tf)
                await asyncio.sleep(0.5)  # respecter le rate-limit Deriv
            except Exception as e:
                logger.error(f"Erreur récupération {symbol} {tf}: {e}")
                result[tf] = []
        return result


async def fetch_market_data() -> dict[str, dict[str, list[dict]]]:
    """
    Récupère les données pour tous les instruments sur tous les timeframes.
    Retourne: { "Boom 1000": { "H4": [...], "H1": [...], ... }, ... }
    """
    app_id = os.environ.get("DERIV_APP_ID", "1089")
    client = DerivClient(app_id=app_id)
    await client.connect()

    all_data = {}
    try:
        for name, symbol in INSTRUMENTS.items():
            logger.info(f"Récupération des données pour {name} ({symbol})...")
            all_data[name] = await client.get_all_timeframes(symbol)
    finally:
        await client.close()

    return all_data
