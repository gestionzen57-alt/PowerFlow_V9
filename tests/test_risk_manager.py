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
    """Cas 3 — confiance < 60 → bloqué avec valeur numérique dans raison.

    Note : CONFIANCE_MIN 80 → 70 → 50 → 60 (audit senior quant 2026-07-17).
    """
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(confiance=59), _ok_context())
    assert res["go"] is False
    assert res["raison_blocage"] == "confiance insuffisante (59)"
    assert res["confiance_finale"] == 0


def test_bloque_confiance_frontiere_50() -> None:
    """Confiance exactement à 60 → passe (frontière inclusive, audit senior quant 2026-07-17)."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(confiance=60), _ok_context())
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
    """Cas 6 — nb_principes_actifs < 2 → bloqué avec valeur dans raison.

    Note : NB_PRINCIPES_MIN restauré à 2 (audit senior quant 2026-07-17).
    """
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(nb_principes=1), _ok_context())
    assert res["go"] is False
    assert res["raison_blocage"] == "principes insuffisants (1)"
    assert res["confiance_finale"] == 0


def test_principes_frontiere_1_ok() -> None:
    """nb_principes exactement à 2 → passe (frontière inclusive, audit senior quant 2026-07-17)."""
    rm = RiskManager()
    res = rm.evaluate(_ok_arbiter(nb_principes=2), _ok_context())
    assert res["go"] is True


def test_raison_blocage_explicite() -> None:
    """Cas 7 — chaque blocage produit une raison unique et non-ambiguë.

    Règle 4 (window) supprimée 2026-07-15 — ne fait plus partie des blocages.
    Note 2026-07-17 audit senior quant : CONFIANCE_MIN=60, NB_PRINCIPES_MIN=2.
    """
    rm = RiskManager()
    raisons = {
        "direction": rm.evaluate(_ok_arbiter(direction="neutre"), _ok_context())["raison_blocage"],
        "confiance": rm.evaluate(_ok_arbiter(confiance=40), _ok_context())["raison_blocage"],
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
    Note 2026-07-17 audit senior quant : CONFIANCE_MIN=60 → confiance=50 déclenche, 60 non.
    """
    rm = RiskManager()
    cas = [
        (_ok_arbiter(direction="neutre"), _ok_context()),
        (_ok_arbiter(confiance=50), _ok_context()),  # <60 maintenant
        (_ok_arbiter(), _ok_context(news_phase="NEWS_SHOCK")),
        (_ok_arbiter(nb_principes=1), _ok_context()),  # <2 maintenant
    ]
    for arb, ctx in cas:
        res = rm.evaluate(arb, ctx)
        assert res["confiance_finale"] == 0, \
            f"confiance_finale devrait être 0, got {res['confiance_finale']} pour {res['raison_blocage']}"


def test_confiance_finale_preservee_si_go() -> None:
    """Si go=True, confiance_finale == confiance_arbitree.
    Note 2026-07-17 audit senior quant : CONFIANCE_MIN=60, on teste valeurs >= 60.
    """
    rm = RiskManager()
    for c in (60, 70, 85, 100):
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

    Note : CONFIANCE_MIN = 60, NB_PRINCIPES_MIN = 2 (audit senior quant 2026-07-17).
    """
    assert CONFIANCE_MIN == 60
    assert NB_PRINCIPES_MIN == 2

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


# ---------- Tests evaluate_batch / should_skip_batch / cache ----------
# Motion CEO 2026-07-17 « optimiser au max » — RISK_MANAGER_VERSION 2.0


def test_should_skip_batch_direction_neutre() -> None:
    """should_skip_batch() détecte direction=None/'neutre' sans toucher au core."""
    arb_neutre_none = _ok_arbiter()
    arb_neutre_none["direction"] = None
    assert RiskManager.should_skip_batch(arb_neutre_none) is True

    arb_neutre_str = _ok_arbiter(direction="neutre")
    assert RiskManager.should_skip_batch(arb_neutre_str) is True

    arb_ok = _ok_arbiter(direction="haussiere")
    assert RiskManager.should_skip_batch(arb_ok) is False


def test_should_skip_batch_input_invalide() -> None:
    """R6 défensif : input non-dict → skip (renverra verdict de blocage)."""
    assert RiskManager.should_skip_batch(None) is True
    assert RiskManager.should_skip_batch("not a dict") is True
    assert RiskManager.should_skip_batch([1, 2]) is True


def test_evaluate_batch_alignement_1_1() -> None:
    """evaluate_batch retourne N verdicts alignés 1:1 sur les inputs."""
    rm = RiskManager()
    arbs = [
        _ok_arbiter(confiance=85),                # go
        _ok_arbiter(direction="neutre"),          # bloc direction
        _ok_arbiter(confiance=30),                # bloc confiance
        _ok_arbiter(nb_principes=2),              # go
        _ok_arbiter(confiance=70),                # go
    ]
    verdicts = rm.evaluate_batch(arbs, _ok_context())
    assert len(verdicts) == len(arbs)
    assert verdicts[0]["go"] is True
    assert verdicts[1]["go"] is False
    assert verdicts[1]["raison_blocage"] == "direction neutre"
    assert verdicts[2]["go"] is False
    assert "confiance insuffisante" in verdicts[2]["raison_blocage"]
    assert verdicts[3]["go"] is True
    assert verdicts[4]["go"] is True


def test_evaluate_batch_dedup_segment() -> None:
    """100 arbiter identiques (dict différents) → 1 verdict canonique réutilisé."""
    rm = RiskManager()
    payload = _ok_arbiter(confiance=75, nb_principes=2)
    arbs = [dict(payload) for _ in range(100)]
    verdicts = rm.evaluate_batch(arbs, _ok_context())
    assert len(verdicts) == 100
    sample = verdicts[0]
    for v in verdicts:
        assert v["go"] == sample["go"]
        assert v["confiance_finale"] == sample["confiance_finale"]
        assert v["raison_blocage"] == sample["raison_blocage"]
        assert v["rules_passed"] == sample["rules_passed"]
    assert sample["go"] is True
    assert sample["confiance_finale"] == 75


def test_evaluate_batch_news_shock_bloque_tout() -> None:
    """news_phase='NEWS_SHOCK' bloque tout le batch (1 lookup pré-calculé)."""
    rm = RiskManager()
    arbs = [_ok_arbiter(confiance=90) for _ in range(5)]
    arbs.append(_ok_arbiter(direction="neutre"))  # skip d'office
    ctx = _ok_context(news_phase="NEWS_SHOCK")
    verdicts = rm.evaluate_batch(arbs, ctx)
    assert len(verdicts) == 6
    for v in verdicts[:5]:
        assert v["go"] is False
        assert v["raison_blocage"] == "news shock en cours"
    assert verdicts[5]["raison_blocage"] == "direction neutre"
    assert verdicts[5]["rules_checked"] == ["direction_neutre"]


def test_evaluate_batch_vide_et_inputs_invalides() -> None:
    """R6 : evaluate_batch([]) → [] ; entrée non-dict ne lève pas d'exception."""
    rm = RiskManager()
    assert rm.evaluate_batch([], _ok_context()) == []
    arbs = [
        _ok_arbiter(confiance=70),
        None,                # type: ignore[list-item]
        _ok_arbiter(confiance=70),
        "string au milieu",  # type: ignore[list-item]
        _ok_arbiter(direction="neutre"),
    ]
    verdicts = rm.evaluate_batch(arbs, _ok_context())
    assert len(verdicts) == 5
    assert verdicts[0]["go"] is True
    assert verdicts[1]["go"] is False
    assert "invalide" in verdicts[1]["raison_blocage"]
    assert verdicts[2]["go"] is True
    assert verdicts[3]["go"] is False
    assert verdicts[4]["raison_blocage"] == "direction neutre"


def test_evaluate_batch_idempotent_et_identique_a_evaluate() -> None:
    """evaluate_batch doit produire des verdicts identiques à evaluate() pour les mêmes arbiter."""
    rm = RiskManager()
    cases = [
        _ok_arbiter(confiance=85),
        _ok_arbiter(confiance=49),                  # bloc confiance
        _ok_arbiter(direction="neutre"),            # bloc direction
        _ok_arbiter(nb_principes=2, confiance=72),  # go
        _ok_arbiter(nb_principes=0),                # bloc principes
    ]
    flat = cases * 5
    batch_verdicts = rm.evaluate_batch(flat, _ok_context())
    assert len(batch_verdicts) == 25
    for i, arb in enumerate(cases):
        ref = rm.evaluate(arb, _ok_context())
        v = batch_verdicts[i]
        assert v["go"] == ref["go"]
        assert v["raison_blocage"] == ref["raison_blocage"]
        assert v["confiance_finale"] == ref["confiance_finale"]
        assert v["rules_checked"] == ref["rules_checked"]
        for pass_idx in range(1, 5):
            v2 = batch_verdicts[i + pass_idx * len(cases)]
            assert v["go"] == v2["go"]
            assert v["raison_blocage"] == v2["raison_blocage"]


def test_cache_confiance_principes_hit() -> None:
    """Le cache class-level stocke bien int() et frozenset() entre deux evaluate()."""
    RiskManager._transform_cache.clear()
    rm = RiskManager()
    arb = _ok_arbiter(confiance=77, nb_principes=2)
    r1 = rm.evaluate(arb, _ok_context())
    # Key = (id(arb), confiance_brute)
    assert (id(arb), 77) in RiskManager._transform_cache
    r2 = rm.evaluate(arb, _ok_context())
    assert r1 == r2
    assert r1["go"] is True
    assert r1["confiance_finale"] == 77


def test_cache_disable_fallback_correct() -> None:
    """enable_cache=False bypass le cache sans altérer les résultats."""
    rm_no_cache = RiskManager(enable_cache=False)
    arb = _ok_arbiter(confiance=65, nb_principes=2)
    r = rm_no_cache.evaluate(arb, _ok_context())
    assert r["go"] is True
    assert r["confiance_finale"] == 65