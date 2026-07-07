"""Tests adaptive_thresholds — Sprint Søn 2026-07-07 CEO quant."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.v9 import adaptive_thresholds
from core.v9.config import (
    ANTAGONISM_THRESHOLD,
    REPLAY_MIN_CAS,
    SIMILARITY_THRESHOLD,
)


def test_replay_min_cas_zero_returns_one():
    """Le paradoxe BOOT (replay_count=0 mais REPLAY_MIN_CAS=3) doit être levé."""
    assert adaptive_thresholds.compute_replay_min_cas(0, 0) == 1


def test_replay_min_cas_low_returns_one():
    assert adaptive_thresholds.compute_replay_min_cas(2, 1) == 1
    assert adaptive_thresholds.compute_replay_min_cas(2, 0) == 1


def test_replay_min_cas_mid_returns_two():
    assert adaptive_thresholds.compute_replay_min_cas(5, 3) == 2
    assert adaptive_thresholds.compute_replay_min_cas(9, 5) == 2


def test_replay_min_cas_high_returns_three():
    assert adaptive_thresholds.compute_replay_min_cas(15, 10) == 3
    assert adaptive_thresholds.compute_replay_min_cas(50, 30) == 3


def test_antagonism_threshold_below_5_returns_current():
    """Garde-fou règle 25 — pas d'invention si < 5 observations."""
    assert adaptive_thresholds.compute_antagonism_threshold([1.0, 2.0, 3.0]) == ANTAGONISM_THRESHOLD
    assert adaptive_thresholds.compute_antagonism_threshold([]) == ANTAGONISM_THRESHOLD


def test_antagonism_threshold_quantile_75():
    obs = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    val = adaptive_thresholds.compute_antagonism_threshold(obs, target_quantile=0.75)
    # P75 sur 10 valeurs triées = idx int(7.5) = 7 → sorted[7] = 50
    assert val == 50.0


def test_similarity_threshold_below_10_returns_current():
    assert adaptive_thresholds.compute_similarity_threshold([0.5, 0.6, 0.7]) == SIMILARITY_THRESHOLD


def test_similarity_threshold_clamped_to_range():
    """Le seuil proposé doit rester dans [0.5, 0.9] (évite valeurs absurdes)."""
    obs = [0.1] * 50  # très faibles
    assert adaptive_thresholds.compute_similarity_threshold(obs) >= 0.5
    obs_high = [0.99] * 50  # très hautes
    assert adaptive_thresholds.compute_similarity_threshold(obs_high) <= 0.9


def test_propose_thresholds_diff_returns_valid_structure(tmp_path):
    """propose_thresholds_diff doit retourner la structure attendue."""
    db_file = tmp_path / "test.db"
    import sqlite3
    con = sqlite3.connect(str(db_file))
    con.close()  # crée le fichier vide
    result = adaptive_thresholds.propose_thresholds_diff(db_path=db_file)
    assert "current" in result
    assert "proposed" in result
    assert "sample_size" in result
    assert "ready_to_apply" in result
    assert "rationale" in result
    assert "REPLAY_MIN_CAS" in result["current"]


def test_propose_thresholds_diff_handles_missing_db():
    """DB absente → ready_to_apply=False, pas de crash."""
    nonexistent = Path("Z:/this/does/not/exist/db.db")
    result = adaptive_thresholds.propose_thresholds_diff(db_path=nonexistent)
    assert result["ready_to_apply"] is False
    # Avec 0 décisions résolues, REPLAY_MIN_CAS proposé doit être 1 (anti-paradoxe)
    # mais ready_to_apply reste False (n<5 = pas assez d'historique)
    assert result["proposed"]["REPLAY_MIN_CAS"] == 1


def test_propose_thresholds_diff_ready_true_with_enough_data(tmp_path):
    """Si la DB a ≥ 5 décisions résolues et qu'un seuil diffère, ready_to_apply=True."""
    db_file = tmp_path / "test_ready.db"
    import sqlite3
    con = sqlite3.connect(str(db_file))
    con.executescript("""
        CREATE TABLE decisions (
            is_win INTEGER, direction TEXT
        );
        INSERT INTO decisions VALUES (1, 'haussiere');
        INSERT INTO decisions VALUES (1, 'haussiere');
        INSERT INTO decisions VALUES (0, 'haussiere');
        INSERT INTO decisions VALUES (1, 'baissiere');
        INSERT INTO decisions VALUES (1, 'haussiere');
        INSERT INTO decisions VALUES (0, 'baissiere');
        INSERT INTO decisions VALUES (1, 'haussiere');
        INSERT INTO decisions VALUES (1, 'baissiere');
        INSERT INTO decisions VALUES (0, 'baissiere');
    """)
    con.commit()
    con.close()
    result = adaptive_thresholds.propose_thresholds_diff(db_path=db_file)
    # n=9 résolues, REPLAY_MIN_CAS adaptatif = 2 (palier 3<=n<10), gel V8 = 3 → diff
    assert result["ready_to_apply"] is True
    assert result["proposed"]["REPLAY_MIN_CAS"] == 2
    assert result["current"]["REPLAY_MIN_CAS"] == REPLAY_MIN_CAS


def test_propose_thresholds_diff_antagonism_with_live_data(tmp_path):
    """Si ≥5 antagonismes observés en DB, le seuil proposé peut s'écarter du gel."""
    db_file = tmp_path / "test_antag.db"
    import sqlite3
    con = sqlite3.connect(str(db_file))
    con.executescript(f"""
        CREATE TABLE scenes (
            antagonismes_json TEXT
        );
        INSERT INTO scenes VALUES ('[{{"intensite": 35.5}}]');
        INSERT INTO scenes VALUES ('[{{"intensite": 40.0}}]');
        INSERT INTO scenes VALUES ('[{{"intensite": 45.0}}]');
        INSERT INTO scenes VALUES ('[{{"intensite": 50.0}}]');
        INSERT INTO scenes VALUES ('[{{"intensite": 55.0}}]');
        INSERT INTO scenes VALUES ('[{{"intensite": 60.0}}]');
        INSERT INTO scenes VALUES ('[{{"intensite": 65.0}}]');
    """)
    con.commit()
    con.close()
    result = adaptive_thresholds.propose_thresholds_diff(db_path=db_file)
    # P75 sur 7 valeurs triées [35.5, 40, 45, 50, 55, 60, 65] = idx int(7*0.75)=5 → 60.0
    assert result["proposed"]["ANTAGONISM_THRESHOLD"] == 60.0
    assert result["proposed"]["ANTAGONISM_THRESHOLD"] != ANTAGONISM_THRESHOLD
