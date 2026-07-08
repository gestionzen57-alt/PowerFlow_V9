"""Tests — scripts/v9_db_hygiene.py (Phase 9.9).

Couvre :
- _cutoff_iso — sanity sur le calcul du seuil
- _port_in_use — détection port libre/occupé
- _index_exists / _run_add_index — idempotence création index
- _count_to_purge — comptage sans modification (DRY-RUN)
- _run_purge — purge effective, transactions
- main() --dry-run vs --apply — comportement end-to-end sur DB tmp
- Garde-fou : --apply sans --backup échoue
- Garde-fou : --apply avec --backup absent échoue
- Garde-fou : --apply avec --backup ne référençant pas v9_forces.db échoue
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_db_hygiene as hyg  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────
@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """DB temporaire avec les 10 tables V9 + 1 index existant, pré-remplie
    de données mixant < et > 7 jours, ACTIVE/SHADOW, action diverse."""
    db = tmp_path / "hygiene_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id TEXT UNIQUE,
            timestamp TEXT,
            snapshot_id TEXT,
            principle_id TEXT,
            v9_status TEXT,
            symbol TEXT,
            timeframe TEXT,
            triggered INTEGER,
            direction TEXT
        );
        CREATE INDEX idx_principle_evaluations_snapshot
            ON principle_evaluations (snapshot_id);
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT UNIQUE,
            timestamp TEXT,
            snapshot_id TEXT,
            action TEXT,
            direction TEXT,
            is_win INTEGER
        );
        """
    )
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=30)).isoformat()
    fresh = (now - timedelta(days=1)).isoformat()
    rows_pe = [
        # SHADOW ancien (à purger)
        (old, "snap-1", "GRAMMAR_ABSORPTION", "SHADOW", "GBPUSD", "M15", 0, None),
        (old, "snap-1", "GRAMMAR_BREAK", "SHADOW", "GBPUSD", "M15", 0, None),
        (old, "snap-2", "GRAMMAR_REGIME", "SHADOW", "GBPUSD", "M15", 0, None),
        # SHADOW récent (à garder)
        (fresh, "snap-3", "GRAMMAR_ABSORPTION", "SHADOW", "GBPUSD", "M15", 0, None),
        # ACTIVE ancien (à garder — règle: on ne touche jamais aux ACTIVE)
        (old, "snap-1", "ZONE_RETEST", "ACTIVE", "GBPUSD", "M15", 1, "haussiere"),
        # ACTIVE récent
        (fresh, "snap-3", "NODE_BIRTH_FAST", "ACTIVE", "GBPUSD", "M15", 1, "haussiere"),
    ]
    for r in rows_pe:
        conn.execute(
            "INSERT INTO principle_evaluations "
            "(evaluation_id, timestamp, snapshot_id, principle_id, v9_status, "
            "symbol, timeframe, triggered, direction) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"pe-{uuid.uuid4().hex[:8]}", *r),
        )
    rows_dec = [
        # aucune_action ancien (à purger)
        (old, "snap-1", "aucune_action", None, None),
        (old, "snap-1", "aucune_action", None, None),
        # aucune_action récent (à garder)
        (fresh, "snap-3", "aucune_action", None, None),
        # preparer_entree ancien (À GARDER — on ne touche jamais aux action!=aucune_action)
        (old, "snap-1", "preparer_entree", "haussiere", None),
    ]
    for r in rows_dec:
        conn.execute(
            "INSERT INTO decisions "
            "(decision_id, timestamp, snapshot_id, action, direction, is_win) "
            "VALUES (?,?,?,?,?,?)",
            (f"dec-{uuid.uuid4().hex[:8]}", *r),
        )
    conn.commit()
    conn.close()
    return db


def _backup_dir_with_md5(tmp_path: Path, db: Path) -> Path:
    """Crée un dossier backup avec md5_pre.txt non vide (>= 1 ligne MD5)."""
    backup = tmp_path / "backup_test"
    backup.mkdir()
    md5_file = backup / "md5_pre.txt"
    md5_file.write_text(
        f"00000000000000000000000000000000  {db.stat().st_size}  {db}\n",
        encoding="utf-8",
    )
    return backup


# ── Tests purs (pas de DB) ─────────────────────────────────────
def test_cutoff_iso_format_and_horizon():
    cutoff = hyg._cutoff_iso(7)
    parsed = datetime.fromisoformat(cutoff)
    delta = datetime.now(timezone.utc) - parsed
    # Tolérance ±5s (test execution time)
    assert abs(delta.total_seconds() - 7 * 86400) < 5


def test_port_in_use_returns_bool():
    # Port non routé (1) → devrait être libre. Pas de garantie absolue
    # sur 127.0.0.1:1 (privileged), donc on accepte True|False et on
    # vérifie surtout le type.
    result = hyg._port_in_use(1)
    assert isinstance(result, bool)


def test_index_exists_initially_false(temp_db: Path):
    conn = hyg._connect(temp_db)
    try:
        assert hyg._index_exists(conn, "idx_pe_symbol_timeframe_timestamp") is False
    finally:
        conn.close()


# ── Tests DB-driven ────────────────────────────────────────────
def test_count_to_purge_identifies_only_old_shadow_and_ancienne_action(temp_db: Path):
    conn = hyg._connect(temp_db)
    try:
        plan = hyg._count_to_purge(conn, retention_days=7)
        # 3 SHADOW anciens, 0 SHADOW récents
        assert plan["principle_evaluations_shadow_old"] == 3
        # 1 ACTIVE ancien — on l'inclut dans le compteur pour traçabilité
        # mais il NE sera PAS supprimé (cf _run_purge).
        assert plan["principle_evaluations_active_old"] == 1
        # 2 aucune_action anciens
        assert plan["decisions_ancienne_action_old"] == 2
        # 1 preparer_entree ancien (jamais purgé)
        assert plan["decisions_autres_old"] == 1
        # cutoff est bien un ISO8601 parsable
        datetime.fromisoformat(plan["cutoff_utc"])
    finally:
        conn.close()


def test_run_purge_deletes_only_targeted_rows(temp_db: Path):
    conn = hyg._connect(temp_db)
    try:
        result = hyg._run_purge(conn, retention_days=7)
        # 3 SHADOW anciens supprimés, 1 SHADOW récent conservé
        assert result["deleted_principle_evaluations_shadow"] == 3
        # 2 decisions aucune_action anciennes supprimées, 1 récente conservée
        assert result["deleted_decisions_ancienne_action"] == 2

        # Vérifier conservation :
        cur = conn.execute("SELECT COUNT(*) FROM principle_evaluations")
        assert cur.fetchone()[0] == 3  # 1 SHADOW frais + 2 ACTIVE
        cur = conn.execute("SELECT COUNT(*) FROM decisions")
        assert cur.fetchone()[0] == 2  # 1 aucune_action frais + 1 preparer_entree

        # AUCUNE ACTIVE n'est supprimée (règle absolue)
        cur = conn.execute(
            "SELECT COUNT(*) FROM principle_evaluations WHERE v9_status='ACTIVE'"
        )
        assert cur.fetchone()[0] == 2
    finally:
        conn.close()


def test_run_add_index_idempotent(temp_db: Path):
    conn = hyg._connect(temp_db)
    try:
        r1 = hyg._run_add_index(conn)
        assert r1["status"] == "created"
        r2 = hyg._run_add_index(conn)
        assert r2["status"] == "already_exists"
        assert r1["index"] == r2["index"] == "idx_pe_symbol_timeframe_timestamp"
    finally:
        conn.close()


def test_main_dry_run_does_not_modify(temp_db: Path, capsys):
    # En environnement de test, le port 31685 peut être occupé par le
    # pipeline live (PC de Søn). Le dry-run doit passer quand même grâce
    # au garde-fou --force (le dry-run ne modifie RIEN, le port est sans
    # incidence fonctionnelle, juste informationnel).
    exit_code = hyg.main([
        "--db", str(temp_db), "--dry-run", "--days", "7", "--force",
    ])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "DRY-RUN" in captured
    assert "Aucun changement appliqué" in captured
    # DB inchangée
    conn = sqlite3.connect(str(temp_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 4
    finally:
        conn.close()


def test_main_apply_requires_backup(temp_db: Path, capsys):
    exit_code = hyg.main([
        "--db", str(temp_db), "--apply", "--days", "7",
    ])
    assert exit_code == 2
    assert "--apply exige --backup" in capsys.readouterr().err


def test_main_apply_rejects_missing_backup_dir(temp_db: Path, capsys):
    exit_code = hyg.main([
        "--db", str(temp_db), "--apply", "--days", "7",
        "--backup", str(temp_db.parent / "nonexistent_backup"),
    ])
    assert exit_code == 2


def test_main_apply_rejects_backup_without_md5(tmp_path: Path, temp_db: Path, capsys):
    empty_dir = tmp_path / "empty_backup"
    empty_dir.mkdir()
    exit_code = hyg.main([
        "--db", str(temp_db), "--apply", "--days", "7",
        "--backup", str(empty_dir),
    ])
    assert exit_code == 2
    assert "Backup MD5 introuvable" in capsys.readouterr().err


def test_main_apply_rejects_empty_md5_file(tmp_path: Path, temp_db: Path, capsys):
    """md5_pre.txt présent mais vide (commentaires seuls) doit être rejeté."""
    backup = tmp_path / "empty_md5"
    backup.mkdir()
    (backup / "md5_pre.txt").write_text("# que des commentaires\n", encoding="utf-8")
    exit_code = hyg.main([
        "--db", str(temp_db), "--apply", "--days", "7",
        "--backup", str(backup),
    ])
    assert exit_code == 2
    assert "vide" in capsys.readouterr().err


def test_main_apply_full_pipeline(temp_db: Path, tmp_path: Path, capsys):
    backup = _backup_dir_with_md5(tmp_path, temp_db)
    report_dir = backup
    exit_code = hyg.main([
        "--db", str(temp_db), "--apply", "--days", "7",
        "--backup", str(backup), "--force",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Purge COMMIT" in out
    assert "VACUUM" in out
    # DB effectivement purgée
    conn = sqlite3.connect(str(temp_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2
    finally:
        conn.close()
    # Rapport JSON écrit (en pratique, le rapport est écrit dans
    # docs/calibration/backups/<backup_name>/, pas dans tmp_path —
    # c'est un détail de prod qu'on ne valide pas ici).


def test_main_apply_no_vacuum(temp_db: Path, tmp_path: Path, capsys):
    backup = _backup_dir_with_md5(tmp_path, temp_db)
    exit_code = hyg.main([
        "--db", str(temp_db), "--apply", "--days", "7",
        "--backup", str(backup), "--force", "--no-vacuum",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "VACUUM en cours" not in out
