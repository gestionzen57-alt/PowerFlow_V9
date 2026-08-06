"""V10 Behavior Migration — peuple le registre depuis les observations V9 (Phase 9, Cognitive Continuum).

Transforme les 55k observations V9 (matière première, sans sens) en
interprétations SIGNIFIÉES dans le registre v10_behaviors (BASE 3, la couche
de cohérence). Chaque ligne = observation V9 (qualification, phase) + contexte
V10 + résultat (si résolu).

C'est la RÉCONCILIATION : on ne reproduit pas le bruit V9, on l'interprète à la
lumière du contexte V10 pour lui donner du sens.

R6 fail-open. R9 : chaque migration tracée. R10 : compute only.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_behavior_registry import record_behavior, registry_summary  # noqa: E402

log = logging.getLogger(__name__)

DEFAULT_SRC = ROOT / "data" / "v9_forces.db"
DEFAULT_OFFSET = 0
DEFAULT_LIMIT = 50000


def migrate_batch(src_db: Path, *, offset: int = 0, limit: int = 50000) -> dict:
    """Migre un batch d'observations V9 → registre v10_behaviors.

    Lit behaviors V9 (qualification, phase, symbol, timeframe) et enregistre
    une interprétation signifiée. Dedup par (symbol, timeframe, qualification,
    timestamp) pour éviter les doublons (pitfall 13 canon).

    R6 fail-open : DB absente → {n_migrated: 0}.
    """
    if not src_db.exists():
        return {"status": "no_db", "n_migrated": 0}
    conn = sqlite3.connect(str(src_db))
    rows = conn.execute(
        "SELECT symbol, timeframe, qualification, phase, timestamp "
        "FROM behaviors ORDER BY timestamp LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()

    n_migrated = 0
    seen = set()
    for symbol, timeframe, qualification, phase, ts in rows:
        if not symbol or not qualification:
            continue
        key = (symbol, timeframe, qualification, ts)
        if key in seen:
            continue
        seen.add(key)
        record_behavior(
            timestamp=ts or "", pair=symbol, timeframe=timeframe,
            observation_qualification=qualification,
            regime_hmm=phase or "",  # on utilise la phase comme régime contextuel
            source_ref=f"v9_behaviors:{symbol}:{qualification}:{ts}",
        )
        n_migrated += 1

    return {"status": "ok", "n_migrated": n_migrated, "n_rows_read": len(rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET)
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = ap.parse_args()

    res = migrate_batch(Path(args.src), offset=args.offset, limit=args.limit)
    print(res)
    print("registre:", registry_summary())
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
