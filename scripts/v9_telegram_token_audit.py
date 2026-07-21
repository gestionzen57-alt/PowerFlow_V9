#!/usr/bin/env python
"""v9_telegram_token_audit.py — Audit tokens Telegram (lecture seule).

Vérifie la présence/état des tokens Telegram sur 3 axes :
1. Fichiers locaux (.env, config/telegram.json, .bak)
2. Historique git (fichiers trackés contenant des tokens)
3. Format valide (8-10 chiffres : 30+ chars base64)

Doctrine : R8 (traçabilité sécurité), R22 (pas d'auto-modif — alerte seule).

Usage :
    python scripts/v9_telegram_token_audit.py            # audit complet
    python scripts/v9_telegram_token_audit.py --json     # sortie JSON
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Pattern Telegram bot token : 8-10 chiffres, ":", 35 chars base64 URL-safe
TOKEN_PATTERN = re.compile(r"\b(\d{8,10}:A[A-Za-z0-9_\-]{30,})\b")
REDACTED = "***REDACTED***"

CHECK_PATHS = [
    ROOT / ".env",
    ROOT / "config" / "telegram.json",
    ROOT / "config" / "telegram.json.bak.20260717",
    ROOT / "config" / "telegram.json.example",
]


def _redact(text: str) -> str:
    return TOKEN_PATTERN.sub(REDACTED, text)


def _scan_local() -> dict:
    """Scanne les fichiers locaux pour tokens Telegram."""
    findings = []
    for p in CHECK_PATHS:
        if not p.exists():
            findings.append({"path": str(p.relative_to(ROOT)), "exists": False, "tokens": 0})
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            matches = TOKEN_PATTERN.findall(content)
            findings.append({
                "path": str(p.relative_to(ROOT)),
                "exists": True,
                "tokens": len(matches),
                "redacted": _redact(content)[:300] if matches else None,
            })
        except Exception as e:
            findings.append({
                "path": str(p.relative_to(ROOT)),
                "exists": True,
                "error": str(e),
            })
    return findings


def _scan_git_history() -> dict:
    """Cherche les tokens Telegram dans l'historique git des fichiers trackés."""
    tracked_files = [
        "config/telegram.json",
        "config/telegram.json.bak.20260717",
        ".env",
    ]
    tracked_files = [f for f in tracked_files if not str(ROOT / f) in CHECK_PATHS or (ROOT / f).exists()]

    leaks = []
    for filepath in tracked_files:
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--oneline", "-p", "--", filepath],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                leaks.append({"file": filepath, "error": result.stderr[:200]})
                continue
            matches = TOKEN_PATTERN.findall(result.stdout)
            if matches:
                leaks.append({
                    "file": filepath,
                    "tokens_in_history": len(matches),
                    "unique_tokens": sorted(set(matches)),
                })
        except Exception as e:
            leaks.append({"file": filepath, "error": str(e)})
    return leaks


def audit() -> dict:
    return {
        "local_scan": _scan_local(),
        "git_history_scan": _scan_git_history(),
        "recommendation": (
            "CEO Søn : @BotFather /revoke × 4, /token × 2, "
            "puis git filter-repo sur config/telegram.json.bak.20260717."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 Telegram Token Audit (lecture seule)")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args()

    report = audit()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== Audit Tokens Telegram (lecture seule) ===\n")
        print("Scan local :")
        for f in report["local_scan"]:
            mark = "🔴" if f.get("tokens", 0) > 0 else ("🟢" if f.get("exists") else "⚪")
            print(f"  {mark} {f['path']} : {f.get('tokens', '?')} token(s)")
        print("\nHistorique git (fichiers trackés) :")
        if not report["git_history_scan"]:
            print("  🟢 Aucune fuite détectée")
        else:
            for f in report["git_history_scan"]:
                if "tokens_in_history" in f:
                    print(f"  🔴 {f['file']} : {f['tokens_in_history']} occurrence(s) dans l'historique")
                    for t in f["unique_tokens"]:
                        print(f"      → {t[:6]}…{t[-6:]}")
                else:
                    print(f"  ⚠️ {f['file']} : {f.get('error', 'erreur inconnue')[:80]}")
        print(f"\nRecommandation : {report['recommendation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
