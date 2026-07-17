"""Tests unitaires — RiskManager (core/v9/risk_manager.py, Phase 10).

Couvre 7 cas exigés par le brief :
  1. test_go_true_toutes_conditions_ok
  2. test_bloque_direction_neutre
  3. test_bloque_confiance_insuffisante
  4. test_bloque_news_shock
  5. test_bloque_fenetre_non_exploitable
  6. test_bloque_principes_insuffisants
  7. test_raison_blocage_explicite

+ tests annexes : ordre d'évaluation, confiance finale, version,
  seuils custom, context None.
"""
from __future__ import annotations

import pytest

from core.v9.risk_manager import (
    CONFIANCE_MIN,
    NB_PRINCIPES_MIN,
    RISK_MANAGER_VERSION,
    RiskManager,
    RiskManagerError,
)


# ---------- Helpers ----------


def _ok_arbiter(direction: str = "haussiere", confiance: int = 85,
                nb_principes: int = 3) -> dict:
    return {
        "direction": direction,
        "confiance_arbitree": confiance,
        "principes_source": [f"P{i}" for i in range(nb_principes)],
        "nb_principes_actifs": nb_principes,
        "timestamp": "2026-07-07T10:00:00+00:00",
        "arbiter_version": "1.0",
        "snapshot_id": "snap_test",
    }


def _ok_context(news_phase: str = "NEUTRE", window_status: str = "exploitable") -> dict:
    return {
        "news_phase": news_phase,
        "window_status": window_status,
    }


# ---------- Tests ----------


def test_go_true_toutes_conditions_ok() -> None:
    """Cas 1 — toutes les règles passent → go=True, confiance_finale préservée.

    Note 2026-07-17 motion CEO : 6 règles désormais (ajout PRINCIPES_BLACKLIST).
    """
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(confiance=85, nb_principes=3),
                      _ok_context())
    assert res["go"] is True
    assert res["raison_blocage"] is None
    assert res["confiance_finale"] == 85
    assert res["risk_manager_version"] == RISK_MANAGER_VERSION
    assert len(res["rules_passed"]) == 6
    assert len(res["rules_checked"]) == 6


def test_bloque_direction_neutre() -> None:
    """Cas 2 — direction='neutre' → go=False, raison explicite."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(direction="neutre"), _ok_context())
    assert res["go"] is False
    assert res["raison_blocage"] == "direction neutre"
    assert res["confiance_finale"] == 0
    assert "direction_neutre" in res["rules_checked"]
    assert "direction_neutre" not in res["rules_passed"]


def test_bloque_direction_none() -> None:
    """direction=None (cas Arbiter vide) → bloqué."""
    rm = RiskManager()
    arb = _ok_arbiter()
    arb["direction"] = None
    res = rm.evaluate(arb, _ok_context())
    assert res["go"] is False
    assert res["raison_blocage"] == "direction neutre"


def test_bloque_confiance_insuffisante() -> None:
    """Cas 3 — confiance < 50 → bloqué avec valeur numérique dans raison.

    Note : CONFIANCE_MIN abaissé 80 → 70 → 50 (CEO 2026-07-17, motion « go débloquer tout »).
    """
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(confiance=49), _ok_context())
    assert res["go"] is False
    assert res["raison_blocage"] == "confiance insuffisante (49)"
    assert res["confiance_finale"] == 0


def test_bloque_confiance_frontiere_50() -> None:
    """Confiance exactement à 50 → passe (frontière inclusive, motion CEO 2026-07-17)."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(confiance=50), _ok_context())
    assert res["go"] is True


def test_bloque_news_shock() -> None:
    """Cas 4 — news_phase='NEWS_SHOCK' → bloqué."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(),
                      _ok_context(news_phase="NEWS_SHOCK"))
    assert res["go"] is False
    assert res["raison_blocage"] == "news shock en cours"
    assert res["confiance_finale"] == 0


def test_news_phase_pre_news_ok() -> None:
    """news_phase='PRE_NEWS' ou 'POST_NEWS' ne bloque PAS (seul SHOCK)."""
    rm = RiskManager()
    for phase in ("PRE_NEWS", "POST_NEWS", "NEUTRE"):
        res = rm.evaluate(_ok_arbiter(), _ok_context(news_phase=phase))
        assert res["go"] is True, f"phase {phase} ne doit pas bloquer"


def test_bloque_fenetre_non_exploitable() -> None:
    """Règle 4 supprimée 2026-07-15 — window_status n'est plus bloquant.
    Le window_gate était trop restrictif (bloquait des signaux valides).
    La direction + confiance + principes suffisent à filtrer."""
    rm = RiskManager()
    for status in ("absente", "watchlist", "non_exploitable", None, ""):
        res = rm.evaluate(_ok_arbiter(), _ok_context(window_status=status))
        assert res["go"] is True, f"status {status!r} ne doit plus bloquer (règle 4 supprimée)"


def test_bloque_principes_insuffisants() -> None:
    """Cas 6 — nb_principes_actifs < 1 → bloqué avec valeur dans raison.

    Note : NB_PRINCIPES_MIN abaissé 2 → 1 (CEO 2026-07-17, motion « go débloquer tout »).
    """
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(nb_principes=0), _ok_context())
    assert res["go"] is False
    assert res["raison_blocage"] == "principes insuffisants (0)"
    assert res["confiance_finale"] == 0


def test_principes_frontiere_1_ok() -> None:
    """nb_principes exactement à 1 → passe (frontière inclusive, motion CEO 2026-07-17)."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(nb_principes=1), _ok_context())
    assert res["go"] is True


def test_raison_blocage_explicite() -> None:
    """Cas 7 — chaque blocage produit une raison unique et non-ambiguë.

    Règle 4 (window) supprimée 2026-07-15 — ne fait plus partie des blocages.
    Note 2026-07-17 motion CEO : CONFIANCE_MIN=50, NB_PRINCIPES_MIN=1.
    """
    rm = RiskManager()
    raisons = {
        "direction": rm.evaluate(_ok_arbiter(direction="neutre"), _ok_context())["raison_blocage"],
        "confiance": rm.evaluate(_ok_arbiter(confiance=30), _ok_context())["raison_blocage"],
        "news": rm.evaluate(_ok_arbiter(), _ok_context(news_phase="NEWS_SHOCK"))["raison_blocage"],
    }
    # Toutes non vides
    assert all(r for r in raisons.values()), f"raison vide : {raisons}"
    # Toutes distinctes
    assert len(set(raisons.values())) == len(raisons), \
        f"raisons non uniques : {raisons}"


def test_ordre_evaluation_direction_d_abord() -> None:
    """Si direction=neutre ET confiance=0, on bloque sur direction
    (première règle), pas sur confiance."""
    rm = RiskManager()
    arb = _ok_arbiter(direction="neutre", confiance=0, nb_principes=0)
    res = rm.evaluate(arb, _ok_context(news_phase="NEWS_SHOCK",
                                       window_status="absente"))
    assert res["rules_checked"] == ["direction_neutre"]
    assert res["raison_blocage"] == "direction neutre"


def test_context_none_autorise_si_window_absente() -> None:
    """Règle 4 supprimée 2026-07-15 — context=None n'est plus bloquant.
    La direction + confiance + principes suffisent à filtrer."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(), None)
    assert res["go"] is True, "context=None ne doit plus bloquer (règle 4 supprimée)"

def test_confiance_finale_zero_si_bloque() -> None:
    """confiance_finale=0 dans tous les cas de blocage.
    Règle 4 (window) supprimée 2026-07-15 — retirée des cas de blocage.
    Note 2026-07-17 : CONFIANCE_MIN=50 → confiance=40 déclenche, 60 non.
    """
    rm = RiskManager()
    cas = [
        (_ok_arbiter(direction="neutre"), _ok_context()),
        (_ok_arbiter(confiance=40), _ok_context()),  # <50 maintenant
        (_ok_arbiter(), _ok_context(news_phase="NEWS_SHOCK")),
        (_ok_arbiter(nb_principes=0), _ok_context()),
    ]
    for arb, ctx in cas:
        res = rm.evaluate(arb, ctx)
        assert res["confiance_finale"] == 0, \
            f"confiance_finale devrait être 0, got {res['confiance_finale']} pour {res['raison_blocage']}"


def test_confiance_finale_preservee_si_go() -> None:
    """Si go=True, confiance_finale == confiance_arbitree.
    Note 2026-07-17 : CONFIANCE_MIN=50, on teste valeurs >= 50.
    """
    rm = RiskManager()
    for c in (50, 60, 85, 100):
        res = rm.evaluate(_ok_arbiter(confiance=c), _ok_context())
        assert res["confiance_finale"] == c


def test_arbiter_result_invalide_leve() -> None:
    """arbiter_result non-dict → RiskManagerError."""
    rm = RiskManager()
    with pytest.raises(RiskManagerError):
        rm.evaluate("not a dict", _ok_context())
    with pytest.raises(RiskManagerError):
        rm.evaluate(None, _ok_context())


def test_seuils_custom() -> None:
    """Seuils confiance_min et nb_principes_min paramétrables."""
    rm = RiskManager(confiance_min=90, nb_principes_min=5)
    # confiance=85 < 90 → bloqué
    res = rm.evaluate(_ok_arbiter(confiance=85, nb_principes=10), _ok_context())
    assert res["go"] is False
    assert "confiance insuffisante (85)" in res["raison_blocage"]

    # confiance=95 OK, nb_principes=3 < 5 → bloqué
    res2 = rm.evaluate(_ok_arbiter(confiance=95, nb_principes=3), _ok_context())
    assert res2["go"] is False
    assert "principes insuffisants (3)" in res2["raison_blocage"]

    # confiance=95, nb_principes=5 → go
    res3 = rm.evaluate(_ok_arbiter(confiance=95, nb_principes=5), _ok_context())
    assert res3["go"] is True


def test_constants_exposees() -> None:
    """Les seuils par défaut sont documentés comme constantes exportées.

    Note : CONFIANCE_MIN = 50 depuis CEO 2026-07-17 (motion « go débloquer tout »).
    Note : NB_PRINCIPES_MIN = 1 depuis CEO 2026-07-17 (idem).
    """
    assert CONFIANCE_MIN == 50
    assert NB_PRINCIPES_MIN == 1

# ---------- Tests PRINCIPES_BLACKLIST (2026-07-17 motion CEO) ----------


def test_principes_blacklist_bloque() -> None:
    """Combinaison GRAMMAR_CONTEXTE + PRICE_LAG blacklistée (WR 36.7% n=30)."""
    rm = RiskManager()
    arb = _ok_arbiter(nb_principes=2)
    arb["principes_source"] = ["GRAMMAR_CONTEXTE", "PRICE_LAG_AT_NODE_BIRTH"]
    res = rm.evaluate(arb, _ok_context())
    assert res["go"] is False
    assert "blacklistée" in res["raison_blocage"]
    assert res["confiance_finale"] == 0
    assert "principes_blacklist" in res["rules_checked"]
    assert "principes_blacklist" not in res["rules_passed"]


def test_principes_blacklist_laisse_passer_autres() -> None:
    """Combinaison non blacklistée → passe la règle 6."""
    rm = RiskManager()
    arb = _ok_arbiter(nb_principes=2)
    arb["principes_source"] = ["PRICE_LAG_AT_NODE_BIRTH"]  # seul → OK
    res = rm.evaluate(arb, _ok_context())
    assert res["go"] is True
    assert "principes_blacklist" in res["rules_passed"]
