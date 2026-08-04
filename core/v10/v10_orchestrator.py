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


# ─────────────────────────────────────────────────────────────────────
# Phase 9 — Source de vérité Fatman (DB directe, pas de proxy)
# ─────────────────────────────────────────────────────────────────────
def compose_enhanced_signal_with_fatman(
    symbol: str,
    pair: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    db_path: Optional[str] = None,
    pairs_bars_for_fallback: Optional[Dict[str, List[dict]]] = None,
    confluence: Optional[object] = None,
    vsa_state: str = "NEUTRAL",
    news_events: Optional[List] = None,
    usd_trend: str = "NEUTRAL",
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> EnhancedSignal:
    """Compose un V10 Signal Enhanced avec lecture DIRECTE Fatman depuis DB.

    Doctrine V10 (Phase 9 architectural fix) :
      - Source primaire : `forces_snapshots` table `v9_forces.db`
        (vraies valeurs Fatman écrites par le collecteur V9 MT4).
      - R6 fail-open : si DB absente/stale → fallback v10_currency_strength.
      - R9 audit : log explicite source = 'v9_forces_db' / 'fallback_strength'.

    Paramètres supplémentaires :
      - db_path : chemin DB live (défaut : "data/v9_forces.db").
      - pairs_bars_for_fallback : barres par paire pour le fallback.
    """
    # 1. Lecture Fatman source de vérité (DB directe)
    currency_rank_base = 0
    currency_rank_quote = 0
    fatman_source_label = "no_fatman"
    try:
        from .v10_fatman_db_reader import get_fatman_with_fallback, freshness_check
        from .v10_fatman_db_reader import FatmanSource as _Fs
        alive = freshness_check(db_path=db_path or "data/v9_forces.db")
        if alive:
            fl = get_fatman_with_fallback(
                pair, timeframe,
                db_path=db_path or "data/v9_forces.db",
                pairs_bars=pairs_bars_for_fallback,
                seed=seed,
            )
            if fl.source == _Fs.V9_FORCES_DB:
                fatman_source_label = "v9_forces_db"
            elif fl.source == _Fs.FALLBACK_STRENGTH:
                fatman_source_label = "fallback_strength"
            currency_rank_base = fl.base_rank
            currency_rank_quote = fl.quote_rank
        else:
            # Pas alive, mais on essaie quand même avec fallback
            fl = get_fatman_with_fallback(
                pair, timeframe,
                db_path=db_path or "data/v9_forces.db",
                pairs_bars=pairs_bars_for_fallback,
                seed=seed,
            )
            fatman_source_label = f"stale_fallback_{fl.source.value}"
            currency_rank_base = fl.base_rank
            currency_rank_quote = fl.quote_rank
    except Exception as exc:
        fatman_source_label = f"exception:{type(exc).__name__}"

    # 2. Delegate au composer standard avec les rangs Fatman réels
    sig = compose_enhanced_signal(
        symbol=symbol, pair=pair, timestamp=timestamp,
        timeframe=timeframe, bars=bars, confluence=confluence,
        vsa_state=vsa_state,
        currency_rank_base=currency_rank_base,
        currency_rank_quote=currency_rank_quote,
        news_events=news_events, usd_trend=usd_trend,
        overrides=overrides, seed=seed,
    )

    # R9 audit explicite de la source Fatman utilisée
    sig.cot = dict(sig.cot) if sig.cot else {}
    sig.cot["0_fatman_source"] = f"Fatman source = {fatman_source_label} (RANK base={currency_rank_base}, quote={currency_rank_quote})"

    # Ajouter aux blockers si source dégradée
    if "fallback" in fatman_source_label:
        sig.blockers.append("FATMAN_FALLBACK")
    if "exception" in fatman_source_label:
        sig.blockers.append("FATMAN_UNAVAILABLE")
    return sig


# ─────────────────────────────────────────────────────────────────────
# Couche 3 — Intégration Market Context Global
# ─────────────────────────────────────────────────────────────────────

def compose_signal_with_context(
    symbol: str,
    pair: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    multi_tf_snapshots: Optional[Dict[str, List]] = None,
    # --- params existants de compose_enhanced_signal_with_fatman ---
    db_path: Optional[str] = None,
    pairs_bars_for_fallback: Optional[Dict[str, List[dict]]] = None,
    confluence: Optional[object] = None,
    vsa_state: str = "NEUTRAL",
    news_events: Optional[List] = None,
    usd_trend: str = "NEUTRAL",
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> "ContextFilteredSignal":
    """Compose un V10 Signal enrichi avec lecture Fatman + filtrage contextuel Couche 3.

    Doctrine V10 Couche 3 :
      - Source primaire Fatman (DB directe via v10_fatman_db_reader).
      - Contexte global (v10_market_context_global.compute_market_context).
      - Si ctx.tradeable=False → downgrade A1 → A2, A2 → A3, A3 → NONE.
      - Si paire dans tradeable_pairs + antagonisme + aligned >= 3 → A1 OK.
      - Si paire dans tradeable_pairs + aligned >= 2 → A2 OK.
      - Sinon → A3 (paire hors top antagonisme, mais contexte OK).

    R6 fail-open : si multi_tf_snapshots vide → tradeable=False, retourne
    le signal Fatman avec un blocker CTX_NO_DATA.
    """
    from .v10_market_context_global import compute_market_context, MarketContext
    # 1. Compose signal Fatman standard
    sig = compose_enhanced_signal_with_fatman(
        symbol=symbol, pair=pair, timestamp=timestamp,
        timeframe=timeframe, bars=bars,
        db_path=db_path, pairs_bars_for_fallback=pairs_bars_for_fallback,
        confluence=confluence, vsa_state=vsa_state,
        news_events=news_events, usd_trend=usd_trend,
        overrides=overrides, seed=seed,
    )

    # 2. Calcule contexte global
    if not multi_tf_snapshots:
        ctx = MarketContext(
            timestamp=timestamp,
            tradeable=False,
            block_reason="no_multi_tf_snapshots",
            audit={"reason": "empty_multi_tf_snapshots"},
        )
    else:
        ctx = compute_market_context(multi_tf_snapshots, timestamp=timestamp)

    # 3. Filtre signal selon contexte
    original_level = sig.setup_level  # "A1" / "A2" / "A3" / "NONE"
    new_level = original_level
    downgrade_reason = ""

    if not ctx.tradeable:
        # Contexte invalide → downgrade progressif
        if original_level == "A1":
            new_level = "A2"
            downgrade_reason = f"A1→A2 (ctx blocked: {ctx.block_reason})"
        elif original_level == "A2":
            new_level = "A3"
            downgrade_reason = f"A2→A3 (ctx blocked: {ctx.block_reason})"
        elif original_level == "A3":
            new_level = "NONE"
            downgrade_reason = f"A3→NONE (ctx blocked: {ctx.block_reason})"
    else:
        # Contexte tradeable — mais la paire est-elle éligible ?
        pair_in_tradeable = pair in ctx.tradeable_pairs
        aligned_count = ctx.audit.get("n_div_tradeable", 0)  # proxy
        # Règles :
        if original_level == "A1":
            if not pair_in_tradeable:
                new_level = "A2"
                downgrade_reason = f"A1→A2 (pair {pair} not in tradeable_pairs {ctx.tradeable_pairs})"
        # A2 reste A2 si pair in tradeable_pairs, sinon downgrade
        elif original_level == "A2":
            if not pair_in_tradeable:
                new_level = "A3"
                downgrade_reason = f"A2→A3 (pair {pair} not in tradeable_pairs {ctx.tradeable_pairs})"

    # 4. Bloque si NONE
    blockers = list(sig.blockers) if sig.blockers else []
    if new_level == "NONE" and "CTX_BLOCKED" not in blockers:
        blockers.append("CTX_BLOCKED")
    if not ctx.tradeable and "CTX_BLOCKED" not in blockers:
        blockers.append("CTX_BLOCKED")

    # 5. Ajoute contexte au CoT (R5)
    sig.cot = dict(sig.cot) if sig.cot else {}
    sig.cot["3_ctx_cycle"] = f"cycle={ctx.cycle}, phase={ctx.phase}, conf={ctx.cycle_confidence:.2f}"
    sig.cot["3_ctx_score"] = f"context_score={ctx.context_score:.1f}/100"
    sig.cot["3_ctx_tradeable"] = f"tradeable={ctx.tradeable}, block={ctx.block_reason or 'none'}"
    sig.cot["3_ctx_pairs"] = f"tradeable_pairs={ctx.tradeable_pairs}, top_antagonisms={ctx.top_antagonisms}"
    if downgrade_reason:
        sig.cot["3_ctx_downgrade"] = downgrade_reason

    # 6. Update signal
    sig.setup_level = new_level
    sig.blockers = blockers

    # 7. Retourne dataclass enrichie
    return ContextFilteredSignal(
        signal=sig,
        context=ctx,
        original_level=original_level,
        final_level=new_level,
        downgraded=(new_level != original_level),
        downgrade_reason=downgrade_reason,
    )


@dataclass
class ContextFilteredSignal:
    """Résultat de compose_signal_with_context — signal + contexte."""
    signal: EnhancedSignal
    context: MarketContext
    original_level: str
    final_level: str
    downgraded: bool
    downgrade_reason: str

    def as_dict(self) -> Dict:
        return {
            "signal": {
                "pair": self.signal.pair if hasattr(self.signal, 'pair') else None,
                "setup_level": self.final_level,
                "blockers": self.signal.blockers if hasattr(self.signal, 'blockers') else [],
            },
            "context": self.context.as_dict(),
            "original_level": self.original_level,
            "final_level": self.final_level,
            "downgraded": self.downgraded,
            "downgrade_reason": self.downgrade_reason,
        }


__all__ = [
    "V10Signal",
    "EnhancedSignal",
    "ContextFilteredSignal",
    "compose_signal",
    "compose_enhanced_signal",
    "compose_enhanced_signal_with_fatman",
    "compose_signal_with_context",
]
