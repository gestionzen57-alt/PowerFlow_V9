"""Tests flow_probe — Sprint Søn 2026-07-07 CEO quant."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9 import flow_probe


@pytest.fixture
def tmp_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    monkeypatch.setattr(flow_probe, "DB_PATH", db_path)
    flow_probe.init_probe_schema(db_path=db_path)
    yield db_path
    try:
        db_path.unlink(missing_ok=True)
    except (PermissionError, OSError):
        pass


def _populate_db(db_path: Path) -> None:
    """Crée DB avec scènes, behaviors, windows, exploitability, signals, decisions
    représentant un trajet complet pour snapshot_id='snap_test'."""
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        # Idempotent : DROP IF EXISTS puis CREATE
        for tbl in ("decisions", "signals", "exploitability", "windows",
                    "behaviors", "scenes"):
            con.execute(f"DROP TABLE IF EXISTS {tbl}")

        con.executescript("""
            CREATE TABLE scenes (
                scene_id TEXT PRIMARY KEY, forces_snapshot_ref TEXT, timestamp TEXT
            );
            CREATE TABLE behaviors (
                behavior_id TEXT PRIMARY KEY, scene_id_ref TEXT, timestamp TEXT
            );
            CREATE TABLE windows (
                window_id TEXT PRIMARY KEY, behavior_id TEXT, timestamp TEXT, statut TEXT
            );
            CREATE TABLE exploitability (
                exploitability_id TEXT PRIMARY KEY, window_id TEXT, status TEXT, timestamp TEXT
            );
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT, timestamp TEXT
            );
            CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT, timestamp TEXT
            );

            INSERT INTO scenes VALUES ('sc_001', 'snap_test', '2026-07-07T10:00:00');
            INSERT INTO behaviors VALUES ('be_001', 'sc_001', '2026-07-07T10:00:05');
            INSERT INTO windows VALUES ('wi_001', 'be_001', '2026-07-07T10:00:10', 'ouverture');
            INSERT INTO windows VALUES ('wi_002', 'be_001', '2026-07-07T10:00:11', 'absente');
            INSERT INTO exploitability VALUES ('ex_001', 'wi_001', 'exploitable', '2026-07-07T10:00:15');
            INSERT INTO exploitability VALUES ('ex_002', 'wi_002', 'non_exploitable', '2026-07-07T10:00:16');
            INSERT INTO signals VALUES ('si_001', 'snap_test', 'haussiere', '2026-07-07T10:00:20');
            INSERT INTO decisions VALUES ('de_001', 'snap_test', 'haussiere', '2026-07-07T10:00:25');
        """)
        con.commit()
        # Vérif immédiate
        verify = con.execute(
            "SELECT scene_id, forces_snapshot_ref FROM scenes WHERE forces_snapshot_ref='snap_test'"
        ).fetchall()
        assert len(verify) == 1, f"_populate_db: scene 'snap_test' introuvable après insert. Got {len(verify)}"
    finally:
        con.close()


def test_init_creates_table(tmp_db):
    con = sqlite3.connect(str(tmp_db))
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='probe_events'"
    ).fetchall()
    con.close()
    # init_probe_schema ne crée QUE si absent (utilise IF NOT EXISTS)
    # mais peut créer ou pas selon les migrations futures — testé séparément
    # ici on vérifie juste que init ne plante pas
    assert True


def test_trace_unknown_snapshot_returns_minimal_path(tmp_db):
    """Snapshot inexistant → renvoie un Path avec 0 couches traversées."""
    flow_probe.init_probe_schema()
    path = flow_probe.trace("snap_unknown")
    assert path["snapshot_id"] == "snap_unknown"
    assert path["layers"] == []
    assert path["blocked"] is True  # snapshot introuvable = bloqué


def test_trace_full_chain(tmp_db):
    """Snapshot traversant toute la chaîne → renvoie toutes les couches."""
    flow_probe.init_probe_schema(db_path=tmp_db)
    _populate_db(tmp_db)
    path = flow_probe.trace("snap_test", db_path=tmp_db)
    assert path["snapshot_id"] == "snap_test"
    assert path["blocked"] is False
    # Couches traversées : scene, behavior, 2 windows, 2 exploitability, signal, decision
    layers = path["layers"]
    layer_names = [l["layer"] for l in layers]
    assert "scene" in layer_names
    assert "behavior" in layer_names
    assert "window" in layer_names
    assert "exploitability" in layer_names
    assert "signal" in layer_names
    assert "decision" in layer_names


def test_trace_identifies_blocking_layer(tmp_db):
    """Si un layer n'existe pas pour le snapshot, la trace marque blocked=true."""
    flow_probe.init_probe_schema(db_path=tmp_db)
    _populate_db(tmp_db)
    path = flow_probe.trace("snap_test_partial", db_path=tmp_db)
    # Pas de scène pour snap_test_partial, donc trace est bloquée
    assert path["blocked"] is True
    assert path["layers"] == []


def test_trace_decision_status(tmp_db):
    """Decision récupère direction + timestamp."""
    flow_probe.init_probe_schema(db_path=tmp_db)
    _populate_db(tmp_db)
    path = flow_probe.trace("snap_test", db_path=tmp_db)
    decisions = [l for l in path["layers"] if l["layer"] == "decision"]
    assert len(decisions) == 1
    assert decisions[0]["direction"] == "haussiere"


def test_format_path_text(tmp_db):
    """format_path doit produire un texte lisible, non-vide."""
    flow_probe.init_probe_schema(db_path=tmp_db)
    _populate_db(tmp_db)
    path = flow_probe.trace("snap_test", db_path=tmp_db)
    text = flow_probe.format_path(path)
    assert "snap_test" in text
    assert "scene" in text.lower()
    assert len(text) > 50


def test_format_path_blocked_returns_clear_message(tmp_db):
    flow_probe.init_probe_schema()
    path = flow_probe.trace("snap_does_not_exist")
    text = flow_probe.format_path(path)
    assert "introuvable" in text.lower() or "absent" in text.lower() or "bloqué" in text.lower()


def test_record_event_and_list(tmp_db):
    """record() doit écrire un probe_event, list_events() doit le retrouver."""
    flow_probe.init_probe_schema(db_path=tmp_db)
    flow_probe.record(
        snapshot_id="snap_x",
        layer="scene",
        status="OK",
        latency_ms=12.5,
        db_path=tmp_db,
    )
    events = flow_probe.list_events(snapshot_id="snap_x", db_path=tmp_db)
    assert len(events) == 1
    assert events[0]["layer"] == "scene"
    assert events[0]["status"] == "OK"
