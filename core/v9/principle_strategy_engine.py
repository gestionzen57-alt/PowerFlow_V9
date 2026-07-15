"""PrincipleStrategyEngine — Stratégie par principe V9.

Lit le strategy_profile de chaque principe ACTIVE depuis son YAML et
l'applique dans le TradeEngine. Remplace le moule unique DYNAMIC par
des profils individualisés optimisés par WR, session, regime.

Architecture :
  Signal Generator → principe X triggered
    └── PrincipleStrategyEngine.get_strategy(principle_id, session, regime)
         ├── Lit strategy_profile du YAML du principe
         ├── Vérifie allowed_sessions (skip si session interdite)
         ├── Ajuste sizing_multiplier selon regime (malus si non préféré)
         ├── Retourne tp_pips, sl_pips, exit_strategy, sizing, etc.
         └── Fallback sur DYNAMIC_PROFILES si pas de strategy_profile

Doctrine :
  - R18 : code pur, aucun LLM
  - R2 : couche additive (fallback sur DYNAMIC si pas de profil)
  - R25' : les profils sont descriptifs, ajustement automatique si delta > 1 pip
  - R6 : try/except, ne crash jamais
"""
from __future__ import annotations

import logging
from typing import Any

from core.v9.config import ROOT_DIR
from core.v9.exit_simulator import (
    DYNAMIC_DEFAULT,
    DYNAMIC_PROFILES,
    ExitStrategy,
    is_session_tradable,
)

log = logging.getLogger(__name__)

STRATEGY_ENGINE_VERSION = "1.0"

# Profils de stratégie par défaut (fallback DYNAMIC)
DEFAULT_STRATEGY: dict[str, Any] = {
    "tp_pips": 10.0,
    "sl_pips": 15.0,
    "exit_strategy": "TP_SL",
    "max_hold_bars": 12,
    "sizing_multiplier": 1.0,
    "min_confidence": 75,
    "allowed_sessions": None,  # None = toutes les sessions tradables
    "preferred_regime": None,  # None = tous les régimes
    "anti_correlation": True,
    "trailing_activation": None,
    "trailing_distance": None,
}


class PrincipleStrategyEngine:
    """Moteur de stratégie par principe.

    Lit le champ `strategy` optionnel dans les YAML des principes ACTIVE.
    Si absent, fallback sur DYNAMIC_PROFILES par session.

    Usage :
        engine = PrincipleStrategyEngine()
        strategy = engine.get_strategy("PRICE_LAG_AT_NODE_BIRTH", "asie", "CASSURE")
        # → {tp_pips: 12, sl_pips: 8, exit_strategy: "TRAILING", ...}
    """

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Charge les strategy_profiles depuis les YAML des principes."""
        import yaml
        from pathlib import Path

        principles_dir = ROOT_DIR / "core" / "v9" / "principles"
        if not principles_dir.exists():
            return

        for yaml_file in principles_dir.glob("*.yaml"):
            try:
                d = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                pid = d.get("id", "")
                strategy = d.get("strategy")
                if strategy and isinstance(strategy, dict):
                    self._profiles[pid] = strategy
            except Exception:
                pass

        log.debug("PrincipleStrategyEngine: %d profils chargés", len(self._profiles))

    def get_strategy(
        self,
        principle_id: str,
        session: str,
        regime: str | None = None,
    ) -> dict[str, Any]:
        """Retourne la stratégie pour un principe dans un contexte donné.

        Args:
            principle_id: ID du principe déclenché
            session: session de marché (asie/london/overlap/new_york/after)
            regime: regime actuel (CASSURE/EXTENSION/NEUTRE/RETOUR_EQUILIBRE...)

        Returns:
            dict avec tp_pips, sl_pips, exit_strategy, sizing_multiplier,
            min_confidence, max_hold_bars, allowed, reason
        """
        result: dict[str, Any] = {
            "principle_id": principle_id,
            "session": session,
            "regime": regime,
            "allowed": True,
            "reason": None,
            "source": "default",
        }

        # 1. Vérifier session tradable (blacklist globale)
        if not is_session_tradable(session):
            result["allowed"] = False
            result["reason"] = f"session_blacklisted ({session})"
            return result

        # 2. Charger le profil du principe
        profile = self._profiles.get(principle_id)
        if profile:
            result["source"] = "principle_profile"
            strategy = {**DEFAULT_STRATEGY, **profile}
        else:
            # Fallback DYNAMIC par session
            result["source"] = "dynamic_fallback"
            dyn = DYNAMIC_PROFILES.get(session, DYNAMIC_DEFAULT)
            strategy = {
                **DEFAULT_STRATEGY,
                "tp_pips": float(dyn["tp_pips"]),
                "sl_pips": float(dyn["sl_pips"]),
                "exit_strategy": "DYNAMIC",
            }

        # 3. Vérifier allowed_sessions du profil
        allowed_sessions = strategy.get("allowed_sessions")
        if allowed_sessions and session not in allowed_sessions:
            result["allowed"] = False
            result["reason"] = f"session_not_allowed ({session} not in {allowed_sessions})"
            return result

        # 4. Ajuster sizing selon regime
        sizing = strategy.get("sizing_multiplier", 1.0)
        preferred_regime = strategy.get("preferred_regime")
        if preferred_regime and regime:
            if regime not in preferred_regime:
                # Malus sizing si regime non préféré (pas skip — juste réduire)
                sizing *= 0.7
                result["regime_malus"] = True

        # 5. Construire le résultat
        result.update({
            "tp_pips": float(strategy.get("tp_pips", 10.0)),
            "sl_pips": float(strategy.get("sl_pips", 15.0)),
            "exit_strategy": strategy.get("exit_strategy", "TP_SL"),
            "max_hold_bars": int(strategy.get("max_hold_bars", 12)),
            "sizing_multiplier": round(sizing, 2),
            "min_confidence": int(strategy.get("min_confidence", 75)),
            "anti_correlation": bool(strategy.get("anti_correlation", True)),
            "trailing_activation": strategy.get("trailing_activation"),
            "trailing_distance": strategy.get("trailing_distance"),
        })

        return result

    def get_expectancy(
        self,
        principle_id: str,
        session: str,
        wr: float,
    ) -> float:
        """Calcule l'expectancy pour un principe dans une session.

        expectancy = WR × tp_pips - (1 - WR) × sl_pips
        """
        strategy = self.get_strategy(principle_id, session)
        if not strategy.get("allowed"):
            return 0.0
        tp = strategy.get("tp_pips", 10.0)
        sl = strategy.get("sl_pips", 15.0)
        return wr * tp - (1 - wr) * sl

    def list_profiles(self) -> dict[str, dict[str, Any]]:
        """Retourne tous les profils chargés (pour audit/debug)."""
        return dict(self._profiles)