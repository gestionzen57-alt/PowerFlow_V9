"""V10 ICT 2022 — Kill Zones + OTE Fibonacci (HERMES autopilote quant Sprint 3b).

Implémente la stratégie publique ICT (Inner Circle Trader) 2022 en pure
Python (100% stdlib, aucune dépendance quant externe — cf. pyproject.toml) :

  KILL ZONES (fenêtres temporelles de forte volatilité, UTC) :
    ASIAN  : 00:00 - 08:00  (Tokyo range — souvent un range étroit avant London)
    LONDON : 08:00 - 13:00  (London open — momentum, liquidity grab)
    NY     : 13:00 - 17:00  (New York AM — le plus volatile, NY open)
    (cohérent avec v10_session_filter mais ici orienté *setup* plutôt que
     qualité de session)

  OTE (Optimal Trade Entry) — zone optimale d'entrée après un sweep :
    Entrée long  : retracement 62% - 79% du swing bas → haut (bullish leg)
    Entrée short : retracement 62% - 79% du swing haut → bas (bearish leg)

  Règle de trading ICT 2022 simplifiée :
    - Kill Zone active ET retracement dans la zone OTE 62-79%
    - Bonus si la Kill Zone est LONDON ou NY (forte conviction)
    - Bonus si la direction du retracement s'aligne avec le bias de la
      structure (premium/discount)

Doctrine V10 : R1-AGIR, R2 additif pur (0 import core/v9/), R6 fail-open
(données insuffisantes → niveau NONE, pas d'exception), R7 tests verts,
R9 audit sérialisable, R10 zéro ordre réel (compute only).

Intégration : le module expose compute_ict_ote() qui peut être branché dans
l'orchestrateur v10 en tant que composant CoT bonus / filtre de conviction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class KillZone(str, Enum):
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NY = "NY"
    OUTSIDE = "OUTSIDE"  # hors zone de forte volatilité → pas de setup
    UNKNOWN = "UNKNOWN"  # R6 fail-open


class OteBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


# ─────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────
# Kill Zones en heures UTC (ICT 2022).
KILL_ZONES_HOURS_UTC: Dict[KillZone, Tuple[int, int]] = {
    KillZone.ASIAN: (0, 8),
    KillZone.LONDON: (8, 13),
    KillZone.NY: (13, 17),
}

# OTE : zone de retracement optimale (62% - 79%).
OTE_LOW: float = 0.62
OTE_HIGH: float = 0.79

# Seuil de conviction pour un setup "haute qualité" (score ≥ 0.70).
HIGH_CONVICTION_THRESHOLD: float = 0.70


@dataclass
class OteSetup:
    """Setup ICT OTE calculé pour un swing donné."""

    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""
    # Kill zone active
    kill_zone: KillZone = KillZone.UNKNOWN
    # Bias déduit du swing (le retracement cible)
    bias: OteBias = OteBias.NEUTRAL
    # Niveau de la zone OTE
    ote_low: float = 0.0
    ote_high: float = 0.0
    # Le prix actuel est-il dans la zone OTE ?
    in_ote: bool = False
    # Score de conviction composite [0, 1]
    conviction_score: float = 0.0
    high_conviction: bool = False
    # Retracement réel du prix dans le swing
    retracement_ratio: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "kill_zone": self.kill_zone.value,
            "bias": self.bias.value,
            "ote_low": round(self.ote_low, 5),
            "ote_high": round(self.ote_high, 5),
            "in_ote": self.in_ote,
            "conviction_score": round(self.conviction_score, 3),
            "high_conviction": self.high_conviction,
            "retracement_ratio": round(self.retracement_ratio, 4),
            "audit": dict(self.audit),
        }


def _kill_zone_at_hour(hour_utc: int) -> KillZone:
    """Renvoie la Kill Zone ICT pour une heure UTC donnée. R6 : hors zone → OUTSIDE."""
    if 0 <= hour_utc < 8:
        return KillZone.ASIAN
    if 8 <= hour_utc < 13:
        return KillZone.LONDON
    if 13 <= hour_utc < 17:
        return KillZone.NY
    return KillZone.OUTSIDE


def _parse_utc(timestamp: Optional[str]) -> datetime:
    """Parse un timestamp ISO UTC. R6 fail-open : invalide → maintenant UTC."""
    if timestamp:
        try:
            s = timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except (ValueError, OSError):
            pass
    return datetime.now(timezone.utc)


def _swing_extremes(
    closes: List[float], highs: List[float], lows: List[float]
) -> Tuple[float, float, float]:
    """Retourne (swing_high, swing_low, current_price) depuis le swing récent.

    Le swing est délimité par l'extremum haut et l'extremum bas sur la
    fenêtre (max des highs, min des lows). R6 : données insuffisantes →
    (0.0, 0.0, 0.0) → setup NONE.
    """
    if not closes:
        return 0.0, 0.0, 0.0
    cur = float(closes[-1])
    if not highs or not lows:
        return cur, cur, cur
    swing_high = float(max(highs))
    swing_low = float(min(lows))
    return swing_high, swing_low, cur


def _trend_bias(closes: List[float], lookback: Optional[int] = None) -> OteBias:
    """Bias de tendance via la pente linéaire des closes récentes.

    Indépendant de la bande OTE : c'est la direction du mouvement dominant
    du swing. BULLISH si pente > 0, BEARISH si pente < 0, NEUTRAL sinon.
    R6 : données courtes → NEUTRAL.
    """
    n = lookback or 10
    seg = closes[-n:]
    if len(seg) < 2:
        return OteBias.NEUTRAL
    xs = list(range(len(seg)))
    ys = [float(v) for v in seg]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 0:
        return OteBias.NEUTRAL
    slope = cov / var_x
    if slope > 0:
        return OteBias.BULLISH
    if slope < 0:
        return OteBias.BEARISH
    return OteBias.NEUTRAL


def _retracement_ratio(swing_high: float, swing_low: float, price: float) -> float:
    """Ratio de retracement du prix entre swing_low (0) et swing_high (1).

    Long (bullish) : le prix retrace depuis le haut vers le bas → ratio
    décroissant de 1.0 à 0.0. On regarde le retracement *depuis le swing*.

    R6 : swing plat (high == low) → 0.0 (neutral).
    """
    span = swing_high - swing_low
    if span <= 0:
        return 0.0
    return (price - swing_low) / span


def compute_ict_ote(
    symbol: str,
    timeframe: str,
    closes: List[float],
    *,
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    timestamp: Optional[str] = None,
    ote_low: float = OTE_LOW,
    ote_high: float = OTE_HIGH,
    seed: Optional[int] = None,
) -> OteSetup:
    """Calcule un setup ICT OTE (Kill Zone + retracement 62-79%).

    Args:
        symbol : ex "EURUSD".
        timeframe : ex "M30", "H1", "H4".
        closes : liste croissante des prix de clôture (source OHLCV).
        highs/lows : options, sinon dérivés de closes (high=low=close).
        timestamp : ISO UTC (défaut maintenant UTC).
        ote_low/ote_high : bornes OTE (défaut 0.62 / 0.79).
        seed : R9 audit.

    Returns:
        OteSetup : kill zone, bias, zone OTE, in_ote, conviction_score.

    R6 fail-open :
      - pas de données → kill_zone UNKNOWN, conviction 0.0, high_conviction False.
      - swing plat / prix hors swing → in_ote False, conviction 0.0.
      - Kill Zone OUTSIDE → pas de setup (conviction 0.0) mais on garde le
        retracement pour audit.
    """
    zone = _kill_zone_at_hour(_parse_utc(timestamp).hour)
    ts_iso = _parse_utc(timestamp).isoformat()

    setup = OteSetup(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts_iso,
        kill_zone=zone,
        audit={"seed": seed, "ote_bounds": (ote_low, ote_high)},
    )

    if not closes:
        setup.audit["reason"] = "no_data"
        return setup

    highs_ = highs if highs else list(closes)
    lows_ = lows if lows else list(closes)
    if len(highs_) != len(closes) or len(lows_) != len(closes):
        # Fallback R6 : dériver high/low de close si longueurs incohérentes.
        highs_ = list(closes)
        lows_ = list(closes)

    swing_high, swing_low, price = _swing_extremes(closes, highs_, lows_)
    setup.audit["swing_high"] = round(swing_high, 5)
    setup.audit["swing_low"] = round(swing_low, 5)

    if swing_high <= swing_low:
        setup.audit["reason"] = "flat_swing"
        return setup

    # Zone OTE absolue = zone 62-79% du swing (en prix).
    span = swing_high - swing_low
    setup.ote_low = swing_low + ote_low * span
    setup.ote_high = swing_low + ote_high * span

    ratio = _retracement_ratio(swing_high, swing_low, price)
    setup.retracement_ratio = round(ratio, 4)

    # in_ote : le prix est dans la bande [ote_low, ote_high].
    setup.in_ote = setup.ote_low <= price <= setup.ote_high

    # Bias OTE = direction du mouvement dominant du swing (pente linéaire),
    # indépendante de la position du prix dans la bande.
    setup.bias = _trend_bias(closes)

    # Score de conviction composite [0, 1] :
    #   - base 0.0
    #   - +0.60 si in_ote (le prix est dans la zone OTE 62-79%)
    #   - +0.15 si Kill Zone ∈ {LONDON, NY}
    #   - +0.25 si Kill Zone == NY (le plus volatile) [cumul LONDON+NY]
    #   Le bonus Kill Zone ne compte QUE si le prix est in_ote (sinon il n'y
    #   a pas de setup à convaincre). Plafonné à 1.0.
    score = 0.0
    if setup.in_ote:
        score += 0.60
        if zone in (KillZone.LONDON, KillZone.NY):
            score += 0.15
        if zone == KillZone.NY:
            score += 0.25
    setup.conviction_score = round(min(1.0, score), 3)
    setup.high_conviction = setup.conviction_score >= HIGH_CONVICTION_THRESHOLD

    setup.audit["ratio_in_range"] = ratio
    setup.audit["reason"] = "ok" if setup.in_ote else "not_in_ote"
    return setup


def apply_ote_to_signal(
    current_level: str,
    ote: OteSetup,
    *,
    ote_downgrade_below: float = 0.60,
) -> tuple:
    """Applique le filtre OTE au setup_level de l'orchestrateur.

    Returns
    -------
    (new_level, was_downgraded, severity)

    Règles (additif sur v10_session_filter.apply_session_to_signal) :
      - A1 : n'est conservé que si le prix est DANS la zone OTE
        (in_ote == True) ET la conviction ≥ ote_downgrade_below.
      - Sinon A1 → A2.
      - A2/A3 : conservés tels quels (le filtre OTE est un boost de
        conviction, pas un verrou de bas niveau).
      - Kill Zone OUTSIDE/UNKNOWN → A1 → A2 (pas de setup forte conviction).
    """
    if current_level != "A1":
        return current_level, False, "none"

    if ote.kill_zone in (KillZone.OUTSIDE, KillZone.UNKNOWN):
        return "A2", True, "soft"  # hors kill zone → pas de setup OTE
    if not ote.in_ote:
        return "A2", True, "soft"  # pas dans la zone OTE → A2
    if ote.conviction_score < ote_downgrade_below:
        return "A2", True, "soft"
    return current_level, False, "none"


__all__ = [
    "KillZone",
    "OteBias",
    "OteSetup",
    "KILL_ZONES_HOURS_UTC",
    "OTE_LOW",
    "OTE_HIGH",
    "HIGH_CONVICTION_THRESHOLD",
    "compute_ict_ote",
    "apply_ote_to_signal",
    "_kill_zone_at_hour",
    "_retracement_ratio",
]


# R2 additif (Mission 1 prep)
OTE_LOW = 0.62
OTE_HIGH = 0.79
HIGH_CONVICTION_THRESHOLD = 0.70
