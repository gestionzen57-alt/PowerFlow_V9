"""v9_load_kill_switches.py — Charge config/v9_kill_switches.env et exec un sous-process.

Origine : motion CEO 2026-07-14 (A1+A2, voir DECISIONS_LOG §2026-07-14).

Mode d'emploi (depuis v9_run_with_kill_switches.bat ou directement) :
    python scripts/v9_load_kill_switches.py -- <script.py> [args...]

Sortie : exit code du sous-process execute avec les env vars posees.

Doctrine :
- R8  : helper pur, aucun core/v9/* modifie.
- R18 : pas de LLM / reseau.
- R25' : switches OFF par defaut dans le code, ce helper ne fait que
  poser l'env var au niveau du process avant exec.
"""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV = ROOT_DIR / "config" / "v9_kill_switches.env"
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"


def _load_env(env_path: Path) -> int:
    if not env_path.exists():
        print(f"[INFO] {env_path} absent - kill switches OFF (defaut).", file=sys.stderr)
        return 0
    loaded = 0
    with env_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            os.environ[key] = value
            loaded += 1
    print(f"[OK] {loaded} kill switch(es) charge(s) depuis {env_path}", file=sys.stderr)
    return loaded


def main() -> int:
    if "--" not in sys.argv:
        print("Usage: v9_load_kill_switches.py -- <script.py> [args...]", file=sys.stderr)
        return 2

    sep = sys.argv.index("--")
    env_path = Path(DEFAULT_ENV)
    # Permettre --env-file avant le --
    if "--env-file" in sys.argv[:sep]:
        i = sys.argv.index("--env-file")
        if i + 1 < sep:
            env_path = Path(sys.argv[i + 1])

    _load_env(env_path)

    sub_args = sys.argv[sep + 1:]
    if not sub_args:
        print("[INFO] Aucun script apres `--`. Wrapper no-op.", file=sys.stderr)
        return 0

    # Exec via le python du venv pour etre coherent avec le reste des scripts
    cmd = [str(VENV_PYTHON)] + sub_args
    return subprocess.call(cmd, cwd=str(ROOT_DIR))


if __name__ == "__main__":
    sys.exit(main())
