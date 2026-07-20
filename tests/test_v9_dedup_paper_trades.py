"""test_v9_dedup_paper_trades.py — Régression dedup paper_trades fantômes (2026-07-20).

Bug originel : `_trade_already_open` du trade_engine filtrait
`closed_at IS NULL` (ne voyait que les trades OUVERTS). Après clôture par
`close_open_trades()`, le hook `post_decision_hook` (TradeEngine fraîche
par snapshot) ré-ouvrait le même snapshot au passage suivant → jusqu'à
17 paper_trades/snapshot pour 1 décision légitime (catastrophe 17/07).

Le commit `c47dc68` a fixé le bug en code (`_trade_already_open` compte
MAINTENANT tout trade du couple snapshot_id+direction). Mais 1001 trades
fantômes restaient en DB.

Ce script `v9_dedup_paper_trades.py` nettoie l'historique en gardant
le MIN(opened_at) par (snapshot_id, direction) et archivant les fantômes.

Doctrine :
- R7 : tests verts obligatoires (régression fermée)
- R6 : dry-run par défaut, MD5 backup obligatoire pour --apply
- R2 : script séparé, ne modifie aucun core/v9/*
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _make_db_with_dupes(tmp_path: Path) -> Path:
    """Crée une DB avec 3 snapshots × 4 trades (1 légitime + 3 fantômes)."""
    db = tmp_path / "test_dedup.db"
    con = sqlite3.connect(db)
    try:
        con.executescript(
            """
            CREATE TABLE paper_trades (
                trade_id TEXT PRIMARY KEY,
                snapshot_id TEXT,
                direction TEXT,
                confiance INTEGER,
                opened_at TEXT,
                closed_at TEXT,
                pips_simulated REAL,
                is_win INTEGER,
                principes_source TEXT,
                risk_go_context TEXT
            );
            """
        )
        # snapshot S1, direction haussiere : 4 trades (1 légitime + 3 fantômes WIN)
        for i, (tid, opened, win) in enumerate([
            ("pt_legit_S1", "2026-07-17T10:00:00+00:00", 1),
            ("pt_fant1_S1", "2026-07-17T11:00:00+00:00", 1),
            ("pt_fant2_S1", "2026-07-17T12:00:00+00:00", 1),
            ("pt_fant3_S1", "2026-07-17T13:00:00+00:00", 0),
        ]):
            con.execute(
                "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
                "opened_at, closed_at, pips_simulated, is_win, principes_source) "
                "VALUES (?, 'S1', 'haussiere', ?, '2026-07-17T14:00:00+00:00', "
                "?, ?, '[\"TEST\"]')",
                (tid, opened, 4.5 if win else -10.0, win),
            )
        # snapshot S2, direction baissiere : 1 seul trade (rien à dédup)
        con.execute(
            "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
            "opened_at, closed_at, pips_simulated, is_win, principes_source) "
            "VALUES ('pt_legit_S2', 'S2', 'baissiere', '2026-07-17T10:00:00+00:00', "
            "'2026-07-17T14:00:00+00:00', -3.0, 0, '[\"TEST\"]')"
        )
        # snapshot S3, direction haussiere : 2 trades (1 légitime + 1 fantôme)
        con.execute(
            "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
            "opened_at, closed_at, pips_simulated, is_win, principes_source) "
            "VALUES ('pt_legit_S3', 'S3', 'haussiere', '2026-07-17T10:00:00+00:00', "
            "'2026-07-17T14:00:00+00:00', 4.5, 1, '[\"TEST\"]')"
        )
        con.execute(
            "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
            "opened_at, closed_at, pips_simulated, is_win, principes_source) "
            "VALUES ('pt_fant1_S3', 'S3', 'haussiere', '2026-07-17T11:00:00+00:00', "
            "'2026-07-17T14:00:00+00:00', 4.5, 1, '[\"TEST\"]')"
        )
        con.commit()
    finally:
        con.close()
    return db


def test_analyze_detects_dupes(tmp_path: Path) -> None:
    """analyze() retourne les bons compteurs."""
    db = _make_db_with_dupes(tmp_path)
    from scripts.v9_dedup_paper_trades import analyze
    stats = analyze(db)
    assert stats["total"] == 7
    assert stats["unique_pairs"] == 3
    assert stats["duplicates_total"] == 4
    assert stats["phantoms"]["n"] == 4  # 3 fantômes S1 + 1 fantôme S3
    assert stats["legitimes"]["n"] == 3  # S1 légitime + S2 légitime + S3 légitime


def test_archive_phantoms_is_idempotent(tmp_path: Path) -> None:
    """archive_phantoms() copie les fantômes sans doublonner."""
    db = _make_db_with_dupes(tmp_path)
    archive_dir = tmp_path / "archive"
    from scripts.v9_dedup_paper_trades import archive_phantoms
    n1 = archive_phantoms(db, archive_dir)
    assert n1 == 4
    n2 = archive_phantoms(db, archive_dir)
    assert n2 == 0  # idempotent (INSERT OR IGNORE)
    # Vérifie le contenu
    archive_db = archive_dir / "paper_trades_fantomes_archive.db"
    con = sqlite3.connect(archive_db)
    try:
        n = con.execute("SELECT COUNT(*) FROM paper_trades_fantomes").fetchone()[0]
        assert n == 4
        ids = {r[0] for r in con.execute(
            "SELECT trade_id FROM paper_trades_fantomes"
        ).fetchall()}
        assert ids == {"pt_fant1_S1", "pt_fant2_S1", "pt_fant3_S1", "pt_fant1_S3"}
    finally:
        con.close()


def test_apply_dedup_removes_only_dupes(tmp_path: Path) -> None:
    """apply_dedup() DROP uniquement les fantômes, garde les légitimes."""
    db = _make_db_with_dupes(tmp_path)
    archive_dir = tmp_path / "archive"
    from scripts.v9_dedup_paper_trades import archive_phantoms, apply_dedup
    archive_phantoms(db, archive_dir)
    result = apply_dedup(db, archive_dir)
    assert result["deleted"] == 4
    assert result["before_total"] == 7
    assert result["after_total"] == 3
    # Vérifie qu'il reste exactement les légitimes
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT trade_id FROM paper_trades ORDER BY trade_id"
        ).fetchall()
        ids = {r[0] for r in rows}
        assert ids == {"pt_legit_S1", "pt_legit_S2", "pt_legit_S3"}
        # P&L post : S1 +4.5 + S2 -3.0 + S3 +4.5 = +6.0 (les fantômes WIN sont DROPés)
        r = con.execute(
            "SELECT ROUND(SUM(pips_simulated), 1) FROM paper_trades"
        ).fetchone()
        assert r[0] == 6.0
    finally:
        con.close()


def test_apply_dedup_idempotent(tmp_path: Path) -> None:
    """apply_dedup() peut tourner plusieurs fois sans effet."""
    db = _make_db_with_dupes(tmp_path)
    archive_dir = tmp_path / "archive"
    from scripts.v9_dedup_paper_trades import archive_phantoms, apply_dedup
    archive_phantoms(db, archive_dir)
    apply_dedup(db, archive_dir)
    # 2e passe : rien à faire
    archive_phantoms(db, archive_dir)
    result = apply_dedup(db, archive_dir)
    assert result["deleted"] == 0


def test_no_dupes_no_op(tmp_path: Path) -> None:
    """Si pas de doublons, apply_dedup est un no-op."""
    db = tmp_path / "test_clean.db"
    con = sqlite3.connect(db)
    try:
        con.executescript(
            """
            CREATE TABLE paper_trades (
                trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
                confiance INTEGER, opened_at TEXT, closed_at TEXT,
                pips_simulated REAL, is_win INTEGER, principes_source TEXT,
                risk_go_context TEXT
            );
            """
        )
        for i in range(5):
            con.execute(
                "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
                "opened_at, closed_at, pips_simulated, is_win, principes_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '[\"TEST\"]')",
                (f"pt_{i}", f"S{i}", "haussiere",
                 "2026-07-17T10:00:00+00:00", "2026-07-17T14:00:00+00:00",
                 4.5, 1),
            )
        con.commit()
    finally:
        con.close()

    archive_dir = tmp_path / "archive"
    from scripts.v9_dedup_paper_trades import archive_phantoms, apply_dedup
    archive_phantoms(db, archive_dir)
    result = apply_dedup(db, archive_dir)
    assert result["deleted"] == 0
    assert result["after_total"] == 5


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
