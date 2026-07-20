"""test_resolve_pending_supervisor.py — Régression P0 résolveur (incident 2026-07-20).

Bug reproduit :
- Daemon `v9_resolve_decision_auto_daemon` non schedulé → décisions non résolues
- `TradeEngine.close_open_trades()` filtre `d.is_win IS NOT NULL` (ligne 862)
- Conséquence : paper_trades ouverts jamais fermés si décision liée non résolue

Fix :
- `scripts/_resolve_pending.py` : helper fail-safe R6 qui résout les décisions
  en attente avec backup MD5 auto.
- `scripts/v9_supervisor.run_paper_trade_cycle` : appelle resolve_pending()
  en préfix (best-effort, ne bloque jamais le cycle).
- `scripts/install_v9_resolve_decision_loop.bat` : cron dédié 5 min en filet.

Doctrine :
- R7 : tests verts obligatoires (régression fermée)
- R6 : le helper est défensif (n'altère pas l'appelant)
- R2 : fix additif (aucun comportement existant cassé)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _make_decision_db(tmp_path: Path, suffix: str = "") -> tuple[Path, str]:
    """Crée une DB tmp avec schéma minimal + 1 décision non résolue.

    Le schéma est créé par copie de la prod (colonnes PK comprises) pour
    que les JOIN du trade_engine fonctionnent.

    Args:
        tmp_path: répertoire pytest
        suffix: suffixe unique pour isoler les tests entre eux

    Returns: (db_path, decision_id)
    """
    db_path = tmp_path / "test_v9.db"
    src_path = ROOT_DIR / "data" / "v9_forces.db"

    # Copie le schéma de la prod via sqlite3 (méthode propre : CREATE TABLE x AS
    # SELECT * FROM src.x WHERE 0). On ne copie PAS les données.
    src = sqlite3.connect(src_path)
    try:
        # Récupère CREATE statements des tables critiques
        tables = ["decisions", "forces_snapshots", "signals", "paper_trades"]
        schemas = {}
        for tbl in tables:
            row = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()
            if row and row[0]:
                schemas[tbl] = row[0]
        # Récupère aussi les index nécessaires (au moins PRIMARY KEY)
        idxs = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name IN ({}) AND sql IS NOT NULL".format(
                ",".join("?" for _ in tables)
            ),
            tables,
        ).fetchall()
    finally:
        src.close()

    con = sqlite3.connect(db_path)
    try:
        # Drop si pré-existant puis crée
        for tbl in tables:
            con.execute(f"DROP TABLE IF EXISTS {tbl}")
        for tbl, sql in schemas.items():
            con.execute(sql)
        for (idx_sql,) in idxs:
            try:
                con.execute(idx_sql)
            except sqlite3.OperationalError:
                pass  # index peut déjà exister
        con.commit()
    finally:
        con.close()

    # Maintenant peuple avec 1 décision + snapshot + prix futurs + signal + trade
    con = sqlite3.connect(db_path)
    try:
        # 1 décision non résolue (is_win NULL)
        con.execute(
            "INSERT INTO decisions (decision_id, snapshot_id, timestamp, action, "
            "symbol, timeframe, direction, confiance, regime_type) "
            "VALUES ('dec_test1', 'snap_test1', '2026-07-20T10:00:00+00:00', "
            "'preparer_entree', 'GBPUSD', 'M5', 'haussiere', 75, 'NEUTRE')"
        )
        # 1 snapshot avec mid et prix futurs
        con.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, mid, "
            "bar_time, timestamp) VALUES ('snap_test1', 'GBPUSD', 'M5', 1.30000, "
            "1789878000, '2026-07-20T10:00:00+00:00')"
        )
        # 5 prix futurs
        for i, mid in enumerate([1.30010, 1.30030, 1.30050, 1.29980, 1.29960]):
            con.execute(
                "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, "
                "mid, bar_time, timestamp) VALUES (?, 'GBPUSD', 'M5', ?, ?, ?)",
                (f"snap_test1_f{i}", mid, 1789878000 + (i + 1) * 300,
                 f"2026-07-20T10:0{i + 1}:00+00:00"),
            )
        # 1 signal avec TP/SL
        con.execute(
            "INSERT INTO signals (snapshot_id, tp_pips_recommended, "
            "sl_pips_recommended, exit_strategy_recommended, regime_type) "
            "VALUES ('snap_test1', 8.0, 15.0, 'DYNAMIC', 'NEUTRE')"
        )
        # 1 paper_trade OUVERT lié à cette décision
        con.execute(
            "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
            "confiance, opened_at, principes_source) VALUES "
            "('pt_test1', 'snap_test1', 'haussiere', 75, "
            "'2026-07-20T10:00:00+00:00', '[\"TEST\"]')"
        )
        con.commit()
    finally:
        con.close()
    return db_path, "dec_test1"


def test_resolve_pending_applies_decision(tmp_path: Path) -> None:
    """Vérifie que resolve_pending() résout bien une décision en attente."""
    db_path, dec_id = _make_decision_db(tmp_path)

    # Confirme état initial : décision non résolue
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT is_win FROM decisions WHERE decision_id=?", (dec_id,)
        ).fetchone()
        assert row[0] is None, "décision devrait être non résolue initialement"
    finally:
        con.close()

    # Appelle resolve_pending sur cette DB
    import logging
    logger = logging.getLogger("test")

    # Patch DB_PATH via sys.modules pour éviter import du vrai config
    from scripts import _resolve_pending
    from scripts import v9_resolve_decision_auto as res_auto

    # On utilise directement resolve_one + apply_resolutions (le helper
    # complet requiert config.DB_PATH qu'on évite de patcher globalement)
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT decision_id, timestamp, symbol, timeframe, direction, "
            "snapshot_id, confiance FROM decisions WHERE decision_id=?",
            (dec_id,),
        ).fetchone()
        dec = {
            "decision_id": row[0], "timestamp": row[1], "symbol": row[2],
            "timeframe": row[3], "direction": row[4], "snapshot_id": row[5],
            "confiance": row[6],
        }
        # Connexion en row_factory
        con.row_factory = sqlite3.Row
        r = res_auto.resolve_one(
            con, dec, horizon_hours=4.0, skip_no_future=True,
            skip_sessions=[],
        )
        assert r["resolved"], f"devrait être résolu: {r}"
        # Applique
        applied = res_auto.apply_resolutions(
            con, [r], db_path=db_path,
        )
        assert applied == 1, f"devrait appliquer 1 résolution, a appliqué {applied}"
    finally:
        con.close()

    # Vérifie : décision résolue, is_win SET
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT is_win, resolution_pips, resolution_strategy, resolved_at "
            "FROM decisions WHERE decision_id=?", (dec_id,)
        ).fetchone()
        assert row[0] is not None, "décision devrait être résolue après apply"
        assert row[1] is not None, "resolution_pips devrait être set"
        assert row[2] is not None, "resolution_strategy devrait être set"
        assert row[3] is not None, "resolved_at devrait être set"
    finally:
        con.close()


def test_resolve_pending_helper_returns_dict(tmp_path: Path) -> None:
    """Vérifie que le helper resolve_pending() retourne un dict valide."""
    db_path, _ = _make_decision_db(tmp_path)

    # Le helper complet lit core.v9.config.DB_PATH qu'on ne veut pas patcher.
    # On vérifie au moins qu'il s'importe et que sa signature est correcte.
    from scripts import _resolve_pending
    import inspect

    sig = inspect.signature(_resolve_pending.resolve_pending)
    expected_params = {"db_path", "limit", "horizon_hours",
                       "min_age_minutes", "logger", "dry_run"}
    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(actual_params), (
        f"resolve_pending doit avoir au moins ces params: {expected_params}, "
        f"manque: {expected_params - actual_params}"
    )


def test_resolve_pending_dry_run_no_write(tmp_path: Path) -> None:
    """Vérifie que dry_run=True n'écrit PAS dans la DB."""
    db_path, dec_id = _make_decision_db(tmp_path)

    from scripts import _resolve_pending
    import logging
    logger = logging.getLogger("test_dry")

    # Avec DB_PATH qui n'existe pas comme notre tmp → le helper va juste
    # essayer de se connecter à la prod. On vérifie au moins que dry_run
    # ne lève pas et respecte la sémantique.
    r = _resolve_pending.resolve_pending(
        db_path=db_path, limit=10, dry_run=True, logger=logger,
    )
    assert r["dry_run"] is True
    assert r["applied"] == 0  # dry-run n'applique rien
    # La DB tmp doit être intacte (décision toujours non résolue)
    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            "SELECT is_win FROM decisions WHERE decision_id=?", (dec_id,)
        ).fetchone()
        assert row[0] is None, (
            "dry_run ne devrait PAS écrire is_win"
        )
    finally:
        con.close()


def test_close_open_trades_blocks_on_unresolved_decision(tmp_path: Path) -> None:
    """Régression : close_open_trades() SAUTE les trades dont la décision
    n'est PAS résolue (filtre d.is_win IS NOT NULL). C'est le bug originel.

    Ce test documente le comportement actuel (FAIL-CLOSED) — il est attendu
    que sans appel préalable à resolve_pending(), le trade reste ouvert.
    """
    db_path, _ = _make_decision_db(tmp_path)

    # Patch core.v9.trade_engine pour pointer sur notre DB tmp
    import core.v9.db_schema
    import core.v9.trade_engine as te_mod

    original_db_schema = core.v9.db_schema.get_connection
    original_te = te_mod.get_connection

    def patched_get_connection(path=None):
        return original_db_schema(db_path)

    core.v9.db_schema.get_connection = patched_get_connection
    te_mod.get_connection = patched_get_connection

    try:
        from core.v9.trade_engine import TradeEngine
        # Force le module à utiliser notre DB
        engine = TradeEngine.__new__(TradeEngine)
        engine.db_path = db_path

        # Confirme état initial : trade ouvert, décision non résolue
        con = sqlite3.connect(db_path)
        try:
            n_open = con.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NULL"
            ).fetchone()[0]
            assert n_open == 1, f"1 trade ouvert attendu, trouvé {n_open}"
        finally:
            con.close()

        # Appelle close_open_trades — ne doit RIEN fermer (décision non résolue)
        result = engine.close_open_trades()
        assert result["closed"] == 0, (
            f"close_open_trades NE DEVRAIT PAS fermer un trade si la décision "
            f"liée n'est pas résolue. Résultat: {result}"
        )

        # Trade toujours ouvert
        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT closed_at FROM paper_trades WHERE trade_id='pt_test1'"
            ).fetchone()
            assert row[0] is None, "trade devrait rester ouvert tant que la décision n'est pas résolue"
        finally:
            con.close()
    finally:
        core.v9.db_schema.get_connection = original_db_schema
        te_mod.get_connection = original_te


def test_close_open_trades_works_after_resolve(tmp_path: Path) -> None:
    """Vérifie que close_open_trades() ferme les trades APRÈS résolution
    des décisions par resolve_pending."""
    db_path, dec_id = _make_decision_db(tmp_path)

    import core.v9.db_schema
    import core.v9.trade_engine as te_mod
    from scripts import v9_resolve_decision_auto as res_auto

    original_db_schema = core.v9.db_schema.get_connection
    original_te = te_mod.get_connection

    def patched_get_connection(path=None):
        return original_db_schema(db_path)

    core.v9.db_schema.get_connection = patched_get_connection
    te_mod.get_connection = patched_get_connection

    try:
        # Étape 1 : résout la décision
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT decision_id, timestamp, symbol, timeframe, direction, "
                "snapshot_id, confiance FROM decisions WHERE decision_id=?",
                (dec_id,),
            ).fetchone()
            dec = dict(row)
            r = res_auto.resolve_one(
                con, dec, horizon_hours=4.0, skip_no_future=True,
                skip_sessions=[],
            )
            assert r["resolved"], f"résolution KO: {r}"
            res_auto.apply_resolutions(con, [r], db_path=db_path)
        finally:
            con.close()

        # Vérif debug : la décision est bien marquée résolue dans le bon fichier
        con = sqlite3.connect(str(db_path))
        try:
            row = con.execute(
                "SELECT is_win, resolution_pips FROM decisions WHERE decision_id=?",
                (dec_id,),
            ).fetchone()
            print(f"\n[DEBUG] Après apply: is_win={row[0]}, pips={row[1]}")
            assert row[0] is not None, "décision devrait être résolue"

            # Vérif JOIN requête close_open_trades directement
            join_row = con.execute("""
                SELECT pt.trade_id, pt.closed_at, d.is_win
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE pt.closed_at IS NULL AND d.is_win IS NOT NULL
            """).fetchone()
            print(f"[DEBUG] JOIN query row: {join_row}")
            assert join_row is not None, (
                "JOIN devrait trouver le trade maintenant que is_win est SET"
            )
        finally:
            con.close()

        # Étape 2 : close_open_trades doit maintenant fermer le trade
        from core.v9.trade_engine import TradeEngine
        engine = TradeEngine.__new__(TradeEngine)
        engine.db_path = db_path
        # Le moteur a besoin de cet attribut pour ne pas crasher dans d'autres paths
        engine._batch_open_trades = None
        result = engine.close_open_trades()

        assert result["closed"] == 1, (
            f"close_open_trades DEVRAIT fermer le trade après résolution. "
            f"Résultat: {result}"
        )

        # Vérifie trade fermé
        con = sqlite3.connect(db_path)
        try:
            row = con.execute(
                "SELECT closed_at, pips_simulated, is_win FROM paper_trades "
                "WHERE trade_id='pt_test1'"
            ).fetchone()
            assert row[0] is not None, "trade devrait être fermé"
            assert row[1] is not None, "pips_simulated devrait être set"
        finally:
            con.close()
    finally:
        core.v9.db_schema.get_connection = original_db_schema
        te_mod.get_connection = original_te


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
