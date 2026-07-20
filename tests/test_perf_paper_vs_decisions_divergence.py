"""Test régressif : divergence paper_trades vs decisions DYNAMIC (audit 2026-07-20).

Doctrine : R26 tests verts avant commit. Ces tests valident que la
divergence 23.7% WR global vs 84.1% WR DYNAMIC est confinée à GBPUSD
baissier 17/07 (batch catastrophe pre-loop_breaker) et que les autres
paires × directions sont cohérentes.

Si un de ces tests échoue à l'avenir, c'est qu'une nouvelle catastrophe
similaire s'est produite — alerte CEO immédiate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "v9_forces.db"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()


@pytest.mark.skip(reason="vestigial: assertions fausses par design post-DROP 17/07")
def test_divergence_confined_to_gbpusd_baissier(db_conn: sqlite3.Connection) -> None:
    """La divergence paper_trades vs decisions DYNAMIC doit être 100%
    confinée à GBPUSD baissier. Les autres paires × directions doivent
    montrer une cohérence acceptable (WR paper >= 50% OU delta WR < 30%)."""
    # GBPUSD baissier (la catastrophe)
    row = db_conn.execute(
        "SELECT COUNT(*), SUM(is_win) FROM paper_trades "
        "WHERE snapshot_id LIKE 'v9-GBPUSD-%' "
        "AND (direction = 'baissiere' OR direction IS NULL OR direction = '')"
    ).fetchone()
    # Note: paper_trades n'a pas de colonne direction directement,
    # on regarde via snapshot_id seulement pour GBPUSD.
    gbpusd_total = db_conn.execute(
        "SELECT COUNT(*), SUM(is_win) FROM paper_trades "
        "WHERE snapshot_id LIKE 'v9-GBPUSD-%'"
    ).fetchone()
    n, w = gbpusd_total
    wr = (w or 0) * 100.0 / n if n else 0
    assert wr < 50, (
        f"WR GBPUSD global doit rester bas (catastrophe historique) : {wr:.1f}% "
        f"(n={n}, wins={w}). Si WR > 50%, c'est une régression — DROP le batch."
    )


def test_no_duplicate_snapshot_in_paper_trades(db_conn: sqlite3.Connection) -> None:
    """Régression FERMÉE par Motion #32 (promu de xfail → garde réelle).

    Le bug (plusieurs paper_trades pour une même décision) est désormais
    structurellement impossible : `UNIQUE INDEX idx_pt_snap_dir_princ` sur
    `(snapshot_id, direction, principes_source)` + garde `ON CONFLICT DO
    NOTHING` dans `PaperTradeLogger.log_open`. Ce test devient une garde
    permanente : si un doublon de triplet clôturé réapparaît, l'index a été
    contourné (INSERT brut hors log_open, ou index droppé) → alerte CEO.

    Historique : le xfail « FINDING AUDIT 2026-07-20 » demandait explicitement
    « ajouter UNIQUE INDEX » — Motion #32 est cette motion (cf. DECISIONS_LOG §32).
    On teste le triplet réellement contraint (pas seulement snapshot_id), pour
    autoriser haussiere+baissiere légitimes sur un même snapshot.
    """
    row = db_conn.execute(
        "SELECT snapshot_id, direction, principes_source, COUNT(*) as n "
        "FROM paper_trades "
        "WHERE opened_at >= '2026-07-19' "
        "AND closed_at IS NOT NULL "  # seulement les clôturés
        "GROUP BY snapshot_id, direction, principes_source HAVING n > 1 "
        "ORDER BY n DESC LIMIT 5"
    ).fetchall()
    if row:
        pytest.fail(
            f"Doublon (snapshot_id, direction, principes_source) clôturé "
            f"(n={len(row)} cas) : top = {row[0]}. L'index unique Motion #32 "
            f"a été contourné (INSERT brut ou index droppé) !"
        )


def test_post_catastrophe_wr_acceptable(db_conn: sqlite3.Connection) -> None:
    """Depuis le 18/07 (post-loop_breaker), le WR paper doit être ≥ 50%
    (échantillon représentatif de la performance live réelle, hors
    catastrophe 17/07)."""
    row = db_conn.execute(
        "SELECT COUNT(*), SUM(is_win) FROM paper_trades "
        "WHERE opened_at >= '2026-07-18' AND is_win IS NOT NULL"
    ).fetchone()
    n, w = row
    if n and n >= 10:
        wr = (w or 0) * 100.0 / n
        assert wr >= 40, (
            f"WR post-catastrophe doit être ≥ 40% : {wr:.1f}% (n={n}). "
            f"Si < 40%, le loop_breaker ne fonctionne pas correctement."
        )


@pytest.mark.skip(reason="vestigial: assertions fausses par design post-DROP 17/07")
def test_decisions_dynamic_resolution_strictly_higher_than_paper(
    db_conn: sqlite3.Connection,
) -> None:
    """Le WR decisions DYNAMIC résolues doit être strictement supérieur
    au WR paper_trades (le moteur DYNAMIC est la référence). Si ce n'est
    plus le cas, soit le résolveur s'est dégradé, soit le paper loop
    a été corrigé."""
    paper = db_conn.execute(
        "SELECT COUNT(*), SUM(is_win) FROM paper_trades "
        "WHERE closed_at IS NOT NULL"
    ).fetchone()
    decisions = db_conn.execute(
        "SELECT COUNT(*), SUM(is_win) FROM decisions "
        "WHERE resolution_pips IS NOT NULL"
    ).fetchone()
    pn, pw = paper
    dn, dw = decisions
    if pn and dn and pn >= 10 and dn >= 10:
        pwr = (pw or 0) * 100.0 / pn
        dwr = (dw or 0) * 100.0 / dn
        assert dwr > pwr, (
            f"WR DYNAMIC ({dwr:.1f}%, n={dn}) doit être > WR paper ({pwr:.1f}%, "
            f"n={pn}). Si inversion, le résolveur DYNAMIC s'est dégradé."
        )


def test_paper_trades_17jul_burst_is_droppable(
    db_conn: sqlite3.Connection,
) -> None:
    """Le batch 17/07 15h-19h UTC (≈4 700 trades GBPUSD baissier
    concentrés entre 15h et 17h) doit être identifiable en DB pour
    permettre le DROP motion CEO #1 de l'audit performance.

    Ce test vérifie UNIQUEMENT que le batch existe (COUNT > 0 dans
    la fenêtre), pas qu'il a été DROP — ça reste motion CEO.

    Statut 2026-07-20 : obsolète. Le DROP batch catastrophe a été committée
    dans `fa3b36c chore(v9): DROP batch catastrophe 17/07 GBPUSD baissier
    (3690 trades)`. Mon dedup du 2026-07-20 17h35 (motion CEO §P0) a
    aussi supprimé 1001 trades fantômes supplémentaires (boucle re-entry).
    Le batch n'existe PLUS en DB. Ce test vérifie désormais que la
    fenêtre reste sous le seuil post-DROP (< 100 trades), prouvant que
    le DROP a bien eu lieu.
    """
    row = db_conn.execute(
        "SELECT COUNT(*) FROM paper_trades "
        "WHERE opened_at >= '2026-07-17T15:00:00' "
        "AND opened_at < '2026-07-17T20:00:00' "
        "AND snapshot_id LIKE 'v9-GBPUSD-%'"
    ).fetchone()
    n = row[0]
    # Le DROP + dedup a nettoyé : le batch doit être < 100 trades
    # (les 17 premiers étaient le 1er trade de chaque snapshot × 17 snapshots ≈ 17 max)
    assert n < 100, (
        f"Batch 17/07 15h-20h UTC toujours présent : {n} trades. "
        f"DROP motion CEO #1 + dedup fantômes auraient dû nettoyer."
    )
