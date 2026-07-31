"""tests/test_v9_mega_edge_l11_l13.py — Phase 9 motion CEO « EDGE FUND MAX ».

Validation L11 behavior qualification blacklist + L13 coalition HTF.
"""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_MEGA_EDGE_ENABLED", raising=False)


def _build_db_with_scenes_and_behaviors(db, snap_id, ts_iso,
                                         behavior_qualif=None,
                                         coalitions_json=None):
    """Construit DB minimale avec forces_snapshots, scenes, behaviors."""
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE forces_snapshots "
            "(snapshot_id TEXT PRIMARY KEY, timestamp TEXT)"
        )
        conn.execute(
            "CREATE TABLE regime_snapshots ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "regime_id TEXT, forces_snapshot_ref TEXT, "
            "symbol TEXT, timeframe TEXT, regime_type TEXT, "
            "vol_regime TEXT)"
        )
        conn.execute(
            "CREATE TABLE scenes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "scene_id TEXT, forces_snapshot_ref TEXT, "
            "coalitions_json TEXT)"
        )
        conn.execute(
            "CREATE TABLE behaviors ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "behavior_id TEXT, scene_id_ref TEXT, "
            "symbol TEXT, timeframe TEXT, qualification TEXT)"
        )
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?, ?)",
            (snap_id, ts_iso),
        )
        if coalitions_json is not None:
            conn.execute(
                "INSERT INTO scenes (scene_id, forces_snapshot_ref, "
                "coalitions_json) VALUES (?, ?, ?)",
                (f"scene-{snap_id}", snap_id, coalitions_json),
            )
        if behavior_qualif is not None:
            scene_id = f"scene-{snap_id}"
            conn.execute(
                "INSERT INTO behaviors (behavior_id, scene_id_ref, symbol, "
                "timeframe, qualification) VALUES (?, ?, ?, ?, ?)",
                (f"beh-{snap_id}", scene_id, "GBPUSD", "M5", behavior_qualif),
            )
        conn.commit()


def test_l11_blacklist_tension_behavior(tmp_path):
    """L11 — behavior tension → go=False."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    snap = "v9-snap-tension"
    ts = (datetime.utcnow().replace(hour=12, minute=0)).isoformat()
    _build_db_with_scenes_and_behaviors(
        db, snap, ts,
        behavior_qualif="tension",
        coalitions_json='{"M5": "x"}',  # has_M5 = lower_TF_only? No: D1 absent
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is False
    assert res["reason"] == "blacklist_behavior_qualification"
    assert res["behavior_qualif"] == "tension"


def test_l11_passes_high_quality_behavior(tmp_path):
    """L11 — behavior high_quality → go=True (pas dans blacklist)."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    snap = "v9-snap-hq"
    ts = (datetime.utcnow().replace(hour=12, minute=0)).isoformat()
    _build_db_with_scenes_and_behaviors(
        db, snap, ts,
        behavior_qualif="high_quality",
        coalitions_json='{"D1": "haussiere"}',
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True


def test_l11_no_behavior_passes(tmp_path):
    """L11 — pas de behavior en DB → go=True (neutre)."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    snap = "v9-snap-no-beh"
    ts = (datetime.utcnow().replace(hour=12, minute=0)).isoformat()
    _build_db_with_scenes_and_behaviors(db, snap, ts)  # rien
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True


def test_l13_blacklist_lower_tf_only_coalition(tmp_path):
    """L13 — coalition lower_TF_only (pas de D1/H4) → go=False."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    snap = "v9-snap-lowtf"
    ts = (datetime.utcnow().replace(hour=12, minute=0)).isoformat()
    _build_db_with_scenes_and_behaviors(
        db, snap, ts,
        coalitions_json='{"M5": "haussiere", "M15": "haussiere"}',
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is False
    assert res["reason"] == "blacklist_lower_tf_only_coalition"


def test_l13_mega_no_coalition_boost_x1_5(tmp_path):
    """L13 — no_coalition → go=True + sizing x1.5."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    snap = "v9-snap-no-coal"
    ts = (datetime.utcnow().replace(hour=12, minute=0)).isoformat()
    _build_db_with_scenes_and_behaviors(
        db, snap, ts,
        coalitions_json=None,  # NULL = no_coalition
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True
    assert "L13_no_coalition_mega_x1.5_sizing" in res["leviers"]
    assert res["sizing_multiplier"] >= 1.5


def test_l13_passes_with_d1_or_h4(tmp_path):
    """L13 — coalition has_D1_or_H4 → go=True."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    snap = "v9-snap-d1"
    ts = (datetime.utcnow().replace(hour=12, minute=0)).isoformat()
    _build_db_with_scenes_and_behaviors(
        db, snap, ts,
        coalitions_json='{"D1": "haussiere", "H4": "haussiere"}',
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True


def test_l14_blacklist_mardi(tmp_path):
    """L14 — mardi UTC → go=False pour GBPUSD haussiere."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    # Trouver le prochain mardi 12h UTC
    today = datetime.utcnow()
    days_ahead = (1 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    mardi = today + timedelta(days=days_ahead)
    mardi = mardi.replace(hour=12, minute=0, second=0, microsecond=0)
    snap = "v9-snap-mardi"
    _build_db_with_scenes_and_behaviors(
        db, snap, mardi.isoformat(),
        coalitions_json='{"D1": "haussiere"}',
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is False
    assert res["reason"] == "blacklist_dow_mardi"
    assert res["dow"] == "mardi"


def test_l14_passes_vendredi(tmp_path):
    """L14 — vendredi UTC → go=True (audit: MEGA WR 97.4%)."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    today = datetime.utcnow()
    days_ahead = (4 - today.weekday()) % 7  # 4 = vendredi
    if days_ahead == 0:
        days_ahead = 7
    vendredi = today + timedelta(days=days_ahead)
    vendredi = vendredi.replace(hour=12, minute=0, second=0, microsecond=0)
    snap = "v9-snap-vendredi"
    _build_db_with_scenes_and_behaviors(
        db, snap, vendredi.isoformat(),
        coalitions_json='{"D1": "haussiere"}',
    )
    res = mega_edge_evaluation(
        symbol="GBPUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True


def test_l14_does_not_apply_to_other_symbols(tmp_path):
    """L14 — mardi EURUSD → go=True (filter GBPUSD only)."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    db = tmp_path / "v9.db"
    today = datetime.utcnow()
    days_ahead = (1 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    mardi = today + timedelta(days=days_ahead)
    mardi = mardi.replace(hour=12, minute=0, second=0, microsecond=0)
    snap = "v9-snap-eur-mardi"
    _build_db_with_scenes_and_behaviors(
        db, snap, mardi.isoformat(),
        coalitions_json='{"D1": "haussiere"}',
    )
    res = mega_edge_evaluation(
        symbol="EURUSD", direction="haussiere",
        snapshot_id=snap,
        principes=["PRICE_LAG_AT_NODE_BIRTH"],
        db_path=db,
    )
    assert res["go"] is True  # EURUSD non filtre par L14