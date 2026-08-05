"""V10 Strategy Layers — façade de câblage des stratégies publiques dans le pipeline live.

⚠️ R2 additif : ce module est un WRAPPER du cœur de filtrage officiel
`v10_filter_compositor.compose_filters` (Sprint 4, Hermes). Il ne duplique
aucune logique de filtrage : il calcule les objets (session / ICT OTE / SMC /
régime HMM) depuis les barres OHLCV et délègue la chaîne de conviction à
`compose_filters`, qui applique :
  1. Session   (v10_session_filter) — downgrade A1 si session faible
  2. ICT OTE   (v10_ict_ote) — downgrade A1 si hors kill zone / zone OTE
  3. SMC       (v10_smc) — boost A3→A2 sur BOS/MSS, jamais de downgrade
  4. Régime    (v10_regime_hmm) — blocage conservateur si UNKNOWN (R6)

R6 fail-open : toute exception → signal inchangé. R10 : zéro ordre réel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .v10_filter_compositor import (
    CompositorResult,
    compose_filters,
)
from .v10_session_filter import get_session_quality
from .v10_ict_ote import compute_ict_ote
from .v10_regime_hmm import compose_regime_signal
from .v10_smc import detect_smc


@dataclass
class StrategyLayersResult:
    """Résultat du câblage des stratégies publiques (wrapper compositor).

    Attributes:
        original_level : niveau d'entrée (avant filtres).
        compositor     : résultat officiel de compose_filters (R9 trace complète).
        audit          : dict JSON-sérialisable (R9).
    """
    original_level: str = "NONE"
    compositor: Optional[CompositorResult] = None
    audit: Dict = field(default_factory=dict)

    @property
    def final_level(self) -> str:
        """Niveau final après filtres (inchangé si fail-open R6)."""
        if self.compositor is None:
            return self.original_level
        return self.compositor.final_level

    @property
    def downgraded(self) -> bool:
        """True si un filtre a baissé le niveau (délégué au compositor)."""
        return bool(self.compositor and self.compositor.downgraded)

    def as_dict(self) -> Dict:
        return {
            "compositor": self.compositor.as_dict() if self.compositor else None,
            "original_level": self.original_level,
            "final_level": self.final_level,
            "downgraded": self.downgraded,
            "audit": dict(self.audit),
        }


def apply_strategy_layers(
    current_level: str,
    *,
    bars: List[dict],
    symbol: str = "",
    timeframe: str = "",
    timestamp: str = "",
    min_bars: int = 30,
    regime_block: bool = True,
) -> StrategyLayersResult:
    """Calcule session + OTE + SMC + régime HMM sur les barres puis applique
    la chaîne de filtres publics (déléguée à compose_filters).

    Args:
        current_level : setup_level de l'orchestrateur ("NONE"/"A3"/"A2"/"A1").
        bars          : liste de dicts OHLCV croissante {open, high, low, close}.
        symbol        : ex "EURUSD" (R9 audit + session par paire).
        timeframe     : ex "M30", "H1" (R9 audit).
        timestamp     : ISO UTC (R9 audit + kill zone horaire + session).
        min_bars      : nombre minimal de barres pour activer les couches
                        (R6 : en dessous → aucune couche active).
        regime_block  : True = régime UNKNOWN force A3→NONE (R6 conservateur).

    Returns:
        StrategyLayersResult avec le résultat officiel du compositor.

    R6 fail-open : toute exception → final_level = current_level inchangé.
    """
    res = StrategyLayersResult(
        original_level=current_level,
        audit={"applied": False, "reason": "not_started"},
    )

    n_bars = len(bars)
    if n_bars < min_bars:
        res.audit = {"applied": False, "reason": f"insufficient_data:{n_bars}", "n_bars": n_bars}
        return res

    try:
        closes = [float(b["close"]) for b in bars]
        highs = [float(b.get("high", b["close"])) for b in bars]
        lows = [float(b.get("low", b["close"])) for b in bars]
    except (KeyError, TypeError, ValueError):
        res.audit = {"applied": False, "reason": "invalid_bars"}
        return res

    # ─── Calcul des objets (chacun R6 fail-open individuellement) ───
    session = None
    ote = None
    smc = None
    regime = None
    calc_errors = []

    try:
        session = get_session_quality(symbol, timestamp=timestamp)
    except Exception as exc:
        calc_errors.append(f"session:{type(exc).__name__}")

    try:
        ote = compute_ict_ote(
            symbol, timeframe, closes,
            highs=highs, lows=lows, timestamp=timestamp,
        )
    except Exception as exc:
        calc_errors.append(f"ote:{type(exc).__name__}")

    try:
        smc = detect_smc(bars, symbol=symbol, timeframe=timeframe, timestamp=timestamp)
    except Exception as exc:
        calc_errors.append(f"smc:{type(exc).__name__}")

    try:
        regime = compose_regime_signal(closes, symbol=symbol, timestamp=timestamp)
    except Exception as exc:
        calc_errors.append(f"regime:{type(exc).__name__}")

    # ─── Chaîne officielle (compose_filters) — cœur unique de filtrage ───
    try:
        comp = compose_filters(
            current_level,
            symbol=symbol, timeframe=timeframe, timestamp=timestamp,
            session=session, ote=ote, smc=smc, regime=regime,
            regime_block=regime_block,
        )
        res.compositor = comp
        res.audit = {
            "applied": True,
            "layers": ["session", "ote", "smc", "regime_hmm"],
            "calc_errors": calc_errors,
            "final_level": comp.final_level,
            "n_bars": n_bars,
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": timestamp,
        }
    except Exception as exc:  # R6 fail-open
        res.audit = {"applied": False, "reason": f"compose_filters_error:{type(exc).__name__}"}

    return res


def apply_strategy_layers_to_signal(
    signal: object,
    *,
    bars: List[dict],
    min_bars: int = 30,
    regime_block: bool = True,
) -> Tuple[object, StrategyLayersResult]:
    """Applique la chaîne de filtres publics sur un signal V10 (EnhancedSignal ou V10Signal).

    Enrichit le signal :
      - `signal.setup_level` = niveau final après filtres.
      - `signal.blockers` += "REGIME_UNKNOWN" si régime HMM inconnu (R6).
      - `signal.reasoning["strategy_layers"]` / `signal.cot["strategy_layers"]`
        = audit complet (R5 CoT + R9).

    R6 fail-open : si `signal` n'a pas de `setup_level` (type inconnu), la
    fonction retourne (signal, result) inchangés.
    """
    if not hasattr(signal, "setup_level"):
        return signal, StrategyLayersResult(audit={"applied": False, "reason": "no_setup_level"})

    res = apply_strategy_layers(
        signal.setup_level,
        bars=bars,
        symbol=getattr(signal, "symbol", ""),
        timeframe=getattr(signal, "timeframe", ""),
        timestamp=getattr(signal, "timestamp", ""),
        min_bars=min_bars,
        regime_block=regime_block,
    )

    if res.compositor is not None:
        signal.setup_level = res.compositor.final_level

    # R5 CoT + R9 audit
    if hasattr(signal, "reasoning") and isinstance(signal.reasoning, dict):
        signal.reasoning["strategy_layers"] = res.as_dict()
    if hasattr(signal, "cot") and isinstance(signal.cot, dict):
        signal.cot["strategy_layers"] = res.as_dict()
    if hasattr(signal, "audit") and isinstance(signal.audit, dict):
        signal.audit["strategy_layers"] = res.as_dict()

    return signal, res


__all__ = [
    "StrategyLayersResult",
    "apply_strategy_layers",
    "apply_strategy_layers_to_signal",
]
