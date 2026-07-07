#!/usr/bin/env python3
"""c5b_run_claude_code.py — Wrapper pour C-5b (tests v9_ops) via Claude Code.

Usage (par cron ou manuel) :
    python .hermes/c5b_run_claude_code.py

Comportement :
- Lit le prompt dans .hermes/c5b_prompt.txt
- Vérifie que CC est dispo (claude --version)
- Lance claude -p en subprocess avec timeout 15 min
- Log dans logs/c5b_claude_code.log (append, pas overwrite)
- Exit 0 si commit créé, exit 1 sinon
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("D:/Projet/V9").resolve()
PROMPT_FILE = ROOT / ".hermes" / "c5b_prompt.txt"
LOG_FILE = ROOT / "logs" / "c5b_claude_code.log"
TIMEOUT_SEC = 900  # 15 min


def main() -> int:
    if not PROMPT_FILE.exists():
        print(f"[ERREUR] Prompt manquant : {PROMPT_FILE}", file=sys.stderr)
        return 1
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    # Vérif CC dispo
    try:
        ver = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if ver.returncode != 0:
            print(f"[ERREUR] Claude Code indispo : {ver.stderr}", file=sys.stderr)
            return 1
        print(f"[OK] Claude Code version : {ver.stdout.strip()}")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[ERREUR] CC introuvable : {e}", file=sys.stderr)
        return 1

    # Lance CC
    cmd = [
        "claude", "-p", prompt,
        "--add-dir", str(ROOT),
        "--max-turns", "25",
        "--max-budget-usd", "4",
        "--dangerously-skip-permissions",
    ]
    print(f"[RUN] {' '.join(cmd[:3])} ... (max-turns 25, budget $4)")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as logf:
        logf.write(f"\n=== C-5b run {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        try:
            result = subprocess.run(
                cmd, cwd=str(ROOT), stdout=logf, stderr=subprocess.STDOUT,
                timeout=TIMEOUT_SEC
            )
            rc = result.returncode
        except subprocess.TimeoutExpired:
            logf.write(f"\n[TIMEOUT après {TIMEOUT_SEC}s]\n")
            print(f"[TIMEOUT] CC tué après {TIMEOUT_SEC}s")
            return 2
    print(f"[DONE] CC exit code: {rc}")
    # Vérif commit
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=10
        )
        print("=== 3 derniers commits ===")
        print(log.stdout)
    except Exception as e:
        print(f"[WARN] git log failed: {e}")
    return rc


if __name__ == "__main__":
    sys.exit(main())