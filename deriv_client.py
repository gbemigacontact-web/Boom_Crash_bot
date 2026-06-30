"""
deriv_client.py
Client WebSocket pour l'API Deriv - récupération des données OHLC
pour les indices synthétiques Boom & Crash.

L'API Deriv est gratuite pour la lecture de données (pas besoin de
compte financé). Documentation officielle : https://developers.deriv.com
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import websockets

logger = logging.getLogger("deriv_client")

DERIV_WS_URL = "wss://ws.derivws.com/websockets/v3?app_id={app_id}"

# Mapping timeframe -> granularité Deriv (en secondes)
TIMEFRAME_GRANULARITY = {
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
}

# Nombre de bougies à récupérer par timeframe (assez pour calculer
# structure, EMA, swing highs/lows, OB, FVG)
CANDLE_COUNT = {
    "M5": 200,
    "M15": 200,
    "M30": 150,
    "H1": 150,
    "H4": 100,
}

# Symboles Deriv officiels pour Boom & Crash
# (vérifiés sur la liste des "Continuous Indices" de Deriv)
INSTRUMENTS = {
    "Boom 500": "BOOM500",
    "Boom 900": "BOOM900",
    "Boom 1000": "BOOM1000",
    "Crash 500": "CRASH500",
    "Crash 900": "CRASH900",
    "Crash 1000": "CRASH1000",
}


class DerivClient:
    """Client minimal pour interroger l'API Deriv via WebSocket."""

    def __init__(self, api_token: str | None = None, app_id: str = "1089"):
        """
        api_token: token API Deriv (lecture seule suffit). Peut être None
                   pour les requêtes publiques de marché (candles), mais
                   on l'utilise quand même pour l'authentification et
                   éviter les limites de rate-limit anonymes.
        app_id: identifiant d'application Deriv. 1089 est l'app_id de
                démonstration publique fournie par Deriv pour les tests.
                Pour la production, créer son propre app_id sur
                https://api.deriv.com (gratuit).
        """
        self.api_token = api_token
        self.app_id = app_id
        self.ws = None

    async def connect(self):
        url = DERIV_WS_URL.format(app_id=self.app_id)
        self.ws = await websockets.connect(url, ping_interval=20, ping_timeout=10)
        if self.api_token:
            await self._authorize()

    async def _authorize(self):
        await self.ws.send(json.dumps({"authorize": self.api_token}))
        response = json.loads(await self.ws.recv())
        if "error" in response:
            raise RuntimeError(f"Échec d'authentification Deriv: {response['error']['message']}")
        logger.info("Authentifié sur Deriv avec succès.")

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def get_candles(self, symbol: str, timeframe: str) -> list[dict]:
        """
        Récupère l'historique de bougies OHLC pour un symbole et un
        timeframe donné via la requête ticks_history (style="candles").
        Retourne une liste de dicts avec: epoch, open, high, low, close.
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
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
            }
            for c in candles
        ]
        return parsed

    async def get_all_timeframes(self, symbol: str) -> dict[str, list[dict]]:
        """Récupère les 5 timeframes (H4, H1, M30, M15, M5) pour un symbole."""
        result = {}
        for tf in ["H4", "H1", "M30", "M15", "M5"]:
            try:
                result[tf] = await self.get_candles(symbol, tf)
                # Petite pause pour respecter le rate-limit Deriv
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Erreur récupération {symbol} {tf}: {e}")
                result[tf] = []
        return result


async def fetch_market_data() -> dict[str, dict[str, list[dict]]]:
    """
    Point d'entrée principal : récupère les données pour tous les
    instruments Boom/Crash configurés, sur tous les timeframes.
    Retourne: { "Boom 1000": { "H4": [...], "H1": [...], ... }, ... }
    """
    api_token = os.environ.get("DERIV_API_TOKEN")
    app_id = os.environ.get("DERIV_APP_ID", "1089")

    client = DerivClient(api_token=api_token, app_id=app_id)
    await client.connect()

    all_data = {}
    try:
        for name, symbol in INSTRUMENTS.items():
            logger.info(f"Récupération des données pour {name} ({symbol})...")
            all_data[name] = await client.get_all_timeframes(symbol)
    finally:
        await client.close()

    return all_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = asyncio.run(fetch_market_data())
    for instrument, timeframes in data.items():
        for tf, candles in timeframes.items():
            print(f"{instrument} {tf}: {len(candles)} bougies récupérées")
