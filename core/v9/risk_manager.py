"""RiskManager — filtre pre-paper-trade (Phase 10).

Doctrine : aucune logique d'exécution d'ordre avant Phase 12 (interdit
fondateur). Ce module est un FILTRE — il décide go/no-go pour le paper
trade (simulation), pas pour un ordre réel.

Reçoit le dict produit par Arbiter.consolidate() + le shared_context
courant (issu de principle_engine._load_shared_context) et applique 5
règles bloquantes. Si toutes passent → go=True, le paper trade peut
être ouvert via PaperTradeLogger.

Aucune écriture DB, aucune décision d'ordre — uniquement une décision
booléenne "on paper-trade cette synthèse consolidée ou non".

Usage :
    rm = RiskManager()
    result = rm.evaluate(arbiter_result, context)
    if result["go"]:
        PaperTradeLogger().log_open(arbiter_result, context)
"""

from __future__ import annotations

RISK_MANAGER_VERSION = "1.0"

# Seuils bloquants (constants exposées pour les tests et la documentation).
CONFIANCE_MIN = 80
NB_PRINCIPES_MIN = 2


class RiskManagerError(ValueError):
    """Erreur d'évaluation du RiskManager (input mal formé)."""


class RiskManager:
    """Applique 5 règles bloquantes sur une synthèse Arbiter + context."""

    def __init__(
        self,
        *,
        confiance_min: int = CONFIANCE_MIN,
        nb_principes_min: int = NB_PRINCIPES_MIN,
    ) -> None:
        self.confiance_min = confiance_min
        self.nb_principes_min = nb_principes_min

    def evaluate(self, arbiter_result: dict, context: dict | None) -> dict:
        """Évalue go/no-go + raison de blocage + confiance finale.

        Toutes les vérifications sont appliquées (court-circuit au premier
        blocage). Le retour est stable :
          {
            "go": bool,
            "raison_blocage": str | None,
            "confiance_finale": int,   # = confiance_arbitree si go, 0 sinon
            "rules_checked": list[str], # noms des règles évaluées
            "rules_passed": list[str],  # noms des règles passées
            "risk_manager_version": str,
          }
        """
        if not isinstance(arbiter_result, dict):
            raise RiskManagerError(
                f"arbiter_result doit être un dict, reçu : {type(arbiter_result).__name__}"
            )
        context = context or {}

        rules_checked: list[str] = []
        rules_passed: list[str] = []
        confiance_arbitree = int(arbiter_result.get("confiance_arbitree", 0) or 0)

        def _block(name: str, raison: str) -> dict:
            # `name` a déjà été ajouté à rules_checked par l'appelant —
            # ne pas le doubler ici.
            return {
                "go": False,
                "raison_blocage": raison,
                "confiance_finale": 0,
                "rules_checked": list(rules_checked),
                "rules_passed": list(rules_passed),
                "risk_manager_version": RISK_MANAGER_VERSION,
            }

        # Règle 1 — direction neutre
        rules_checked.append("direction_neutre")
        direction = arbiter_result.get("direction")
        if direction in (None, "neutre"):
            return _block("direction_neutre", "direction neutre")
        rules_passed.append("direction_neutre")

        # Règle 2 — confiance insuffisante
        rules_checked.append("confiance_min")
        if confiance_arbitree < self.confiance_min:
            return _block(
                "confiance_min",
                f"confiance insuffisante ({confiance_arbitree})",
            )
        rules_passed.append("confiance_min")

        # Règle 3 — news shock en cours
        rules_checked.append("news_phase")
        if context.get("news_phase") == "NEWS_SHOCK":
            return _block("news_phase", "news shock en cours")
        rules_passed.append("news_phase")

        # Règle 4 — fenêtre non exploitable
        rules_checked.append("window_exploitable")
        if context.get("window_status") != "exploitable":
            return _block(
                "window_exploitable",
                "fenêtre non exploitable",
            )
        rules_passed.append("window_exploitable")

        # Règle 5 — principes insuffisants
        rules_checked.append("nb_principes_min")
        nb_principes = int(arbiter_result.get("nb_principes_actifs", 0) or 0)
        if nb_principes < self.nb_principes_min:
            return _block(
                "nb_principes_min",
                f"principes insuffisants ({nb_principes})",
            )
        rules_passed.append("nb_principes_min")

        # Toutes les règles passées → go
        return {
            "go": True,
            "raison_blocage": None,
            "confiance_finale": confiance_arbitree,
            "rules_checked": rules_checked,
            "rules_passed": rules_passed,
            "risk_manager_version": RISK_MANAGER_VERSION,
        }