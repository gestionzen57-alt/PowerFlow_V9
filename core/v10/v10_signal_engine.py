"""V10 Signal Engine — agrégation Fatman éditeur + score composite (ÉTAPE 3).

Agrège :
  - v10_fatman_editor.compute_fatman_editor (formule éditeur, Phase ÉTAPE 1)
  - v10_force.compute_force (F1-F5)
  - v10_structure.compute_structure (S1-S9)
  - v10_context.compute_context (C1-C7, news/range/vol/session)

Sortie : SignalEngine avec :
  - direction (BULLISH / BEARISH)
  - score composite 0-100 (pondéré)
  - leverage recommandé (S1=50, S2=30, S3=20, etc., aligné HERMES_PLAN)
  - fatman_signal (FORT/MOYEN/AUCUN, éditeur §3)
  - fatman_delta (signe + magnitude)
  - cot R5 : reasoning 5 étapes
  - audit R9 : tout sérialisable JSON

Doctrine V10 : R1-AGIR, R2 additif pur (importe seulement v10_fatman_
editor), R6 fail-open (tout manquant → score 50, signal AUCUN), R7
tests verts, R9 audit honnête, R10 0 capital.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Lazy import : pattern Phase 32/23 — importe seulement à l'appel
def _compute_fatman_editor_safe(pairs_bars, timestamp, weights):
    try:
        from .v10_fatman_editor import compute_fatman_editor
    except Exception:
        return None
    try:
        return compute_fatman_editor(pairs_bars, timestamp=timestamp,
                                       weights=weights)
    except Exception:
        return None


def _compute_force_safe(symbol, timestamp, tf, bars, overrides):
    try:
        from .v10_force import compute_force
    except Exception:
        return None
    try:
        return compute_force(symbol, timestamp, tf, bars, overrides=overrides)
    except Exception:
        return None


def _compute_structure_safe(symbol, timestamp, tf, bars, overrides):
    try:
        from .v10_structure import compute_structure
    except Exception:
        return None
    try:
        return compute_structure(symbol, timestamp, tf, bars, overrides=overrides)
    except Exception:
        return None


def _compute_context_safe(symbol, timestamp, tf, news=None, bars=None,
                          usd_trend="NEUTRAL", overrides=None):
    try:
        from .v10_context import compute_context
    except Exception:
        return None
    try:
        return compute_context(symbol, timestamp, tf,
                               news_events=news, bars=bars,
                               usd_trend=usd_trend, overrides=overrides)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# Dataclass sortie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class SignalEngine:
    """Signal V10 agrégé — couche supérieur pour orchestrateur/backtest."""
    symbol: str
    pair: str
    timestamp: str
    timeframe: str
    # Fatman éditeur
    fatman_signal: str = "AUCUN"   # FORT/MOYEN/AUCUN
    fatman_delta: float = 0.0
    fatman_score_base: float = 50.0
    fatman_score_quote: float = 50.0
    # Scores par couche
    force_score: float = 50.0
    structure_score: float = 50.0
    context_score: float = 50.0
    # Agrégation
    score_composite: float = 50.0
    direction: str = "NONE"       # BULLISH / BEARISH / NONE
    leverage: int = 0              # 0/20/30/50 selon score
    # R5 chain-of-thought
    cot: Dict[str, str] = field(default_factory=dict)
    # R9 audit
    inputs_used: Dict[str, bool] = field(default_factory=dict)
    seed: Optional[int] = None

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "pair": self.pair,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "fatman_signal": self.fatman_signal,
            "fatman_delta": round(self.fatman_delta, 3),
            "fatman_score_base": round(self.fatman_score_base, 2),
            "fatman_score_quote": round(self.fatman_score_quote, 2),
            "force_score": round(self.force_score, 2),
            "structure_score": round(self.structure_score, 2),
            "context_score": round(self.context_score, 2),
            "score_composite": round(self.score_composite, 2),
            "direction": self.direction,
            "leverage": self.leverage,
            "cot": dict(self.cot),
            "inputs_used": dict(self.inputs_used),
            "seed": self.seed,
        }


# ─────────────────────────────────────────────────────────────────────
# Pondérations (R8 surchargeables)
# ─────────────────────────────────────────────────────────────────────
DEFAULT_ENGINE_WEIGHTS: Dict[str, float] = {
    "fatman": 0.40,
    "force": 0.25,
    "structure": 0.20,
    "context": 0.15,
}


def _normalize_weights(w: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Normalise les poids pour sommer à 1.0 (R8 tolérant)."""
    base = dict(DEFAULT_ENGINE_WEIGHTS)
    if w:
        base.update(w)
    total = sum(base.values())
    if total <= 0:
        return DEFAULT_ENGINE_WEIGHTS
    return {k: v / total for k, v in base.items()}


def _score_to_50(score: float) -> float:
    """Convertit un score 0-100 brut en indice 0-100 normalisé pour agrégation.

    R6 : scores manquants → 50 neutre. Plafonné [0, 100].
    """
    if score is None:
        return 50.0
    return max(0.0, min(100.0, float(score)))


# ─────────────────────────────────────────────────────────────────────
# Calcule direction (BULLISH/BEARISH) depuis fatman delta
# ─────────────────────────────────────────────────────────────────────
def _direction_from_delta(delta: float, fatman_signal: str) -> str:
    if fatman_signal == "AUCUN":
        return "NONE"
    return "BULLISH" if delta > 0 else "BEARISH" if delta < 0 else "NONE"


# ─────────────────────────────────────────────────────────────────────
# Mapping score → leverage (plan §MATRICE SIGNAUX)
# ─────────────────────────────────────────────────────────────────────
def _leverage_from_score(score: float, direction: str, fatman_signal: str) -> int:
    """Leverage selon le score composite et le signal Fatman éditeur.

    Plan :
      score ≥ 75 + Fatman FORT → 50 (S1 Momentum fort)
      score ≥ 60 + Fatman FORT/MOYEN → 30 (S2 Continuation)
      score ≥ 50 + structure BREAK/REJECT → 20 (S3 Reversal M30)
      score < 50 → 0 (abstention obligatoire)
    """
    if direction == "NONE" or fatman_signal == "AUCUN":
        return 0
    if score >= 75 and fatman_signal == "FORT":
        return 50
    if score >= 60 and fatman_signal in ("FORT", "MOYEN"):
        return 30
    if score >= 50:
        return 20
    return 0


# ─────────────────────────────────────────────────────────────────────
# Engine principal
# ─────────────────────────────────────────────────────────────────────
def compute_signal_engine(
    symbol: str,
    pair: str,
    timestamp: str,
    timeframe: str,
    *,
    pairs_bars: Optional[Dict[str, Dict[str, List[float]]]] = None,
    bars: Optional[List[dict]] = None,
    news_events: Optional[List] = None,
    usd_trend: str = "NEUTRAL",
    weights: Optional[Dict[str, float]] = None,
    fatman_weights: Optional[Dict[str, float]] = None,
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> SignalEngine:
    """Agrège Fatman éditeur + force + structure + context.

    Args:
        symbol, pair, timestamp, timeframe : identification.
        pairs_bars : { pair : { tf : [closes] } } pour Fatman éditeur.
        bars : [{open, high, low, close}] pour force/structure (mono-TF).
        news_events, usd_trend, overrides, seed : kwargs standard V10.

    R6 fail-open : tous les sous-modules manquants → score 50,
    Fatman AUCUN, direction NONE. Aucun crash.
    """
    pair = pair or symbol
    w = _normalize_weights(weights)
    sig = SignalEngine(
        symbol=symbol, pair=pair, timestamp=timestamp,
        timeframe=timeframe, seed=seed,
    )

    # 1. Fatman éditeur (4 poids TF + momentum 20)
    fatman_result = None
    if pairs_bars:
        fatman_result = _compute_fatman_editor_safe(
            pairs_bars, timestamp=timestamp, weights=fatman_weights,
        )
    if fatman_result and pair in fatman_result.deltas:
        d = fatman_result.deltas[pair]
        sig.fatman_delta = d
        sig.fatman_signal = fatman_result.signals.get(pair, "AUCUN")
        sig.fatman_score_base = fatman_result.scores.get(
            pair[:3], 50.0
        )
        sig.fatman_score_quote = fatman_result.scores.get(
            pair[3:], 50.0
        )
        sig.inputs_used["fatman"] = True
    sig.cot["1_fatman"] = (
        f"delta={sig.fatman_delta:.3f}, "
        f"signal={sig.fatman_signal}, "
        f"score_base={sig.fatman_score_base:.1f}, "
        f"score_quote={sig.fatman_score_quote:.1f}"
    )

    # 2. Force
    if bars:
        force_res = _compute_force_safe(symbol, timestamp, timeframe,
                                         bars, overrides)
        if force_res is not None:
            try:
                sig.force_score = _score_to_50(
                    getattr(force_res, "force_score", 50.0)
                    or 50.0
                )
                sig.inputs_used["force"] = True
            except Exception:
                pass
    sig.cot["2_force"] = f"score={sig.force_score:.1f}"

    # 3. Structure
    if bars:
        struct_res = _compute_structure_safe(symbol, timestamp, timeframe,
                                             bars, overrides)
        if struct_res is not None:
            try:
                sig.structure_score = _score_to_50(
                    getattr(struct_res, "structure_score", 50.0)
                    or 50.0
                )
                sig.inputs_used["structure"] = True
            except Exception:
                pass
    sig.cot["3_structure"] = f"score={sig.structure_score:.1f}"

    # 4. Context
    ctx_res = None
    if bars:
        ctx_res = _compute_context_safe(symbol, timestamp, timeframe,
                                        news=news_events, bars=bars,
                                        usd_trend=usd_trend,
                                        overrides=overrides)
    if ctx_res is not None:
        try:
            sig.context_score = _score_to_50(
                getattr(ctx_res, "context_score", 50.0) or 50.0
            )
            sig.inputs_used["context"] = True
        except Exception:
            pass
    sig.cot["4_context"] = f"score={sig.context_score:.1f}, tradeable={getattr(ctx_res, 'tradeable', True)}"

    # 5. Agrégation pondérée
    sig.score_composite = (
        w["fatman"] * (
            50.0 + 50.0 * sig.fatman_delta  # convert delta → 0-100
        ) if fatman_result else 50.0
        if False else  # défensif : fallback si weights différents
        # Calcul simple et stable (sans remonter aux weights)
        max(0.0, min(100.0,
            50.0 + 50.0 * sig.fatman_delta  # [-1,+1] → [0,100]
        )) if fatman_result else 50.0
    )
    # Pondération réelle multi-couche
    composite = (
        w["fatman"] * (50.0 + 50.0 * sig.fatman_delta if fatman_result else 50.0)
        + w["force"] * sig.force_score
        + w["structure"] * sig.structure_score
        + w["context"] * sig.context_score
    )
    sig.score_composite = round(max(0.0, min(100.0, composite)), 2)

    # 6. Direction (depuis fatman delta + signal)
    sig.direction = _direction_from_delta(sig.fatman_delta, sig.fatman_signal)

    # 7. Leverage
    sig.leverage = _leverage_from_score(
        sig.score_composite, sig.direction, sig.fatman_signal
    )

    sig.cot["5_score_composite"] = (
        f"composite={sig.score_composite:.1f}/100, "
        f"direction={sig.direction}, leverage={sig.leverage}"
    )

    return sig


# ─────────────────────────────────────────────────────────────────────
# Backtest sommaire (R9 : pour R10 pas d'exécution réelle,
# juste une simulation sur barres historiques)
# ─────────────────────────────────────────────────────────────────────
def backtest_simple(
    pair: str,
    pairs_bars: Dict[str, Dict[str, List[float]]],
    *,
    timestamps: Optional[List[str]] = None,
    n_bars: int = 100,
    pivot_step: int = 5,
) -> Dict:
    """Backtest sommaire : boucler sur les N derniers timestamps,
    émettre un signal Fatman à chaque pivot, comptabiliser les
    'gains' (delta > 0 et prix monte dans les 5 barres suivantes).

    Returns dict : { n_signals, n_aligned_with_price, WR_pct }.
    R10 : aucune exécution réelle, juste une simulation.
    """
    if not pairs_bars or pair not in pairs_bars:
        return {"n_signals": 0, "n_aligned_with_price": 0, "WR_pct": 0.0}
    closes = pairs_bars[pair].get("H1") or pairs_bars[pair].get("M30") or []
    closes = list(closes)
    if len(closes) < n_bars + 5:
        return {"n_signals": 0, "n_aligned_with_price": 0, "WR_pct": 0.0}
    tail = closes[-n_bars - 5:]
    n_signals = 0
    n_aligned = 0
    i = 0
    while i < n_bars:
        # Snapshot limité à i+1 barres
        snap_bars = {p: {tf: vals[: i + 30] for tf, vals in tfs.items()}
                      for p, tfs in pairs_bars.items()
                      if any(len(vals) > i for vals in tfs.values())}
        if not snap_bars:
            i += pivot_step
            continue
        r = _compute_fatman_editor_safe(
            snap_bars, timestamp=f"step_{i}", weights=None,
        )
        if r and pair in r.deltas:
            d = r.deltas[pair]
            if r.signals[pair] in ("FORT", "MOYEN"):
                n_signals += 1
                # Vérité : prix monte sur les 5 prochaines barres ?
                if i + 5 < len(tail):
                    next_close = tail[i + 5]
                    cur_close = tail[i]
                    moved = (next_close - cur_close) / cur_close
                    if (d > 0 and moved > 0) or (d < 0 and moved < 0):
                        n_aligned += 1
        i += pivot_step
    wr = round(100.0 * n_aligned / n_signals, 1) if n_signals else 0.0
    return {"n_signals": n_signals, "n_aligned_with_price": n_aligned,
            "WR_pct": wr, "target_pct": 60.0, "wr_meets_target": wr >= 60.0}


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────
__all__ = [
    "SignalEngine",
    "DEFAULT_ENGINE_WEIGHTS",
    "compute_signal_engine",
    "backtest_simple",
]
