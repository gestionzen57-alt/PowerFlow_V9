"""v9_order_queue_watcher.py — ORDER-BRIDGE, CLI opérateur (2026-07-13).

Rapporte et purge l'état de `data/order_queue/` (déposé par
`core/v9/order_executor.py`, lu côté EA MT4 — action opérateur distincte
non modifiée ici). Ne parle jamais à MT4, ne fait aucun appel réseau
(R18) : uniquement du filesystem local via `core/v9/order_queue_watcher.py`.

Usage :
    # Rapport seul (rien n'est modifié) — défaut
    python scripts/v9_order_queue_watcher.py

    # Purge réelle : archive consumed/expired vers data/order_queue/archive/
    python scripts/v9_order_queue_watcher.py --apply

    # Paramètres optionnels
    python scripts/v9_order_queue_watcher.py --apply --expiry-hours 12 \\
        --queue-dir data/order_queue --archive-dir data/order_queue/archive

Sécurité :
- Dry-run par défaut (aucun fichier déplacé).
- Jamais de suppression — les commandes `consumed`/`expired` sont
  déplacées vers `archive_dir`, jamais effacées (traçabilité financière).
- Les commandes `pending` ne sont jamais touchées.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.order_queue_watcher import (  # noqa: E402
    EXPIRY_HOURS_DEFAULT,
    purge_queue,
    scan_queue,
)


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Applique la purge (défaut: dry-run)")
    parser.add_argument("--queue-dir", type=Path, default=None, help="Défaut: data/order_queue/")
    parser.add_argument("--archive-dir", type=Path, default=None, help="Défaut: <queue-dir>/archive/")
    parser.add_argument("--expiry-hours", type=float, default=EXPIRY_HOURS_DEFAULT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = _parse_args(argv)

    entries = scan_queue(args.queue_dir, expiry_hours=args.expiry_hours)
    print(f"[SCAN] {len(entries)} commande(s) dans la file.")
    for entry in entries:
        print(f"  - {entry.command_id}: {entry.status} (age={entry.age_hours:.1f}h)")

    report = purge_queue(
        args.queue_dir,
        archive_dir=args.archive_dir,
        expiry_hours=args.expiry_hours,
        apply=args.apply,
    )
    mode = "APPLIQUÉ" if args.apply else "DRY-RUN"
    print(f"\n[{mode}] pending={report['pending']} "
          f"consumed_archived={report['consumed_archived']} "
          f"expired_archived={report['expired_archived']}")
    if not args.apply and (report["consumed_archived"] or report["expired_archived"]):
        print("Relance avec --apply pour archiver réellement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
