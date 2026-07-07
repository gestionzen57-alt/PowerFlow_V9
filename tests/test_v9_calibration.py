"""Tests — scripts/v9_calibration.py (calibration seuils, export, stats V9).

Couvre les fonctions pures (sans I/O) et les fonctions DB avec DB temporaire.
Aucun test ne touche data/v9_forces.db (toujours tmp_path/monkeypatch).

Fonctions testées :
- _percentile(values, pct) — p50/p95 d'une liste
- _force_amplitude(row) — amplitude max-min des 8 forces
- _pairwise_force_gaps(row) — écarts absolus entre toutes les paires
- _snapshot_intervals_ms_by_tf(rows) — intervalles réels par TF
- suggest_thresholds(forces_rows, conn) — suggestions P20/P80/P90/P95
- run_stats(conn) avec conn=None (DB absente)
- run_export(conn, "csv"/"json") avec conn=None (DB absente)
- table_exists, fetch_all_dicts, column_names (DB temporaire)
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_calibration  # noqa: E402


# ── _percentile ─────────────────────────────────────────────
def test_percentile_empty() -> None:
    assert v9_calibration._percentile([], 50) is None


def test_percentile_known_values() -> None:
    # P50 de [1..10] = 5.5, P95 proche de 9.55
    p50 = v9_calibration._percentile([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50)
    p95 = v9_calibration._percentile([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95)
    assert 5.0 <= p50 <= 6.0
    assert 9.0 <= p95 <= 10.0


# ── _force_amplitude ────────────────────────────────────────
def test_force_amplitude_returns_max_min() -> None:
    row = {f"force_{d}": float(v) for d, v in zip(
        ["usd", "gbp", "eur", "jpy", "cad", "chf", "aud", "nzd"],
        [10, 20, 30, 40, 50, 60, 70, 80]
    )}
    assert v9_calibration._force_amplitude(row) == 70.0  # 80-10


def test_force_amplitude_none_when_missing() -> None:
    assert v9_calibration._force_amplitude({}) is None


# ── _pairwise_force_gaps ────────────────────────────────────
def test_pairwise_force_gaps_8_pairs() -> None:
    # 8 devises → C(8,2) = 28 paires
    row = {f"force_{d}": float(v) for d, v in zip(
        ["usd", "gbp", "eur", "jpy", "cad", "chf", "aud", "nzd"],
        [0, 10, 20, 30, 40, 50, 60, 70]
    )}
    gaps = v9_calibration._pairwise_force_gaps(row)
    assert len(gaps) == 28
    assert min(gaps) == 10.0
    assert max(gaps) == 70.0


def test_pairwise_force_gaps_skips_missing() -> None:
    row = {"force_usd": 10.0, "force_gbp": 20.0}  # 2 devises → 1 paire
    gaps = v9_calibration._pairwise_force_gaps(row)
    assert gaps == [10.0]


# ── _snapshot_intervals_ms_by_tf ─────────────────────────────
def test_snapshot_intervals_groups_by_tf() -> None:
    rows = [
        {"timeframe": "M5", "bar_time": 1000},
        {"timeframe": "M5", "bar_time": 1300},  # 300s = 300000ms
        {"timeframe": "M5", "bar_time": 1600},  # 300s
        {"timeframe": "H1", "bar_time": 1000},
        {"timeframe": "H1", "bar_time": 4600},  # 3600s = 3 600 000ms
    ]
    intervals = v9_calibration._snapshot_intervals_ms_by_tf(rows)
    assert "M5" in intervals and "H1" in intervals
    assert intervals["M5"] == [300_000, 300_000]
    assert intervals["H1"] == [3_600_000]


def test_snapshot_intervals_filters_non_positive() -> None:
    # bar_time identique → intervalle 0, doit être filtré
    rows = [
        {"timeframe": "M5", "bar_time": 1000},
        {"timeframe": "M5", "bar_time": 1000},  # delta 0
    ]
    intervals = v9_calibration._snapshot_intervals_ms_by_tf(rows)
    assert intervals["M5"] == []


# ── suggest_thresholds ──────────────────────────────────────
def test_suggest_thresholds_returns_dict() -> None:
    rows = [
        {**{f"force_{d}": float(v) for d, v in zip(
            ["usd", "gbp", "eur", "jpy", "cad", "chf", "aud", "nzd"],
            [0, 10, 20, 30, 40, 50, 60, 70]
        )}, "bar_time": 1000, "timeframe": "M5"}
    ]
    result = v9_calibration.suggest_thresholds(rows, conn=None)
    # Clés en UPPERCASE (cf. code v9_calibration.suggest_thresholds)
    assert "COALITION_THRESHOLD" in result
    assert "ANTAGONISM_THRESHOLD" in result
    assert "PLIURE_THRESHOLD" in result
    assert "STALE_THRESHOLDS_MS" in result
    # P20 < P80 (gaps de 10 à 70)
    assert result["COALITION_THRESHOLD"] < result["ANTAGONISM_THRESHOLD"]


# ── run_stats avec conn=None ────────────────────────────────
def test_run_stats_no_db(capsys: pytest.CaptureFixture[str]) -> None:
    rc = v9_calibration.run_stats(None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Aucune donnée disponible" in out


# ── run_export avec conn=None (DB absente → 0 rows) ─────────
def test_run_export_csv_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(v9_calibration, "OUTPUT_DIR", tmp_path / "output")
    rc = v9_calibration.run_export(None, "csv")
    assert rc == 0
    # Fichiers créés (vides)
    out_dir = tmp_path / "output"
    assert out_dir.exists()
    csvs = list(out_dir.glob("*.csv"))
    assert len(csvs) == len(v9_calibration.TABLES)


def test_run_export_json_no_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_calibration, "OUTPUT_DIR", tmp_path / "output")
    rc = v9_calibration.run_export(None, "json")
    assert rc == 0
    out_dir = tmp_path / "output"
    jsons = list(out_dir.glob("*.json"))
    assert len(jsons) == len(v9_calibration.TABLES)


# ── DB temporaire : table_exists, fetch_all_dicts, column_names ──
def test_table_exists_and_fetch(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO foo VALUES (1, 'a'), (2, 'b')")
    conn.commit()
    assert v9_calibration.table_exists(conn, "foo") is True
    assert v9_calibration.table_exists(conn, "missing") is False
    rows = v9_calibration.fetch_all_dicts(conn, "foo")
    assert len(rows) == 2
    assert rows[0]["name"] == "a"
    cols = v9_calibration.column_names(conn, "foo")
    assert cols == ["id", "name"]
    conn.close()


def test_fetch_all_dicts_empty_table(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE bar (x INTEGER)")
    conn.commit()
    assert v9_calibration.fetch_all_dicts(conn, "bar") == []
    conn.close()