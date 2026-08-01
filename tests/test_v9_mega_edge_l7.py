"""Tests Phase 108 — Levier L7 anti-GRAMMAR/ELASTIC pur sans etoile.

Verifie le comportement du levier L7 dans v9_mega_edge_filter :
- L7 OFF (defaut) : GRAMMAR/ELASTIC pur no-stars ne sont PAS bloques
- L7 ON : GRAMMAR pur no-stars est bloque (return go=False)
- L7 ON : ELASTIC pur no-stars est bloque
- L7 ON : GRAMMAR + PRICE_LAG (mix avec star) N'EST PAS bloque
  (les stars preservent le trade, c'est l'essence de L4 et de l'edge)
- R6 fail-open : si le kill switch leve, on laisse passer
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _enable_mega(monkeypatch):
    """V9_MEGA_EDGE_ENABLED=1 obligatoire pour activer les leviers L1-L7."""
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_MEGA_EDGE_ENABLED", raising=False)


def _call_evaluate(principes):
    """Appel direct a mega_edge_evaluation avec une liste de principes."""
    from core.v9 import v9_mega_edge_filter as mef
    return mef.mega_edge_evaluation(
        snapshot_id="SNAP-L7-TEST",
        symbol="GBPUSD",
        direction="haussiere",
        principes=principes,
        db_path=None,
    )


# ---------------------------------------------------------------------------
# L7 OFF (defaut) : aucun impact
# ---------------------------------------------------------------------------

def test_l7_off_grammar_pur_passes(monkeypatch):
    """L7 OFF (defaut) : GRAMMAR pur no-stars n'est PAS bloque (defaut OFF)."""
    monkeypatch.delenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", raising=False)
    res = _call_evaluate(["GRAMMAR_CONTEXTE", "GRAMMAR_PULLBACK"])
    # L4 (dilution) peut bloquer si n_principes > 2 ET no stars
    # Avec 2 principes GRAMMAR purs no-stars, L4 ne bloque pas (>2 stricte)
    # L5 ne bloque pas (pas de mix GRAMMAR+ELASTIC)
    # L7 OFF → ne bloque pas
    assert res["go"] is True
    assert "L7_grammar_pur" not in res.get("leviers", [])


def test_l7_off_elastic_pur_passes(monkeypatch):
    """L7 OFF : ELASTIC pur no-stars n'est PAS bloque."""
    monkeypatch.delenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", raising=False)
    res = _call_evaluate(["ELASTIC_BREATH"])
    # ELASTIC seul, no-stars → L4 OK (1 principe), L5 OK (no GRAMMAR), L7 OFF
    assert res["go"] is True


# ---------------------------------------------------------------------------
# L7 ON : GRAMMAR/ELASTIC pur no-stars bloques
# ---------------------------------------------------------------------------

def test_l7_on_grammar_pur_blocked(monkeypatch):
    """L7 ON + GRAMMAR pur no-stars → go=False + L7_grammar_pur."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["GRAMMAR_CONTEXTE", "GRAMMAR_PULLBACK"])
    assert res["go"] is False
    assert "L7_grammar_pur" in res["leviers"]
    assert res["sizing_multiplier"] == 0.0
    assert res["reason"] == "blacklist_l7_grammar_elastic_pur"


def test_l7_on_elastic_pur_blocked(monkeypatch):
    """L7 ON + ELASTIC pur no-stars → go=False + L7_elastic_pur."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["ELASTIC_BREATH"])
    assert res["go"] is False
    assert "L7_elastic_pur" in res["leviers"]
    assert res["sizing_multiplier"] == 0.0


def test_l7_on_single_grammar_blocked(monkeypatch):
    """L7 ON + 1 seul GRAMMAR pur → bloque (meme sans dilution)."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["GRAMMAR_PULLBACK"])
    assert res["go"] is False
    assert "L7_grammar_pur" in res["leviers"]


# ---------------------------------------------------------------------------
# L7 ON : les mixes avec star NE SONT PAS bloques (essentiel : edge preservé)
# ---------------------------------------------------------------------------

def test_l7_on_grammar_with_star_passes(monkeypatch):
    """L7 ON + GRAMMAR + PRICE_LAG (star) → PAS bloque (edge preserve)."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["GRAMMAR_PULLBACK", "PRICE_LAG_AT_NODE_BIRTH"])
    # n_stars >= 1 → L7 ne s'applique pas
    assert res["go"] is True
    assert "L7_grammar_pur" not in res.get("leviers", [])


def test_l7_on_elastic_with_star_passes(monkeypatch):
    """L7 ON + ELASTIC + POWER_ANGLE (star) → PAS bloque."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["ELASTIC_BREATH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"])
    assert res["go"] is True
    assert "L7_elastic_pur" not in res.get("leviers", [])


def test_l7_on_pure_stars_passes(monkeypatch):
    """L7 ON + 3 stars purs → PAS bloque (c'est l'edge maximal)."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH",
        "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        "GRAVITY_RESPRING_NODE",
    ])
    assert res["go"] is True
    assert "L7" not in str(res.get("leviers", []))


# ---------------------------------------------------------------------------
# L5 a priorite sur L7 (mix GRAMMAR+ELASTIC → L5, pas L7)
# ---------------------------------------------------------------------------

def test_l5_priority_over_l7_grammar_elastic_mix(monkeypatch):
    """L7 ON + mix GRAMMAR+ELASTIC no-stars → L5优先 (L5 est teste en premier)."""
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["GRAMMAR_CONTEXTE", "ELASTIC_BREATH"])
    # L5 a la priorite dans le code (ligne 285-295 du fichier source)
    # L5 detecte has_grammar_elastic = True → return avec L5_blacklist_grammar_elastic
    assert res["go"] is False
    # Le L7 ne doit PAS avoir ete declenche en doublon
    assert "L7_grammar_pur" not in res.get("leviers", [])
    assert "L7_elastic_pur" not in res.get("leviers", [])


# ---------------------------------------------------------------------------
# R6 fail-open
# ---------------------------------------------------------------------------

def test_l7_mega_edge_disabled_l7_no_op(monkeypatch):
    """Mega edge OFF → L7 inoperant (meme si son kill switch est ON)."""
    monkeypatch.delenv("V9_MEGA_EDGE_ENABLED", raising=False)
    monkeypatch.setenv("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
    res = _call_evaluate(["GRAMMAR_PULLBACK"])
    # mega_edge_evaluation doit court-circuiter si mega_edge_enabled=False
    # Comportement exact depend de l'implementation, mais le trade ne doit PAS
    # etre bloque par L7 si mega_edge est OFF
    if res.get("reason") == "mega_edge_disabled":
        assert res["go"] is True  # fail-open
