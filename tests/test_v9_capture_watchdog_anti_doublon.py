"""tests/test_v9_capture_watchdog_anti_doublon.py — Tests Phase 151/152 anti-doublon.

Vérifie que `check_no_duplicates()` du watchdog capture_server détecte
correctement les write contention (= cause racine corruption Phase 149) ET
tue les doublons en gardant le port-holder (Phase 152).

Doctrine : R7 (tests verts), R2 additif (nouveau fichier test, 0 modif core/).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import scripts.v9_capture_watchdog as wd


# ── Phase 151 : détection pure ────────────────────────────────────────


def test_check_no_duplicates_zero_when_no_capture() -> None:
    """Aucun capture_server → 0 doublon."""
    with patch.object(wd, "list_capture_pids", return_value=[]):
        killed = wd.check_no_duplicates(kill_extras=False)
    assert killed == 0


def test_check_no_duplicates_zero_when_singleton() -> None:
    """1 seul capture_server → 0 doublon (cas normal)."""
    with patch.object(wd, "list_capture_pids", return_value=[1234]):
        killed = wd.check_no_duplicates(kill_extras=False)
    assert killed == 0


def test_check_no_duplicates_detects_two() -> None:
    """2 capture_server → 1 doublon (cause corruption Phase 149)."""
    with patch.object(wd, "list_capture_pids", return_value=[1234, 5678]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=1234):
            killed = wd.check_no_duplicates(kill_extras=False)
    assert killed == 0  # kill_extras=False → log only


def test_check_no_duplicates_detects_three() -> None:
    """3 capture_server → 2 doublons (cas extrême, write contention triple)."""
    with patch.object(wd, "list_capture_pids", return_value=[1, 2, 3]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=2):
            killed = wd.check_no_duplicates(kill_extras=False)
    assert killed == 0  # kill_extras=False


# ── Phase 152 : kill auto ─────────────────────────────────────────────


def test_check_no_duplicates_kills_extras_when_enabled() -> None:
    """Phase 152 : si doublons détectés, kill les extras (pas le keeper)."""
    with patch.object(wd, "list_capture_pids", return_value=[1234, 5678]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=1234):
            with patch.object(wd.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                killed = wd.check_no_duplicates(kill_extras=True)
    assert killed == 1
    # Vérifie que taskkill a été appelé pour 5678 (l'extra)
    calls = mock_run.call_args_list
    assert any("5678" in str(c) for c in calls)


def test_check_no_duplicates_kills_all_extras_when_3() -> None:
    """Phase 152 : 3 capture_server avec keeper=2 → kill [1, 3] = 2 kills."""
    with patch.object(wd, "list_capture_pids", return_value=[1, 2, 3]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=2):
            with patch.object(wd.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                killed = wd.check_no_duplicates(kill_extras=True)
    assert killed == 2


def test_check_no_duplicates_fallback_when_no_port_holder() -> None:
    """Phase 152 : si port-holder introuvable, garde le 1er de la liste, tue le reste."""
    with patch.object(wd, "list_capture_pids", return_value=[111, 222, 333]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=None):
            with patch.object(wd.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                killed = wd.check_no_duplicates(kill_extras=True)
    assert killed == 2  # 222 + 333 tués, 111 (1er) gardé


# ── Phase 152 : find_pid_on_port_31685 ───────────────────────────────


def test_find_pid_on_port_returns_pid_when_listening() -> None:
    """Phase 152 : netstat parse correctement une ligne LISTENING."""
    fake_output = """
  TCP    127.0.0.1:31685    0.0.0.0:0    LISTENING    1234
  TCP    192.168.1.1:8080    0.0.0.0:0    LISTENING    5678
"""
    with patch.object(wd.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_output, stderr="")
        pid = wd.find_pid_on_port_31685()
    assert pid == 1234


def test_find_pid_on_port_returns_none_when_no_listening() -> None:
    """Phase 152 : retourne None si port non-LISTENING."""
    fake_output = "  TCP    0.0.0.0:80    0.0.0.0:0    LISTENING    9999"
    with patch.object(wd.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_output, stderr="")
        pid = wd.find_pid_on_port_31685()
    assert pid is None


# ── Phase 153 : alerte Telegram ──────────────────────────────────────


def test_send_doublon_alert_message_format() -> None:
    """Phase 153 : message Telegram contient les PIDs et le nombre tués."""
    with patch.object(wd, "send_telegram_alert", return_value=True) as mock_alert:
        ok = wd.send_doublon_alert(
            pids=[100, 200, 300],
            keeper_pid=100,
            killed=[200, 300],
        )
    assert ok is True
    msg = mock_alert.call_args[0][0]
    assert "DOUBLON" in msg
    assert "3" in msg  # 3 pids détectés
    assert "100" in msg  # keeper
    assert "200" in msg
    assert "300" in msg


def test_send_doublon_alert_returns_false_when_send_fails() -> None:
    """Phase 153 : si Telegram échoue, retourne False (best-effort)."""
    with patch.object(wd, "send_telegram_alert", return_value=False):
        ok = wd.send_doublon_alert(
            pids=[1, 2],
            keeper_pid=1,
            killed=[2],
        )
    assert ok is False


def test_check_no_duplicates_alerts_when_kills() -> None:
    """Phase 153 : si doublons tués, alerte Telegram est appelée."""
    with patch.object(wd, "list_capture_pids", return_value=[1234, 5678]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=1234):
            with patch.object(wd.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                with patch.object(wd, "send_doublon_alert", return_value=True) as mock_alert:
                    killed = wd.check_no_duplicates(kill_extras=True, alert=True)
    assert killed == 1
    assert mock_alert.call_count == 1
    # args : pids, keeper_pid, killed
    args = mock_alert.call_args[0]
    assert args[0] == [1234, 5678]
    assert args[1] == 1234
    assert args[2] == [5678]


def test_check_no_duplicates_no_alert_when_no_kills() -> None:
    """Phase 153 : si 0 kill (singleton), alerte NON appelée."""
    with patch.object(wd, "list_capture_pids", return_value=[1234]):
        with patch.object(wd, "send_doublon_alert") as mock_alert:
            killed = wd.check_no_duplicates(kill_extras=True, alert=True)
    assert killed == 0
    assert mock_alert.call_count == 0


def test_check_no_duplicates_alert_disabled() -> None:
    """Phase 153 : alert=False désactive l'envoi Telegram (utile en test)."""
    with patch.object(wd, "list_capture_pids", return_value=[1234, 5678]):
        with patch.object(wd, "find_pid_on_port_31685", return_value=1234):
            with patch.object(wd.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
                with patch.object(wd, "send_doublon_alert") as mock_alert:
                    killed = wd.check_no_duplicates(kill_extras=True, alert=False)
    assert killed == 1
    assert mock_alert.call_count == 0
