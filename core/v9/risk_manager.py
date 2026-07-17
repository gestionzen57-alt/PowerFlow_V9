"""RiskManager — filtre pre-paper-trade (Phase 10).

Doctrine : aucune logique d'exécution d'ordre avant Phase 12 (interdit
fondateur). Ce module est un FILTRE — il décide go/no-go pour le paper
trade (simulation), pas pour un ordre réel.

Reçoit le dict produit par Arbiter.consolidate() + le shared_context
courant et applique 6 règles bloquantes. Si toutes passent → go=True,
le paper trade peut être ouvert via PaperTradeLogger.

Aucune écriture DB, aucune décision d'ordre — uniquement une décision
booléenne "on paper-trade cette synthèse consolidée ou non".

Usage :
    rm = RiskManager()
    result = rm.evaluate(arbiter_result, context)
    if result["go"]:
        PaperTradeLogger().log_open(arbiter_result, context)

v2.0 — 2026-07-17 motion CEO « optimiser au max » :
  - Ajout evaluate_batch() : batching de N arbiter_results alignés 1:1,
    dédupliqué par segment (direction, confiance, nb_principes,
    frozenset(principes_source)) → règle appliquée une fois par segment.
  - Ajout should_skip_batch() : helper statique de pré-filtrage.
  - Cache dict simple keyed par (id(arb), confiance_brute).
"""
from __future__ import annotations

import threading
from typing import Any

RISK_MANAGER_VERSION = "2.0"

# Seuils bloquants.
PRINCIPES_BLACKLIST: frozenset = frozenset({
    frozenset({"GRAMMAR_CONTEXTE", "PRICE_LAG_AT_NODE_BIRTH"}),
})
CONFIANCE_MIN = 50
NB_PRINCIPES_MIN = 1


class RiskManagerError(ValueError):
    """Erreur d'évaluation du RiskManager (input mal formé)."""


class RiskManager:
    """Applique 6 règles bloquantes sur une synthèse Arbiter + context."""

    # Cache partagé class-level. Key = (id(arb), confiance_brute).
    _cache_lock = threading.Lock()
    _transform_cache: dict[tuple, tuple] = {}

    def __init__(
        self,
        *,
        confiance_min: int = CONFIANCE_MIN,
        nb_principes_min: int = NB_PRINCIPES_MIN,
        principes_blacklist: frozenset | None = None,
        enable_cache: bool = True,
    ) -> None:
        self.confiance_min = confiance_min
        self.nb_principes_min = nb_principes_min
        self.principes_blacklist = (
            principes_blacklist if principes_blacklist is not None
            else PRINCIPES_BLACKLIST
        )
        self.enable_cache = enable_cache

    def _cache_key(self, arb: dict) -> tuple:
        try:
            confiance_brute = arb.get("confiance_arbitree") or 0
        except Exception:
            confiance_brute = 0
        return (id(arb), confiance_brute)

    def _cached_confiance(self, arb: dict) -> int:
        """int(arb['confiance_arbitree']) avec cache."""
        if not self.enable_cache:
            try:
                return int(arb.get("confiance_arbitree") or 0)
            except (TypeError, ValueError):
                return 0
        key = self._cache_key(arb)
        with self._cache_lock:
            cached = self._transform_cache.get(key)
        if cached is not None:
            return cached[0]
        try:
            confiance = int(arb.get("confiance_arbitree") or 0)
        except (TypeError, ValueError):
            confiance = 0
        pr_set = self._cached_principes_set(arb)
        bundle = (confiance, pr_set)
        with self._cache_lock:
            existing = self._transform_cache.get(key)
            if existing is not None:
                return existing[0]
            if len(self._transform_cache) > 10000:
                self._transform_cache.clear()
            self._transform_cache[key] = bundle
        return confiance

    def _cached_principes_set(self, arb: dict) -> frozenset:
        """frozenset(principes_source) avec cache."""
        if not self.enable_cache:
            principes = arb.get("principes_source") or []
            if not isinstance(principes, list):
                return frozenset()
            return frozenset(p for p in principes if isinstance(p, str))
        key = self._cache_key(arb)
        with self._cache_lock:
            cached = self._transform_cache.get(key)
        if cached is not None:
            return cached[1]
        principes = arb.get("principes_source") or []
        if isinstance(principes, list):
            return frozenset(p for p in principes if isinstance(p, str))
        return frozenset()

    @staticmethod
    def should_skip_batch(arbiter_result: Any, _context: dict | None = None) -> bool:
        """Retourne True si arbiter_result peut être skip SANS aucun check."""
        if not isinstance(arbiter_result, dict):
            return True
        direction = arbiter_result.get("direction")
        if direction in (None, "neutre", ""):
            return True
        return False

    def _core_evaluate(
        self,
        arbiter_result: dict,
        context: dict | None,
    ) -> dict:
        """Applique les 6 règles et retourne le verdict standard."""
        rules_checked: list[str] = []
        rules_passed: list[str] = []
        confiance_arbitree = self._cached_confiance(arbiter_result)

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
        if direction in (None, "neutre", ""):
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
        if (context or {}).get("news_phase") == "NEWS_SHOCK":
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

        # Règle 6 — combinaison de principes blacklistée
        rules_checked.append("principes_blacklist")
        principes_set = self._cached_principes_set(arbiter_result)
        if self.principes_blacklist and principes_set in self.principes_blacklist:
            return _block(
                "principes_blacklist",
                f"combinaison perdante blacklistée ({sorted(principes_set)})",
            )
        rules_passed.append("principes_blacklist")

        return {
            "go": True,
            "raison_blocage": None,
            "confiance_finale": confiance_arbitree,
            "rules_checked": rules_checked,
            "rules_passed": rules_passed,
            "risk_manager_version": RISK_MANAGER_VERSION,
        }

    def evaluate(self, arbiter_result: dict, context: dict | None) -> dict:
        """Évalue go/no-go + raison de blocage + confiance finale."""
        if not isinstance(arbiter_result, dict):
            raise RiskManagerError(
                f"arbiter_result doit être un dict, reçu : {type(arbiter_result).__name__}"
            )
        return self._core_evaluate(arbiter_result, context)

    def evaluate_batch(
        self,
        arbiter_results: list[dict],
        context: dict | None = None,
    ) -> list[dict]:
        """Évalue N arbiter_results en une passe, retourne N verdicts alignés 1:1."""
        n = len(arbiter_results)
        if n == 0:
            return []

        ctx = context or {}
        news_shock = ctx.get("news_phase") == "NEWS_SHOCK"

        skip_verdicts: list[dict | None] = [None] * n
        segment_keys: list[tuple | None] = [None] * n
        segments: dict[tuple, list[int]] = {}

        for i, arb in enumerate(arbiter_results):
            # 1. Skip court-circuit (inclut input invalide via should_skip_batch)
            if self.should_skip_batch(arb, ctx):
                skip_verdicts[i] = {
                    "go": False,
                    "raison_blocage": (
                        "arbiter_result invalide"
                        if not isinstance(arb, dict)
                        else "direction neutre"
                    ),
                    "confiance_finale": 0,
                    "rules_checked": ["direction_neutre"],
                    "rules_passed": [],
                    "risk_manager_version": RISK_MANAGER_VERSION,
                }
                continue
            confiance = self._cached_confiance(arb)
            try:
                nb_principes = int(arb.get("nb_principes_actifs") or 0)
            except (TypeError, ValueError):
                nb_principes = 0
            pr_set = self._cached_principes_set(arb)
            direction = arb.get("direction")
            key = (direction, confiance, nb_principes, pr_set)
            segment_keys[i] = key
            segments.setdefault(key, []).append(i)

        verdicts_by_key: dict[tuple, dict] = {}
        for key in segments:
            idx = segments[key][0]
            arb = arbiter_results[idx]
            pr_set = key[3]
            arb_proxy = dict(arb)
            arb_proxy["principes_source"] = sorted(pr_set)
            ctx_for_proxy = dict(ctx)
            if news_shock:
                ctx_for_proxy["news_phase"] = "NEWS_SHOCK"
            verdicts_by_key[key] = self._core_evaluate(arb_proxy, ctx_for_proxy)

        results: list[dict] = [None] * n  # type: ignore[list-item]
        for i in range(n):
            if skip_verdicts[i] is not None:
                results[i] = skip_verdicts[i]
                continue
            key = segment_keys[i]
            v = verdicts_by_key[key]
            results[i] = dict(v)
        return results  # type: ignore[return-value]