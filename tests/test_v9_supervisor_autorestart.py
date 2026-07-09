"""Tests pour le mode --autorestart de v9_supervisor.py.

Périmètre (chantier 2026-07-09 supervision H24) :
- run_autorestart() doit être idempotent et idempotent en présence du serveur live.
- do_release_port=False : on NE TOUCHE PAS au serveur live (PID 7696 en prod).
- On teste via les briques pures (is_server_running, ensure_port_free)
  et via un mock du flux "serveur inactif → relance".

R8 respectée : pas de modif core/v9/*. Pas de dépendance pip.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from scripts.v9_supervisor import (  # noqa: E402
    is_server_running,
    is_port_available,
    ensure_port_free,
    run_autorestart,
)


# ── 1. run_autorestart est idempotent quand le serveur live est OK ──
def test_autorestart_no_op_when_server_alive():
    """Si PID file = serveur live et port légitimement occupé, run_autorestart
    ne fait RIEN (pas de relance, pas d'alerte Telegram, exit 0)."""
    with patch("scripts.v9_supervisor.is_server_running", return_value=(True, 7696)), \
         patch("scripts.v9_supervisor.is_port_available", return_value=False), \
         patch("scripts.v9_supervisor.find_pid_on_port", return_value=7696), \
         patch("scripts.v9_supervisor.start_capture_server_background") as mock_start, \
         patch("scripts.v9_supervisor.ensure_port_free") as mock_free:
        rc = run_autorestart()
        assert rc == 0
        mock_start.assert_not_called()
        mock_free.assert_not_called()


# ── 2. run_autorestart relance le serveur quand inactif ──
def test_autorestart_starts_when_server_inactive():
    """Si is_server_running=False, run_autorestart doit tenter une relance."""
    with patch("scripts.v9_supervisor.is_server_running", return_value=(False, None)), \
         patch("scripts.v9_supervisor.is_port_available", return_value=True), \
         patch("scripts.v9_supervisor.find_pid_on_port", return_value=None), \
         patch("scripts.v9_supervisor.ensure_port_free") as mock_free, \
         patch("scripts.v9_supervisor.start_capture_server_background") as mock_start:
        rc = run_autorestart()
        assert rc == 0
        mock_free.assert_called_once()
        mock_start.assert_called_once()


# ── 3. run_autorestart détecte un PID stale et libère le port ──
def test_autorestart_kills_stale_pid():
    """Si le port est occupé par un PID différent du PID file → stale → kill + relance."""
    with patch("scripts.v9_supervisor.is_server_running", return_value=(True, 9999)), \
         patch("scripts.v9_supervisor.is_port_available", return_value=False), \
         patch("scripts.v9_supervisor.find_pid_on_port", return_value=8888), \
         patch("scripts.v9_supervisor.ensure_port_free") as mock_free, \
         patch("scripts.v9_supervisor.start_capture_server_background") as mock_start:
        rc = run_autorestart()
        assert rc == 0
        # ensure_port_free appelé (libère le port stale)
        mock_free.assert_called_once()
        # start appelé (relance)
        mock_start.assert_called_once()


# ── 4. Alerte Telegram best-effort, jamais bloquante ──
def test_autorestart_telegram_failure_does_not_block():
    """Si Telegram est non configuré ou échoue, run_autorestart doit
    retourner 0 et avoir démarré le serveur quand même."""
    with patch("scripts.v9_supervisor.is_server_running", return_value=(False, None)), \
         patch("scripts.v9_supervisor.is_port_available", return_value=True), \
         patch("scripts.v9_supervisor.find_pid_on_port", return_value=None), \
         patch("scripts.v9_supervisor.ensure_port_free"), \
         patch("scripts.v9_supervisor.start_capture_server_background") as mock_start, \
         patch("pathlib.Path.exists", return_value=False):
        rc = run_autorestart()
        assert rc == 0
        mock_start.assert_called_once()


# ── 5. ensure_port_free : port déjà libre → no-op ──
def test_ensure_port_free_already_free():
    """Si le port est déjà libre, ensure_port_free doit retourner True
    sans appeler kill_pid."""
    with patch("scripts.v9_supervisor.is_port_available", return_value=True), \
         patch("scripts.v9_supervisor.kill_pid") as mock_kill:
        from scripts.v9_supervisor import setup_logging
        logger = setup_logging("test")
        result = ensure_port_free(31685, logger)
        assert result is True
        mock_kill.assert_not_called()
