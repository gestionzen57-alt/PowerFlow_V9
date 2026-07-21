"""Schéma DB V9 — table `paper_trades` (data/v9_forces.db).

Phase 9.7 : simulation paper-trade (zéro ordre réel avant Phase 12).
Chaque trade ouvert par PaperTradeLogger est journalisé avec :
  - snapshot_id d'origine (référence aux décisions consolidées)
  - direction + confiance arbitrée (post-arbiter)
  - principes_source (JSON)
  - opened_at / closed_at / pips_simulated / is_win
  - risk_go_context (snapshot du shared_context au moment du go)

Doctrine : cette table est la base du paper-trade V9. Aucune logique
d'exécution d'ordre — uniquement simulation / collecte WIN/LOSS pour
alimenter la calibration post-Phase 10.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection

PAPER_TRADES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id          TEXT PRIMARY KEY,
    snapshot_id       TEXT NOT NULL,
    direction         TEXT NOT NULL,
    confiance         INTEGER NOT NULL,
    principes_source  TEXT NOT NULL,
    opened_at         TEXT NOT NULL,
    closed_at         TEXT,
    pips_simulated    REAL,
    is_win            INTEGER,
    risk_go_context   TEXT
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_snapshot
    ON paper_trades (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_paper_trades_opened_at
    ON paper_trades (opened_at);

-- Motion #32 : idempotence — un même (snapshot_id, direction, principes_source)
-- = une même décision => un seul paper-trade. Empêche la re-duplication à la
-- ré-résolution (cf. incident 2026-07-20, 18 lignes fantômes).
CREATE UNIQUE INDEX IF NOT EXISTS idx_pt_snap_dir_princ
    ON paper_trades (snapshot_id, direction, principes_source);
"""


def init_paper_trades_db(db_path: Path | None = None) -> None:
    """Crée la table paper_trades et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(PAPER_TRADES_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()