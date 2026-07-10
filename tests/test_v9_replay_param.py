#!/usr/bin/env python3
"""test_v9_replay_param.py — Tests du replay paramétrique V9.

Couvre :
- _session_for_hour (asia/london/ny/off)
- _detect_coalitions (paires alignées)
- _detect_antagonisms (haute vs basse)
- _detect_pliure (variation pentes)
- _load_snapshots (filtre timeframes + sessions)
- _build_report (deltas baseline/override)
- CLI --threshold-override (mock DB)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from scripts.v9_replay_param import (
    _session_for_hour,
    _detect_coalitions,
    _detect_antagonisms,
    _detect_pliure,
    _build_report,
    SceneStats,
    main,
)


# ── _session_for_hour ──────────────────────────────────────────────────
@pytest.mark.parametrize("hour,expected", [
    (0, "asia"), (5, "asia"), (6, "asia"),
    (7, "london"), (10, "london"), (11, "london"),
    (12, "ny"), (15, "ny"), (16, "ny"),
    (17, "off"), (20, "off"), (21, "off"),
    (22, "asia"), (23, "asia"),
])
def test_session_for_hour(hour: int, expected: str) -> None:
    assert _session_for_hour(hour) == expected


# ── _detect_coalitions ────────────────────────────────────────────────
def test_detect_coalitions_basic() -> None:
    forces = {"USD": 60.0, "GBP": 62.0, "JPY": 40.0, "EUR": 55.0}
    # USD/GBP à 2 d'écart, GBP/EUR à 7, etc.
    coa = _detect_coalitions(forces, threshold=5.0)
    # Toutes paires à ≤ 5 d'écart — on normalise par sorted pour l'assert
    pairs = {tuple(sorted(p)) for p in coa}
    assert ("GBP", "USD") in pairs  # écart 2
    assert ("EUR", "USD") in pairs  # écart 5
    # écart 7 entre EUR et GBP > threshold 5 → PAS de coalition
    assert ("EUR", "GBP") not in pairs
    # JPY ne se coalise avec personne (≥15 d'écart min)
    assert all("JPY" not in p for p in pairs)


def test_detect_coalitions_empty() -> None:
    assert _detect_coalitions({}, 5.0) == []


def test_detect_coalitions_strict_threshold() -> None:
    forces = {"USD": 50.0, "GBP": 53.0}
    assert len(_detect_coalitions(forces, threshold=2.5)) == 0
    assert len(_detect_coalitions(forces, threshold=3.5)) == 1


# ── _detect_antagonisms ───────────────────────────────────────────────
def test_detect_antagonisms_basic() -> None:
    forces = {"USD": 80.0, "JPY": 30.0, "GBP": 55.0}
    # Écart max=80-30=50 ≥ 40 → antagonisme JPY/USD
    ant = _detect_antagonisms(forces, threshold=40.0)
    assert ("JPY", "USD") in ant


def test_detect_antagonisms_below_threshold() -> None:
    forces = {"USD": 55.0, "JPY": 50.0}
    # Écart 5 < 30 → aucun antagonisme
    assert _detect_antagonisms(forces, threshold=30.0) == []


def test_detect_antagonisms_picks_extremes() -> None:
    forces = {"USD": 90.0, "GBP": 60.0, "JPY": 30.0, "EUR": 50.0}
    ant = _detect_antagonisms(forces, threshold=50.0)
    # Max=USD 90, min=JPY 30 → écart 60 ≥ 50
    assert ("JPY", "USD") in ant


# ── _detect_pliure ────────────────────────────────────────────────────
def test_detect_pliure_insufficient_history() -> None:
    assert _detect_pliure([], 1.7) == 0
    assert _detect_pliure([{"force_usd": 50.0}], 1.7) == 0


def test_detect_pliure_no_pivot() -> None:
    history = [{"force_usd": 50.0}, {"force_usd": 51.0}, {"force_usd": 52.0}]
    # deltas constants (1.0) → variation 0 → pas de pliure
    assert _detect_pliure(history, threshold=0.5) == 0


def test_detect_pliure_detected() -> None:
    # deltas: +1, +10 → variation 9 ≥ 5 → 1 pliure
    history = [
        {"force_usd": 50.0},
        {"force_usd": 51.0},
        {"force_usd": 61.0},
    ]
    assert _detect_pliure(history, threshold=5.0) == 1


# ── _build_report ─────────────────────────────────────────────────────
def test_build_report_baseline_only() -> None:
    stats = SceneStats(n_scenes=100, n_with_coalition=50, n_coalitions_total=120)
    snapshots = [{"timestamp": "2026-07-09T10:00:00+00:00", "_session": "london"}]

    report = _build_report(
        snapshots, stats, None,
        5.38, 31.39, 1.7,
        None, None, None,
        _fake_args(),
    )
    assert report["baseline_stats"]["n_scenes"] == 100
    assert report["baseline_stats"]["pct_coalition"] == 50.0
    assert "override_stats" not in report
    assert "deltas" not in report


def test_build_report_with_override() -> None:
    base = SceneStats(n_scenes=100, n_with_coalition=80, n_coalitions_total=200)
    ov = SceneStats(n_scenes=100, n_with_coalition=90, n_coalitions_total=250)
    snapshots = []

    report = _build_report(
        snapshots, base, ov,
        5.38, 31.39, 1.7,
        3.0, 40.0, 2.5,
        _fake_args(),
    )
    assert report["override_stats"]["pct_coalition"] == 90.0
    assert report["deltas"]["delta_pct_coalition"] == 10.0
    assert report["deltas"]["delta_n_coalitions"] == 50


def test_build_report_zero_scenes_safe() -> None:
    """Pas de division par zéro si aucun snapshot."""
    stats = SceneStats()  # tout à 0
    report = _build_report(
        [], stats, None,
        5.38, 31.39, 1.7,
        None, None, None,
        _fake_args(),
    )
    assert report["baseline_stats"]["pct_coalition"] == 0.0
    assert report["baseline_stats"]["pct_antagonism"] == 0.0


# ── Helper ────────────────────────────────────────────────────────────
class _FakeArgs:
    limit = 100
    timeframes = ["M5", "M15"]
    sessions = None
    examples_per_stat = 3


def _fake_args() -> _FakeArgs:
    return _FakeArgs()


# ── CLI integration (DB mock) ─────────────────────────────────────────
def test_cli_runs_with_mock_db(tmp_path: Path, monkeypatch, capsys) -> None:
    """Test end-to-end avec DB temporaire."""
    db = tmp_path / "v9_forces.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            symbol TEXT NOT NULL,
            stale INTEGER NOT NULL,
            force_usd REAL, force_gbp REAL, force_eur REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL
        );
    """)
    # 3 snapshots synthétiques, M5, écart connu
    for i, t in enumerate([
        "2026-07-09T10:00:00+00:00",
        "2026-07-09T10:05:00+00:00",
        "2026-07-09T10:10:00+00:00",
    ]):
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"snap_{i}", t, "M5", "GBPUSD", 0, 60.0, 58.0, 55.0, 40.0,
             50.0, 52.0, 48.0, 70.0),
        )
    conn.commit()
    conn.close()

    # Monkeypatch DB_PATH
    from core.v9 import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "DB_PATH", db)
    # Aussi patcher db_schema.get_connection pour utiliser le bon path
    from core.v9 import db_schema
    monkeypatch.setattr(db_schema, "DB_PATH", db)

    # Écrire l'override AVANT l'appel main
    override_path = db.with_suffix(".json")
    override_path.write_text(
        json.dumps({"coalition_threshold": 3.0, "antagonism_threshold": 40.0, "pliure_threshold": 2.5})
    )

    rc = main([
        "--limit", "3",
        "--timeframes", "M5",
        "--threshold-override", str(override_path),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "V9 — REPLAY PARAMETRIQUE" in captured.out
    assert "Override : 3 scenes" in captured.out
    assert "Deltas" in captured.out
