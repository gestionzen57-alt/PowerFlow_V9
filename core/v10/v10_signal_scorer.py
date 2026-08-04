"""V10 Signal Scorer Enhanced — Phase 4 Edge Fund.

Injecte VSA (Phase 2) + Confluence (Phase 3) + BOS structure + range
devise + session dans le scoring de l'orchestrateur V10 pour atteindre
les critères A1/A2/A3 plus stricts du brief.

Critères A1 (brief Phase 4 — high conviction) :
  - confluence_score >= 0.85  ET
  - devise alignée rang 1-2 (forte) ou 6-7 (faible) selon direction  ET
  - VSA directionnel (MARKUP/ACCUMULATION long ; MARKDOWN/DISTRIBUTION short)  ET
  - BOS confirmé (BOS_BULL/BOS_BEAR) OU structure EXTENSION forte  ET
  - session active (LONDON/NY, pas ASIAN/QUIET)

Critères A2 (medium conviction) : confluence >= 0.72 ET 4/5 critères A1.
Critères A3 (low conviction) : confluence >= 0.50 ET 3/5 critères A1.

Doctrine §7 PHASE 4 plan Edge Fund :
  R1-AGIR, R2 additif pur, R5 chain-of-thought, R9 audit, R10 zero capital.

Ce module NE REMPLACE PAS compose_signal() — il l'ENRICHIT.
Si confluence/vsa sont absents (degraded mode), on retombe sur l'ancien scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .v10_confluence import (
    ConflSummary,
    ConfBias,
    SCORE_A1_THRESHOLD,
    SCORE_A2_THRESHOLD,
    SCORE_A3_THRESHOLD,
)
from .v10_vsa import VSAState


# ─────────────────────────────────────────────────────────────────────
# Configuration : pondérations des 5 critères A1
# ─────────────────────────────────────────────────────────────────────
DEFAULT_CRITERIA_WEIGHTS = {
    "confluence": 0.30,
    "currency_rank": 0.20,
    "vsa_directional": 0.20,
    "bos_structure": 0.15,
    "session_active": 0.15,
}

# Sessions considérées comme "actives" (force + liquidité)
ACTIVE_SESSIONS = ("LONDON", "NY", "OVERLAP")
QUIET_SESSIONS = ("ASIAN", "QUIET", "QUIET_HOURS")


@dataclass
class EnhancedSignal:
    """V10 Signal enrichi — Phase 4."""

    symbol: str
    timestamp: str
    timeframe: str
    pair: str                        # ex "EURUSD" (logical pair)
    direction: str                   # BULLISH / BEARISH
    setup_level: str = "NONE"        # A1 / A2 / A3 / NONE

    # Scores
    composite_score: float = 0.0     # agrégé pondéré (0-1)
    confluence_score: float = 0.0
    criteria_met: Dict[str, bool] = field(default_factory=dict)

    # Contexte
    confluence_summary: Optional[Dict] = None
    vsa_state: str = "NEUTRAL"
    bos: str = "NONE"
    session: str = "UNKNOWN"
    currency_rank_base: int = 0
    currency_rank_quote: int = 0

    # Trade
    tradeable: bool = False
    blockers: List[str] = field(default_factory=list)

    # R5 chain-of-thought explicite (5 étapes)
    cot: Dict[str, str] = field(default_factory=dict)

    # R9 audit
    seed: Optional[int] = None
    degraded_mode: bool = False  # True si confluence/VSA absents

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "pair": self.pair,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "setup_level": self.setup_level,
            "composite_score": round(self.composite_score, 4),
            "confluence_score": round(self.confluence_score, 4),
            "criteria_met": dict(self.criteria_met),
            "confluence_summary": self.confluence_summary,
            "vsa_state": self.vsa_state,
            "bos": self.bos,
            "session": self.session,
            "currency_rank_base": self.currency_rank_base,
            "currency_rank_quote": self.currency_rank_quote,
            "tradeable": self.tradeable,
            "blockers": list(self.blockers),
            "cot": dict(self.cot),
            "audit": {
                "seed": self.seed,
                "degraded_mode": self.degraded_mode,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _criterion_confluence(conf_score: float) -> bool:
    return conf_score >= SCORE_A1_THRESHOLD


def _criterion_currency_rank(
    direction_sign: int,
    rank_base: int,
    rank_quote: int,
) -> bool:
    """True si devise base est top-2 (BUY) ou bot-2 (SELL), OU devis quote alignée inverse."""
    if rank_base == 0 or rank_quote == 0:
        return False
    if direction_sign > 0:
        return rank_base <= 2 and rank_quote >= 6
    if direction_sign < 0:
        return rank_base >= 6 and rank_quote <= 2
    return False


def _criterion_vsa(vsa_state: str, direction_sign: int) -> bool:
    """VSA directionnel aligné avec le signal."""
    if direction_sign == 0:
        return False
    state = vsa_state.upper()
    if direction_sign > 0:
        return state in ("MARKUP", "ACCUMULATION")
    return state in ("MARKDOWN", "DISTRIBUTION")


def _criterion_bos(bos: str, direction_sign: int) -> bool:
    if direction_sign == 0:
        return False
    if direction_sign > 0:
        return bos.upper() in ("BOS_BULL", "EXTENSION_BULL", "REJECT_BULL")
    return bos.upper() in ("BOS_BEAR", "EXTENSION_BEAR", "REJECT_BEAR")


def _criterion_session(session: str) -> bool:
    return session.upper() in ACTIVE_SESSIONS


def _compute_direction(confl: Optional[ConflSummary]) -> int:
    """Extrait la direction signée depuis la confluence."""
    if confl is None:
        return 0
    return confl.dominant_bias.sign()


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def score_enhanced_signal(
    *,
    symbol: str,
    pair: str,
    timestamp: str,
    timeframe: str,
    confluence: Optional[ConflSummary],
    vsa_state: str = "NEUTRAL",
    bos: str = "NONE",
    session: str = "UNKNOWN",
    currency_rank_base: int = 0,
    currency_rank_quote: int = 0,
    criteria_weights: Optional[Dict[str, float]] = None,
    seed: Optional[int] = None,
) -> EnhancedSignal:
    """Calcule le V10 Signal Enhanced.

    Tous les inputs sont optionnels. Si `confluence` est None → degraded mode
    : on ne peut pas atteindre A1 (car critère confluence=False) mais on peut
    signaler A2/A3 si les autres critères sont forts.

    Parameters
    ----------
    symbol, pair, timestamp, timeframe : identification.
    confluence : ConflSummary Phase 3 (peut être None).
    vsa_state   : "MARKUP"/"MARKDOWN"/"ACCUMULATION"/"DISTRIBUTION"/"NEUTRAL".
    bos         : "BOS_BULL"/"BOS_BEAR"/"NONE".
    session     : "LONDON"/"NY"/"ASIAN"/"OVERLAP"/"QUIET".
    currency_rank_base : rang (1=fort .. 7=faible) de la devise base.
    currency_rank_quote : rang de la devise quote.

    Returns
    -------
    EnhancedSignal dataclass avec CoT R5 dans `cot`.
    """
    weights = criteria_weights or dict(DEFAULT_CRITERIA_WEIGHTS)
    sig = EnhancedSignal(
        symbol=symbol,
        pair=pair,
        timestamp=timestamp,
        timeframe=timeframe,
        direction="BULLISH",  # défaut, sera affiné ci-dessous
        vsa_state=vsa_state,
        bos=bos,
        session=session,
        currency_rank_base=currency_rank_base,
        currency_rank_quote=currency_rank_quote,
        seed=seed,
    )

    # --- Direction dérivée de la confluence ---
    direction_sign = _compute_direction(confluence)
    sig.direction = "BULLISH" if direction_sign > 0 else ("BEARISH" if direction_sign < 0 else "NONE")

    # --- Mode dégradé si confluence absente ---
    sig.degraded_mode = confluence is None
    sig.confluence_score = confluence.score if confluence else 0.0
    sig.confluence_summary = confluence.as_dict() if confluence else None

    # --- 5 critères A1 ---
    sig.criteria_met = {
        "confluence": not sig.degraded_mode and _criterion_confluence(sig.confluence_score),
        "currency_rank": _criterion_currency_rank(direction_sign, currency_rank_base, currency_rank_quote),
        "vsa_directional": _criterion_vsa(vsa_state, direction_sign),
        "bos_structure": _criterion_bos(bos, direction_sign),
        "session_active": _criterion_session(session),
    }

    # --- Composite score (pondéré sur les 5 critères ; chaque critère binaire) ---
    if direction_sign == 0:
        sig.composite_score = 0.0
        sig.setup_level = "NONE"
        sig.tradeable = False
        sig.blockers.append("NO_DIRECTION")
        sig.cot = _empty_cot("Aucune direction dérivée")
        return sig

    # On score chaque critère en [0,1] (criterion met -> 1.0, sinon 0.0 ou 0.3 si partial)
    # Pour A1 on exige des bins ; mais score composite est continu.
    score = 0.0
    score += weights.get("confluence", 0.0) * (
        1.0 if sig.criteria_met["confluence"] else
        (0.3 if sig.confluence_score >= SCORE_A2_THRESHOLD else 0.0)
    )
    score += weights.get("currency_rank", 0.0) * (
        1.0 if sig.criteria_met["currency_rank"] else
        (0.5 if (currency_rank_base <= 3 and direction_sign > 0) or (currency_rank_base >= 5 and direction_sign < 0) else 0.0)
    )
    score += weights.get("vsa_directional", 0.0) * (
        1.0 if sig.criteria_met["vsa_directional"] else 0.0
    )
    score += weights.get("bos_structure", 0.0) * (
        1.0 if sig.criteria_met["bos_structure"] else
        (0.5 if bos.upper() == "NONE" else 0.0)
    )
    score += weights.get("session_active", 0.0) * (
        1.0 if sig.criteria_met["session_active"] else
        (0.5 if session.upper() == "OVERLAP" else 0.2)
    )
    sig.composite_score = round(min(1.0, score), 4)

    # --- Niveau A1/A2/A3 ---
    n_met = sum(1 for v in sig.criteria_met.values() if v)
    if (
        sig.criteria_met["confluence"]
        and sig.criteria_met["currency_rank"]
        and sig.criteria_met["vsa_directional"]
        and sig.criteria_met["bos_structure"]
        and sig.criteria_met["session_active"]
        and sig.confluence_score >= SCORE_A1_THRESHOLD
    ):
        sig.setup_level = "A1"
        sig.tradeable = True
    elif sig.confluence_score >= SCORE_A2_THRESHOLD and n_met >= 4:
        sig.setup_level = "A2"
        sig.tradeable = True
    elif sig.confluence_score >= SCORE_A3_THRESHOLD and n_met >= 3:
        sig.setup_level = "A3"
        sig.tradeable = True
    else:
        sig.setup_level = "NONE"
        sig.tradeable = False
        # Recenser les bloqueurs
        for k, met in sig.criteria_met.items():
            if not met:
                sig.blockers.append(k.upper())

    # --- R5 chain-of-thought explicite ---
    sig.cot = _build_cot(
        direction=sig.direction,
        direction_sign=direction_sign,
        sig=sig,
        n_met=n_met,
    )
    return sig


def _empty_cot(reason: str) -> Dict[str, str]:
    return {
        "1_see": "Aucun input exploitable",
        "2_think": reason,
        "3_decide": "Aucun signal (NONE)",
        "4_risk": "Aucun risque (signal-only)",
        "5_learn": "Activer Phase 1/2/3 (currency_strength + vsa + confluence).",
    }


def _build_cot(
    direction: str,
    direction_sign: int,
    sig: EnhancedSignal,
    n_met: int,
) -> Dict[str, str]:
    cot = {}
    cot["1_see"] = (
        f"Confluence={sig.confluence_score:.3f} "
        f"VSA={sig.vsa_state} BOS={sig.bos} "
        f"Session={sig.session} "
        f"Rank(base)={sig.currency_rank_base}/7 Rank(quote)={sig.currency_rank_quote}/7"
    )
    cot["2_think"] = (
        f"Direction dérivée={direction} (sign={direction_sign:+d}). "
        f"{n_met}/5 critères A1 validés. "
        + ", ".join(f"{k}={'OK' if v else 'KO'}" for k, v in sig.criteria_met.items())
    )
    if sig.setup_level == "A1":
        cot["3_decide"] = (
            f"Signal A1 (high conviction) — composite={sig.composite_score:.3f}. "
            "Contexte de microstructure favorable."
        )
        cot["4_risk"] = (
            "Risque micro-lot (max 2 % capital, lev ≤ 5×, DD max 10 % — doctrine R10). "
            "TP/SL fixés par confluence S/R — non exécuté tant que track record Søn < 30 trades."
        )
    elif sig.setup_level == "A2":
        cot["3_decide"] = (
            f"Signal A2 (medium) — composite={sig.composite_score:.3f}. "
            "Contexte valide mais incomplet (1-2 critères KO)."
        )
        cot["4_risk"] = "Surveillance ; entrée conditionnelle si propagation H1/H4 dans les 30 min."
    elif sig.setup_level == "A3":
        cot["3_decide"] = (
            f"Signal A3 (low) — composite={sig.composite_score:.3f}. "
            "Faible conviction — entrée SHADOW uniquement."
        )
        cot["4_risk"] = "Risque minimal (paper trade + log only)."
    else:
        cot["3_decide"] = "Aucun signal (NONE) — bloqueurs: " + ",".join(sig.blockers)
        cot["4_risk"] = "Hors marché (R10) ; attendre rafraîchissement 5min."
    cot["5_learn"] = (
        f"Mesurer: si signal.level={sig.setup_level}, post-mortem à clôture bougie. "
        "Mettre à jour RL reward à chaque trade clôturé."
    )
    return cot


__all__ = [
    "EnhancedSignal",
    "score_enhanced_signal",
    "DEFAULT_CRITERIA_WEIGHTS",
    "ACTIVE_SESSIONS",
    "QUIET_SESSIONS",
]
