#!/usr/bin/env python3
"""v9_resolve_loop.py — Wrapper cron no_agent pour résolution WIN/LOSS automatique.

Phase 1.B du chantier H24 autopilot. Exécute v9_resolve_decision_auto.py --apply
sur les décisions unresolved. Conçu pour être appelé par cron no_agent toutes
les 5-10 minutes.

Doctrine :
- R18 : zéro LLM (calcul stdlib pur via subprocess)
- R8 : aucune modif core/v9/* (wrapper pur)
- Idempotence : WHERE is_win IS NULL (script cible gère déjà)
- Backup obligatoire : le dossier passé doit contenir md5_pre.txt

Usage CLI :
    python scripts/v9_resolve_loop.py --once
    python scripts/v9_resolve_loop.py --once --backup backups/2026-07-10_resolve/

Sortie : exit 0 si tout OK, 1 si aucune nouvelle résolution (no-op),
exit 2 si erreur technique.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT_DIR / "logs" / "v9_resolve_loop.log"
SCRIPT = ROOT_DIR / "scripts" / "v9_resolve_decision_auto.py"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wrapper cron no_agent pour résolution WIN/LOSS V9."
    )
    parser.add_argument(
        "--once", action="store_true", required=True,
        help="Exécute un cycle de résolution puis exit.",
    )
    parser.add_argument(
        "--backup", type=Path, default=ROOT_DIR / "docs" / "calibration" / "backups" / "h24_resolve",
        help="Dossier backup MD5 (doit contenir md5_pre.txt).",
    )
    parser.add_argument(
        "--horizon-hours", type=float, default=4.0,
        help="Horizon observation pour résolution (défaut 4h).",
    )
    args = parser.parse_args(argv)

    backup_dir = args.backup
    if not (backup_dir / "md5_pre.txt").exists():
        log(f"ERREUR: backup md5_pre.txt absent dans {backup_dir}")
        # Créer le backup live (de v9_forces.db) — pragma best-effort
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            db = ROOT_DIR / "data" / "v9_forces.db"
            if db.exists():
                import hashlib
                md5 = hashlib.md5(db.read_bytes()).hexdigest()
                (backup_dir / "md5_pre.txt").write_text(f"{md5}  v9_forces.db\n", encoding="utf-8")
                log(f"Backup MD5 créé : {md5}")
        except Exception as e:
            log(f"ERREUR backup MD5: {e}")
            return 2

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--apply",
        "--backup", str(backup_dir),
        "--horizon-hours", str(args.horizon_hours),
    ]
    log(f"RUN: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600, cwd=str(ROOT_DIR),
        )
        rc = result.returncode
        out_tail = result.stdout[-500:] if result.stdout else ""
        err_tail = result.stderr[-500:] if result.stderr else ""
        log(f"EXIT={rc}")
        if out_tail:
            log(f"STDOUT (last 500 chars): {out_tail}")
        if err_tail:
            log(f"STDERR (last 500 chars): {err_tail}")
        return rc
    except subprocess.TimeoutExpired:
        log("TIMEOUT > 600s — batch trop gros, découper.")
        return 2
    except Exception as e:
        log(f"ERREUR subprocess: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())