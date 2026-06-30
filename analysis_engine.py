"""
analysis_engine.py
Moteur d'analyse technique pour Boom & Crash.

Implémente :
- Détection de tendance (EMA + structure de marché)
- Détection des spikes (bougies Boom/Crash anormales)
- Order Blocks (OB) et Fair Value Gaps (FVG)
- Liquidity sweeps (EQH/EQL)
- CHoCH / BOS (changement de structure)
- Le système de scoring des 5 confirmations défini dans la stratégie
"""

from dataclasses import dataclass, field
from enum import Enum


class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ScenarioType(Enum):
    CONTINUATION = "Continuation de tendance"
    POST_SPIKE_RECOVERY = "Post-spike recovery"
    CHOCH_BOS = "CHoCH & BOS"
    LIQUIDITY_SWEEP = "Liquidity sweep"


@dataclass
class Signal:
    instrument: str
    timeframe: str
    direction: Direction
    scenario: ScenarioType
    entry_price: float
    stop_loss: float
    take_profit: float
    confirmations: list[str] = field(default_factory=list)
    confidence_score: int = 0  # sur 5 (nombre de confirmations validées)
    notes: str = ""


# ---------------------------------------------------------------------------
# Indicateurs de base
# ---------------------------------------------------------------------------

def ema(values: list[float], period: int) -> list[float]:
    """Calcule l'EMA (Exponential Moving Average)."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema_values = [sum(values[:period]) / period]
    for price in values[period:]:
        ema_values.append(price * k + ema_values[-1] * (1 - k))
    return ema_values


def candle_body_ratio(candle: dict) -> float:
    """Ratio corps/range total d'une bougie (mesure du momentum)."""
    full_range = candle["high"] - candle["low"]
    if full_range == 0:
        return 0
    body = abs(candle["close"] - candle["open"])
    return body / full_range


# ---------------------------------------------------------------------------
# Détection de spike (cœur de la mécanique Boom/Crash)
# ---------------------------------------------------------------------------

def detect_spike(candles: list[dict], lookback: int = 30, threshold_multiplier: float = 3.0) -> list[int]:
    """
    Détecte les bougies "spike" : celles dont le range (high-low) dépasse
    threshold_multiplier fois le range moyen des `lookback` bougies
    précédentes. Retourne les index des bougies spike dans la liste.
    """
    spike_indices = []
    for i in range(lookback, len(candles)):
        window = candles[i - lookback:i]
        avg_range = sum(c["high"] - c["low"] for c in window) / lookback
        if avg_range == 0:
            continue
        current_range = candles[i]["high"] - candles[i]["low"]
        if current_range > avg_range * threshold_multiplier:
            spike_indices.append(i)
    return spike_indices


def candles_since_last_spike(candles: list[dict]) -> int:
    """Nombre de bougies écoulées depuis le dernier spike détecté."""
    spikes = detect_spike(candles)
    if not spikes:
        return 9999
    return len(candles) - 1 - spikes[-1]


# ---------------------------------------------------------------------------
# Tendance multi-timeframe
# ---------------------------------------------------------------------------

def detect_trend(candles: list[dict]) -> Direction:
    """
    Détermine la tendance via EMA 20 vs EMA 50 sur les clôtures.
    EMA20 > EMA50 -> bullish, EMA20 < EMA50 -> bearish.
    """
    closes = [c["close"] for c in candles]
    if len(closes) < 55:
        return Direction.NEUTRAL

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    if not ema20 or not ema50:
        return Direction.NEUTRAL

    if ema20[-1] > ema50[-1]:
        return Direction.BULLISH
    elif ema20[-1] < ema50[-1]:
        return Direction.BEARISH
    return Direction.NEUTRAL


# ---------------------------------------------------------------------------
# Structure de marché : swing highs/lows, CHoCH, BOS
# ---------------------------------------------------------------------------

def find_swing_points(candles: list[dict], window: int = 3) -> tuple[list[int], list[int]]:
    """
    Identifie les swing highs et swing lows (pivot avec `window` bougies
    de chaque côté plus basses/hautes).
    Retourne (indices_swing_high, indices_swing_low).
    """
    highs, lows = [], []
    for i in range(window, len(candles) - window):
        local_high = candles[i]["high"]
        local_low = candles[i]["low"]
        is_swing_high = all(
            candles[j]["high"] <= local_high
            for j in range(i - window, i + window + 1) if j != i
        )
        is_swing_low = all(
            candles[j]["low"] >= local_low
            for j in range(i - window, i + window + 1) if j != i
        )
        if is_swing_high:
            highs.append(i)
        if is_swing_low:
            lows.append(i)
    return highs, lows


def detect_choch_bos(candles: list[dict]) -> str | None:
    """
    Détecte un Change of Character (CHoCH) : cassure d'un swing point
    dans le sens opposé à la tendance précédente.
    Retourne "bullish_choch", "bearish_choch", ou None.
    """
    highs, lows = find_swing_points(candles)
    if len(highs) < 2 or len(lows) < 2:
        return None

    last_close = candles[-1]["close"]
    last_swing_high = candles[highs[-1]]["high"]
    last_swing_low = candles[lows[-1]]["low"]

    if last_close > last_swing_high and len(lows) >= 2:
        if candles[lows[-1]]["low"] < candles[lows[-2]]["low"]:
            return "bullish_choch"

    if last_close < last_swing_low and len(highs) >= 2:
        if candles[highs[-1]]["high"] > candles[highs[-2]]["high"]:
            return "bearish_choch"

    return None


# ---------------------------------------------------------------------------
# Order Blocks (OB) et Fair Value Gaps (FVG)
# ---------------------------------------------------------------------------

def find_order_blocks(candles: list[dict], direction: Direction) -> list[dict]:
    """
    Identifie les Order Blocks non mitigés : la dernière bougie opposée
    à la tendance avant un mouvement impulsif dans le sens de la tendance.
    """
    obs = []
    for i in range(1, len(candles) - 3):
        c = candles[i]
        is_bearish = c["close"] < c["open"]
        is_bullish = c["close"] > c["open"]

        if direction == Direction.BULLISH and is_bearish:
            next3 = candles[i + 1:i + 4]
            if all(n["close"] > n["open"] for n in next3) and next3[-1]["close"] > c["high"]:
                obs.append({"index": i, "type": "bullish", "high": c["high"], "low": c["low"]})

        if direction == Direction.BEARISH and is_bullish:
            next3 = candles[i + 1:i + 4]
            if all(n["close"] < n["open"] for n in next3) and next3[-1]["close"] < c["low"]:
                obs.append({"index": i, "type": "bearish", "high": c["high"], "low": c["low"]})

    return obs


def find_fair_value_gaps(candles: list[dict]) -> list[dict]:
    """
    Détecte les Fair Value Gaps : déséquilibre de 3 bougies où la mèche
    de la bougie 1 ne touche pas la mèche de la bougie 3.
    """
    fvgs = []
    for i in range(2, len(candles)):
        c1, c3 = candles[i - 2], candles[i]
        if c1["high"] < c3["low"]:
            fvgs.append({"index": i, "type": "bullish", "top": c3["low"], "bottom": c1["high"]})
        elif c1["low"] > c3["high"]:
            fvgs.append({"index": i, "type": "bearish", "top": c1["low"], "bottom": c3["high"]})
    return fvgs


def is_price_in_zone(price: float, zone_low: float, zone_high: float) -> bool:
    return zone_low <= price <= zone_high


# ---------------------------------------------------------------------------
# Liquidity sweep (EQH / EQL)
# ---------------------------------------------------------------------------

def detect_liquidity_sweep(candles: list[dict], tolerance: float = 0.0015) -> str | None:
    """
    Détecte un sweep de liquidité : le prix dépasse un niveau de swing
    équivalent (EQH/EQL) puis clôture en deçà (rejet).
    """
    highs, lows = find_swing_points(candles)
    if len(highs) < 2 or len(lows) < 2:
        return None

    last = candles[-1]

    h1, h2 = candles[highs[-2]]["high"], candles[highs[-1]]["high"]
    if abs(h1 - h2) / h1 < tolerance:
        if last["high"] > max(h1, h2) and last["close"] < max(h1, h2):
            return "eqh_sweep"

    l1, l2 = candles[lows[-2]]["low"], candles[lows[-1]]["low"]
    if abs(l1 - l2) / l1 < tolerance:
        if last["low"] < min(l1, l2) and last["close"] > min(l1, l2):
            return "eql_sweep"

    return None


# ---------------------------------------------------------------------------
# Moteur principal : analyse multi-timeframe et génération de signal
# ---------------------------------------------------------------------------

INSTRUMENT_BIAS = {
    "Boom": Direction.BEARISH,
    "Crash": Direction.BULLISH,
}


def get_instrument_family(instrument_name: str) -> str:
    return "Boom" if instrument_name.startswith("Boom") else "Crash"


def analyze_instrument(instrument_name: str, timeframes_data: dict[str, list[dict]]) -> Signal | None:
    """
    Analyse complète multi-timeframe d'un instrument selon la logique :
    - H4/H1 : direction de tendance
    - M30/M15 : structure intermédiaire, OB/FVG, CHoCH
    - M5 : timing d'entrée, bougie de confirmation

    Applique les 5 confirmations obligatoires. Retourne un Signal si
    au moins 4/5 confirmations sont validées, sinon None.
    """
    h4 = timeframes_data.get("H4", [])
    h1 = timeframes_data.get("H1", [])
    m30 = timeframes_data.get("M30", [])
    m15 = timeframes_data.get("M15", [])
    m5 = timeframes_data.get("M5", [])

    if not all([h4, h1, m30, m15, m5]) or len(h4) < 55 or len(h1) < 55:
        return None

    confirmations = []
    family = get_instrument_family(instrument_name)
    structural_bias = INSTRUMENT_BIAS[family]

    trend_h4 = detect_trend(h4)
    trend_h1 = detect_trend(h1)
    if trend_h4 == trend_h1 and trend_h4 != Direction.NEUTRAL:
        confirmations.append(f"Tendance alignée H4/H1: {trend_h4.value}")
        direction = trend_h4
    else:
        return None

    if candles_since_last_spike(m5) < 5:
        return None

    scenario = None

    choch_signal = detect_choch_bos(m15)
    sweep_signal = detect_liquidity_sweep(m15)

    if sweep_signal == "eqh_sweep" and direction == Direction.BEARISH:
        scenario = ScenarioType.LIQUIDITY_SWEEP
        confirmations.append("Sweep de liquidité EQH détecté (M15)")
    elif sweep_signal == "eql_sweep" and direction == Direction.BULLISH:
        scenario = ScenarioType.LIQUIDITY_SWEEP
        confirmations.append("Sweep de liquidité EQL détecté (M15)")
    elif choch_signal == "bullish_choch" and direction == Direction.BEARISH:
        scenario = ScenarioType.CHOCH_BOS
        confirmations.append("CHoCH haussier confirmé (M15)")
        direction = Direction.BULLISH
    elif choch_signal == "bearish_choch" and direction == Direction.BULLISH:
        scenario = ScenarioType.CHOCH_BOS
        confirmations.append("CHoCH baissier confirmé (M15)")
        direction = Direction.BEARISH
    else:
        scenario = ScenarioType.CONTINUATION
        confirmations.append("Scénario de continuation de tendance")

    obs = find_order_blocks(m15, direction)
    fvgs = find_fair_value_gaps(m5)

    current_price = m5[-1]["close"]
    in_ob = False
    in_fvg = False
    entry_zone = None

    for ob in obs[-3:]:
        if is_price_in_zone(current_price, ob["low"], ob["high"]):
            in_ob = True
            entry_zone = ob
            break

    if not in_ob:
        for fvg in fvgs[-3:]:
            if is_price_in_zone(current_price, fvg["bottom"], fvg["top"]):
                in_fvg = True
                entry_zone = fvg
                break

    if in_ob:
        confirmations.append("Prix dans un Order Block non mitigé")
    elif in_fvg:
        confirmations.append("Prix dans un Fair Value Gap")
    else:
        return None

    last_candle = m5[-1]
    body_ratio = candle_body_ratio(last_candle)
    is_bullish_candle = last_candle["close"] > last_candle["open"]
    is_bearish_candle = last_candle["close"] < last_candle["open"]

    confirmation_candle_valid = False
    if direction == Direction.BULLISH and is_bullish_candle and body_ratio > 0.5:
        confirmation_candle_valid = True
    elif direction == Direction.BEARISH and is_bearish_candle and body_ratio > 0.5:
        confirmation_candle_valid = True

    if confirmation_candle_valid:
        confirmations.append(f"Bougie de confirmation M5 (corps {body_ratio:.0%})")
    else:
        return None

    recent_bodies = [candle_body_ratio(c) for c in m5[-5:]]
    avg_body_ratio = sum(recent_bodies) / len(recent_bodies)
    if avg_body_ratio > 0.4:
        confirmations.append(f"Momentum M5 cohérent (corps moyen {avg_body_ratio:.0%})")
    else:
        return None

    highs, lows = find_swing_points(m15)
    if not highs or not lows:
        return None

    buffer = abs(current_price) * 0.002

    if direction == Direction.BULLISH:
        last_swing_low = m15[lows[-1]]["low"]
        stop_loss = last_swing_low - buffer
        risk = current_price - stop_loss
        if risk <= 0:
            return None
        take_profit = current_price + (risk * 2.5)
    else:
        last_swing_high = m15[highs[-1]]["high"]
        stop_loss = last_swing_high + buffer
        risk = stop_loss - current_price
        if risk <= 0:
            return None
        take_profit = current_price - (risk * 2.5)

    confirmations.append("SL structurel placé (RR 1:2.5)")

    score = len(confirmations)
    if score < 4:
        return None

    return Signal(
        instrument=instrument_name,
        timeframe="Multi (H4→M5)",
        direction=direction,
        scenario=scenario,
        entry_price=current_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confirmations=confirmations,
        confidence_score=score,
        notes=f"Biais structurel {family}: {structural_bias.value}",
    )


def analyze_all_instruments(market_data: dict[str, dict[str, list[dict]]]) -> list[Signal]:
    """Lance l'analyse sur tous les instruments et retourne les signaux valides."""
    signals = []
    for instrument_name, timeframes_data in market_data.items():
        signal = analyze_instrument(instrument_name, timeframes_data)
        if signal:
            signals.append(signal)
    return signals
