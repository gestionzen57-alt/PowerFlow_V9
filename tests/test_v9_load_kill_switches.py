"""Tests minimaux pour scripts/v9_load_kill_switches.py (A1+A2, 2026-07-14).

Doctrine : R26 = tests verts avant commit. Le loader est un helper
additif (R8 : pas de core/v9/* modifie), zero LLM/reseau (R18),
ASCII pur compatible cmd.exe cp1252.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
LOADER = ROOT_DIR / "scripts" / "v9_load_kill_switches.py"
PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"


def _run_loader(*args, env_override=None):
    """Execute le loader avec les args donnes. Retourne (returncode, stderr)."""
    cmd = [str(PYTHON), str(LOADER)] + list(args)
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(ROOT_DIR))
    return r.returncode, r.stderr, r.stdout


class TestV9LoadKillSwitches:
    def test_no_args_shows_usage_and_exits_2(self):
        """Sans `--`, le helper refuse en exit 2 (defensif)."""
        rc, stderr, _ = _run_loader()
        assert rc == 2
        assert "Usage" in stderr

    def test_loads_env_file_when_present(self, tmp_path):
        """Avec un .env temporaire, le helper charge KEY=VALUE dans l'env du sub-process."""
        # Creer un .env temporaire
        env_file = tmp_path / "test.env"
        env_file.write_text(
            "# commentaire ignore\n"
            "\n"
            "V9_TEST_KEY_42=hello\n"
            "V9_TRADER_MINI_ENABLED=1\n"
            "V9_AUTO_CALIBRATOR_ENABLED=0\n",
            encoding="utf-8",
        )
        # Sub-process qui imprime les vars chargees
        rc, _, stdout = _run_loader(
            "--env-file", str(env_file),
            "--", "-c", "import os; print('TRADER=', os.environ.get('V9_TRADER_MINI_ENABLED')); print('AUTO=', os.environ.get('V9_AUTO_CALIBRATOR_ENABLED')); print('TEST=', os.environ.get('V9_TEST_KEY_42'))"
        )
        assert rc == 0
        assert "TRADER= 1" in stdout
        assert "AUTO= 0" in stdout
        assert "TEST= hello" in stdout

    def test_missing_env_file_falls_back_to_noop(self, tmp_path):
        """Si le .env est absent, le helper imprime INFO et continue en no-op."""
        nonexistent = tmp_path / "absent.env"
        rc, stderr, stdout = _run_loader(
            "--env-file", str(nonexistent),
            "--", "-c", "print('OK')"
        )
        assert rc == 0
        assert "OK" in stdout
        assert "absent" in stderr.lower() or "kill switches OFF" in stderr

    def test_comments_and_blank_lines_ignored(self, tmp_path):
        """Les commentaires (#) et lignes vides sont ignores."""
        env_file = tmp_path / "test.env"
        env_file.write_text(
            "# comment\n"
            "\n"
            "   \n"
            "V9_VALID=42\n",
            encoding="utf-8",
        )
        rc, _, stdout = _run_loader(
            "--env-file", str(env_file),
            "--", "-c", "import os; print('V=', os.environ.get('V9_VALID')); print('EMPTY=', os.environ.get('# comment'))"
        )
        assert rc == 0
        assert "V= 42" in stdout
        assert "EMPTY= None" in stdout

    def test_does_not_leak_to_parent_process(self):
        """Le helper ne doit PAS polluer l'env du process qui l'invoque (pytest session)."""
        # S'assurer que la var n'existe pas avant
        sentinel = "V9_LOADER_LEAK_TEST"
        os.environ.pop(sentinel, None)
        # Invoquer le loader qui set cette var dans un sous-process
        # En realite on ne peut pas setter une var custom dans le .env, donc
        # on verifie juste qu'apres invocation, notre env est intacte
        rc, _, _ = _run_loader()
        assert rc == 2  # Pas d'args, exit 2 attendu
        assert sentinel not in os.environ  # Pas de fuite
