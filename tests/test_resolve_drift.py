"""test_resolve_drift.py — Motion #32 : idempotence paper_trades (résolution drift loop).

Contexte (audit docs/audits/RESOLUTION_DRIFT_DEEP_DIVE_20260720.md) :
l'incident du 2026-07-20 (3 snapshots GBPUSD M15 résolus 6× → 18 lignes fantômes)
venait de l'ABSENCE de contrainte d'unicité sur paper_trades. Le prompt Motion #32
ciblait un schéma inexistant (principle_name/side/outcome) ; le schéma RÉEL est
(trade_id PK, snapshot_id, direction, confiance, principes_source, ...).

Correctif livré :
  - migration idempotente `core/v9/migrations/20260720_unique_paper_trade.sql`
    (dédup MIN(rowid) + UNIQUE INDEX sur (snapshot_id, direction, principes_source)) ;
  - garde applicative `PaperTradeLogger.log_open` : INSERT ... ON CONFLICT DO NOTHING,
    renvoie le trade_id canonique existant (jamais un id fantôme) ;
  - rollback non destructif `scripts/v9_rollback_motion32.py` (DROP INDEX seul).

Doctrine : R7 (tests verts), R2 (additif), R6 (défensif).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MIGRATION_SQL = ROOT_DIR / "core" / "v9" / "migrations" / "20260720_unique_paper_trade.sql"


def _fresh_db(tmp_path: Path) -> Path:
    """DB paper_trades au schéma RÉEL, index unique inclus (via init)."""
    db = tmp_path / "pt.db"
    from core.v9.paper_trades_db import init_paper_trades_db
    init_paper_trades_db(db)
    return db


def _legacy_db_no_unique(tmp_path: Path) -> Path:
    """DB paper_trades SANS l'index unique (état pré-migration, doublons possibles)."""
    db = tmp_path / "pt_legacy.db"
    con = sqlite3.connect(db)
    try:
        con.executescript(
            """
            CREATE TABLE paper_trades (
                trade_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                confiance INTEGER NOT NULL,
                principes_source TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                pips_simulated REAL,
                is_win INTEGER,
                risk_go_context TEXT
            );
            """
        )
        con.commit()
    finally:
        con.close()
    return db


def _insert(con: sqlite3.Connection, tid: str, snap: str, direction: str,
            princ: str, pips: float | None = None, is_win: int | None = None) -> None:
    con.execute(
        "INSERT INTO paper_trades (trade_id, snapshot_id, direction, confiance,"
        " principes_source, opened_at, closed_at, pips_simulated, is_win)"
        " VALUES (?,?,?,50,?,?,?,?,?)",
        (tid, snap, direction, princ, f"2026-07-20T10:00:00+00:00",
         "2026-07-20T14:00:00+00:00" if pips is not None else None, pips, is_win),
    )


def _run_migration(db: Path) -> None:
    con = sqlite3.connect(db)
    try:
        con.executescript(MIGRATION_SQL.read_text(encoding="utf-8"))
        con.commit()
    finally:
        con.close()


# ── 1. La contrainte bloque une insertion dupliquée ─────────────────
def test_dedup_unique_constraint_blocks_duplicate(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    con = sqlite3.connect(db)
    try:
        _insert(con, "pt_a", "SNAP1", "haussiere", '["P1"]', 5.0, 1)
        con.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _insert(con, "pt_b", "SNAP1", "haussiere", '["P1"]', 9.0, 1)
    finally:
        con.close()


# ── 2. log_open est idempotent : même triplet → même trade_id ───────
def test_log_open_idempotent_returns_same_trade_id(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    from core.v9.paper_trade_logger import PaperTradeLogger
    logger = PaperTradeLogger(db_path=db)
    arb = {
        "snapshot_id": "SNAP_X", "direction": "haussiere",
        "confiance_arbitree": 80, "principes_source": ["P1", "P2"],
    }
    tid1 = logger.log_open(arb)
    tid2 = logger.log_open(arb)          # ré-résolution du même snapshot
    assert tid1 == tid2                   # pas d'id fantôme
    con = sqlite3.connect(db)
    try:
        n = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    finally:
        con.close()
    assert n == 1                         # une seule ligne, pas de doublon


# ── 3. Direction distincte = deux trades légitimes (pas sur-contraint) ─
def test_distinct_direction_creates_two_trades(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    from core.v9.paper_trade_logger import PaperTradeLogger
    logger = PaperTradeLogger(db_path=db)
    base = {"snapshot_id": "SNAP_Y", "confiance_arbitree": 70,
            "principes_source": ["P1"]}
    tid_h = logger.log_open({**base, "direction": "haussiere"})
    tid_b = logger.log_open({**base, "direction": "baissiere"})
    assert tid_h != tid_b
    con = sqlite3.connect(db)
    try:
        n = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    finally:
        con.close()
    assert n == 2


# ── 4. Migration idempotente : ré-exécutable, index présent ─────────
def test_migration_idempotent(tmp_path: Path) -> None:
    db = _legacy_db_no_unique(tmp_path)
    _run_migration(db)
    _run_migration(db)                    # 2e passe : no-op
    con = sqlite3.connect(db)
    try:
        idx = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index'"
            " AND name='idx_pt_snap_dir_princ'"
        ).fetchone()
    finally:
        con.close()
    assert idx is not None


# ── 5. WR recalculé après dédup migration (garde MIN(rowid)) ────────
def test_wr_recomputed_after_dedup(tmp_path: Path) -> None:
    db = _legacy_db_no_unique(tmp_path)
    con = sqlite3.connect(db)
    try:
        # 3 fantômes sur SNAP1/haussiere (le 1er = perte, gonflé par 2 wins fantômes)
        _insert(con, "pt_1", "SNAP1", "haussiere", '["P1"]', -8.0, 0)  # gardé (MIN rowid)
        _insert(con, "pt_2", "SNAP1", "haussiere", '["P1"]', 6.0, 1)   # fantôme
        _insert(con, "pt_3", "SNAP1", "haussiere", '["P1"]', 6.0, 1)   # fantôme
        _insert(con, "pt_4", "SNAP2", "baissiere", '["P1"]', 4.0, 1)   # légitime
        con.commit()
        wr_before = con.execute(
            "SELECT 100.0*AVG(is_win) FROM paper_trades"
        ).fetchone()[0]
    finally:
        con.close()
    assert round(wr_before) == 75          # 3/4 wins avant dédup (gonflé)

    _run_migration(db)

    con = sqlite3.connect(db)
    try:
        n = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        wr_after = con.execute(
            "SELECT 100.0*AVG(is_win) FROM paper_trades"
        ).fetchone()[0]
        kept = {r[0] for r in con.execute("SELECT trade_id FROM paper_trades")}
    finally:
        con.close()
    assert n == 2                          # 1 par triplet
    assert kept == {"pt_1", "pt_4"}        # MIN(rowid) conservé
    assert round(wr_after) == 50           # 1/2 wins après dédup (réel)


# ── 6. Rollback non destructif et idempotent (DROP INDEX seul) ──────
def test_rollback_path_idempotent(tmp_path: Path) -> None:
    db = _fresh_db(tmp_path)
    con = sqlite3.connect(db)
    try:
        _insert(con, "pt_a", "SNAP1", "haussiere", '["P1"]', 5.0, 1)
        con.commit()
    finally:
        con.close()
    from scripts.v9_rollback_motion32 import rollback, _index_exists

    assert rollback(db) == 0               # supprime l'index
    con = sqlite3.connect(db)
    try:
        assert not _index_exists(con)      # index parti
        n = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    finally:
        con.close()
    assert n == 1                          # AUCUNE donnée perdue
    assert rollback(db) == 0               # 2e passe : no-op, code 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
