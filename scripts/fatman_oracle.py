"""V10 Phase 6 — Fatman Hawkeye Oracle déterministe (Søn-simulé).

ATTENTION — R9 AUDIT
====================
Ce module est un ORACLE ALGORITHMIQUE qui SIMULE la lecture visuelle Hawkeye
de Søn sur 20 setups. Il n'utilise PAS le feedback réel du CEO Søn — c'est
une heuristique déterministe calibrée sur la doctrine publiée de Søn
(Fatman Hawkeye = confluence EMA(8)/EMA(34) + spread ATR-normalisé
+ structure BOS + session).

Toute validation est marquée "simulated" dans les audits.

DOCTRINE :
  - R6 fail-open (oracle=NULL → ensemble rejeté)
  - R9 auditable (seed + raison du verdict par setup)
  - R10 zéro capital (jamais d'ordre)

Oracle output pour un setup OHLCV :
  - verdict : "VALID" / "INVALID" / "AMBIGUOUS"
  - score   : 0-100 (somme pondérée des signaux Hawkeye)
  - reason  : explication R5 (chain-of-thought)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# Configuration Fatman Hawkeye (calibrée d'après la lecture TA publiée)
# ─────────────────────────────────────────────────────────────────────
FATMAN_HAWKEYE_RULES = {
    "ema_cross_weight": 0.30,         # EMA(8) vs EMA(34) alignement direction
    "ema_spread_weight": 0.15,        # spread EMA / ATR
    "bos_weight": 0.20,               # Break of Structure confirmé
    "session_weight": 0.15,           # LONDON/NY/OVERLAP (actives)
    "volume_weight": 0.10,            # tick_volume > SMA(vol)
    "spread_atr_weight": 0.10,        # close proche d'un S/R structurel
    "validation_threshold": 65.0,     # score >= 65 → VALID
    "rejection_threshold": 35.0,      # score <= 35 → INVALID ; sinon AMBIGUOUS
}

ACTIVE_FATMAN_SESSIONS = ("LONDON", "NY", "OVERLAP")


@dataclass
class FatmanSetup:
    """Un setup Hawkeye présenté à l'oracle (1 bougie × structure)."""
    setup_id: str
    symbol: str
    timestamp: str
    timeframe: str

    # OHLCV de la bougie courante
    open: float
    high: float
    low: float
    close: float
    tick_volume: float

    # Direction attendue : "LONG" / "SHORT"
    expected_direction: str
    direction_set_by_v10: Optional[str] = None  # ce que V10 a jugé

    # Contexte
    session: str = "UNKNOWN"
    bos: str = "NONE"             # BOS_BULL / BOS_BEAR / NONE
    vsa_state: str = "NEUTRAL"    # VSA Phase 2

    # Historique pour EMA/spread
    prior_closes: List[float] = field(default_factory=list)
    prior_volumes: List[float] = field(default_factory=list)
    atr_value: float = 0.0        # ATR(14) courant

    # V10 résultat (phase 4)
    v10_setup_level: str = "NONE"
    v10_confluence_score: float = 0.0


@dataclass
class FatmanVerdict:
    """Verdict oracle pour un setup."""
    setup_id: str
    verdict: str                  # "VALID"/"INVALID"/"AMBIGUOUS"
    score: float                  # 0-100
    agreement: bool               # True si oracle verdict == V10 verdict
    reason: str                   # R5 chain-of-thought détaillé
    breakdown: Dict[str, float] = field(default_factory=dict)
    simulated: bool = True        # R9 marquage explicite

    def as_dict(self) -> Dict:
        return {
            "setup_id": self.setup_id,
            "verdict": self.verdict,
            "score": round(self.score, 2),
            "agreement": self.agreement,
            "reason": self.reason,
            "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()},
            "simulated": self.simulated,
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers Hawkeye (pure functions)
# ─────────────────────────────────────────────────────────────────────
def _ema(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return 0.0
    if len(values) < period:
        period = len(values)
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _sma(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return 0.0
    sample = values[-period:]
    return sum(sample) / len(sample) if sample else 0.0


def _score_ema_cross(setup: FatmanSetup) -> Tuple[float, str]:
    """EMA(8) vs EMA(34) sur l'historique des closes."""
    closes = list(setup.prior_closes) + [setup.close]
    if len(closes) < 35:
        return 0.0, "ema_cross: historique insuffisant"
    e_short = _ema(closes, 8)
    e_long = _ema(closes, 34)
    if setup.expected_direction == "LONG":
        if e_short > e_long:
            return 1.0, f"ema_cross OK (e8={e_short:.5f} > e34={e_long:.5f}) for LONG"
        return 0.0, f"ema_cross KO (e8={e_short:.5f} < e34={e_long:.5f}) — pas de confirmation LONG"
    if setup.expected_direction == "SHORT":
        if e_short < e_long:
            return 1.0, f"ema_cross OK (e8={e_short:.5f} < e34={e_long:.5f}) for SHORT"
        return 0.0, f"ema_cross KO (e8={e_short:.5f} > e34={e_long:.5f}) — pas de confirmation SHORT"
    return 0.5, "ema_cross: direction EXPECTED inconnue"


def _score_ema_spread(setup: FatmanSetup) -> Tuple[float, str]:
    """|EMA(8) - EMA(34)| / ATR — spread normalisé."""
    if setup.atr_value <= 0:
        return 0.0, "ema_spread: ATR=0"
    closes = list(setup.prior_closes) + [setup.close]
    if len(closes) < 35:
        return 0.0, "ema_spread: historique insuffisant"
    e_short = _ema(closes, 8)
    e_long = _ema(closes, 34)
    spread = abs(e_short - e_long) / setup.atr_value
    # Score : spread > 0.05 ATR → bullish, > 0.10 → strong
    if spread > 0.10:
        return 1.0, f"ema_spread fort ({spread:.3f} × ATR)"
    if spread > 0.05:
        return 0.7, f"ema_spread moyen ({spread:.3f} × ATR)"
    if spread > 0.02:
        return 0.4, f"ema_spread faible ({spread:.3f} × ATR)"
    return 0.0, f"ema_spread KO ({spread:.3f} × ATR — range)"


def _score_bos(setup: FatmanSetup) -> Tuple[float, str]:
    """BOS aligné avec la direction attendue."""
    bos = setup.bos.upper()
    if setup.expected_direction == "LONG":
        if bos == "BOS_BULL":
            return 1.0, "bos: BOS_BULL aligné LONG"
        if bos == "BOS_BEAR":
            return 0.0, "bos: BOS_BEAR contre LONG"
        return 0.4, "bos: pas de break confirmé"
    if setup.expected_direction == "SHORT":
        if bos == "BOS_BEAR":
            return 1.0, "bos: BOS_BEAR aligné SHORT"
        if bos == "BOS_BULL":
            return 0.0, "bos: BOS_BULL contre SHORT"
        return 0.4, "bos: pas de break confirmé"
    return 0.4, "bos: pas de direction attendue"


def _score_session(setup: FatmanSetup) -> Tuple[float, str]:
    s = setup.session.upper()
    if s in ACTIVE_FATMAN_SESSIONS:
        return 1.0, f"session: {s} (active)"
    if s == "OVERLAP":
        return 1.0, "session: OVERLAP (pic liquidité)"
    if s == "ASIAN":
        return 0.3, "session: ASIAN (liquidité réduite)"
    if s in ("QUIET", "QUIET_HOURS"):
        return 0.0, f"session: {s} (à éviter)"
    return 0.5, f"session: {s} (inconnue)"


def _score_volume(setup: FatmanSetup) -> Tuple[float, str]:
    """Volume de la bougie vs SMA(N)."""
    if setup.tick_volume <= 0 or not setup.prior_volumes:
        return 0.4, "volume: sec / inconnu"
    avg_vol = _sma(setup.prior_volumes, len(setup.prior_volumes))
    if avg_vol <= 0:
        return 0.4, "volume: avg=0"
    rel = setup.tick_volume / avg_vol
    if rel > 2.0:
        return 1.0, f"volume: climax ({rel:.2f}×)"
    if rel > 1.2:
        return 0.7, f"volume: élevé ({rel:.2f}×)"
    if rel > 0.5:
        return 0.4, f"volume: normal ({rel:.2f}×)"
    return 0.1, f"volume: sec ({rel:.2f}×)"


def _score_spread_atr(setup: FatmanSetup) -> Tuple[float, str]:
    """close relative à la range ATR — setup qui n'est pas au bout."""
    if setup.atr_value <= 0:
        return 0.5, "spread_atr: ATR=0"
    rng = setup.high - setup.low
    rel = rng / setup.atr_value if setup.atr_value > 0 else 0.0
    if 0.5 <= rel <= 1.5:
        return 0.8, f"spread_atr: range typique ({rel:.2f}× ATR)"
    if rel > 2.0:
        return 0.4, f"spread_atr: range large ({rel:.2f}× ATR) — possible exhaustion"
    return 0.6, f"spread_atr: range étroit ({rel:.2f}× ATR)"


# ─────────────────────────────────────────────────────────────────────
# Oracle principal
# ─────────────────────────────────────────────────────────────────────
def oracle_fatman(setup: FatmanSetup) -> FatmanVerdict:
    """Évalue un setup selon les critères Hawkeye Fatman.

    Returns
    -------
    FatmanVerdict avec verdict, score 0-100, agreement bool (V10 vs Hawkeye),
    et reason R5 chain-of-thought.
    """
    if setup.expected_direction not in ("LONG", "SHORT"):
        return FatmanVerdict(
            setup_id=setup.setup_id,
            verdict="AMBIGUOUS",
            score=50.0,
            agreement=False,
            reason="Direction EXPECTED absente (LONG/SHORT requis)",
            simulated=True,
        )

    # Calcul des 6 scores (chacun ∈ [0, 1])
    components = {
        "ema_cross": _score_ema_cross(setup),
        "ema_spread": _score_ema_spread(setup),
        "bos": _score_bos(setup),
        "session": _score_session(setup),
        "volume": _score_volume(setup),
        "spread_atr": _score_spread_atr(setup),
    }
    breakdown = {k: v[0] for k, v in components.items()}

    # Score pondéré Hawkeye 0-100
    w = FATMAN_HAWKEYE_RULES
    score_f = (
        w["ema_cross_weight"] * breakdown["ema_cross"] +
        w["ema_spread_weight"] * breakdown["ema_spread"] +
        w["bos_weight"] * breakdown["bos"] +
        w["session_weight"] * breakdown["session"] +
        w["volume_weight"] * breakdown["volume"] +
        w["spread_atr_weight"] * breakdown["spread_atr"]
    )
    score = round(score_f * 100, 2)

    # Verdict
    if score >= w["validation_threshold"]:
        verdict = "VALID"
    elif score <= w["rejection_threshold"]:
        verdict = "INVALID"
    else:
        verdict = "AMBIGUOUS"

    # Comparison V10
    v10_verdict = (
        "VALID" if setup.v10_setup_level == "A1"
        else "AMBIGUOUS" if setup.v10_setup_level in ("A2", "A3")
        else "INVALID"
    )
    agreement = (verdict == v10_verdict)

    # R5 reason
    lines = [
        f"Setup {setup.setup_id} : {setup.symbol} {setup.timeframe} {setup.timestamp}",
        f"Direction attendue : {setup.expected_direction}",
        f"V10 a jugé : {setup.v10_setup_level} (confluence={setup.v10_confluence_score:.2f})",
        f"Hawkeye score : {score:.2f}/100 → verdict={verdict}",
        f"Composants : " + ", ".join(f"{k}={v[0]:.2f}" for k, v in components.items()),
        f"Détail : " + " | ".join(f"{k}: {v[1]}" for k, v in components.items()),
        f"Accord V10↔Hawkeye : {agreement}",
    ]
    return FatmanVerdict(
        setup_id=setup.setup_id,
        verdict=verdict,
        score=score,
        agreement=agreement,
        reason="\n".join(lines),
        breakdown={k: round(v, 4) for k, v in breakdown.items()},
        simulated=True,
    )


__all__ = [
    "FatmanSetup",
    "FatmanVerdict",
    "oracle_fatman",
    "FATMAN_HAWKEYE_RULES",
    "ACTIVE_FATMAN_SESSIONS",
]
