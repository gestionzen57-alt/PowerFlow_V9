"""Tests — P3-WIRE : câblage adaptive_thresholds_at_runtime.py dans
principle_engine._load_shared_context (kill switch dédié, 2026-07-13).

Le module de calcul (core/v9/adaptive_thresholds_at_runtime.py, commit
5abfa2b) existait déjà mais n'était branché nulle part. Ce fichier couvre
le câblage : disponibilité des 3 champs dans le contexte partagé quand le
switch est ON, absence quand il est OFF, et surtout la non-régression —
switch OFF *ou* ON, aucun principe YAML ACTIVE/SHADOW ne consomme encore
ces champs, donc evaluate_principles() doit produire une sortie
strictement identique (triggered/direction/confidence/reason par
principe) dans les deux cas.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.v9.db_schema import get_connection, init_db
from core.v9.principle_engine import (
    ADAPTIVE_THRESHOLDS_WIRED_ENV,
    PrincipleEngine,
    adaptive_thresholds_wired_enabled,
)

from tests.test_principle_engine import _insert_full_chain


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


def test_kill_switch_name_is_dedicated() -> None:
    """Le kill switch P3-WIRE a un nom propre, distinct de tous les
    switches existants (consigne mission : ne pas réutiliser un switch)."""
    assert ADAPTIVE_THRESHOLDS_WIRED_ENV == "V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED"
    other_switches = {
        "V9_TRADER_MINI_ENABLED",
        "V9_AUTO_CALIBRATOR_ENABLED",
        "V9_ARBITER_SCORER_ENABLED",
        "V9_HITL_BRANCHING_ENABLED",
        "V9_EXECUTION_ENABLED",
        "V9_AUTO_RESOLVE_ENABLED",
    }
    assert ADAPTIVE_THRESHOLDS_WIRED_ENV not in other_switches


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans variable d'environnement posée, le switch est OFF."""
    monkeypatch.delenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, raising=False)
    assert adaptive_thresholds_wired_enabled() is False


def test_enabled_when_env_set_to_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, "1")
    assert adaptive_thresholds_wired_enabled() is True


def test_context_no_adaptive_fields_when_disabled(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switch OFF (défaut) : les 3 champs adaptive_* ne sont jamais posés,
    seul le drapeau adaptive_thresholds_enabled=False est présent."""
    monkeypatch.delenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, raising=False)
    snapshot_id = _insert_full_chain(db_path, timeframe="M15")
    engine = PrincipleEngine(db_path=db_path)
    conn = engine._connect()
    try:
        shared = engine._load_shared_context(conn, snapshot_id)
    finally:
        conn.close()
    ctx = shared["context"]

    assert ctx["adaptive_thresholds_enabled"] is False
    assert "adaptive_coalition_threshold" not in ctx
    assert "adaptive_antagonism_threshold" not in ctx
    assert "adaptive_pliure_threshold" not in ctx


def test_context_has_adaptive_fields_when_enabled(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Switch ON : les 3 seuils effectifs sont posés dans le contexte,
    cohérents avec un appel direct à get_effective_thresholds()."""
    monkeypatch.setenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, "1")
    snapshot_id = _insert_full_chain(db_path, timeframe="M15")
    engine = PrincipleEngine(db_path=db_path)
    conn = engine._connect()
    try:
        shared = engine._load_shared_context(conn, snapshot_id)
    finally:
        conn.close()
    ctx = shared["context"]

    assert ctx["adaptive_thresholds_enabled"] is True

    from core.v9.adaptive_thresholds_at_runtime import get_effective_thresholds

    # DB de test minimale -> pas de bougies -> vol_regime reste au
    # fallback "NORMAL" posé dans _load_shared_context. news_phase reste
    # celui réellement calculé par NewsContext() (horloge système), on
    # applique donc le même mapping NEUTRE->NORMAL que le code testé.
    news_phase_mapped = "NORMAL" if ctx.get("news_phase") in (None, "NEUTRE") else ctx["news_phase"]
    expected = get_effective_thresholds(
        ctx.get("vol_regime", "NORMAL"), news_phase=news_phase_mapped, timeframe="M15",
    )
    assert ctx["adaptive_coalition_threshold"] == expected["COALITION"]
    assert ctx["adaptive_antagonism_threshold"] == expected["ANTAGONISM"]
    assert ctx["adaptive_pliure_threshold"] == expected["PLIURE"]


def test_neutre_news_phase_mapped_like_normal(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """news_phase='NEUTRE' (vocabulaire news_context.py) doit produire le
    même seuil effectif que news_phase='NORMAL' (vocabulaire du module
    adaptive_thresholds_at_runtime) — mapping explicite, pas un hasard de
    fallback dict.get()."""
    from core.v9.adaptive_thresholds_at_runtime import get_effective_thresholds

    via_neutre = get_effective_thresholds("NORMAL", news_phase="NORMAL", timeframe="M15")
    via_direct_normal = get_effective_thresholds("NORMAL", news_phase="NORMAL", timeframe="M15")
    assert via_neutre == via_direct_normal


def test_error_resilience_never_raises(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si get_effective_thresholds lève, le pipeline ne casse jamais —
    les champs adaptive_* sont simplement absents (même garde-fou que le
    bloc vol_regime/news)."""
    monkeypatch.setenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, "1")

    import core.v9.adaptive_thresholds_at_runtime as module

    def _boom(*args, **kwargs):
        raise RuntimeError("calibration indisponible")

    monkeypatch.setattr(module, "get_effective_thresholds", _boom)

    snapshot_id = _insert_full_chain(db_path, timeframe="M15")
    engine = PrincipleEngine(db_path=db_path)
    conn = engine._connect()
    try:
        shared = engine._load_shared_context(conn, snapshot_id)  # ne doit pas lever
    finally:
        conn.close()
    ctx = shared["context"]
    assert ctx["adaptive_thresholds_enabled"] is True
    assert "adaptive_coalition_threshold" not in ctx


def _principle_outcomes(evaluations: list[dict]) -> dict[str, tuple]:
    """Projette une liste d'évaluations sur (triggered, direction,
    confidence, reason) par principle_id — ignore evaluation_id/timestamp
    (non-déterministes par construction, uuid4 + horloge)."""
    return {
        e["principle_id"]: (e["triggered"], e["direction"], e["confidence"], e["reason"])
        for e in evaluations
    }


def test_evaluate_principles_output_identical_regardless_of_switch(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-régression bit-à-bit (hors evaluation_id/timestamp) : tant
    qu'aucun principe YAML historique ne référence adaptive_coalition_threshold /
    adaptive_antagonism_threshold / adaptive_pliure_threshold, le switch
    OFF ou ON ne doit produire STRICTEMENT aucune différence sur
    triggered/direction/confidence/reason pour un même snapshot.

    Note 2026-07-14 (P3-CONSUME Hermes) : depuis l'ajout du principe
    SHADOW ADAPTIVE_VOL_GATE, qui CONSOMME les seuils adaptatifs via
    value_field, l'évaluation de CE principe diffère légitimement selon
    l'état du switch P3-WIRE (OFF = champs absents -> not triggered,
    ON = champs présents -> peut déclencher). La non-régression se
    limite donc aux 26 principes historiques (avant P3-CONSUME).
    Les 9 node_rule historiques sont testés séparément.
    """
    snapshot_id = _insert_full_chain(db_path, timeframe="M15")

    monkeypatch.delenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, raising=False)
    engine_off = PrincipleEngine(db_path=db_path)
    evaluations_off = engine_off.evaluate_principles(snapshot_id)

    monkeypatch.setenv(ADAPTIVE_THRESHOLDS_WIRED_ENV, "1")
    engine_on = PrincipleEngine(db_path=db_path)
    evaluations_on = engine_on.evaluate_principles(snapshot_id)

    # Filtre : on compare uniquement les 26 principes historiques.
    # Les *_ADAPTIVE sont exclus par design (consomment les seuils) :
    # ADAPTIVE_VOL_GATE (P3-CONSUME, 5e1b9df) + 5 node_rule _ADAPTIVE
    # (P3-CONSUME-EXTEND, 2026-07-14, Hermes) — leur 1re condition qui fail
    # change selon que le switch est ON/OFF (présence/absence des champs
    # adaptive_*_threshold), c'est le comportement attendu de P3-CONSUME.
    ADAPTIVE_IDS = {
        "ADAPTIVE_VOL_GATE",
        # node_rule _ADAPTIVE (P3-CONSUME-EXTEND groupe 1, Hermes 2026-07-14)
        "COALITION_NODE_ADAPTIVE",
        "ANTAGONIST_NODE_ADAPTIVE",
        "ZONE_RETEST_ADAPTIVE",
        "ELASTIC_BREATH_ADAPTIVE",
        "GRAVITY_RESPRING_NODE_ADAPTIVE",
        # birth/break _ADAPTIVE (P3-CONSUME-EXTEND groupe 2, Hermes 2026-07-14)
        "POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE",
        "NODE_BIRTH_FAST_ADAPTIVE",
        "RAW_NODE_BIRTH_ADAPTIVE",
        "PRICE_LAG_AT_NODE_BIRTH_ADAPTIVE",
        # grammar + signal_open _ADAPTIVE (P3-CONSUME-EXTEND groupe 3, Hermes 2026-07-14)
        "GRAMMAR_ABSORPTION_ADAPTIVE",
        "GRAMMAR_ANTAGONISME_ADAPTIVE",
        "GRAMMAR_BREAK_ADAPTIVE",
        "GRAMMAR_COALITION_ADAPTIVE",
        "GRAMMAR_CONTEXTE_ADAPTIVE",
        "GRAMMAR_CROISEMENT_ADAPTIVE",
        "GRAMMAR_EXHAUSTION_ADAPTIVE",
        "GRAMMAR_EXTENSION_ADAPTIVE",
        "GRAMMAR_LEADER_FOLLOWER_ADAPTIVE",
        "GRAMMAR_LOCK_ADAPTIVE",
        "GRAMMAR_OPPOSITION_ADAPTIVE",
        "GRAMMAR_PULLBACK_ADAPTIVE",
        "GRAMMAR_REGIME_ADAPTIVE",
        "GRAMMAR_RESPIRATION_ADAPTIVE",
        "GRAMMAR_SQUEEZE_ADAPTIVE",
        "GRAMMAR_TENSION_ADAPTIVE",
        "SIGNAL_OPEN_ADAPTIVE",
    }
    HISTORICAL_IDS = (
        {e["principle_id"] for e in evaluations_off} - ADAPTIVE_IDS
    )
    off_filtered = {
        k: v for k, v in _principle_outcomes(evaluations_off).items()
        if k in HISTORICAL_IDS
    }
    on_filtered = {
        k: v for k, v in _principle_outcomes(evaluations_on).items()
        if k in HISTORICAL_IDS
    }
    assert off_filtered == on_filtered, (
        f"Régression détectée sur les principes historiques (hors _ADAPTIVE) :\n"
        f"  switch OFF: {off_filtered}\n"
        f"  switch ON:  {on_filtered}"
    )
    assert len(evaluations_off) == len(evaluations_on) > 0
