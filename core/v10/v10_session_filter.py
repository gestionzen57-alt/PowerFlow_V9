"""V10 Session Filter — qualité de session par paire × heure UTC.

Upgrade Phase 4 : remplace is_session_active booléen par score continu
[0, 1] tenant compte de la paire × session × heure UTC.

Horaires UTC :
  ASIAN   : 00:00 - 08:00
  LONDON  : 07:00 - 11:00
  OVERLAP : 12:00 - 16:00 (London + NY)
  NY      : 13:00 - 21:00
  QUIET   : 21:00 - 00:00

Paires × sessions optimales (empirique) :
  EURUSD/GBPUSD : LONDON + OVERLAP → A1 uniquement
  USDJPY/USDCHF : LONDON + NY
  AUDUSD/NZDUSD : ASIA + LONDON open
  USDCAD        : NY uniquement
  OTHER         : score par défaut

API : get_session_quality(symbol) → SessionQuality
  - session_now ∈ {ASIAN, LONDON, OVERLAP, NY, QUIET}
  - is_optimal_for_pair : bool
  - quality_score ∈ [0, 1]
  - timestamp, audit

Doctrine : R2 additif, R6 fail-open (now UTC default), R9, R10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

log = logging.getLogger(__name__)


class SessionName(str, Enum):
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    OVERLAP = "OVERLAP"
    NY = "NY"
    QUIET = "QUIET"
    UNKNOWN = "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
SESSION_HOURS_UTC = {
    SessionName.ASIAN: (0, 8),
    SessionName.LONDON: (7, 11),
    SessionName.OVERLAP: (12, 16),
    SessionName.NY: (13, 21),
    SessionName.QUIET: (21, 24),  # puis wrap à ASIAN
}


# Pair × sessions optimales + quality_score par session
PAIR_SESSION_MATRIX = {
    "EURUSD": {
        SessionName.OVERLAP: 1.00,
        SessionName.LONDON: 0.85,
        SessionName.NY: 0.75,
        SessionName.ASIAN: 0.30,
        SessionName.QUIET: 0.10,
    },
    "GBPUSD": {
        SessionName.OVERLAP: 1.00,
        SessionName.LONDON: 0.90,  # GBPUSD fort sur London
        SessionName.NY: 0.65,
        SessionName.ASIAN: 0.25,
        SessionName.QUIET: 0.10,
    },
    "USDJPY": {
        SessionName.LONDON: 0.85,
        SessionName.NY: 0.85,
        SessionName.OVERLAP: 0.95,
        SessionName.ASIAN: 0.70,
        SessionName.QUIET: 0.15,
    },
    "USDCHF": {
        SessionName.LONDON: 0.80,
        SessionName.NY: 0.80,
        SessionName.OVERLAP: 0.90,
        SessionName.ASIAN: 0.50,
        SessionName.QUIET: 0.15,
    },
    "AUDUSD": {
        SessionName.ASIAN: 0.85,
        SessionName.LONDON: 0.75,
        SessionName.OVERLAP: 0.80,
        SessionName.NY: 0.50,
        SessionName.QUIET: 0.20,
    },
    "NZDUSD": {
        SessionName.ASIAN: 0.90,
        SessionName.LONDON: 0.70,
        SessionName.OVERLAP: 0.75,
        SessionName.NY: 0.45,
        SessionName.QUIET: 0.20,
    },
    "USDCAD": {
        SessionName.NY: 1.00,
        SessionName.OVERLAP: 0.90,
        SessionName.LONDON: 0.55,
        SessionName.ASIAN: 0.25,
        SessionName.QUIET: 0.10,
    },
    "EURGBP": {
        SessionName.LONDON: 1.00,
        SessionName.OVERLAP: 0.85,
        SessionName.NY: 0.50,
        SessionName.ASIAN: 0.30,
        SessionName.QUIET: 0.10,
    },
    "OTHER": {
        SessionName.LONDON: 0.50,
        SessionName.NY: 0.50,
        SessionName.OVERLAP: 0.60,
        SessionName.ASIAN: 0.40,
        SessionName.QUIET: 0.20,
    },
}


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────
@dataclass
class SessionQuality:
    symbol: str = ""
    timestamp: str = ""
    session_now: SessionName = SessionName.UNKNOWN
    is_optimal_for_pair: bool = False
    quality_score: float = 0.0
    a1_eligible: bool = False   # True si quality >= 0.80 et is_optimal_for_pair
    best_session: SessionName = SessionName.UNKNOWN
    best_score: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "session_now": self.session_now.value,
            "is_optimal_for_pair": self.is_optimal_for_pair,
            "quality_score": round(self.quality_score, 3),
            "a1_eligible": self.a1_eligible,
            "best_session": self.best_session.value,
            "best_score": round(self.best_score, 3),
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _session_at_hour(hour_utc: int) -> SessionName:
    """Renvoie la session pour une heure UTC donnée.

    ASIAN    : 00:00 - 06:59 (avant London open)
    LONDON   : 07:00 - 11:59 (morning pure)
    OVERLAP  : 12:00 - 15:59 (London afternoon + NY morning)
    NY       : 16:00 - 20:59 (NY pure après London close)
    QUIET    : 21:00 - 23:59
    """
    if 0 <= hour_utc < 7:
        return SessionName.ASIAN
    if 7 <= hour_utc < 12:
        return SessionName.LONDON
    if 12 <= hour_utc < 16:
        return SessionName.OVERLAP
    if 16 <= hour_utc < 21:
        return SessionName.NY
    if 21 <= hour_utc < 24:
        return SessionName.QUIET
    return SessionName.UNKNOWN


def _matrix_for(symbol: str) -> Dict[SessionName, float]:
    sym = symbol.upper().strip()
    return PAIR_SESSION_MATRIX.get(sym, PAIR_SESSION_MATRIX["OTHER"])


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def get_session_quality(
    symbol: str,
    *,
    timestamp: Optional[str] = None,
    seed: Optional[int] = None,
) -> SessionQuality:
    """Évalue la qualité de session pour la paire à l'heure UTC courante.

    Parameters
    ----------
    symbol : ex "EURUSD".
    timestamp : ISO 8601 UTC (défaut : maintenant UTC).
    seed : R9.

    Returns
    -------
    SessionQuality avec score [0, 1] + is_optimal_for_pair + a1_eligible.
    """
    if timestamp:
        ts = timestamp
        try:
            s = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        except (ValueError, OSError):
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
        ts = dt.isoformat()

    q = SessionQuality(symbol=symbol.upper(), timestamp=ts, audit={"seed": seed})
    session_now = _session_at_hour(dt.hour)
    q.session_now = session_now
    matrix = _matrix_for(symbol)
    score = matrix.get(session_now, 0.5)
    q.quality_score = score

    # Best session/score for this pair
    best_s = max(matrix.items(), key=lambda kv: kv[1])
    q.best_session = best_s[0]
    q.best_score = best_s[1]

    # is_optimal_for_pair : True si session_now fournit score >= 0.85
    q.is_optimal_for_pair = score >= 0.85
    # a1_eligible : True si l'orchestrateur a encore le droit d'envoyer un A1
    q.a1_eligible = score >= 0.80

    q.audit["matrix_used"] = dict(matrix)
    q.audit["hour_utc"] = dt.hour
    return q


# ─────────────────────────────────────────────────────────────────────
# Intégration — applique au composite_score ou garde le niveau A1
# ─────────────────────────────────────────────────────────────────────
SETUP_LEVEL_RANK_SF = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}


def apply_session_to_signal(
    current_level: str,
    session: SessionQuality,
) -> tuple:
    """Applique le filtre session au setup_level.

    Returns
    -------
    (new_level, was_downgraded, severity)

    Règles :
      - Si current_level == A1 et quality_score < 0.80 → downgrade A2
      - Si current_level == A1 et is_optimal_for_pair == False → downgrade A2
      - Si current_level == A1 et session est QUIET → downgrade A2
      - Sinon → conserve.
    """
    cur_rank = SETUP_LEVEL_RANK_SF.get(current_level, 0)
    if current_level != "A1":
        return current_level, False, "none"
    # Downgrade A1 → A2 si pas de session optimale
    if session.quality_score < 0.80:
        return "A2", True, "soft"
    if not session.is_optimal_for_pair:
        return "A2", True, "soft"
    if session.session_now == SessionName.QUIET:
        return "A2", True, "soft"
    return current_level, False, "none"


__all__ = [
    "SessionName",
    "SessionQuality",
    "SESSION_HOURS_UTC",
    "PAIR_SESSION_MATRIX",
    "get_session_quality",
    "apply_session_to_signal",
    "_session_at_hour",
    "_matrix_for",
]
