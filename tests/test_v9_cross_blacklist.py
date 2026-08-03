"""Tests pour v9_cross_blacklist.py (Phase 134 L17).

Couvre les cas critiques :
1. Kill switch OFF : jamais blacklister
2. Kill switch ON + croisement dans static -> blacklister
3. Kill switch ON + croisement hors static -> pass-through
4. Normalisation principe_set : ordre different doit matcher
5. Regime case-insensitive (uppercase)
6. Session case-insensitive (lowercase)
7. Principes avec espaces : strip
8. Principes vides : pass-through (R6 fail-open)
"""
import pytest

from core.v9.v9_cross_blacklist import (
    VERSION,
    STATIC_BLACKLIST_DEFAULT,
    _normalize_principe_set,
    cross_blacklist_enabled,
    evaluate_cross_blacklist,
    get_static_blacklist,
    is_cross_blacklisted,
)


def test_module_version():
    assert VERSION == "1.0"


def test_get_static_blacklist_returns_5():
    """Static blacklist = 5 croisements (motion CEO 03/08)."""
    bl = get_static_blacklist()
    assert len(bl) == 5
    # Tous en REJET × asie (audit SQL Phase 132)
    for entry in bl:
        assert entry[1] == "REJET"
        assert entry[2] == "asie"


def test_normalize_principe_set_sorted():
    """Normalisation : ordre alphabetique, strip espaces."""
    ps = _normalize_principe_set(["Z", "A", "M"])
    assert ps == ("A", "M", "Z")
    ps = _normalize_principe_set(["  B ", "A", "C  "])
    assert ps == ("A", "B", "C")


def test_normalize_principe_set_empty():
    """Liste vide : tuple vide."""
    assert _normalize_principe_set([]) == ()


def test_kill_switch_default_off_in_isolated_env(monkeypatch):
    """Defaut OFF (R25' strict) si env ET fichier n'ont pas la cle.

    Le .env du projet a V9_...=1 par motion CEO. Ce test verifie
    isolement : monkeypatch force la cle a 0 et recharge le module.
    """
    monkeypatch.setenv("V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED", "0")
    import importlib
    from core.v9 import kill_switches
    kill_switches._switches = None
    importlib.reload(kill_switches)
    import core.v9.kill_switches as ks
    assert ks.cross_blacklist_enabled() is False


def test_kill_switch_off_passthrough():
    """Kill switch OFF (motion CEO passee ou isole) : blacklisted=False meme si match.

    Le .env du projet a V9_...=1 par motion CEO. Ce test utilise un env
    isole pour simuler le cas kill switch OFF.
    """
    import os
    os.environ["V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED"] = "0"
    import importlib
    from core.v9 import kill_switches
    kill_switches._switches = None
    importlib.reload(kill_switches)

    r = evaluate_cross_blacklist(
        principes=["GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"],
        regime="REJET",
        session="asie",
    )
    assert r["blacklisted"] is False
    assert r["reason"] == "kill_switch_off"

    # Cleanup
    os.environ.pop("V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED", None)
    kill_switches._switches = None
    importlib.reload(kill_switches)


def test_is_cross_blacklisted_match():
    """is_cross_blacklisted : match exact."""
    p = ["GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"]
    assert is_cross_blacklisted(p, "REJET", "asie") is True


def test_is_cross_blacklisted_no_match_regime():
    """Match regime different -> False."""
    p = ["GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"]
    assert is_cross_blacklisted(p, "CASSURE", "asie") is False


def test_is_cross_blacklisted_no_match_session():
    """Match session differente -> False."""
    p = ["GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"]
    assert is_cross_blacklisted(p, "REJET", "london") is False


def test_is_cross_blacklisted_order_independent():
    """Ordre des principes irrelevant (normalisation sorted)."""
    p1 = ["GRAMMAR_EXHAUSTION", "GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE"]
    p2 = ["GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_CONTEXTE", "GRAMMAR_EXHAUSTION"]
    # Les deux doivent matcher (sorted identique)
    assert is_cross_blacklisted(p1, "REJET", "asie") is True
    assert is_cross_blacklisted(p2, "REJET", "asie") is True


def test_is_cross_blacklisted_case_insensitive():
    """Regime et session case-insensitive (REJET/rejet = match)."""
    p = ["GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"]
    assert is_cross_blacklisted(p, "rejet", "asie") is True
    assert is_cross_blacklisted(p, "REJET", "ASIE") is True


def test_is_cross_blacklisted_empty_principes():
    """Principes vide : pass-through (R6 fail-open)."""
    assert is_cross_blacklisted([], "REJET", "asie") is False


def test_evaluate_kill_switch_on_match():
    """Kill switch ON (force via env) + match -> blacklisted=True."""
    import os
    os.environ["V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED"] = "1"
    import importlib
    from core.v9 import kill_switches
    kill_switches._switches = None
    importlib.reload(kill_switches)

    try:
        r = evaluate_cross_blacklist(
            principes=["GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"],
            regime="REJET",
            session="asie",
        )
        assert r["blacklisted"] is True
        assert r["active"] is True
        assert "L17_cross_blacklist_grammar_rejet_asie" in r["leviers"]
        assert r["cross"] is not None
    finally:
        os.environ.pop("V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED", None)
        kill_switches._switches = None
        importlib.reload(kill_switches)


def test_evaluate_kill_switch_on_no_match():
    """Kill switch ON + pas de match -> pass-through."""
    import os
    os.environ["V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED"] = "1"
    import importlib
    from core.v9 import kill_switches
    kill_switches._switches = None
    importlib.reload(kill_switches)

    try:
        r = evaluate_cross_blacklist(
            principes=["OTHER_PRINCIPE"],
            regime="CASSURE",
            session="london",
        )
        assert r["blacklisted"] is False
        assert r["active"] is False
        assert r["reason"] == "cross_not_in_blacklist"
    finally:
        os.environ.pop("V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED", None)
        kill_switches._switches = None
        importlib.reload(kill_switches)


def test_static_blacklist_immutable_default():
    """get_static_blacklist retourne copie (pas reference mutable)."""
    bl1 = get_static_blacklist()
    bl1.clear()  # Modifie la copie
    bl2 = get_static_blacklist()
    # bl2 doit toujours avoir 5 entrees (la constante n'est pas affectee)
    assert len(bl2) == 5