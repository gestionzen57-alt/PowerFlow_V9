"""Tests — CVD tick-level MT4 (Chantier C, 2026-07-18) PowerFlow V9.

Couvre les 4 briques additives, toutes derrière V9_CVD_ENABLED (défaut OFF) :
  1. Migration idempotente (db_schema.migrate_cvd + schéma frais)
  2. capture_server : intersection colonnes (prod safe avant migration)
  3. forces_reader : passe cvd_delta/cvd_cumul de l'EA vers la row
  4. scene_builder : expose cvd_cumul + flag cvd_divergence (gated)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import core.v9.capture_server as capture_server
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db, migrate_cvd
from core.v9.forces_reader import ForcesReader
from core.v9.kill_switches import cvd_enabled
from core.v9.scene_builder import SceneBuilder
from core.v9.stale_gate import StaleGate

BASE_TIME = 1_751_700_000


def _iso(epoch_s: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _raw(**over) -> dict:
    raw = {
        "schema_version": "1.0", "snapshot_id": f"v9-cvd-{BASE_TIME}",
        "timestamp": _iso(BASE_TIME), "source": "MT4_SDI",
        "symbol": "GBPUSD", "timeframe": "M5",
        "bar_time": BASE_TIME, "bar_close_time": BASE_TIME + 300,
        "server_time": BASE_TIME, "capture_time": BASE_TIME, "shift": 1,
        "is_closed_bar": True,
        "open": 1.25, "high": 1.255, "low": 1.248, "close": 1.253,
        "tick_volume": 120, "spread_points": 10, "spread_price": 0.0001,
        "bid": 1.2529, "ask": 1.2531, "mid": 1.2530,
        "force_usd": 40.0, "force_gbp": 50.0, "force_eur": 45.0, "force_jpy": 30.0,
        "force_cad": 35.0, "force_chf": 42.0, "force_aud": 38.0, "force_nzd": 33.0,
    }
    raw.update(over)
    return raw


# ── 1. Migration ───────────────────────────────────────────────────

def test_fresh_schema_has_cvd_columns(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    init_db(db)
    conn = get_connection(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(forces_snapshots)").fetchall()}
    finally:
        conn.close()
    assert "cvd_delta" in cols and "cvd_cumul" in cols


def test_migrate_cvd_adds_columns_to_old_schema(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE forces_snapshots (id INTEGER PRIMARY KEY, snapshot_id TEXT, close REAL)"
    )
    conn.commit()
    added = migrate_cvd(conn)
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(forces_snapshots)").fetchall()}
    conn.close()
    assert set(added) == {"cvd_delta", "cvd_cumul"}
    assert "cvd_delta" in cols and "cvd_cumul" in cols


def test_migrate_cvd_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "idem.db"
    init_db(db)  # déjà cvd via schéma frais
    conn = get_connection(db)
    try:
        assert migrate_cvd(conn) == []  # rien à ajouter
    finally:
        conn.close()


# ── 2. capture_server : intersection colonnes (prod safe) ──────────

def test_effective_columns_excludes_absent_cvd(tmp_path: Path) -> None:
    """Base ancienne (sans cvd) : l'INSERT ne référence pas cvd -> pas de crash
    prod avant migration."""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    # Table minimale sans cvd, avec les colonnes de base.
    base_cols = [c for c in FORCES_COLUMNS if c not in ("cvd_delta", "cvd_cumul")]
    conn.execute(f"CREATE TABLE forces_snapshots ({', '.join(c + ' TEXT' for c in base_cols)})")
    conn.commit()
    capture_server._effective_columns = None  # reset cache
    try:
        cols = capture_server._get_effective_columns(conn)
        assert "cvd_delta" not in cols and "cvd_cumul" not in cols
    finally:
        capture_server._effective_columns = None
        conn.close()


def test_effective_columns_includes_cvd_after_migration(tmp_path: Path) -> None:
    db = tmp_path / "new.db"
    init_db(db)
    conn = get_connection(db)
    capture_server._effective_columns = None
    try:
        cols = capture_server._get_effective_columns(conn)
        assert "cvd_delta" in cols and "cvd_cumul" in cols
    finally:
        capture_server._effective_columns = None
        conn.close()


# ── 3. forces_reader : passthrough cvd ─────────────────────────────

def test_forces_reader_passes_cvd_fields() -> None:
    reader = ForcesReader(StaleGate({"M5": 35_000}))
    result = reader.transform(_raw(cvd_delta=120, cvd_cumul=5000), now_ms=BASE_TIME * 1000)
    row = result["row"]
    assert row["cvd_delta"] == 120
    assert row["cvd_cumul"] == 5000


def test_forces_reader_cvd_absent_is_none() -> None:
    reader = ForcesReader(StaleGate({"M5": 35_000}))
    row = reader.transform(_raw(), now_ms=BASE_TIME * 1000)["row"]
    assert row["cvd_delta"] is None and row["cvd_cumul"] is None


# ── 4. scene_builder : exposition + divergence (gated) ─────────────

@pytest.fixture
def builder(tmp_path: Path) -> SceneBuilder:
    return SceneBuilder(db_path=tmp_path / "v9.db", config={"memory_dir": tmp_path / "mem"})


def test_cvd_assessment_off_passthrough(builder: SceneBuilder, monkeypatch) -> None:
    monkeypatch.setenv("V9_CVD_ENABLED", "0")
    out = builder._cvd_assessment({"close": 1.25, "cvd_delta": -5, "cvd_cumul": 10}, {"close": 1.20})
    assert out["enabled"] is False
    assert out["cvd_divergence"] is False


def test_cvd_assessment_on_detects_bearish_divergence(builder: SceneBuilder, monkeypatch) -> None:
    monkeypatch.setenv("V9_CVD_ENABLED", "1")
    # prix monte (1.25 > 1.20) mais flux vendeur (cvd_delta < 0) -> divergence.
    out = builder._cvd_assessment(
        {"close": 1.25, "cvd_delta": -50, "cvd_cumul": 900}, {"close": 1.20}
    )
    assert out["enabled"] is True
    assert out["cvd_cumul"] == 900
    assert out["cvd_divergence"] is True


def test_cvd_assessment_on_no_divergence_when_aligned(builder: SceneBuilder, monkeypatch) -> None:
    monkeypatch.setenv("V9_CVD_ENABLED", "1")
    # prix monte ET flux acheteur -> pas de divergence.
    out = builder._cvd_assessment(
        {"close": 1.25, "cvd_delta": 50, "cvd_cumul": 1100}, {"close": 1.20}
    )
    assert out["cvd_divergence"] is False


def test_cvd_assessment_missing_data_no_crash(builder: SceneBuilder, monkeypatch) -> None:
    monkeypatch.setenv("V9_CVD_ENABLED", "1")
    out = builder._cvd_assessment({"close": 1.25}, None)  # cvd absent + pas de prev
    assert out["enabled"] is True
    assert out["cvd_divergence"] is False


def test_cvd_enabled_default_off(monkeypatch) -> None:
    # Défaut CODE = OFF. Depuis la motion CEO 2026-07-20, le fichier déployé
    # config/v9_kill_switches.env fixe V9_CVD_ENABLED=1 (déploiement Chantier C).
    # On isole du fichier en vidant le cache du chargeur : get() retombe alors
    # sur son défaut "0". Le test valide le contrat CODE, pas la config live.
    import core.v9.kill_switches as ks
    monkeypatch.delenv("V9_CVD_ENABLED", raising=False)
    monkeypatch.setattr(ks, "_switches", {})
    assert cvd_enabled() is False
