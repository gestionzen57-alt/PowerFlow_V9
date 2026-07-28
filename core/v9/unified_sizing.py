"""UnifiedSizingEngine — Composition multiplicative cohérente du sizing V9.

Remplace la composition ad-hoc dans trade_engine.py par un moteur unique,
borné, tracé, avec ordre d'application défensif → agressif.

Architecture :
  base_size × portfolio_risk × dd_protector × risk_parity × kelly × meta_strategy
  
Bornes finales : [0.1, 3.0] (sécurité dure)

Doctrine : R2 additif, R6 défensif, R18 code pur, R30 boucle fermée.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Bornes de sécurité dures (jamais dépassées)
FINAL_MULT_MIN = 0.1
FINAL_MULT_MAX = 3.0

# Bornes par composant (validation défensive)
COMPONENT_BOUNDS = {
    "portfolio_risk": (0.0, 1.0),      # 0.0 = block, 0.5 = corrélation haute, 1.0 = normal
    "dd_protector": (0.0, 1.0),        # 0.0 = halt, 0.5 = reduce_50, 1.0 = normal
    "risk_parity": (0.0, 1.5),         # risk budget weight (peut dépasser 1.0 si peu de paires)
    "kelly": (0.1, 3.0),               # Kelly fractionnel borné
    "meta_strategy": (0.3, 2.0),       # ajustement selon stratégie d'exécution
}


@dataclass
class SizingComponents:
    """Composants individuels du sizing (pour traçabilité)."""
    portfolio_risk: float = 1.0
    dd_protector: float = 1.0
    risk_parity: float = 1.0
    kelly: float | None = None
    meta_strategy: float = 1.0
    
    def to_dict(self) -> dict[str, float | None]:
        return {
            "portfolio_risk": self.portfolio_risk,
            "dd_protector": self.dd_protector,
            "risk_parity": self.risk_parity,
            "kelly": self.kelly,
            "meta_strategy": self.meta_strategy,
        }


@dataclass
class SizingResult:
    """Résultat final du calcul de sizing."""
    final_multiplier: float
    base_size: float
    final_size: float
    components: SizingComponents
    rationale: list[str]
    blocked: bool = False
    block_reason: str | None = None
    warnings: list[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "final_multiplier": self.final_multiplier,
            "base_size": self.base_size,
            "final_size": self.final_size,
            "components": self.components.to_dict(),
            "rationale": self.rationale,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "warnings": self.warnings,
        }


class UnifiedSizingEngine:
    """Moteur de sizing unifié — composition multiplicative ordonnée."""
    
    def __init__(self):
        self._call_count = 0
    
    def compute(
        self,
        base_size: float,
        context: dict[str, Any],
        portfolio_risk_mult: float = 1.0,
        dd_protector_mult: float = 1.0,
        risk_parity_weight: float = 1.0,
        kelly_mult: float | None = None,
        meta_strategy_mult: float = 1.0,
    ) -> SizingResult:
        """
        Calcule le multiplicateur final de sizing.
        
        Args:
            base_size: Taille de base (ex: 1.0 lot)
            context: Contexte {principle_id, symbol, session, regime, phase, ...}
            portfolio_risk_mult: Sortie PortfolioRiskManager (0.0 block, 0.5 reduce, 1.0 ok)
            dd_protector_mult: Sortie DrawdownProtector (0.0 halt, 0.5 reduce_50, 1.0 normal)
            risk_parity_weight: Poids risk-parity pour la paire (0..1.5)
            kelly_mult: Multiplicateur Kelly bayésien (None si désactivé)
            meta_strategy_mult: Ajustement méta-stratégie (FAST_EXIT=0.7, TP_PARTIAL=0.9, TRAILING=1.1, TP_SL=1.0)
        
        Returns:
            SizingResult avec final_multiplier borné [0.1, 3.0] et rationale complète.
        """
        self._call_count += 1
        
        components = SizingComponents(
            portfolio_risk=portfolio_risk_mult,
            dd_protector=dd_protector_mult,
            risk_parity=risk_parity_weight,
            kelly=kelly_mult,
            meta_strategy=meta_strategy_mult,
        )
        
        rationale = []
        warnings = []
        
        # ──────────────────────────────────────────────────────────────────
        # 1. PORTFOLIO RISK (P0 Survival) — GATE DUR
        # ──────────────────────────────────────────────────────────────────
        pr = self._clamp_component("portfolio_risk", portfolio_risk_mult)
        if pr == 0.0:
            return SizingResult(
                final_multiplier=0.0,
                base_size=base_size,
                final_size=0.0,
                components=components,
                rationale=["portfolio_risk=0.0 → BLOCK"],
                blocked=True,
                block_reason="portfolio_risk_block",
            )
        components.portfolio_risk = pr
        rationale.append(f"portfolio_risk×{pr:.3f}")
        
        # ──────────────────────────────────────────────────────────────────
        # 2. DRAWDOWN PROTECTOR (Circuit Breaker) — GATE DUR
        # ──────────────────────────────────────────────────────────────────
        dd = self._clamp_component("dd_protector", dd_protector_mult)
        if dd == 0.0:
            return SizingResult(
                final_multiplier=0.0,
                base_size=base_size,
                final_size=0.0,
                components=components,
                rationale=rationale + ["dd_protector=0.0 → HALT"],
                blocked=True,
                block_reason="dd_protector_halt",
            )
        components.dd_protector = dd
        rationale.append(f"dd_protector×{dd:.3f}")
        
        # ──────────────────────────────────────────────────────────────────
        # 3. RISK PARITY (Risk Budget) — BUDGET PAR PAIRE
        # ──────────────────────────────────────────────────────────────────
        rp = self._clamp_component("risk_parity", risk_parity_weight)
        if rp < 0.1:
            warnings.append(f"risk_parity weight très faible: {rp:.3f} → plancher 0.1")
            rp = 0.1
        components.risk_parity = rp
        rationale.append(f"risk_parity×{rp:.3f}")
        
        # ──────────────────────────────────────────────────────────────────
        # 4. KELLY FRACTIONNEL (Edge Probabiliste) — OPTIONNEL
        # ──────────────────────────────────────────────────────────────────
        if kelly_mult is not None:
            kl = self._clamp_component("kelly", kelly_mult)
            components.kelly = kl
            rationale.append(f"kelly×{kl:.3f}")
        else:
            rationale.append("kelly=disabled (1.0)")
        
        # ──────────────────────────────────────────────────────────────────
        # 5. META STRATEGY (Profil Exécution) — AJUSTEMENT FIN
        # ──────────────────────────────────────────────────────────────────
        ms = self._clamp_component("meta_strategy", meta_strategy_mult)
        components.meta_strategy = ms
        rationale.append(f"meta_strategy×{ms:.3f}")
        
        # ──────────────────────────────────────────────────────────────────
        # COMPOSITION FINALE
        # ──────────────────────────────────────────────────────────────────
        mult = (
            components.portfolio_risk *
            components.dd_protector *
            components.risk_parity *
            (components.kelly or 1.0) *
            components.meta_strategy
        )
        
        # Bornes finales dures
        final_mult = max(FINAL_MULT_MIN, min(FINAL_MULT_MAX, mult))
        
        if final_mult != mult:
            warnings.append(f"Multiplicateur clampé: {mult:.3f} → {final_mult:.3f} (bornes [{FINAL_MULT_MIN}, {FINAL_MULT_MAX}])")
        
        final_size = base_size * final_mult
        
        rationale.append(f"FINAL_MULT={final_mult:.3f} (base={base_size} → size={final_size:.3f})")
        
        return SizingResult(
            final_multiplier=final_mult,
            base_size=base_size,
            final_size=final_size,
            components=components,
            rationale=rationale,
            warnings=warnings,
        )
    
    def _clamp_component(self, name: str, value: float) -> float:
        """Clamp un composant dans ses bornes avec warning si hors bornes."""
        lo, hi = COMPONENT_BOUNDS.get(name, (0.0, 10.0))
        if value < lo or value > hi:
            logger.warning(f"UnifiedSizing: {name}={value:.3f} hors bornes [{lo}, {hi}] → clampé")
            return max(lo, min(hi, value))
        return value
    
    def get_meta_strategy_multiplier(self, strategy: str) -> float:
        """Retourne le multiplicateur selon la stratégie d'exécution choisie."""
        multipliers = {
            "FAST_EXIT": 0.7,      # sortie rapide → taille réduite
            "TP_PARTIAL": 0.9,     # TP partiel → légèrement réduit
            "TP_SL": 1.0,          # standard → neutre
            "TRAILING": 1.1,       # trailing → laisse courir, taille légèrement supérieure
        }
        return multipliers.get(strategy.upper(), 1.0)


# ──────────────────────────────────────────────────────────────────────────────
# Fonction d'API simple pour intégration trade_engine
# ──────────────────────────────────────────────────────────────────────────────

_engine_instance: UnifiedSizingEngine | None = None


def get_unified_sizing_engine() -> UnifiedSizingEngine:
    """Singleton pour éviter réinstanciation à chaque trade."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = UnifiedSizingEngine()
    return _engine_instance


def compute_unified_sizing(
    base_size: float,
    context: dict[str, Any],
    portfolio_risk_mult: float = 1.0,
    dd_protector_mult: float = 1.0,
    risk_parity_weight: float = 1.0,
    kelly_mult: float | None = None,
    meta_strategy: str | None = None,
    meta_strategy_mult: float | None = None,
) -> SizingResult:
    """API simplifiée pour trade_engine.py."""
    engine = get_unified_sizing_engine()
    
    # Si meta_strategy fourni, calculer le multiplicateur
    if meta_strategy_mult is None and meta_strategy is not None:
        meta_strategy_mult = engine.get_meta_strategy_multiplier(meta_strategy)
    elif meta_strategy_mult is None:
        meta_strategy_mult = 1.0
    
    return engine.compute(
        base_size=base_size,
        context=context,
        portfolio_risk_mult=portfolio_risk_mult,
        dd_protector_mult=dd_protector_mult,
        risk_parity_weight=risk_parity_weight,
        kelly_mult=kelly_mult,
        meta_strategy_mult=meta_strategy_mult,
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI pour test
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Unified Sizing Engine V9")
    parser.add_argument("--base-size", type=float, default=1.0)
    parser.add_argument("--portfolio-risk", type=float, default=1.0)
    parser.add_argument("--dd-protector", type=float, default=1.0)
    parser.add_argument("--risk-parity", type=float, default=1.0)
    parser.add_argument("--kelly", type=float, default=None)
    parser.add_argument("--meta-strategy", type=str, default="TP_SL")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    meta_mult = {
        "FAST_EXIT": 0.7,
        "TP_PARTIAL": 0.9,
        "TP_SL": 1.0,
        "TRAILING": 1.1,
    }.get(args.meta_strategy.upper(), 1.0)
    
    result = compute_unified_sizing(
        base_size=args.base_size,
        context={},
        portfolio_risk_mult=args.portfolio_risk,
        dd_protector_mult=args.dd_protector,
        risk_parity_weight=args.risk_parity,
        kelly_mult=args.kelly,
        meta_strategy_mult=meta_mult,
    )
    
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Base size: {args.base_size}")
        print(f"Final multiplier: {result.final_multiplier:.3f}")
        print(f"Final size: {result.final_size:.3f}")
        print(f"Components: {result.components.to_dict()}")
        print(f"Rationale: {' → '.join(result.rationale)}")
        if result.warnings:
            print(f"Warnings: {result.warnings}")
        if result.blocked:
            print(f"BLOCKED: {result.block_reason}")
    
    return 0 if not result.blocked else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())