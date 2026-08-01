"""Tests v9_oos_freeze_test.py — Phase 105 motion CEO.

Couvre : backup_md5, freeze_db (sur DB temp), walk_forward_oos,
compare_metrics (verdict STABLE/DRIFT), append_jsonl, run_freeze_test
end-to-end sur DB in-memory.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.v9_oos_freeze_test import (  # noqa: E402
    DELTA_EXPECTANCY_THRESHOLD_PIPS,
    DELTA_WR_THRESHOLD_PTS,
    append_jsonl,
    backup_md5,
    compare_metrics,
    freeze_db,
    run_freeze_test,
    walk_forward_oos,
)

logging.getLogger("v9.oos_freeze_test").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_db(tmp_path: Path, n_trades: int = 20) -> Path:
    """Cree une mini-DB avec paper_trades + forces_snapshots."""
    db = tmp_path / "v9_forces.db"
    with sqlite3.connect(str(db)) as c:
        c.executescript("""
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            confiance INTEGER,
            principes_source TEXT,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            pips_simulated REAL NOT NULL,
            is_win INTEGER NOT NULL,
            risk_go_context TEXT,
            spread_pips REAL,
            pips_net_of_spread REAL
        );
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            symbol TEXT,
            timeframe TEXT
        );
        """)
        # Inserer n_trades repartis sur 60 jours
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        for i in range(n_trades):
            opened = base + timedelta(days=i * 3, hours=12)
            is_win = 1 if i % 4 != 0 else 0  # 75% WR
            pips = 20.0 if is_win else -8.0
            sid = f"SNAP_GBPUSD_{opened.strftime('%Y%m%d%H%M%S')}"
            c.execute(
                "INSERT INTO forces_snapshots (snapshot_id, timestamp, symbol, timeframe)"
                " VALUES (?, ?, 'GBPUSD', 'M1')",
                (sid, opened.isoformat()),
            )
            c.execute(
                """INSERT INTO paper_trades
                   (trade_id, snapshot_id, direction, confiance, opened_at,
                    pips_simulated, is_win)
                   VALUES (?, ?, 'haussiere', 75, ?, ?, ?)""",
                (f"T{i:04d}", sid, opened.isoformat(), pips, is_win),
            )
    return db


# ---------------------------------------------------------------------------
# Tests unitaires
# ---------------------------------------------------------------------------

def test_backup_md5_writes_files(tmp_path):
    db = _make_temp_db(tmp_path, n_trades=5)
    # Monkey-patch le BACKUP_DIR pour pointer vers tmp
    import scripts.v9_oos_freeze_test as mod
    original_dir = mod.BACKUP_DIR
    mod.BACKUP_DIR = tmp_path / "backups"
    try:
        sha = backup_md5(db, tag="test")
        assert isinstance(sha, str) and len(sha) == 64
        files = list((tmp_path / "backups").glob("v9_forces_test_*.sha256"))
        assert files, "fichier .sha256 absent"
        content = files[0].read_text()
        assert sha in content
    finally:
        mod.BACKUP_DIR = original_dir


def test_freeze_db_creates_copy(tmp_path):
    db = _make_temp_db(tmp_path, n_trades=5)
    freeze_dir = tmp_path / "freezes"
    import scripts.v9_oos_freeze_test as mod
    original = mod.FREEZE_DIR
    mod.FREEZE_DIR = freeze_dir
    try:
        fpath, t_freeze, meta = freeze_db(db)
        assert fpath is not None
        assert fpath.exists()
        assert fpath.stat().st_size > 0
        assert meta["method"] == "vacuum_into"
        # Verifier que la frozen DB contient les memes rows
        with sqlite3.connect(str(fpath)) as c:
            n = c.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        assert n == 5
        # Verifier format t_freeze
        datetime.fromisoformat(t_freeze.replace("Z", "+00:00"))
    finally:
        mod.FREEZE_DIR = original


def test_freeze_db_corrupt_returns_none(tmp_path, monkeypatch):
    """DB corrompue → freeze_db retourne None + meta.warning renseigne."""
    db = _make_temp_db(tmp_path, n_trades=5)
    import scripts.v9_oos_freeze_test as mod
    freeze_dir = tmp_path / "freezes"
    monkeypatch.setattr(mod, "FREEZE_DIR", freeze_dir)

    # Forcer quick_check a lever DatabaseError : wrapper de connexion
    real_connect = mod.sqlite3.connect

    class WrappedConn:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, *a, **kw):
            if "quick_check" in sql:
                raise mod.sqlite3.DatabaseError("database disk image is malformed")
            return self._real.execute(sql, *a, **kw)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return self._real.__exit__(*a)

    def wrapper_connect(*args, **kwargs):
        return WrappedConn(real_connect(*args, **kwargs))

    monkeypatch.setattr(mod.sqlite3, "connect", wrapper_connect)

    fpath, t_freeze, meta = freeze_db(db, freeze_dir=freeze_dir)
    assert fpath is None
    assert meta["warning"] is not None
    assert "PRAGMA quick_check failed" in meta["warning"]


def test_run_freeze_test_degraded_on_corrupt_db(tmp_path, monkeypatch):
    """DB corrompue → verdict DEGRADED + exit_code=1 + frozen.skipped."""
    db = _make_temp_db(tmp_path, n_trades=10)
    import scripts.v9_oos_freeze_test as mod
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(mod, "FREEZE_DIR", tmp_path / "freezes")
    monkeypatch.setattr(mod, "FREEZE_LOG_JSONL", tmp_path / "log.jsonl")
    # Forcer freeze_db a echouer
    monkeypatch.setattr(mod, "freeze_db",
                        lambda db_path, freeze_dir=None: (None, "2026-08-01T00:00:00+00:00",
                                                          {"method": None, "size_mb": 0,
                                                           "elapsed_s": 0.0,
                                                           "warning": "DB malformee"}))
    monkeypatch.setattr(mod, "walk_forward_oos",
                        lambda *a, **kw: {"windows": [], "summary": {
                            "wr_avg": 70.0, "expectancy_avg": 0.5,
                            "brier_avg": 0.05, "n_total": 10,
                            "wins_total": 7, "total_pips": 5.0,
                            "n_windows_passed_wr70": 1,
                        }})
    rep = run_freeze_test(db_path=db, skip_backup=True)
    assert rep["comparison"]["verdict"] == "DEGRADED"
    assert rep["exit_code"] == 1
    assert rep["frozen"]["skipped"] == "freeze_failed"
    # Log JSONL doit avoir freeze_warning renseigne
    log_lines = (tmp_path / "log.jsonl").read_text(encoding="utf-8").strip().split("\n")
    rec = json.loads(log_lines[0])
    assert rec["freeze_warning"] == "DB malformee"


def test_walk_forward_oos_returns_structure(tmp_path):
    db = _make_temp_db(tmp_path, n_trades=10)
    as_of = "2026-08-01T00:00:00+00:00"
    res = walk_forward_oos(
        db, as_of_iso=as_of, n_windows=2, window_days=10, offset_days=3,
    )
    assert "windows" in res and "summary" in res
    assert len(res["windows"]) == 2
    s = res["summary"]
    assert s["n_total"] >= 0
    assert "wr_avg" in s and "expectancy_avg" in s


def test_walk_forward_oos_handles_missing_db(tmp_path):
    res = walk_forward_oos(tmp_path / "no.db", as_of_iso="2026-08-01T00:00:00+00:00")
    assert res == {"windows": [], "summary": {}}


def test_compare_metrics_stable():
    live = {"summary": {"wr_avg": 75.0, "expectancy_avg": 1.0, "brier_avg": 0.05,
                         "n_total": 50, "wins_total": 37, "total_pips": 50.0,
                         "n_windows_passed_wr70": 3}}
    frozen = {"summary": {"wr_avg": 73.0, "expectancy_avg": 0.5, "brier_avg": 0.06,
                           "n_total": 50, "wins_total": 36, "total_pips": 25.0,
                           "n_windows_passed_wr70": 3}}
    cmp = compare_metrics(live, frozen, t_freeze="2026-08-01T00:00:00+00:00")
    assert cmp["verdict"] == "STABLE"
    assert cmp["delta_wr_pts"] == pytest.approx(2.0, abs=0.01)
    assert cmp["delta_expectancy_pips"] == pytest.approx(0.5, abs=0.01)


def test_compare_metrics_drift_wr():
    live = {"summary": {"wr_avg": 80.0, "expectancy_avg": 1.0, "brier_avg": 0.05}}
    frozen = {"summary": {"wr_avg": 70.0, "expectancy_avg": 1.0, "brier_avg": 0.05}}
    cmp = compare_metrics(live, frozen, t_freeze="2026-08-01T00:00:00+00:00")
    assert cmp["verdict"] == "DRIFT"
    assert any("delta_wr" in r for r in cmp["reasons"])


def test_compare_metrics_drift_expectancy():
    live = {"summary": {"wr_avg": 75.0, "expectancy_avg": 2.5, "brier_avg": 0.05}}
    frozen = {"summary": {"wr_avg": 75.0, "expectancy_avg": 0.5, "brier_avg": 0.05}}
    cmp = compare_metrics(live, frozen, t_freeze="2026-08-01T00:00:00+00:00")
    assert cmp["verdict"] == "DRIFT"
    assert any("delta_expectancy" in r for r in cmp["reasons"])


def test_append_jsonl_creates_file(tmp_path):
    log = tmp_path / "log.jsonl"
    append_jsonl(log, {"verdict": "STABLE", "delta_wr_pts": 1.5})
    append_jsonl(log, {"verdict": "DRIFT", "delta_wr_pts": 6.0})
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    rec1 = json.loads(lines[0])
    assert rec1["verdict"] == "STABLE"


def test_run_freeze_test_missing_db(tmp_path):
    rep = run_freeze_test(
        db_path=tmp_path / "nope.db",
        skip_backup=True,
    )
    assert rep["verdict"] == "ERROR"
    assert rep["exit_code"] == 4


def test_run_freeze_test_end_to_end_stable(tmp_path, monkeypatch):
    """End-to-end : DB temp + skip_backup, on force le verdict STABLE via mock."""
    db = _make_temp_db(tmp_path, n_trades=30)
    # Forcer BACKUP_DIR/FREEZE_DIR vers tmp pour ne pas polluer le repo
    import scripts.v9_oos_freeze_test as mod
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(mod, "FREEZE_DIR", tmp_path / "freezes")
    monkeypatch.setattr(mod, "FREEZE_LOG_JSONL", tmp_path / "log.jsonl")

    # Mock walk_forward_oos pour retourner les memes valeurs des deux cotes
    def fake_wf(db_path, as_of_iso, n_windows, window_days, offset_days):
        return {"windows": [], "summary": {
            "n_total": 30, "wins_total": 22, "wr_avg": 73.3,
            "total_pips": 150.0, "expectancy_avg": 5.0,
            "brier_avg": 0.05, "n_windows_passed_wr70": 3,
        }}
    monkeypatch.setattr(mod, "walk_forward_oos", fake_wf)

    rep = run_freeze_test(db_path=db, skip_backup=True)
    assert rep["comparison"]["verdict"] == "STABLE"
    assert rep["exit_code"] == 0
    # Log JSONL doit contenir une ligne
    log_lines = (tmp_path / "log.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(log_lines) == 1


def test_run_freeze_test_end_to_end_drift(tmp_path, monkeypatch):
    db = _make_temp_db(tmp_path, n_trades=30)
    import scripts.v9_oos_freeze_test as mod
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(mod, "FREEZE_DIR", tmp_path / "freezes")
    monkeypatch.setattr(mod, "FREEZE_LOG_JSONL", tmp_path / "log.jsonl")

    # Simuler un drift : frozen WR=60, live WR=80 → delta=20pts > seuil
    counter = {"n": 0}

    def fake_wf(db_path, as_of_iso, n_windows, window_days, offset_days):
        counter["n"] += 1
        if counter["n"] == 1:
            # live
            return {"summary": {"wr_avg": 80.0, "expectancy_avg": 6.0,
                                "brier_avg": 0.04, "n_total": 30,
                                "wins_total": 24, "total_pips": 180.0,
                                "n_windows_passed_wr70": 3}}
        return {"summary": {"wr_avg": 60.0, "expectancy_avg": 1.0,
                            "brier_avg": 0.10, "n_total": 30,
                            "wins_total": 18, "total_pips": 30.0,
                            "n_windows_passed_wr70": 0}}

    monkeypatch.setattr(mod, "walk_forward_oos", fake_wf)
    rep = run_freeze_test(db_path=db, skip_backup=True)
    assert rep["comparison"]["verdict"] == "DRIFT"
    assert rep["exit_code"] == 1
    assert abs(rep["comparison"]["delta_wr_pts"] - 20.0) < 0.01


def test_thresholds_constants():
    """Les seuils CEO sont explicites et documentes."""
    assert DELTA_WR_THRESHOLD_PTS == 5.0
    assert DELTA_EXPECTANCY_THRESHOLD_PIPS == 1.0


def test_schema_version_present(tmp_path, monkeypatch):
    """Le rapport porte un schema_version pour evolutivite."""
    db = _make_temp_db(tmp_path, n_trades=10)
    import scripts.v9_oos_freeze_test as mod
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(mod, "FREEZE_DIR", tmp_path / "freezes")
    monkeypatch.setattr(mod, "FREEZE_LOG_JSONL", tmp_path / "log.jsonl")
    monkeypatch.setattr(mod, "walk_forward_oos",
                        lambda *a, **kw: {"windows": [], "summary": {
                            "wr_avg": 70.0, "expectancy_avg": 0.5,
                            "brier_avg": 0.05, "n_total": 10,
                            "wins_total": 7, "total_pips": 5.0,
                            "n_windows_passed_wr70": 1,
                        }})
    rep = run_freeze_test(db_path=db, skip_backup=True)
    assert rep["schema_version"] == "1.0"
    assert rep["phase"] == "105"
