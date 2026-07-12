"""Tests — scripts/v9_batch_resolve_dynamic_full.py (Brief O1, 2026-07-12).

Couvre :
- _ensure_indices — crée idx_decisions_decision_id (le fix du bloqueur)
- _fetch_target_decisions — filtre strict resolution_strategy='TP_SL'
- simulate_all — asie/london/overlap -> DYNAMIC, new_york/after -> SKIPPED,
  no_data -> SKIPPED
- apply_results — UPDATE ensembliste, idempotent (re-run = no-op)
- build_report — agrégation par session
- main() — dry-run ne modifie rien, --apply exige --backup, apply de bout
  en bout met à jour la DB et est idempotent au 2e passage
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_batch_resolve_dynamic_full as brdf  # noqa: E402

BASE = datetime(2026, 7, 12, 0, 0, 0, tzinfo=timezone.utc)


def _mk_decision(conn, did, hour, direction, resolution_strategy="TP_SL"):
    ts = (BASE + timedelta(hours=hour)).isoformat()
    conn.execute(
        "INSERT INTO decisions "
        "(decision_id, timestamp, snapshot_id, symbol, timeframe, direction, "
        " action, resolution_strategy) "
        "VALUES (?, ?, ?, 'GBPUSD', 'M15', ?, 'preparer_entree', ?)",
        (did, ts, f"snap-{did}", direction, resolution_strategy),
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?, ?, 'GBPUSD', 'M15', 1.2500)",
        (f"snap-{did}", ts),
    )


def _mk_future_prices(conn, did, hour, mids):
    for i, mid in enumerate(mids):
        ts = (BASE + timedelta(hours=hour, minutes=15 * (i + 1))).isoformat()
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?, ?, 'GBPUSD', 'M15', ?)",
            (f"future-{did}-{i}", ts, mid),
        )


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "o1_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT,
            timestamp TEXT,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            action TEXT,
            is_win INTEGER,
            resolution_pips REAL,
            resolved_at TEXT,
            resolution_strategy TEXT DEFAULT 'TP_SL',
            resolution_details TEXT
        );
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            mid REAL
        );
        """
    )
    # D-ASIE : hour=2 (asie), TP_SL, prix futur haussier -> DYNAMIC win
    _mk_decision(conn, "D-ASIE", 2, "haussiere")
    _mk_future_prices(conn, "D-ASIE", 2, [1.2510, 1.2515, 1.2520, 1.2530])

    # D-LONDON : hour=8 (london), TP_SL, prix futur baissier -> DYNAMIC loss
    _mk_decision(conn, "D-LONDON", 8, "haussiere")
    _mk_future_prices(conn, "D-LONDON", 8, [1.2490, 1.2480, 1.2470, 1.2460])

    # D-NY : hour=18 (new_york), TP_SL -> doit être SKIPPED sans simulation
    _mk_decision(conn, "D-NY", 18, "haussiere")
    _mk_future_prices(conn, "D-NY", 18, [1.2600, 1.2700])  # ignoré (skip direct)

    # D-NODATA : hour=3 (asie), TP_SL, AUCUN prix futur -> SKIPPED no_data
    _mk_decision(conn, "D-NODATA", 3, "haussiere")

    # D-ALREADY-DYNAMIC : déjà résolue, ne doit JAMAIS être sélectionnée/touchée
    _mk_decision(conn, "D-ALREADY-DYNAMIC", 2, "haussiere", resolution_strategy="DYNAMIC")

    # D-ALREADY-SKIPPED : déjà résolue, ne doit jamais être touchée
    _mk_decision(conn, "D-ALREADY-SKIPPED", 18, "haussiere", resolution_strategy="SKIPPED")

    conn.commit()
    conn.close()
    return db


# ── _ensure_indices ────────────────────────────────────────────

def test_ensure_indices_creates_decision_id_index(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        brdf._ensure_indices(conn)
        names = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='decisions'"
            )
        }
        assert "idx_decisions_decision_id" in names
    finally:
        conn.close()


def test_ensure_indices_idempotent(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        brdf._ensure_indices(conn)
        brdf._ensure_indices(conn)  # 2e appel ne doit pas lever
    finally:
        conn.close()


# ── _fetch_target_decisions ────────────────────────────────────

def test_fetch_target_decisions_filters_tp_sl_only(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        ids = [r[0] for r in rows]
        assert set(ids) == {"D-ASIE", "D-LONDON", "D-NY", "D-NODATA"}
        assert "D-ALREADY-DYNAMIC" not in ids
        assert "D-ALREADY-SKIPPED" not in ids
    finally:
        conn.close()


# ── simulate_all ────────────────────────────────────────────────

def test_simulate_all_asie_session_produces_dynamic(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        entry_mids, future = brdf._load_price_context(conn, rows)
        results, per_session = brdf.simulate_all(rows, entry_mids, future)
    finally:
        conn.close()

    by_id = {r["decision_id"]: r for r in results}
    assert by_id["D-ASIE"]["resolution_strategy"] == "DYNAMIC"
    assert by_id["D-ASIE"]["is_win"] == 1
    assert "asie" in per_session


def test_simulate_all_new_york_always_skipped_no_simulation(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        entry_mids, future = brdf._load_price_context(conn, rows)
        results, _ = brdf.simulate_all(rows, entry_mids, future)
    finally:
        conn.close()

    by_id = {r["decision_id"]: r for r in results}
    assert by_id["D-NY"]["resolution_strategy"] == "SKIPPED"
    details = json.loads(by_id["D-NY"]["resolution_details"])
    assert details["exit_reason"] == "skipped_new_york"


def test_simulate_all_no_future_prices_skipped(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        entry_mids, future = brdf._load_price_context(conn, rows)
        results, _ = brdf.simulate_all(rows, entry_mids, future)
    finally:
        conn.close()

    by_id = {r["decision_id"]: r for r in results}
    assert by_id["D-NODATA"]["resolution_strategy"] == "SKIPPED"
    details = json.loads(by_id["D-NODATA"]["resolution_details"])
    assert details["exit_reason"] == "no_data"


# ── apply_results ───────────────────────────────────────────────

def test_apply_results_updates_only_matching_rows(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        entry_mids, future = brdf._load_price_context(conn, rows)
        results, _ = brdf.simulate_all(rows, entry_mids, future)
        applied = brdf.apply_results(conn, results)
        conn.commit()
        assert applied == len(rows) == 4

        remaining = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE resolution_strategy='TP_SL'"
        ).fetchone()[0]
        assert remaining == 0

        # Les décisions déjà résolues ne doivent PAS avoir été altérées
        already = conn.execute(
            "SELECT resolution_strategy FROM decisions WHERE decision_id='D-ALREADY-DYNAMIC'"
        ).fetchone()[0]
        assert already == "DYNAMIC"
    finally:
        conn.close()


def test_apply_results_idempotent_second_run_is_noop(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        entry_mids, future = brdf._load_price_context(conn, rows)
        results, _ = brdf.simulate_all(rows, entry_mids, future)
        brdf.apply_results(conn, results)
        conn.commit()

        # 2e run : plus aucune décision TP_SL -> rien à appliquer
        rows2 = brdf._fetch_target_decisions(conn)
        assert rows2 == []

        # Si on retente d'appliquer les MÊMES résultats (defense in depth),
        # le WHERE resolution_strategy='TP_SL' bloque toute ré-écriture.
        applied2 = brdf.apply_results(conn, results)
        conn.commit()
        assert applied2 == 0
    finally:
        conn.close()


# ── build_report ────────────────────────────────────────────────

def test_build_report_aggregates_by_session(temp_db: Path):
    conn = brdf._connect(temp_db)
    try:
        rows = brdf._fetch_target_decisions(conn)
        entry_mids, future = brdf._load_price_context(conn, rows)
        results, per_session = brdf.simulate_all(rows, entry_mids, future)
    finally:
        conn.close()

    report = brdf.build_report(results, per_session, applied=4)
    assert report["n_target_decisions"] == 4
    assert report["n_dynamic"] == 2  # D-ASIE, D-LONDON
    assert report["n_skipped"] == 2  # D-NY, D-NODATA
    assert "asie" in report["by_session"]
    assert "new_york" in report["by_session"]
    assert report["n_rows_applied"] == 4


# ── main() CLI ──────────────────────────────────────────────────

def test_main_dry_run_does_not_modify_db(temp_db: Path, tmp_path: Path):
    report_path = tmp_path / "report.json"
    rc = brdf.main(["--db", str(temp_db), "--dry-run", "--report", str(report_path)])
    assert rc == 0

    conn = sqlite3.connect(str(temp_db))
    remaining = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE resolution_strategy='TP_SL'"
    ).fetchone()[0]
    conn.close()
    assert remaining == 4  # rien n'a été modifié
    assert report_path.exists()


def test_main_apply_requires_backup(temp_db: Path):
    rc = brdf.main(["--db", str(temp_db), "--apply"])
    assert rc == 2


def test_main_apply_requires_existing_backup_md5(temp_db: Path, tmp_path: Path):
    empty_backup = tmp_path / "no_md5_here"
    empty_backup.mkdir()
    rc = brdf.main(["--db", str(temp_db), "--apply", "--backup", str(empty_backup)])
    assert rc == 2


def test_main_apply_end_to_end_updates_db_and_is_idempotent(temp_db: Path, tmp_path: Path):
    backup_dir = tmp_path / "backup"
    report_path = tmp_path / "report.json"

    rc = brdf.main([
        "--db", str(temp_db), "--make-backup", "--apply",
        "--backup", str(backup_dir), "--report", str(report_path),
    ])
    assert rc == 0
    assert (backup_dir / "md5_pre.txt").exists()
    assert (backup_dir / "MANIFEST.md").exists()

    conn = sqlite3.connect(str(temp_db))
    remaining = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE resolution_strategy='TP_SL'"
    ).fetchone()[0]
    conn.close()
    assert remaining == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["n_rows_applied"] == 4

    # 2e run --apply : idempotent, 0 décision cible restante
    rc2 = brdf.main([
        "--db", str(temp_db), "--apply",
        "--backup", str(backup_dir), "--report", str(report_path),
    ])
    assert rc2 == 0
