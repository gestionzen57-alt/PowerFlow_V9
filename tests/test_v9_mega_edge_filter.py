"""tests/test_v9_mega_edge_filter.py — Phase 2 motion CEO « EDGE FUND MAX »."""
import json
import os
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _enable_mega(monkeypatch):
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_MEGA_EDGE_ENABLED", raising=False)


@pytest.fixture
def tmp_db(tmp_path):
    """DB minimale avec table forces_snapshots pour tests L1/L2 heure UTC."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, "
            "timestamp TEXT)"
        )
        conn.commit()
    yield db


def _insert_snapshot(db, snap_id, hour_utc_offset_days=0):
    """Insère un snapshot avec timestamp à 11h UTC today."""
    base = datetime(2026, 7, 28, hour_utc_offset_days, 0, 0)
    # Force l'heure via timestamp
    target = base.replace(day=28)
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO forces_snapshots VALUES (?, ?)",
            (snap_id, target.isoformat()),
        )
        conn.commit()


def _db_with_snapshot_at(db, snap_id, hour, day_offset=0):
    """Insère snapshot avec timestamp à hour UTC, jours=offset."""
    target = datetime(2026, 7, 20, hour, 0, 0) + timedelta(days=day_offset)
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO forces_snapshots VALUES (?, ?)",
            (snap_id, target.isoformat()),
        )
        conn.commit()


def test_module_helpers():
    """mega_edge_enabled lit env, défaut ON autopilot."""
    from core.v9.v9_mega_edge_filter import mega_edge_enabled
    assert mega_edge_enabled() is True


def test_kill_hour_00_09_utc_blocks(tmp_path):
    """L2 — UTC 00h-09h → go=False."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-00h", 5)  # 5h UTC = kill hour
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id="v9-snap-00h",
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is False
    assert res["reason"] == "kill_hour"


def test_mega_edge_gbpusd_haussiere_11h_utc_passes(tmp_path):
    """L1 — GBPUSD haussière 11h UTC → go=True, L1 triggered."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-11h", 11)
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id="v9-snap-11h",
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True
    assert "L1_mega_edge_gbpusd_11_13_utc" in res["leviers"]


def test_mega_edge_13h_utc_sizing_boost(tmp_path):
    """L6 — UTC 13h → sizing_mult=1.5."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-13h", 13)
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id="v9-snap-13h",
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True
    assert res["sizing_multiplier"] == 1.5
    assert "L6_sizing_boost_x1.5_hour_13" in res["leviers"]


def test_blacklist_grammar_elastic_blocks(tmp_path):
    """L5 — GRAMMAR + ELASTIC_BREATH → go=False."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-mix", 12)
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id="v9-snap-mix",
        principes=["GRAMMAR_CONTEXTE", "ELASTIC_BREATH"],
        db_path=db,
    )
    assert res["go"] is False
    assert res["reason"] == "blacklist_mix"


def test_no_stars_dilution_blocks(tmp_path):
    """L4 — >2 principes sans star → go=False."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-dilution", 12)
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id="v9-snap-dilution",
        principes=["A", "B", "C", "D"],  # 4 principes, 0 star
        db_path=db,
    )
    assert res["go"] is False
    assert res["reason"] == "no_stars_dilution"


def test_stars_pass_with_sizing_boost(tmp_path):
    """1 star + GBPUSD haussiere 11h UTC → OK + L1."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-star", 12)
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id="v9-snap-star",
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True
    assert "L4_stars(1)" in res["leviers"]


def test_non_gbpusd_passes_with_degraded_sizing(tmp_path):
    """Hors GBPUSD → sizing x0.5, go=True dégradé."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-other", 12)
    res = mega_edge_evaluation(
        symbol="EURUSD", direction="haussiere",
        snapshot_id="v9-snap-other",
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True
    assert res["sizing_multiplier"] == 0.5
    assert "graceful_degrade_non_gbpusd" in res["leviers"]


def test_kill_switch_off_disables_filter(tmp_path, monkeypatch):
    """V9_MEGA_EDGE_ENABLED=0 → go=True no_filter."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation, mega_edge_enabled
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "0")
    assert mega_edge_enabled() is False
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, timestamp TEXT)")
        conn.commit()
    _db_with_snapshot_at(db, "v9-snap-killh", 3)
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="baissiere",
        snapshot_id="v9-snap-killh",
        principes=["ELASTIC_BREATH", "GRAMMAR_CONTEXTE"],
        db_path=db,
    )
    assert res["go"] is True
    assert res["reason"] == "no_filter"


def test_time_exit_should_close():
    """L3 helper : >5min → True."""
    from core.v9.v9_mega_edge_filter import time_exit_should_close
    past = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
    assert time_exit_should_close(past) is True
    recent = datetime.utcnow().isoformat()
    assert time_exit_should_close(recent) is False
