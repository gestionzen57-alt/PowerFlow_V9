"""Tests — MODE LECTURE V9 (core/v9/memory_query.py + scripts/v9_read.py)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import memory_query  # noqa: E402
from core.v9.db_schema import init_all_dbs  # noqa: E402
from scripts import v9_read  # noqa: E402


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "read_test.db"
    init_all_dbs(db)
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO scenes (scene_id, timestamp, forces_snapshot_ref, coalitions_json, "
        "cinematique_json, zone_json, contexte_temporel_json, stale) VALUES (?,?,?,?,?,?,?,0)",
        ("scene-1", now, "snap-1",
         json.dumps([{"devises_alignees": ["USD", "EUR"], "intensite_alignement": 10.0}]),
         json.dumps({"angle": 12.0}), json.dumps({"structure": "zone d'extension"}),
         json.dumps({"session": "Londres"})),
    )
    conn.execute(
        "INSERT INTO behaviors (behavior_id, scene_id_ref, qualification, symbol, timeframe, "
        "confiance_qualification) VALUES (?,?,?,?,?,?)",
        ("behavior-1", "scene-1", "recroisement", "EURUSD", "M15", 70),
    )
    conn.execute(
        "INSERT INTO windows (window_id, behavior_id, statut, niveau_confiance) VALUES (?,?,?,?)",
        ("window-1", "behavior-1", "ouverte", 65),
    )
    conn.execute(
        "INSERT INTO regime_snapshots (forces_snapshot_ref, currency, regime_type) VALUES (?,?,?)",
        ("snap-1", "EUR", "CASSURE"),
    )
    conn.execute(
        "INSERT INTO decisions (decision_id, scene_id, symbol, timeframe, is_win) VALUES (?,?,?,?,?)",
        ("decision-1", "scene-1", "EURUSD", "M15", 1),
    )
    conn.execute(
        "INSERT INTO principle_evaluations (principle_id, snapshot_id, timestamp, triggered, "
        "direction, confidence) VALUES (?,?,?,1,?,?)",
        ("ZONE_RETEST", "snap-1", now, "haussiere", 80),
    )
    conn.commit()
    conn.close()
    return db


def test_get_current_state_returns_dict(seeded_db: Path) -> None:
    state = memory_query.get_current_state(db_path=seeded_db)
    assert isinstance(state, dict)
    assert state["scene"]["scene_id"] == "scene-1"
    assert memory_query.get_current_state(db_path=Path("no_such.db")) == {}


def test_find_similar_scenes_returns_list(seeded_db: Path) -> None:
    similar = memory_query.find_similar_scenes("scene-1", db_path=seeded_db)
    assert isinstance(similar, list)
    assert memory_query.find_similar_scenes("missing", db_path=seeded_db) == []


def test_get_yaml_triggers_history_returns_dict(seeded_db: Path) -> None:
    hist = memory_query.get_yaml_triggers_history(db_path=seeded_db)
    assert isinstance(hist, dict)
    assert hist["per_principle"]["ZONE_RETEST"]["count"] == 1
    assert "ZONE_RETEST" in hist["top5"]


def test_get_market_narrative_returns_string(seeded_db: Path) -> None:
    narrative = memory_query.get_market_narrative(db_path=seeded_db)
    assert isinstance(narrative, str)
    assert "Marché" in narrative
    assert "Mémoire" in narrative


def test_read_cli_deep_exits_zero(seeded_db: Path, capsys: pytest.CaptureFixture) -> None:
    rc = v9_read.main(["--deep", "--db", str(seeded_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "ÉTAT COURANT" in captured.out
    assert "scene-1" in captured.out


def test_read_cli_scene_handles_missing(seeded_db: Path, capsys: pytest.CaptureFixture) -> None:
    rc = v9_read.main(["--scene", "scene-inconnue", "--db", str(seeded_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Aucune scène" in captured.out

    rc_ok = v9_read.main(["--scene", "scene-1", "--db", str(seeded_db)])
    assert rc_ok == 0

    rc_no_db = v9_read.main(["--scene", "scene-1", "--db", str(Path("no_such.db"))])
    captured = capsys.readouterr()
    assert rc_no_db == 0
    assert "Aucune scène" in captured.out


def test_read_cli_yaml_handles_missing(seeded_db: Path, capsys: pytest.CaptureFixture) -> None:
    rc = v9_read.main(["--yaml", "PRINCIPE_INEXISTANT", "--db", str(seeded_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "aucun déclenchement" in captured.out

    rc_ok = v9_read.main(["--yaml", "ZONE_RETEST", "--db", str(seeded_db)])
    captured_ok = capsys.readouterr()
    assert rc_ok == 0
    assert "ZONE_RETEST" in captured_ok.out


def test_read_cli_watch_loop_breaks_on_keyboard(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def _raise_after_first(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(v9_read, "clear_screen", lambda: None)
    monkeypatch.setattr(v9_read.time, "sleep", _raise_after_first)
    rc = v9_read.main(["--watch", "--db", str(seeded_db)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Marché" in captured.out
