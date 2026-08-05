"""V10 Strategy Layers — câblage additif des stratégies publiques dans le pipeline live.

Point d'entrée unique post-orchestrateur pour les 3 stratégies publiques
livrées par le Sprint 2/3b (autopilote quant Hermes) :
  1. ICT OTE  — Kill Zones + OTE 62-79% (v10_ict_ote.apply_ote_to_signal)
  2. Regime HMM — détection de régime + changepoints (v10_regime_hmm)
  3. SMC — BOS/MSS + Order Blocks + FVG (v10_smc)

Principe (R2 additif pur, R6 fail-open) :
  - Ne MODIFIE jamais le setup_level d'un signal hors A1/A2 (les stratégies
    publiques sont des filtres de conviction, pas des verrous de bas niveau).
  - A1 → downgrade si OTE invalide (hors kill zone / hors zone / faible conviction).
  - A2 → boost A1 SI OTE in_ote + haute conviction (confluence publique).
  - HMM/SMC → enrichissent l'audit + blockers (régime volatil / structure
    contradictoire) sans casser le signal.
  - Toute erreur → R6 fail-open (le signal passe tel quel).

Doctrine : R1-AGIR, R2 additif pur, R5 CoT (narratives), R6 fail-open,
R7 tests verts, R9 audit sérialisable, R10 zéro ordre réel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .v10_ict_ote import (
    KillZone,
    OteBias,
    OteSetup,
    compute_ict_ote,
    apply_ote_to_signal,
)
from .v10_regime_hmm import (
    Regime,
    RegimeResult,
    compose_regime_signal,
)
from .v10_smc import (
    SMCStructure,
    OrderBlockSide,
    FvgSide,
    SmcResult,
    detect_smc,
    smc_to_signal_level,
)


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class StrategyLayersResult:
    """Résultat du câblage des 3 stratégies sur un signal V10.

    Attributes:
        ote_setup      : setup ICT OTE (kill zone, in_ote, conviction).
        ote_level      : setup_level après filtre OTE (None si non applicable).
        ote_downgraded : True si le filtre OTE a baissé le niveau.
        regime         : régime HMM détecté (UNKNOWN si fail-open).
        smc            : structure SMC détectée (NONE si fail-open).
        final_level    : setup_level final après toutes les couches.
        audit          : dict JSON-sérialisable (R9).
    """
    ote_setup: Optional[OteSetup] = None
    ote_level: Optional[str] = None
    ote_downgraded: bool = False
    ote_reason: str = ""
    regime: Optional[RegimeResult] = None
    smc: Optional[SmcResult] = None
    final_level: str = ""
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "ote": self.ote_setup.as_dict() if self.ote_setup else None,
            "ote_level": self.ote_level,
            "ote_downgraded": self.ote_downgraded,
            "ote_reason": self.ote_reason,
            "regime": self.regime.as_dict() if self.regime else None,
            "smc": self.smc.as_dict() if self.smc else None,
            "final_level": self.final_level,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# CORE — appliquer les 3 couches sur un setup_level
# ─────────────────────────────────────────────────────────────────────

def apply_strategy_layers(
    current_level: str,
    *,
    bars: List[dict],
    symbol: str = "",
    timeframe: str = "",
    timestamp: str = "",
    ote_conviction_min: float = 0.60,
    ote_downgrade_below: float = 0.60,
    min_bars: int = 30,
) -> StrategyLayersResult:
    """Applique OTE + HMM + SMC sur un setup_level et retourne le niveau final.

    Args:
        current_level : setup_level de l'orchestrateur ("NONE"/"A3"/"A2"/"A1").
        bars          : liste de dicts OHLCV croissante {open, high, low, close}.
        symbol        : ex "EURUSD" (R9 audit).
        timeframe     : ex "M30", "H1" (R9 audit).
        timestamp     : ISO UTC (R9 audit + kill zone horaire).
        ote_conviction_min : conviction minimale pour booster A2 → A1 (0-1).
        ote_downgrade_below: conviction sous laquelle A1 → A2 (0-1).
        min_bars      : nombre minimal de barres pour activer les couches
                        (R6 : en dessous → aucune couche active).

    Returns:
        StrategyLayersResult avec final_level (le niveau après filtrage).

    Règles (additif) :
      - A1 : downgrade A1→A2 si OTE hors kill zone / hors zone / conviction
        faible (filtre de conviction publique).
      - A2 : boost A2→A1 si OTE in_ote ET conviction ≥ ote_conviction_min
        ET kill zone ∈ {LONDON, NY} (confluence publique forte).
      - A3/NONE : aucune modification (les stratégies publiques ne créent
        pas de signal là où l'orchestrateur n'a pas validé).
      - HMM VOLATILE / NEWS_LOCK → ajoute un blocker R10 (audit only,
        ne downgrade pas — l'orchestrateur est la source du niveau).
      - SMC : enrichit audit ; ne booste pas au-dessus de A2.
      - Toute exception → R6 fail-open : final_level = current_level.
    """
    res = StrategyLayersResult(
        ote_setup=None,
        regime=None,
        smc=None,
        final_level=current_level,
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

    final = current_level
    reasons = []

    # ─── Couche 1 — ICT OTE ───
    try:
        ote = compute_ict_ote(
            symbol, timeframe, closes,
            highs=highs, lows=lows, timestamp=timestamp,
        )
        res.ote_setup = ote
        new_level, was_downgraded, severity = apply_ote_to_signal(
            final, ote, ote_downgrade_below=ote_downgrade_below,
        )
        if new_level != final:
            reasons.append(f"ote:{severity}")
            final = new_level
        res.ote_level = new_level
        res.ote_downgraded = was_downgraded
        res.ote_reason = f"kill_zone={ote.kill_zone.value} in_ote={ote.in_ote} conviction={ote.conviction_score}"
        # Boost A2 → A1 si confluence publique forte (OTE + kill zone active)
        if (
            final == "A2"
            and ote.in_ote
            and ote.conviction_score >= ote_conviction_min
            and ote.kill_zone in (KillZone.LONDON, KillZone.NY)
        ):
            final = "A1"
            res.ote_level = "A1"
            reasons.append("ote:boost_a1")
    except Exception as exc:  # R6 fail-open
        res.audit["ote_error"] = str(exc)

    # ─── Couche 2 — Régime HMM (audit + blocker R10) ───
    try:
        regime = compose_regime_signal(
            closes, symbol=symbol, timestamp=timestamp, n_states=5,
        )
        res.regime = regime
        if regime.regime in (Regime.VOLATILE, Regime.NEWS_LOCK):
            reasons.append(f"regime:{regime.regime.value.lower()}")
    except Exception as exc:  # R6 fail-open
        res.audit["regime_error"] = str(exc)

    # ─── Couche 3 — SMC (audit + enrichissement) ───
    try:
        smc = detect_smc(bars, symbol=symbol, timeframe=timeframe, timestamp=timestamp)
        res.smc = smc
        if smc.structure in (SMCStructure.MSS_BULL, SMCStructure.MSS_BEAR):
            # shift de structure → info forte (audit only, ne downgrade pas)
            reasons.append(f"smc:{smc.structure.value.lower()}")
        elif smc.structure in (SMCStructure.BOS_BULL, SMCStructure.BOS_BEAR):
            reasons.append(f"smc:{smc.structure.value.lower()}")
    except Exception as exc:  # R6 fail-open
        res.audit["smc_error"] = str(exc)

    res.final_level = final
    res.audit = {
        "applied": True,
        "layers": ["ote", "regime_hmm", "smc"],
        "reasons": reasons,
        "n_bars": n_bars,
        "symbol": symbol,
        "timeframe": timeframe,
        "timestamp": timestamp,
    }
    return res


def apply_strategy_layers_to_signal(
    signal: object,
    *,
    bars: List[dict],
    ote_conviction_min: float = 0.60,
    ote_downgrade_below: float = 0.60,
    min_bars: int = 30,
) -> Tuple[object, StrategyLayersResult]:
    """Applique les couches stratégiques sur un signal V10 (EnhancedSignal ou V10Signal).

    Enrichit le signal :
      - `signal.setup_level` = niveau final après filtres.
      - `signal.blockers` += "REGIME_VOLATILE" / "REGIME_NEWS_LOCK" si HMM
        détecte un régime risqué (R10 : audit only, pas de downgrade forcé).
      - `signal.reasoning["strategy_layers"]` = dict audit (R5 CoT).
      - `signal.audit["strategy_layers"]` = dict audit (si champ existe).

    R6 fail-open : si `signal` n'a pas de `setup_level` (type inconnu), la
    fonction retourne (signal, result) inchangés.
    """
    if not hasattr(signal, "setup_level"):
        return signal, StrategyLayersResult(final_level=getattr(signal, "setup_level", "NONE"))

    res = apply_strategy_layers(
        signal.setup_level,
        bars=bars,
        symbol=getattr(signal, "symbol", ""),
        timeframe=getattr(signal, "timeframe", ""),
        timestamp=getattr(signal, "timestamp", ""),
        ote_conviction_min=ote_conviction_min,
        ote_downgrade_below=ote_downgrade_below,
        min_bars=min_bars,
    )

    signal.setup_level = res.final_level

    if res.regime is not None and res.regime.regime in (Regime.VOLATILE, Regime.NEWS_LOCK):
        if hasattr(signal, "blockers"):
            blocker = f"REGIME_{res.regime.regime.value}"
            if blocker not in signal.blockers:
                signal.blockers.append(blocker)

    # R5 CoT — narratif des couches dans reasoning (V10Signal) et cot (EnhancedSignal)
    if hasattr(signal, "reasoning") and isinstance(signal.reasoning, dict):
        signal.reasoning["strategy_layers"] = res.as_dict()
    if hasattr(signal, "cot") and isinstance(signal.cot, dict):
        signal.cot["strategy_layers"] = res.as_dict()

    # R9 audit — si le signal expose un champ audit
    if hasattr(signal, "audit") and isinstance(signal.audit, dict):
        signal.audit["strategy_layers"] = res.as_dict()

    return signal, res


__all__ = [
    "StrategyLayersResult",
    "apply_strategy_layers",
    "apply_strategy_layers_to_signal",
]
