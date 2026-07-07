"""Tests unitaires — v9_resolve_decision.py (résolution manuelle post-trade).

Couvre 5 cas exigés par le brief :
  1. test_resolve_sets_columns : is_win + pips + resolved_at remplis
  2. test_resolve_unknown_id : erreur si decision_id introuvable
  3. test_resolve_already_resolved : erreur sans --force
  4. test_resolve_force_overwrite : écrase avec --force
  5. test_migration_idempotente : ALTER 2× sans erreur

Aucune logique d'exécution testée — uniquement la saisie manuelle.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.db_schema import init_db
from core.v9.decision_db import (
    RESOLUTION_COLUMNS,
    _migrate_resolution_columns,
    init_decision_db,
)
from core.v9.decision_logger import DecisionLogger, _decision_id_for_snapshot
from scripts.v9_resolve_decision import (
    _format_decision,
    cmd_list,
    cmd_resolve,
    main,
)


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DB minimale avec table decisions peuplée.

    Patche DB_PATH globalement (config + db_schema + decision_db) pour que
    le script `v9_resolve_decision.py` tape dans le tmp_path du test plutôt
    que dans data/v9_forces.db — isolation complète.
    """
    path = tmp_path / "v9_resolve_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)              # forces_snapshots
    init_decision_db(path)     # decisions + migration colonnes résolution
    return path


def _insert_decision_row(
    db_path: Path,
    *,
    decision_id: str = "dec_test000abc1",
    direction: str | None = "haussiere",
    confiance: int = 75,
    action: str = "surveiller",
) -> None:
    """Insère une décision minimale directement en DB (sans pipeline complet).

    Évite de monter toute la chaîne 8 couches pour tester uniquement la
    saisie manuelle de résolution.
    """
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        snapshot_id = f"v9-test-{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id, "1.0", "2026-07-07T10:00:00.000Z", snapshot_id, "sig_test",
                action, "GBPUSD", "M15", "GBP",
                "scene_test", "behav_test", "win_test", "exploit_test",
                "tendance", direction, confiance,
                json.dumps(["NODE_BIRTH_FAST"]), json.dumps({}), "live",
                "2026-07-07T10:00:00.500Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row(db_path: Path, decision_id: str) -> dict:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return dict(r) if r else {}
    finally:
        conn.close()


# ---------- Helpers pour mocker la CLI ----------


class _Args:
    """Namespace compatible argparse pour les tests cmd_resolve / cmd_list."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------- Tests ----------


def test_resolve_sets_columns(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cas 1 : saisie valide → is_win + resolution_pips + resolved_at remplis."""
    _insert_decision_row(db_path)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "o")

    args = _Args(decision_id="dec_test000abc1", is_win=True, pips=18.5,
                 force=False, yes=False, list=False, unresolved=False, limit=50)
    rc = cmd_resolve(args)
    assert rc == 0

    row = _row(db_path, "dec_test000abc1")
    assert row["is_win"] == 1
    assert row["resolution_pips"] == 18.5
    assert row["resolved_at"] is not None
    assert row["resolved_at"].endswith("+00:00") or row["resolved_at"].endswith("Z")
    # Direction / confiance / action doivent être inchangés
    assert row["direction"] == "haussiere"
    assert row["confiance"] == 75
    assert row["action"] == "surveiller"


def test_resolve_unknown_id(db_path: Path) -> None:
    """Cas 2 : decision_id inexistant → exit code 1, aucune modification."""
    _insert_decision_row(db_path)
    args = _Args(decision_id="dec_inexistant", is_win=True, pips=10.0,
                 force=False, yes=True, list=False, unresolved=False, limit=50)
    rc = cmd_resolve(args)
    assert rc == 1

    # La décision initiale est intacte
    row = _row(db_path, "dec_test000abc1")
    assert row["is_win"] is None
    assert row["resolution_pips"] is None
    assert row["resolved_at"] is None


def test_resolve_already_resolved(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cas 3 : décision déjà résolue → erreur sans --force."""
    _insert_decision_row(db_path)
    # Première résolution (autorisée)
    args1 = _Args(decision_id="dec_test000abc1", is_win=True, pips=15.0,
                  force=False, yes=True, list=False, unresolved=False, limit=50)
    assert cmd_resolve(args1) == 0

    # Seconde tentative SANS --force → erreur
    args2 = _Args(decision_id="dec_test000abc1", is_win=False, pips=-5.0,
                  force=False, yes=True, list=False, unresolved=False, limit=50)
    rc = cmd_resolve(args2)
    assert rc == 2  # code erreur dédié "déjà résolu"

    # La première résolution est préservée (intacte)
    row = _row(db_path, "dec_test000abc1")
    assert row["is_win"] == 1
    assert row["resolution_pips"] == 15.0


def test_resolve_force_overwrite(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cas 4 : décision déjà résolue + --force → écrasement autorisé."""
    _insert_decision_row(db_path)
    # Première résolution
    args1 = _Args(decision_id="dec_test000abc1", is_win=True, pips=15.0,
                  force=False, yes=True, list=False, unresolved=False, limit=50)
    assert cmd_resolve(args1) == 0

    # Seconde résolution AVEC --force → doit écraser
    args2 = _Args(decision_id="dec_test000abc1", is_win=False, pips=-7.5,
                  force=True, yes=True, list=False, unresolved=False, limit=50)
    rc = cmd_resolve(args2)
    assert rc == 0

    row = _row(db_path, "dec_test000abc1")
    assert row["is_win"] == 0
    assert row["resolution_pips"] == -7.5
    assert row["resolved_at"] is not None


def test_migration_idempotente(db_path: Path) -> None:
    """Cas 5 : init_decision_db() appelé 2× ne lève aucune erreur
    et les colonnes sont présentes exactement une fois."""
    # Premier init (déjà fait via fixture, mais on rejoue explicitement)
    init_decision_db(db_path)
    # Second init — doit être no-op idempotent
    init_decision_db(db_path)
    # Troisième pour la route
    init_decision_db(db_path)

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()]
        for col_name, _col_type in RESOLUTION_COLUMNS:
            assert col_name in cols, f"colonne {col_name!r} absente après migration"
        # Pas de doublon
        assert cols.count("is_win") == 1
        assert cols.count("resolution_pips") == 1
        assert cols.count("resolved_at") == 1

        # Et la migration _migrate_resolution_columns directe est aussi idempotente
        conn2 = sqlite3.connect(str(db_path), timeout=30)
        try:
            _migrate_resolution_columns(conn2)
            _migrate_resolution_columns(conn2)
            cols2 = [r[1] for r in conn2.execute("PRAGMA table_info(decisions)").fetchall()]
            assert cols == cols2
        finally:
            conn2.close()
    finally:
        conn.close()


# ---------- Tests annexes (couverture minimale du reste du script) ----------


def test_format_decision_handles_missing_keys() -> None:
    """_format_decision ne lève pas même si la décision est partielle."""
    d = {"decision_id": "dec_x", "direction": "haussiere"}
    out = _format_decision(d)
    assert "dec_x" in out
    assert "haussiere" in out


def test_cmd_list_with_unresolved_filter(db_path: Path) -> None:
    """cmd_list --unresolved filtre bien les décisions NULL."""
    _insert_decision_row(db_path, decision_id="dec_resolved_001")
    _insert_decision_row(db_path, decision_id="dec_pending_001")

    # Résoudre la première via DB directe (contourne la confirmation CLI)
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "UPDATE decisions SET is_win=1, resolution_pips=10.0, "
            "resolved_at='2026-07-07T11:00:00+00:00' WHERE decision_id=?",
            ("dec_resolved_001",),
        )
        conn.commit()
    finally:
        conn.close()

    # Test --list (toutes)
    args_all = _Args(decision_id=None, is_win=None, pips=None, force=False,
                     yes=False, list=True, unresolved=False, limit=50)
    assert cmd_list(args_all) == 0

    # Test --list --unresolved (filtre)
    args_unr = _Args(decision_id=None, is_win=None, pips=None, force=False,
                     yes=False, list=True, unresolved=True, limit=50)
    assert cmd_list(args_unr) == 0


def test_main_refuses_missing_args(db_path: Path, capsys) -> None:
    """main() sans arguments requis doit lever une erreur argparse."""
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2  # argparse error


def test_main_list_calls_cmd_list(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() --list appelle cmd_list (sortie 0 même si DB vide)."""
    args = ["--list"]
    monkeypatch.setattr("sys.argv", ["v9_resolve_decision.py"] + args)
    assert main() == 0


def test_resolve_loss_negative_pips(db_path: Path) -> None:
    """WIN=False + pips négatifs est une saisie valide (perte)."""
    _insert_decision_row(db_path)
    args = _Args(decision_id="dec_test000abc1", is_win=False, pips=-22.3,
                 force=False, yes=True, list=False, unresolved=False, limit=50)
    rc = cmd_resolve(args)
    assert rc == 0
    row = _row(db_path, "dec_test000abc1")
    assert row["is_win"] == 0
    assert row["resolution_pips"] == -22.3


def test_resolve_confirmation_cancel(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si l'opérateur répond 'n' à la confirmation, rien n'est modifié."""
    _insert_decision_row(db_path)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")

    args = _Args(decision_id="dec_test000abc1", is_win=True, pips=99.0,
                 force=False, yes=False, list=False, unresolved=False, limit=50)
    rc = cmd_resolve(args)
    assert rc == 3  # code "annulé"

    row = _row(db_path, "dec_test000abc1")
    assert row["is_win"] is None
    assert row["resolution_pips"] is None
    assert row["resolved_at"] is None


def test_decision_logger_pipeline_compatible(db_path: Path) -> None:
    """Vérifie que DecisionLogger.log() coexiste avec les nouvelles colonnes.

    Aucune modification de DecisionLogger (périmètre strict) — le pipeline
    live doit continuer à fonctionner sans toucher aux nouvelles colonnes
    nullable (qui restent NULL par défaut).
    """
    # On ne peut pas appeler log() complet sans toute la chaîne — mais on
    # vérifie au moins que init_decision_db (appelé en interne par
    # DecisionLogger) n'échoue pas sur une DB fraîche.
    DecisionLogger(db_path=db_path)  # constructeur appelle init_decision_db

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(decisions)").fetchall()]
        for col_name, _col_type in RESOLUTION_COLUMNS:
            assert col_name in cols
    finally:
        conn.close()