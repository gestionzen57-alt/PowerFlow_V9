"""Tests — core/v9/shadow_evaluator.py (P2 Shadow mode, 2026-07-13).

Vérifie :
- Kill switch V9_SHADOW_MODE_ENABLED défaut OFF (R25').
- run_shadow_pass produit une décision source_type='shadow' distincte de
  la décision live, sans jamais toucher aux tables perceptuelles
  (regime_snapshots / zone_diagnostics — UNIQUE(snapshot, currency) +
  INSERT OR REPLACE, corruption possible si re-detect()).
- Restauration de l'environnement dans tous les cas (succès ou échec).
- ShadowDecisionLogger ne déclenche jamais le branchement HITL Telegram.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.v9 import orchestrator
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.shadow_evaluator import (
    SHADOW_ENV_OVERRIDES,
    SHADOW_MODE_ENV,
    SOURCE_TYPE_SHADOW,
    ShadowDecisionLogger,
    is_shadow_mode_enabled,
    run_shadow_pass,
)


def _insert_forces_snapshot(db_path: Path, *, bar_time: int = 0) -> str:
    snapshot_id = f"v9-shadow-{bar_time:04d}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": f"2026-07-13T10:{bar_time:02d}:00.000Z",
        "source": "MT4_SDI",
        "symbol": "GBPUSD",
        "timeframe": "M5",
        "bar_time": bar_time,
        "is_closed_bar": True,
        "high": 1.2900, "low": 1.2800, "close": 1.2860,
        "force_usd": 50.0, "force_gbp": 70.0, "force_eur": 45.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "compression_extension_etat": "neutre", "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": f"2026-07-13T10:{bar_time:02d}:00.100Z",
    })
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(FORCES_COLUMNS)
        placeholders = ", ".join(["?"] * len(FORCES_COLUMNS))
        conn.execute(
            f"INSERT INTO forces_snapshots ({col_names}) VALUES ({placeholders})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


def _count(db_path: Path, table: str) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def live_snapshot(tmp_path: Path) -> tuple[Path, str]:
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    init_db(db_path)
    snapshot_id = _insert_forces_snapshot(db_path)
    result = orchestrator.run_chain(snapshot_id, db_path=db_path, memory_dir=memory_dir)
    assert result["error"] is None
    assert result["decision_id"] is not None
    return db_path, snapshot_id


# ── Kill switch ─────────────────────────────────────────────────────────


def test_is_shadow_mode_enabled_default_off(monkeypatch) -> None:
    monkeypatch.delenv(SHADOW_MODE_ENV, raising=False)
    assert is_shadow_mode_enabled() is False


def test_is_shadow_mode_enabled_on(monkeypatch) -> None:
    monkeypatch.setenv(SHADOW_MODE_ENV, "1")
    assert is_shadow_mode_enabled() is True


def test_is_shadow_mode_enabled_zero_is_off(monkeypatch) -> None:
    monkeypatch.setenv(SHADOW_MODE_ENV, "0")
    assert is_shadow_mode_enabled() is False


# ── ShadowDecisionLogger — jamais de branchement HITL Telegram ─────────


def test_shadow_decision_logger_apply_hitl_branching_always_zero() -> None:
    logger_instance = ShadowDecisionLogger.__new__(ShadowDecisionLogger)
    result = logger_instance._apply_hitl_branching(
        direction="haussiere", confiance=50, symbol="GBPUSD",
        timeframe="M5", principes=["p1"],
    )
    assert result == 0


# ── run_shadow_pass — non-régression tables perceptuelles ──────────────


def test_run_shadow_pass_creates_distinct_shadow_decision(live_snapshot) -> None:
    db_path, snapshot_id = live_snapshot

    shadow_decision = run_shadow_pass(snapshot_id, db_path=db_path)

    assert shadow_decision is not None
    assert shadow_decision["source_type"] == SOURCE_TYPE_SHADOW
    assert shadow_decision["snapshot_id"] == snapshot_id

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT decision_id, source_type FROM decisions WHERE snapshot_id = ? ORDER BY id",
            (snapshot_id,),
        ).fetchall()
    finally:
        conn.close()
    source_types = {r[1] for r in rows}
    assert source_types == {"live", "shadow"}
    # Deux décisions distinctes, jamais la même ligne écrasée.
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]


def test_run_shadow_pass_never_touches_regime_or_zone_tables(live_snapshot) -> None:
    db_path, snapshot_id = live_snapshot
    regime_before = _count(db_path, "regime_snapshots")
    zone_before = _count(db_path, "zone_diagnostics")

    run_shadow_pass(snapshot_id, db_path=db_path)

    assert _count(db_path, "regime_snapshots") == regime_before
    assert _count(db_path, "zone_diagnostics") == zone_before


def test_run_shadow_pass_leaves_live_decision_untouched(live_snapshot) -> None:
    db_path, snapshot_id = live_snapshot
    conn = get_connection(db_path)
    try:
        live_before = conn.execute(
            "SELECT decision_id, action, confiance FROM decisions "
            "WHERE snapshot_id = ? AND source_type = 'live'",
            (snapshot_id,),
        ).fetchone()
    finally:
        conn.close()

    run_shadow_pass(snapshot_id, db_path=db_path)

    conn = get_connection(db_path)
    try:
        live_after = conn.execute(
            "SELECT decision_id, action, confiance FROM decisions "
            "WHERE snapshot_id = ? AND source_type = 'live'",
            (snapshot_id,),
        ).fetchone()
    finally:
        conn.close()
    assert live_before == live_after


# ── Restauration environnement ──────────────────────────────────────────


def test_run_shadow_pass_restores_env_when_previously_unset(live_snapshot, monkeypatch) -> None:
    db_path, snapshot_id = live_snapshot
    for key in SHADOW_ENV_OVERRIDES:
        monkeypatch.delenv(key, raising=False)

    run_shadow_pass(snapshot_id, db_path=db_path)

    for key in SHADOW_ENV_OVERRIDES:
        assert key not in os.environ


def test_run_shadow_pass_restores_env_when_previously_set(live_snapshot, monkeypatch) -> None:
    db_path, snapshot_id = live_snapshot
    for key in SHADOW_ENV_OVERRIDES:
        monkeypatch.setenv(key, "0")

    run_shadow_pass(snapshot_id, db_path=db_path)

    for key in SHADOW_ENV_OVERRIDES:
        assert os.environ.get(key) == "0"


def test_run_shadow_pass_restores_env_even_on_failure(live_snapshot, monkeypatch) -> None:
    db_path, snapshot_id = live_snapshot
    for key in SHADOW_ENV_OVERRIDES:
        monkeypatch.delenv(key, raising=False)

    from core.v9 import shadow_evaluator

    def _boom(self, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(shadow_evaluator.PrincipleEngine, "evaluate_principles", _boom)

    result = run_shadow_pass(snapshot_id, db_path=db_path)

    assert result is None
    for key in SHADOW_ENV_OVERRIDES:
        assert key not in os.environ


def test_run_shadow_pass_applies_overrides_during_the_call(live_snapshot, monkeypatch) -> None:
    """Vérifie que le kill switch expérimental est bien vu ACTIF par
    PrincipleEngine pendant le passage shadow (pas seulement posé/retiré
    dans l'environnement sans effet)."""
    db_path, snapshot_id = live_snapshot
    for key in SHADOW_ENV_OVERRIDES:
        monkeypatch.delenv(key, raising=False)

    from core.v9 import principle_engine

    seen: list[bool] = []
    original = principle_engine.adaptive_thresholds_wired_enabled

    def _spy():
        seen.append(original())
        return original()

    monkeypatch.setattr(principle_engine, "adaptive_thresholds_wired_enabled", _spy)

    run_shadow_pass(snapshot_id, db_path=db_path)

    assert True in seen
