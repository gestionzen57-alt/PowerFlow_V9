"""V10 Orchestrateur — compose Force + Structure + Contexte → V10 Signal.

Le cœur du pivot SIGNAL-ONLY : transforme les bougies brutes en un
« setup » hiérarchisé (A1 excellent / A2 bon / A3 moyen / NONE aucun)
que le scanner comportemental alerte à Søn pour validation manuelle.

Aucun capital n'est risqué : ce module produit des signaux, pas des ordres.
L'exécution réelle (micro-lot) reste conditionnée à un edge VALIDÉ par le
track record Søn (Phase H du plan directeur).

Critère de setup (doctrine plan V10 Phase G) :
    vraie entrée = force_level >= MEDIUM
                   AND structure_type IN (BREAK, REJECT)
                   AND context_state NOT IN (NEWS, ILLIQUIDE)

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7 tests, R9 audit,
R10 capital protégé (signaux seulement, jamais d'ordre).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .v10_force import compute_force
from .v10_structure import compute_structure
from .v10_context import compute_context
from .v10_signal_scorer import (
    EnhancedSignal,
    score_enhanced_signal,
    DEFAULT_CRITERIA_WEIGHTS,
    ACTIVE_SESSIONS,
)

# Niveaux de setup (priorité croissante)
SETUP_RANK = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}

# Seuils pour A1 (excellent setup) — versionnés, recalibrés Phase I
A1_RULES = {
    "force": ("EXTREME", "HIGH"),
    "structure": ("BREAK", "REJECT"),
    "context_vol": ("NORMAL", "HIGH"),  # EXCLUDE LOW/EXTREME pour A1
}


@dataclass
class V10Signal:
    symbol: str
    timestamp: str
    timeframe: str
    direction: str            # BULLISH / BEARISH
    setup_level: str = "NONE"  # NONE / A3 / A2 / A1
    confidence: float = 0.0
    force_level: str = "LOW"
    structure_type: str = "NONE"
    context_state: str = "CLEAR"
    tradeable: bool = False
    blockers: List[str] = field(default_factory=list)
    reasoning: Dict = field(default_factory=dict)  # R5 chain-of-thought

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "setup_level": self.setup_level,
            "confidence": round(self.confidence, 3),
            "force_level": self.force_level,
            "structure_type": self.structure_type,
            "context_state": self.context_state,
            "tradeable": self.tradeable,
            "blockers": self.blockers,
            "reasoning": self.reasoning,
        }


def _direction(force_res, structure_res) -> str:
    """Direction dérivée de la pression acheteurs + structure."""
    buy_pressure = force_res.f1_buy_pressure
    bull = buy_pressure > 0.5
    if structure_res.s8_break == "BOS_BEAR":
        bull = False
    elif structure_res.s8_break == "BOS_BULL":
        bull = True
    return "BULLISH" if bull else "BEARISH"


def compose_signal(
    symbol: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    news_events: Optional[List] = None,
    usd_trend: str = "NEUTRAL",
    overrides: Optional[dict] = None,
) -> V10Signal:
    """Compose les 3 modules en un V10 Signal.

    bars : OHLCV croissantes. news_events : datetimes UTC.
    """
    force_res = compute_force(symbol, timestamp, timeframe, bars, overrides=overrides)
    struct_res = compute_structure(symbol, timestamp, timeframe, bars, overrides=overrides)
    ctx_res = compute_context(
        symbol, timestamp, timeframe,
        news_events=news_events, bars=bars, usd_trend=usd_trend, overrides=overrides,
    )

    sig = V10Signal(
        symbol=symbol, timestamp=timestamp, timeframe=timeframe,
        direction=_direction(force_res, struct_res),
        force_level=force_res.force_level,
        structure_type=struct_res.structure_type,
        context_state=ctx_res.c2_news_state if ctx_res.c2_news_state == "NO_TRADE_ZONE" else "CLEAR",
        tradeable=ctx_res.tradeable,
        blockers=list(ctx_res.blockers),
    )

    # ---- Critère d'entrée (plan V10 Phase G, élargi à continuation) ----
    # BREAK/REJECT = retournement ; EXTENSION = continuation de tendance
    # (tradeable seulement si la force est forte, sinon on ne chasse pas)
    context_blocked = ctx_res.c2_news_state == "NO_TRADE_ZONE" or ctx_res.c6_spread_regime == "ILLIQUIDE"
    structure_ok = struct_res.structure_type in ("BREAK", "REJECT", "EXTENSION")
    force_ok = force_res.force_level in ("HIGH", "EXTREME")
    # EXTENSION sans force forte = chasser un move déjà fait → non tradeable
    if struct_res.structure_type == "EXTENSION" and force_res.force_level != "EXTREME":
        structure_ok = False
    tradeable = ctx_res.tradeable and force_ok and structure_ok and not context_blocked

    sig.tradeable = tradeable
    if tradeable:
        # Scoring continu 0..1 pour hiérarchiser
        score = 0.0
        if force_res.force_level == "EXTREME":
            score += 0.4
        elif force_res.force_level == "HIGH":
            score += 0.3
        if struct_res.structure_type == "BREAK":
            score += 0.3
        elif struct_res.structure_type == "REJECT":
            score += 0.2
        elif struct_res.structure_type == "EXTENSION":
            score += 0.2  # continuation (jamais A1, mais A2/A3 possible)
        if ctx_res.c4_vol_regime in ("NORMAL", "HIGH"):
            score += 0.2
        if ctx_res.c7_usd_trend == usd_trend and usd_trend != "NEUTRAL":
            score += 0.1
        sig.confidence = round(min(1.0, score), 3)
        # Niveaux
        if (force_res.force_level in A1_RULES["force"]
                and struct_res.structure_type in A1_RULES["structure"]
                and ctx_res.c4_vol_regime in A1_RULES["context_vol"]):
            sig.setup_level = "A1"
        elif score >= 0.55:
            sig.setup_level = "A2"
        elif score >= 0.35:
            sig.setup_level = "A3"
        else:
            sig.setup_level = "NONE"
    else:
        sig.confidence = 0.0
        sig.setup_level = "NONE"
        if not force_ok:
            sig.blockers.append("FORCE")
        if not structure_ok:
            sig.blockers.append("STRUCTURE")

    # ---- R5 chain-of-thought ----
    sig.reasoning = {
        "force": force_res.force_level,
        "structure": struct_res.structure_type,
        "context_session": ctx_res.c1_session,
        "context_news": ctx_res.c2_news_state,
        "context_vol": ctx_res.c4_vol_regime,
        "context_spread": ctx_res.c6_spread_regime,
        "f1_buy_pressure": round(force_res.f1_buy_pressure, 3),
        "s8_break": struct_res.s8_break,
        "s7_market_structure": struct_res.s7_market_structure,
        "why": (f"setup={sig.setup_level} | force={force_res.force_level} "
                f"| struct={struct_res.structure_type} | dir={sig.direction}"),
    }
    return sig


# ─────────────────────────────────────────────────────────────────────
# Phase 4 — Orchestration Enhanced (VSA + Confluence + Structure + Context)
# ─────────────────────────────────────────────────────────────────────
def compose_enhanced_signal(
    symbol: str,
    pair: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    confluence: Optional[object] = None,
    vsa_state: str = "NEUTRAL",
    currency_rank_base: int = 0,
    currency_rank_quote: int = 0,
    news_events: Optional[List] = None,
    usd_trend: str = "NEUTRAL",
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> EnhancedSignal:
    """Compose un V10 Signal Enhanced (Phase 4 Edge Fund).

    Mêmes inputs que compose_signal(), plus :
      - `confluence` : ConflSummary Phase 3 (optionnel — si None, degraded mode).
      - `vsa_state`  : "MARKUP"/"MARKDOWN"/"ACCUMULATION"/"DISTRIBUTION"/"NEUTRAL".
      - `currency_rank_base`, `currency_rank_quote` : rangs de devises (1=top..7=bot).

    Returns
    -------
    EnhancedSignal avec CoT R5 dans `cot`.

    Doctrine : si force/structure/context bloquent, on les conserve dans les
    `blockers` retournés par EnhancedSignal pour traçabilité R9.
    """
    from .v10_vsa import compute_vsa  # import local pour éviter cycle

    # Exécuter les modules de base
    force_res = compute_force(symbol, timestamp, timeframe, bars, overrides=overrides)
    struct_res = compute_structure(symbol, timestamp, timeframe, bars, overrides=overrides)
    ctx_res = compute_context(
        symbol, timestamp, timeframe,
        news_events=news_events, bars=bars, usd_trend=usd_trend, overrides=overrides,
    )

    # Si VSA fourni = None, on le calcule localement
    vsa_used = vsa_state
    if vsa_state == "NEUTRAL" and bars:
        try:
            v = compute_vsa(symbol, timestamp, timeframe, bars, seed=seed)
            vsa_used = v.state.value if v else "NEUTRAL"
        except Exception:
            vsa_used = "NEUTRAL"

    # Construire le signal enhanced
    sig = score_enhanced_signal(
        symbol=symbol,
        pair=pair,
        timestamp=timestamp,
        timeframe=timeframe,
        confluence=confluence,
        vsa_state=vsa_used,
        bos=struct_res.s8_break,
        session=ctx_res.c1_session,
        currency_rank_base=currency_rank_base,
        currency_rank_quote=currency_rank_quote,
        seed=seed,
    )

    # Si le contexte (news/session) bloque, ajouter aux blockers mais ne pas
    # écraser le niveau calculé — on l'enrichit seulement.
    if ctx_res.c2_news_state == "NO_TRADE_ZONE":
        sig.blockers.append("NEWS_NO_TRADE")
    if ctx_res.c6_spread_regime == "ILLIQUIDE":
        sig.blockers.append("SPREAD_ILLIQUIDE")
    # Si ces 2 sont actifs, on force tradeable=False pour sécurité
    if "NEWS_NO_TRADE" in sig.blockers or "SPREAD_ILLIQUIDE" in sig.blockers:
        sig.tradeable = False
    return sig
