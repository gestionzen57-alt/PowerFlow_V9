"""RiskManager — filtre pre-paper-trade (Phase 10).

Doctrine : aucune logique d'exécution d'ordre avant Phase 12 (interdit
fondateur). Ce module est un FILTRE — il décide go/no-go pour le paper
trade (simulation), pas pour un ordre réel.

Reçoit le dict produit par Arbiter.consolidate() + le shared_context
courant (issu de principle_engine._load_shared_context) et applique 6
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

RISK_MANAGER_VERSION = "1.1"  # 2026-07-17 motion CEO — ajout PRINCIPES_BLACKLIST

# Seuils bloquants (constants exposées pour les tests et la documentation).
# CONFIANCE_MIN : abaissé 80 → 70 (CEO 2026-07-10 — biais inverse détecté).
# Référence : docs/reports/H24_PAPER_OFFLINE_20260710.json
# (817 PASSED WR 85.19% vs 183 BLOCKED WR 94.54% — le filtre 80 rejetait
# les trades faciles et acceptait les over-confiants).
# 2026-07-17 17:05 — Motion CEO « go débloquer tout fait tout pour go » :
#   CONFIANCE_MIN abaissé 70 → 50 (couvrir les confiances 50-69).
#   NB_PRINCIPES_MIN abaissé 2 → 1 (un principe suffit pour entrer).
#   Logique : un CEO senior quant sait que bloquer l'apprentissage est pire
#   que de trader avec une confiance moyenne. Le sizing Kelly fractionnel
#   absorbe le risque (réduit la position quand WR<50% observé).
# 2026-07-17 17:42 — Motion CEO « continue optimiser au max » :
#   Ajout PRINCIPES_BLACKLIST : combinaisons perdantes identifiées par
#   analyse 369 paper-trades clôturés. Ex: GRAMMAR_CONTEXTE + PRICE_LAG
#   = WR 36.7% n=30 -6.57 pips/trade (boulet statistique).
PRINCIPES_BLACKLIST: frozenset = frozenset({
    frozenset({"GRAMMAR_CONTEXTE", "PRICE_LAG_AT_NODE_BIRTH"}),
})
CONFIANCE_MIN = 50
NB_PRINCIPES_MIN = 1


class RiskManagerError(ValueError):
    """Erreur d'évaluation du RiskManager (input mal formé)."""


class RiskManager:
    """Applique 6 règles bloquantes sur une synthèse Arbiter + context."""

    def __init__(
        self,
        *,
        confiance_min: int = CONFIANCE_MIN,
        nb_principes_min: int = NB_PRINCIPES_MIN,
        principes_blacklist: frozenset | None = None,
    ) -> None:
        self.confiance_min = confiance_min
        self.nb_principes_min = nb_principes_min
        self.principes_blacklist = (
            principes_blacklist if principes_blacklist is not None
            else PRINCIPES_BLACKLIST
        )

    def evaluate(self, arbiter_result: dict, context: dict | None) -> dict:
        """Évalue go/no-go + raison de blocage + confiance finale.

        Toutes les vérifications sont appliquées (court-circuit au premier
        blocage). Le retour est stable :
          {
            "go": bool,
            "raison_blocage": str | None,
            "confiance_finale": int,
            "rules_checked": list[str],
            "rules_passed": list[str],
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
        confiance_arbitree = arbiter_result.get("confiance_arbitree", 0) or 0
        try:
            confiance_arbitree = int(confiance_arbitree)
        except (TypeError, ValueError):
            confiance_arbitree = 0

        def _block(name: str, raison: str) -> dict:
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

        # Règle 4 — fenêtre non exploitable (SUPPRIMÉE 2026-07-15)
        rules_checked.append("window_exploitable")
        rules_passed.append("window_exploitable")

        # Règle 5 — principes insuffisants
        rules_checked.append("nb_principes_min")
        nb_principes = arbiter_result.get("nb_principes_actifs") or 0
        try:
            nb_principes = int(nb_principes)
        except (TypeError, ValueError):
            nb_principes = 0
        if nb_principes < self.nb_principes_min:
            return _block(
                "nb_principes_min",
                f"principes insuffisants ({nb_principes})",
            )
        rules_passed.append("nb_principes_min")

        # Règle 6 — combinaison de principes blacklistée (2026-07-17 motion CEO)
        rules_checked.append("principes_blacklist")
        principes = arbiter_result.get("principes_source") or []
        if isinstance(principes, list):
            principes_set = frozenset(p for p in principes if isinstance(p, str))
            if self.principes_blacklist and principes_set in self.principes_blacklist:
                return _block(
                    "principes_blacklist",
                    f"combinaison perdante blacklistée ({sorted(principes_set)})",
                )
        rules_passed.append("principes_blacklist")

        # Toutes les règles passées → go
        return {
            "go": True,
            "raison_blocage": None,
            "confiance_finale": confiance_arbitree,
            "rules_checked": rules_checked,
            "rules_passed": rules_passed,
            "risk_manager_version": RISK_MANAGER_VERSION,
        }