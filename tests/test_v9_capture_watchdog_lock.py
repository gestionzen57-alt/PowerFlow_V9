"""tests/test_v9_capture_watchdog_lock.py — Tests Phase 170 single-instance lock.

Verifie que `_acquire_lock()` du watchdog capture_server :
  1. Acquiert le lock si le fichier est absent (cas normal au boot).
  2. Acquiert le lock si le PID est mort (stale recovery, R6 fail-open).
  3. Refuse l'acquisition si un PID VIVANT tient deja le lock (doublon).
  4. Libere le lock proprement via `_release_lock()` si on est le owner.
  5. Ne libere PAS le lock si on n'est pas le owner (concurrence).

Doctrine : R7 (tests verts), R2 additif (nouveau fichier test, 0 modif core/).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.v9_capture_watchdog as wd


# ── Helpers de mock ────────────────────────────────────────────


def _mock_get_process_stdout(pid: int, alive: bool) -> str:
    """Genere la sortie PowerShell simulee pour Get-Process."""
    if alive:
        return f"python\n"
    return ""


# ── Phase 170 : _acquire_lock ──────────────────────────────────


def test_acquire_lock_succeeds_when_no_file(tmp_path: Path) -> None:
    """Cas 1 : pas de lock file → on ecrit notre PID, retourne True."""
    fake_lock = tmp_path / ".watchdog.lock"
    assert not fake_lock.exists()
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        with patch.object(wd, "_pid_alive", return_value=True):
            ok = wd._acquire_lock()
    assert ok is True
    assert fake_lock.exists()
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == wd._MY_PID


def test_acquire_lock_succeeds_when_own_pid(tmp_path: Path) -> None:
    """Cas bonus : lock contient deja notre PID (re-import) → retourne True."""
    fake_lock = tmp_path / ".watchdog.lock"
    fake_lock.write_text(str(wd._MY_PID), encoding="utf-8")
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        with patch.object(wd, "_pid_alive", return_value=True):
            ok = wd._acquire_lock()
    assert ok is True
    # Pas d'ecriture supplementaire (meme PID, fichier identique).
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == wd._MY_PID


def test_acquire_lock_recovers_stale_when_dead_pid(tmp_path: Path) -> None:
    """Cas 2 : lock stale (PID mort) → on ecrase, retourne True (R6 fail-open)."""
    fake_lock = tmp_path / ".watchdog.lock"
    fake_lock.write_text("999999", encoding="utf-8")  # PID mort (clairement)
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        with patch.object(wd, "_pid_alive", return_value=False):  # mort
            ok = wd._acquire_lock()
    assert ok is True
    # Notre PID a pris le pas sur l'ancien.
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == wd._MY_PID


def test_acquire_lock_refuses_when_alive_other_pid(tmp_path: Path) -> None:
    """Cas 3 : un autre watchdog VIVANT tient le lock → False (doublon)."""
    fake_lock = tmp_path / ".watchdog.lock"
    other_pid = 999999
    fake_lock.write_text(str(other_pid), encoding="utf-8")
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        with patch.object(wd, "_pid_alive", return_value=True):  # vivant !
            ok = wd._acquire_lock()
    assert ok is False
    # Le lock N'a PAS ete ecrase.
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == other_pid


def test_acquire_lock_handles_corrupt_lock_file(tmp_path: Path) -> None:
    """Cas 4 : lock file corrompu (non-numerique) → on ecrase, retourne True."""
    fake_lock = tmp_path / ".watchdog.lock"
    fake_lock.write_text("not-a-pid\n", encoding="utf-8")
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        ok = wd._acquire_lock()
    assert ok is True
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == wd._MY_PID


# ── Phase 170 : _release_lock ──────────────────────────────────


def test_release_lock_removes_when_owner(tmp_path: Path) -> None:
    """Cas 5 : si on est le owner du lock, _release_lock le supprime."""
    fake_lock = tmp_path / ".watchdog.lock"
    fake_lock.write_text(str(wd._MY_PID), encoding="utf-8")
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        wd._release_lock()
    assert not fake_lock.exists()


def test_release_lock_preserves_when_not_owner(tmp_path: Path) -> None:
    """Cas 6 : si on N'est PAS le owner, _release_lock ne touche PAS."""
    fake_lock = tmp_path / ".watchdog.lock"
    other_pid = 999999
    fake_lock.write_text(str(other_pid), encoding="utf-8")
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        wd._release_lock()
    # Toujours la, intact.
    assert fake_lock.exists()
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == other_pid


def test_release_lock_silent_when_no_file(tmp_path: Path) -> None:
    """Cas 7 : _release_lock ne crash pas si le lock est absent (best-effort)."""
    fake_lock = tmp_path / ".watchdog.lock"
    assert not fake_lock.exists()
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        wd._release_lock()  # ne doit PAS lever
    assert not fake_lock.exists()


# ── Phase 170 : _read_lock_pid / _write_lock_atomic ────────────


def test_read_lock_pid_returns_zero_when_no_file(tmp_path: Path) -> None:
    """Cas 8 : _read_lock_pid retourne 0 si fichier absent."""
    fake_lock = tmp_path / ".watchdog.lock"
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        assert wd._read_lock_pid() == 0


def test_read_lock_pid_returns_zero_when_garbage(tmp_path: Path) -> None:
    """Cas 9 : _read_lock_pid retourne 0 si contenu non-numerique."""
    fake_lock = tmp_path / ".watchdog.lock"
    fake_lock.write_text("garbage", encoding="utf-8")
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        assert wd._read_lock_pid() == 0


def test_write_lock_atomic_creates_file(tmp_path: Path) -> None:
    """Cas 10 : _write_lock_atomic ecrit le PID dans un fichier valide."""
    fake_lock = tmp_path / ".watchdog.lock"
    with patch.object(wd, "_LOCK_FILE", fake_lock):
        wd._write_lock_atomic(42)
    assert fake_lock.exists()
    assert int(fake_lock.read_text(encoding="utf-8").strip()) == 42
    # Pas de fichier .tmp residue.
    assert not fake_lock.with_suffix(fake_lock.suffix + ".tmp").exists()


def test_write_lock_atomic_creates_parent_dir(tmp_path: Path) -> None:
    """Cas 11 : _write_lock_atomic cree le dossier parent si absent."""
    nested = tmp_path / "logs" / ".watchdog.lock"
    with patch.object(wd, "_LOCK_FILE", nested):
        wd._write_lock_atomic(123)
    assert nested.exists()
    assert int(nested.read_text(encoding="utf-8").strip()) == 123


# ── Phase 170 : _pid_alive ─────────────────────────────────────


def test_pid_alive_returns_false_for_zero() -> None:
    """Cas 12 : PID 0 → False (jamais vivant)."""
    assert wd._pid_alive(0) is False


def test_pid_alive_returns_false_for_negative() -> None:
    """Cas 13 : PID negatif → False (jamais vivant)."""
    assert wd._pid_alive(-1) is False


def test_pid_alive_returns_true_when_powershell_says_python() -> None:
    """Cas 14 : si Get-Process sort 'python', _pid_alive retourne True."""
    fake_output = "python\n"
    with patch.object(wd.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_output, stderr="")
        alive = wd._pid_alive(12345)
    assert alive is True


def test_pid_alive_returns_false_when_powershell_empty() -> None:
    """Cas 15 : si Get-Process sort vide (PID introuvable), False."""
    with patch.object(wd.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        alive = wd._pid_alive(999999)
    assert alive is False


def test_pid_alive_returns_false_when_subprocess_fails() -> None:
    """Cas 16 : si subprocess leve (timeout, etc.), False (R6 fail-open)."""
    with patch.object(wd.subprocess, "run", side_effect=Exception("boom")):
        alive = wd._pid_alive(12345)
    assert alive is False
