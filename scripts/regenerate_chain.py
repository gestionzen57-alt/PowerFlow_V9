#!/usr/bin/env python3
"""regenerate_chain.py — Reconstruit scenes/behaviors/windows/exploitability.

Relit tous les snapshots non-stale de forces_snapshots (data/v9_forces.db),
par ordre chronologique, et les fait traverser la chaîne cognitive complète
via core.v9.orchestrator.run_chain. Utilisé après un nettoyage de doublons
(replay non-idempotent) pour reconstruire un historique cohérent dans
scenes/behaviors/windows/exploitability.

Usage :
    python scripts/regenerate_chain.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.orchestrator import run_chain  # noqa: E402

PROGRESS_EVERY = 50


def main() -> int:
    conn = get_connection(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT snapshot_id FROM forces_snapshots WHERE stale = 0 ORDER BY timestamp ASC"
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    print(f"Snapshots non-stale a traiter : {total}")

    scenes = behaviors = windows = evaluations = errors = 0
    error_details: list[str] = []
    durations_ms: list[float] = []

    for i, (snapshot_id,) in enumerate(rows, start=1):
        t0 = time.perf_counter()
        result = run_chain(snapshot_id)
        durations_ms.append((time.perf_counter() - t0) * 1000)

        if result["scene_id"]:
            scenes += 1
        if result["behavior_id"]:
            behaviors += 1
        if result["window_id"]:
            windows += 1
        if result["exploitability_id"]:
            evaluations += 1
        if result["error"]:
            errors += 1
            error_details.append(f"{snapshot_id}: {result['error']}")

        if i % PROGRESS_EVERY == 0 or i == total:
            print(
                f"[{i}/{total}] scenes={scenes} behaviors={behaviors} "
                f"windows={windows} evaluations={evaluations} erreurs={errors}"
            )

    avg_ms = sum(durations_ms) / len(durations_ms) if durations_ms else 0.0

    print("=" * 60)
    print("Rapport final - Regeneration de la chaine V9")
    print("=" * 60)
    print(f"Snapshots traites          : {total}")
    print(f"Scenes produites           : {scenes}")
    print(f"Comportements qualifies    : {behaviors}")
    print(f"Fenetres produites         : {windows}")
    print(f"Evaluations exploitabilite : {evaluations}")
    print(f"Latence moyenne par snapshot (chaine complete) : {avg_ms:.2f}ms")
    print(f"Erreurs detectees ({errors}):")
    for detail in error_details[:20]:
        print(f"  - {detail}")
    if len(error_details) > 20:
        print(f"  ... et {len(error_details) - 20} autres")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
