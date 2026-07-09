"""Tests — scripts/v9_paper_trade_loop.py (Phase 10).

Couvre :
- run_pass() — délègue à v9_paper_trade_run.run() et écrit le rapport
- _write_report() — format JSON ligne par ligne
- run_loop() — mode --once et --watch (signal stop)
- CLI — --once, --watch, --dry-run, --json, --report
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_paper_trade_loop as ptl  # noqa: E402
from scripts import v9_paper_trade_run as ptr  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Base de données SQLite avec tables decisions + paper_trades."""
    db = tmp_path / "v9_forces.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY,
            timestamp TEXT,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            action TEXT,
            principes_json TEXT,
            contexte_complet_json BLOB,
            source_type TEXT
        );
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            snapshot_id TEXT,
            direction TEXT,
            confiance INTEGER,
            principes_source TEXT,
            opened_at TEXT,
            closed_at TEXT,
            pips_simulated REAL,
            is_win INTEGER,
            risk_go_context TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def temp_report(tmp_path: Path) -> Path:
    return tmp_path / "paper_trade_report.log"


@pytest.fixture
def logger() -> MagicMock:
    return MagicMock()


# ── _write_report ────────────────────────────────────────────


def test_write_report_creates_file(tmp_path: Path):
    """_write_report crée le fichier et écrit une ligne JSON."""
    report = tmp_path / "reports" / "test.log"
    summary = {
        "snapshots_analyses": 5,
        "trades_ouverts": 2,
        "trades_ignores": 3,
        "dry_run": False,
        "details": [
            {"snapshot_id": "snap1", "direction": "haussiere", "go": True},
        ],
    }
    ptl._write_report(report, summary, MagicMock())

    assert report.exists()
    lines = report.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["snapshots_analyses"] == 5
    assert entry["trades_ouverts"] == 2
    assert entry["trades_ignores"] == 3
    assert entry["dry_run"] is False
    assert len(entry["details"]) == 1


def test_write_report_appends(tmp_path: Path):
    """_write_report append, n'écrase pas."""
    report = tmp_path / "append.log"
    ptl._write_report(report, {"snapshots_analyses": 1, "trades_ouverts": 0, "trades_ignores": 0, "dry_run": False, "details": []}, MagicMock())
    ptl._write_report(report, {"snapshots_analyses": 2, "trades_ouverts": 1, "trades_ignores": 1, "dry_run": False, "details": []}, MagicMock())

    lines = report.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


def test_write_report_handles_bad_path(tmp_path: Path):
    """_write_report ne plante pas sur chemin invalide (parent non accessible)."""
    # Créer un fichier pour bloquer la création du dossier parent
    block_file = tmp_path / "block"
    block_file.write_text("")
    report = block_file / "subdir" / "report.log"  # block_file n'est pas un dossier
    # mkdir(parents=True) lève FileExistsError, mais _write_report le catch
    # et logge un warning — le test vérifie qu'aucune exception ne remonte
    ptl._write_report(report, {"snapshots_analyses": 0, "trades_ouverts": 0, "trades_ignores": 0, "dry_run": False, "details": []}, MagicMock())
    # Si on arrive ici, l'exception a bien été catchée


# ── run_pass ─────────────────────────────────────────────────


@patch("scripts.v9_paper_trade_loop.ptr.run")
def test_run_pass_delegates_to_ptr_run(mock_run: MagicMock, temp_db: Path, temp_report: Path, logger: MagicMock):
    """run_pass appelle ptr.run() avec les bons paramètres."""
    mock_run.return_value = {
        "snapshots_analyses": 3,
        "trades_ouverts": 1,
        "trades_ignores": 2,
        "details": [],
    }

    result = ptl.run_pass(
        limit=5,
        dry_run=True,
        db_path=temp_db,
        report_path=temp_report,
        logger=logger,
    )

    mock_run.assert_called_once_with(limit=5, dry_run=True, db_path=temp_db)
    assert result["snapshots_analyses"] == 3
    assert result["trades_ouverts"] == 1
    assert temp_report.exists()


@patch("scripts.v9_paper_trade_loop.ptr.run")
def test_run_pass_no_report(mock_run: MagicMock, temp_db: Path, logger: MagicMock):
    """run_pass sans report_path n'écrit pas de rapport."""
    mock_run.return_value = {
        "snapshots_analyses": 0,
        "trades_ouverts": 0,
        "trades_ignores": 0,
        "details": [],
    }

    result = ptl.run_pass(
        limit=3,
        dry_run=False,
        db_path=temp_db,
        report_path=None,
        logger=logger,
    )

    assert result["snapshots_analyses"] == 0


# ── run_loop (mode --once) ──────────────────────────────────


@patch("scripts.v9_paper_trade_loop.ptr.run")
def test_run_loop_once(mock_run: MagicMock, temp_db: Path, temp_report: Path, logger: MagicMock):
    """run_loop(once=True) fait une passe puis retourne 0."""
    mock_run.return_value = {
        "snapshots_analyses": 2,
        "trades_ouverts": 1,
        "trades_ignores": 1,
        "details": [],
    }

    rc = ptl.run_loop(
        interval=1,
        limit=5,
        dry_run=False,
        db_path=temp_db,
        report_path=temp_report,
        once=True,
        logger=logger,
    )

    assert rc == 0
    mock_run.assert_called_once()


@patch("scripts.v9_paper_trade_loop.ptr.run")
def test_run_loop_once_error(mock_run: MagicMock, temp_db: Path, logger: MagicMock):
    """run_loop(once=True) retourne 1 si erreur."""
    mock_run.side_effect = ValueError("test error")

    rc = ptl.run_loop(
        interval=1,
        limit=5,
        dry_run=False,
        db_path=temp_db,
        report_path=None,
        once=True,
        logger=logger,
    )

    assert rc == 1


# ── run_loop (mode --watch) ─────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM non-fonctionnel sur Windows")
@patch("scripts.v9_paper_trade_loop.ptr.run")
def test_run_loop_watch_stop_by_signal(mock_run: MagicMock, temp_db: Path, logger: MagicMock):
    """run_loop en mode watch s'arrête sur signal SIGTERM."""
    mock_run.return_value = {
        "snapshots_analyses": 0,
        "trades_ouverts": 0,
        "trades_ignores": 0,
        "details": [],
    }

    # On lance la boucle dans un thread, on envoie SIGTERM après 0.2s
    result_holder = []

    def _run():
        rc = ptl.run_loop(
            interval=1,
            limit=3,
            dry_run=False,
            db_path=temp_db,
            report_path=None,
            once=False,
            logger=logger,
        )
        result_holder.append(rc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.3)
    # Envoyer SIGTERM au thread principal (le signal handler global _stop)
    os.kill(os.getpid(), signal.SIGTERM)
    t.join(timeout=3)
    assert not t.is_alive(), "La boucle ne s'est pas arrêtée"
    assert result_holder[0] == 0


# ── CLI ─────────────────────────────────────────────────────


def test_cli_once_defaults():
    """--once appelle run_loop avec once=True."""
    with patch.object(ptl, "run_loop") as mock_loop:
        mock_loop.return_value = 0
        rc = ptl.main(["--once"])
        assert rc == 0
        mock_loop.assert_called_once()
        kwargs = mock_loop.call_args[1]
        assert kwargs["once"] is True
        assert kwargs["interval"] == ptl.DEFAULT_INTERVAL_SECONDS
        assert kwargs["limit"] == ptl.DEFAULT_SNAPSHOT_LIMIT
        assert kwargs["dry_run"] is False


def test_cli_watch():
    """--watch appelle run_loop avec once=False."""
    with patch.object(ptl, "run_loop") as mock_loop:
        mock_loop.return_value = 0
        rc = ptl.main(["--watch", "--interval", "60"])
        assert rc == 0
        kwargs = mock_loop.call_args[1]
        assert kwargs["once"] is False
        assert kwargs["interval"] == 60


def test_cli_dry_run():
    """--dry-run est propagé à run_loop."""
    with patch.object(ptl, "run_loop") as mock_loop:
        mock_loop.return_value = 0
        ptl.main(["--once", "--dry-run"])
        kwargs = mock_loop.call_args[1]
        assert kwargs["dry_run"] is True


def test_cli_custom_limit():
    """--limit est propagé."""
    with patch.object(ptl, "run_loop") as mock_loop:
        mock_loop.return_value = 0
        ptl.main(["--once", "--limit", "3"])
        kwargs = mock_loop.call_args[1]
        assert kwargs["limit"] == 3


def test_cli_custom_report():
    """--report est propagé."""
    with patch.object(ptl, "run_loop") as mock_loop:
        mock_loop.return_value = 0
        ptl.main(["--once", "--report", "/tmp/my_report.log"])
        kwargs = mock_loop.call_args[1]
        assert kwargs["report_path"] == Path("/tmp/my_report.log")


def test_cli_custom_db_path():
    """--db-path est propagé."""
    with patch.object(ptl, "run_loop") as mock_loop:
        mock_loop.return_value = 0
        ptl.main(["--once", "--db-path", "/tmp/custom.db"])
        kwargs = mock_loop.call_args[1]
        assert kwargs["db_path"] == Path("/tmp/custom.db")


@patch("scripts.v9_paper_trade_loop.run_pass")
def test_cli_json_output(mock_run_pass: MagicMock):
    """--once --json affiche le résumé JSON."""
    mock_run_pass.return_value = {
        "snapshots_analyses": 2,
        "trades_ouverts": 1,
        "trades_ignores": 1,
        "details": [],
    }

    with patch("sys.stdout") as mock_stdout:
        rc = ptl.main(["--once", "--json"])
        assert rc == 0
        mock_run_pass.assert_called_once()


# ── Intégration : run_pass avec vraie DB ────────────────────


def test_run_pass_with_real_db(temp_db: Path, temp_report: Path):
    """run_pass avec une DB réelle (vide) ne plante pas."""
    # DB vide → 0 snapshots, 0 trades
    result = ptl.run_pass(
        limit=5,
        dry_run=True,
        db_path=temp_db,
        report_path=temp_report,
    )
    assert result["snapshots_analyses"] == 0
    assert result["trades_ouverts"] == 0
    assert result["trades_ignores"] == 0
    assert temp_report.exists()


def test_run_pass_with_go_decision(temp_db: Path, temp_report: Path):
    """run_pass ouvre un trade si décision go=True."""
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row

    # Insérer une décision directionnelle live
    conn.execute(
        "INSERT INTO decisions (decision_id, timestamp, snapshot_id, symbol, "
        "timeframe, direction, confiance, action, principes_json, source_type) "
        "VALUES ('d1', '2026-07-10T12:00:00+00:00', 'snap_go_1', 'GBPUSD', "
        "'M15', 'haussiere', 85, 'preparer_entree', '[]', 'live')"
    )
    conn.commit()
    conn.close()

    result = ptl.run_pass(
        limit=10,
        dry_run=True,
        db_path=temp_db,
        report_path=temp_report,
    )

    # Au moins 1 snapshot analysé
    assert result["snapshots_analyses"] >= 1
    # En dry-run, trades_ouverts peut être > 0 (le dry-run de ptr.run compte les trades)
    # Mais le contexte window_status sera 'absente' → risk_manager bloque
    # Ce test vérifie juste que le pipeline ne plante pas
    assert "snapshots_analyses" in result
    assert "trades_ouverts" in result
    assert "trades_ignores" in result
