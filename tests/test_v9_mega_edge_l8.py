"""Tests Phase 120 — Levier L8 blacklister mega-combinaisons (n_principes >= 5).

Verifie le comportement du levier L8 dans v9_mega_edge_filter :
- L8 OFF (defaut) : n_principes >= 5 ne sont PAS bloques
- L8 ON + 5 principes : bloque (return go=False)
- L8 ON + 4 principes : PAS bloque (sous le seuil)
- L8 ON + 3 principes : PAS bloque
- R6 fail-open : si L8 leve ou mega_edge OFF, on laisse passer
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _enable_mega(monkeypatch):
    """V9_MEGA_EDGE_ENABLED=1 obligatoire pour activer les leviers L1-L8."""
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_MEGA_EDGE_ENABLED", raising=False)


def _call_evaluate(principes, l8_on=False):
    """Appel direct a mega_edge_evaluation avec une liste de principes."""
    from core.v9 import v9_mega_edge_filter as mef
    from core.v9 import kill_switches as ks
    if l8_on:
        with patch.object(ks, "mega_edge_l8_principle_count_blacklist_enabled", return_value=True):
            return mef.mega_edge_evaluation(
                snapshot_id="SNAP-L8-TEST",
                symbol="GBPUSD",
                direction="haussiere",
                principes=principes,
                db_path=None,
            )
    return mef.mega_edge_evaluation(
        snapshot_id="SNAP-L8-TEST",
        symbol="GBPUSD",
        direction="haussiere",
        principes=principes,
        db_path=None,
    )


# ---------------------------------------------------------------------------
# L8 OFF (defaut) : aucun impact
# ---------------------------------------------------------------------------

def test_l8_off_5_principes_passes(monkeypatch):
    """L8 OFF + 5 principes : ne bloque PAS (defaut OFF)."""
    monkeypatch.delenv("V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED", raising=False)
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        "GRAVITY_RESPRING_NODE", "GRAMMAR_PULLBACK", "ZONE_RETEST"
    ], l8_on=False)
    # L8 OFF → ne bloque pas
    assert "L8_principle_count" not in res.get("leviers", [])


def test_l8_off_10_principes_passes(monkeypatch):
    """L8 OFF + 10 principes : ne bloque PAS."""
    monkeypatch.delenv("V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED", raising=False)
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "GRAMMAR_PULLBACK", "GRAMMAR_CONTEXTE",
        "ZONE_RETEST", "ELASTIC_BREATH", "NODE_BIRTH_FAST", "RAW_NODE_BIRTH",
        "GRAMMAR_EXHAUSTION", "GRAMMAR_CROISEMENT", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"
    ], l8_on=False)
    assert "L8_principle_count" not in res.get("leviers", [])


# ---------------------------------------------------------------------------
# L8 ON : n_principes >= 5 bloques
# ---------------------------------------------------------------------------

def test_l8_on_5_principes_blocked():
    """L8 ON + 5 principes (3 stars + 2 GRAMMAR) : go=False + L8_principle_count."""
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        "GRAVITY_RESPRING_NODE", "GRAMMAR_PULLBACK", "ZONE_RETEST"
    ], l8_on=True)
    assert res["go"] is False
    assert "L8_principle_count" in res.get("leviers", [])
    assert res["reason"] == "blacklist_l8_principle_count_ge5"


def test_l8_on_10_principes_blocked():
    """L8 ON + 10 principes (pas de GRAMMAR+ELASTIC simultane) : go=False."""
    # Eviter GRAMMAR+ELASTIC ensemble (sinon L5 bloque avant L8)
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "GRAMMAR_PULLBACK", "GRAMMAR_CONTEXTE",
        "ZONE_RETEST", "NODE_BIRTH_FAST", "RAW_NODE_BIRTH",
        "GRAMMAR_EXHAUSTION", "GRAMMAR_CROISEMENT",
        "POWER_ANGLE_BREAK_TO_PRICE_IMPACT", "GRAVITY_RESPRING_NODE"
    ], l8_on=True)
    assert res["go"] is False
    assert "L8_principle_count" in res.get("leviers", [])


def test_l8_on_4_principes_passes():
    """L8 ON + 4 principes : PAS bloque (sous seuil)."""
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        "GRAVITY_RESPRING_NODE", "GRAMMAR_PULLBACK"
    ], l8_on=True)
    # L4 (dilution) peut bloquer si n_principes > 2 ET no stars
    # Ici on a 3 stars + 1 GRAMMAR, donc n_stars=3, L4 OK
    # L8 ON mais n_principes=4 < 5, donc PAS bloque
    assert "L8_principle_count" not in res.get("leviers", [])


def test_l8_on_3_principes_passes():
    """L8 ON + 3 principes : PAS bloque (sous seuil)."""
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        "GRAVITY_RESPRING_NODE"
    ], l8_on=True)
    # 3 stars purs, n_principes=3 < 5
    assert "L8_principle_count" not in res.get("leviers", [])
    # Edge authentique : doit passer
    assert res["go"] is True


def test_l8_on_2_principes_passes():
    """L8 ON + 2 principes : PAS bloque."""
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"
    ], l8_on=True)
    assert "L8_principle_count" not in res.get("leviers", [])


def test_l8_on_mega_edge_disabled_l8_no_op(monkeypatch):
    """L8 ON + mega_edge OFF : R6 fail-open, L8 n'opere pas."""
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "0")
    # On doit aussi patcher L8 pour eviter le bug latent (Phase 117 fix)
    from core.v9 import kill_switches as ks
    with patch.object(ks, "mega_edge_l8_principle_count_blacklist_enabled", return_value=True):
        from core.v9 import v9_mega_edge_filter as mef
        res = mef.mega_edge_evaluation(
            snapshot_id="SNAP-L8-TEST",
            symbol="GBPUSD",
            direction="haussiere",
            principes=[
                "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
                "GRAVITY_RESPRING_NODE", "GRAMMAR_PULLBACK", "ZONE_RETEST",
                "ELASTIC_BREATH", "NODE_BIRTH_FAST", "RAW_NODE_BIRTH",
                "GRAMMAR_EXHAUSTION", "GRAMMAR_CROISEMENT"
            ],
            db_path=None,
        )
    # mega_edge OFF → pas de filtrage, go=True (defaut)
    assert res["go"] is True


def test_l8_priority_over_l4_dilution():
    """L8 (n>=5) doit bloquer AVANT L4 (dilution >2 no-stars)."""
    # Sans GRAMMAR+ELASTIC pour eviter L5
    res = _call_evaluate([
        "PRICE_LAG_AT_NODE_BIRTH", "GRAMMAR_PULLBACK", "GRAMMAR_CONTEXTE",
        "ZONE_RETEST", "NODE_BIRTH_FAST"  # 5 principes, dont 1 star, pas d'ELASTIC
    ], l8_on=True)
    # L8 (n_principes >= 5) doit bloquer
    assert res["go"] is False
    assert "L8_principle_count" in res.get("leviers", [])
    # L4 (dilution >2 no-stars) ne doit PAS avoir été évalué
    assert "L4_stars_only_no_dilution" not in res.get("leviers", [])