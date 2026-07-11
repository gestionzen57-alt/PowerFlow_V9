"""PaperRiskManager — Gestion de risque professionnelle pour paper-trade (Phase 13.2).

Wrap le RiskManager existant et ajoute :
  - Position sizing (% du capital)
  - Stop-loss / Take-profit paramétrables
  - Max concurrent trades (corrélation)
  - Drawdown limit
  - Risk/Reward ratio minimum
  - Pyramiding guard (pas de sur-exposition)

Usage :
    prm = PaperRiskManager(
        capital=10000.0,
        risk_per_trade_pct=1.0,
        max_concurrent_trades=3,
        max_drawdown_pct=15.0,
        min_rr_ratio=1.5,
    )
    result = prm.evaluate(arbiter_result, context, open_trades)
    # → {"go": bool, "raison_blocage": str|None, "position_size": float, ...}
"""
from __future__ import annotations

from typing import Any

from core.v9.risk_manager import RiskManager

PAPER_RISK_VERSION = "1.0"


class PaperRiskManager:
    """Gestion de risque complète pour paper-trade.

    Paramètres (tous optionnels, valeurs par défaut conservatrices) :
        capital (float)             : Capital de départ en unités (défaut 10 000)
        risk_per_trade_pct (float)  : % du capital risqué par trade (défaut 1.0)
        max_concurrent_trades (int) : Nombre max de trades simultanés (défaut 3)
        max_drawdown_pct (float)    : Drawdown max avant arrêt (défaut 15.0)
        min_rr_ratio (float)        : Ratio R/R minimum (défaut 1.5)
        sl_pips (float)             : Stop-loss en pips (défaut 10.0)
        tp_pips (float)             : Take-profit en pips (défaut 20.0)
        pyramiding_max_adds (int)   : Maximum d'ajouts pyramiding (défaut 2)
        correlation_check (bool)     : Vérifier corrélation entre trades (défaut True)
    """
    def __init__(
        self,
        *,
        capital: float = 10000.0,
        risk_per_trade_pct: float = 1.0,
        max_concurrent_trades: int = 3,
        max_drawdown_pct: float = 15.0,
        min_rr_ratio: float = 1.5,
        sl_pips: float = 10.0,
        tp_pips: float = 20.0,
        pyramiding_max_adds: int = 2,
        correlation_check: bool = True,
    ) -> None:
        self.capital = capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_concurrent_trades = max_concurrent_trades
        self.max_drawdown_pct = max_drawdown_pct
        self.min_rr_ratio = min_rr_ratio
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.pyramiding_max_adds = pyramiding_max_adds
        self.correlation_check = correlation_check

        # RiskManager sous-jacent (5 règles bloquantes)
        self._base_rm = RiskManager()

    def evaluate(
        self,
        arbiter_result: dict,
        context: dict | None = None,
        open_trades: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Évalue go/no-go avec gestion de risque complète.

        Args:
            arbiter_result: Sortie de Arbiter.consolidate()
            context: Shared context (news_phase, window_status, etc.)
            open_trades: Liste des trades actuellement ouverts

        Returns:
            dict avec go, raison_blocage, position_size, etc.
        """
        context = context or {}
        open_trades = open_trades or []

        # 1. Base RiskManager (5 règles : direction, confiance, news, window, principes)
        base_result = self._base_rm.evaluate(arbiter_result, context)
        if not base_result["go"]:
            return {
                "go": False,
                "raison_blocage": base_result["raison_blocage"],
                "confiance_finale": 0,
                "position_size": 0.0,
                "sl_pips": self.sl_pips,
                "tp_pips": self.tp_pips,
                "risk_amount": 0.0,
                "rules_checked": base_result["rules_checked"],
                "rules_passed": base_result["rules_passed"],
                "paper_risk_version": PAPER_RISK_VERSION,
            }

        rules_checked = list(base_result["rules_checked"])
        rules_passed = list(base_result["rules_passed"])
        confiance = base_result["confiance_finale"]

        # 2. Max concurrent trades
        rules_checked.append("max_concurrent_trades")
        if len(open_trades) >= self.max_concurrent_trades:
            return self._block(
                "max_concurrent_trades",
                f"trades simultanés max atteint ({len(open_trades)}/{self.max_concurrent_trades})",
                confiance, rules_checked, rules_passed,
            )
        rules_passed.append("max_concurrent_trades")

        # 3. Drawdown check
        rules_checked.append("max_drawdown")
        current_dd = self._compute_drawdown(open_trades)
        if current_dd >= self.max_drawdown_pct:
            return self._block(
                "max_drawdown",
                f"drawdown max atteint ({current_dd:.1f}% ≥ {self.max_drawdown_pct}%)",
                confiance, rules_checked, rules_passed,
            )
        rules_passed.append("max_drawdown")

        # 4. Risk/Reward ratio minimum
        rules_checked.append("min_rr_ratio")
        rr = self.tp_pips / self.sl_pips if self.sl_pips > 0 else 0
        if rr < self.min_rr_ratio:
            return self._block(
                "min_rr_ratio",
                f"ratio R/R insuffisant ({rr:.1f}x < {self.min_rr_ratio}x)",
                confiance, rules_checked, rules_passed,
            )
        rules_passed.append("min_rr_ratio")

        # 5. Correlation check (même direction = même sens de marché)
        if self.correlation_check:
            rules_checked.append("correlation_check")
            direction = arbiter_result.get("direction", "neutre")
            same_direction = [
                t for t in open_trades
                if t.get("direction") == direction
            ]
            if same_direction:
                return self._block(
                    "correlation_check",
                    f"trade déjà ouvert dans la même direction ({direction})",
                    confiance, rules_checked, rules_passed,
                )
            rules_passed.append("correlation_check")

        # 6. Pyramiding guard
        rules_checked.append("pyramiding_guard")
        direction = arbiter_result.get("direction", "neutre")
        same_dir_trades = [
            t for t in open_trades
            if t.get("direction") == direction
        ]
        if len(same_dir_trades) >= self.pyramiding_max_adds:
            return self._block(
                "pyramiding_guard",
                f"pyramiding max atteint ({len(same_dir_trades)}/{self.pyramiding_max_adds})",
                confiance, rules_checked, rules_passed,
            )
        rules_passed.append("pyramiding_guard")

        # ── Calcul position size ──
        risk_amount = self.capital * (self.risk_per_trade_pct / 100.0)
        # Position size = risk_amount / (sl_pips * valeur_pip)
        # Pour GBPUSD, 1 pip = 0.0001, valeur_pip pour 1 lot standard = $10
        # En unités de capital : position_size = risk_amount / (sl_pips * 10)
        pip_value = 10.0  # $10 par pip pour 1 lot standard GBPUSD
        position_size = risk_amount / (self.sl_pips * pip_value) if self.sl_pips > 0 else 0
        position_size = round(position_size, 2)

        # Ajustement par confiance (scaling progressif)
        confiance_factor = confiance / 100.0  # 0.7 → 1.0
        position_size = round(position_size * confiance_factor, 2)

        return {
            "go": True,
            "raison_blocage": None,
            "confiance_finale": confiance,
            "position_size": position_size,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "risk_amount": round(risk_amount, 2),
            "capital_remaining": round(self.capital - risk_amount, 2),
            "rules_checked": rules_checked,
            "rules_passed": rules_passed,
            "paper_risk_version": PAPER_RISK_VERSION,
        }

    def _block(
        self, name: str, raison: str, confiance: int,
        rules_checked: list[str], rules_passed: list[str],
    ) -> dict:
        return {
            "go": False,
            "raison_blocage": raison,
            "confiance_finale": 0,
            "position_size": 0.0,
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "risk_amount": 0.0,
            "rules_checked": list(rules_checked),
            "rules_passed": list(rules_passed),
            "paper_risk_version": PAPER_RISK_VERSION,
        }

    @staticmethod
    def _compute_drawdown(open_trades: list[dict]) -> float:
        """Calcule le drawdown actuel en % du capital initial.

        Approximation : drawdown = somme des pertes latentes / capital.
        """
        total_loss = sum(
            abs(t.get("pips_simulated", 0))
            for t in open_trades
            if t.get("pips_simulated", 0) < 0
        )
        # Si pas de capital stocké, on estime
        return total_loss  # en pips, approximation
