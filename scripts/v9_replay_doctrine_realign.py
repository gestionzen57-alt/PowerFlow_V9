"""v9_replay_doctrine_realign.py — Replay comparant SignalGenerator
pré-patch (10 principes ACTIVE historiques) vs post-patch (27 ACTIVE,
config.py actuel) — Phase C6 doctrine realign (§R8-levée-doctrine-realign,
DECISIONS_LOG 2026-07-08).

Lecture seule : aucune écriture DB, ne réévalue jamais les principes
(reste sur les lignes principle_evaluations déjà persistées) — seul le
FILTRE d'appartenance à l'ensemble ACTIVE change entre les deux colonnes
comparées (la colonne v9_status persistée en DB reflète toujours l'état
ACTUEL de config.py, jamais l'historique, donc on filtre nous-mêmes sur
principle_id plutôt que de lire cette colonne).

Reproduit l'algorithme de vote de
core/v9/signal_generator.py::SignalGenerator._build_active_signal — à
resynchroniser si cet algorithme change (même convention documentée que
scripts/v9_replay_rule29.py::replay_for_behavior).

Usage :
    python scripts/v9_replay_doctrine_realign.py --hours 24
    python scripts/v9_replay_doctrine_realign.py --days 7
    python scripts/v9_replay_doctrine_realign.py --hours 24 --symbol GBPUSD
    python scripts/v9_replay_doctrine_realign.py --from 2026-07-07T00:00:00Z --to 2026-07-08T00:00:00Z
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, PRINCIPLE_ACTIVE_IDS, SIGNAL_CONFIANCE_HORIZON_COURT  # noqa: E402
from core.v9.signal_generator import SymbolCurrencies  # noqa: E402

# Ensemble ACTIVE historique pré-patch (avant C1, DECISIONS_LOG
# 2026-07-08 §R8-levée-doctrine-realign) — figé ici volontairement.
# config.PRINCIPLE_ACTIVE_IDS ne porte plus que l'ensemble post-patch
# (27) ; ce script existe précisément pour rejouer contre l'ancien état.
PRE_PATCH_ACTIVE_IDS = frozenset({
    "ANTAGONIST_NODE", "COALITION_NODE", "ELASTIC_BREATH",
    "GRAVITY_RESPRING_NODE", "NODE_BIRTH_FAST",
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT", "PRICE_LAG_AT_NODE_BIRTH",
    "RAW_NODE_BIRTH", "ZONE_RETEST", "GRAMMAR_REGIME",
})
POST_PATCH_ACTIVE_IDS = frozenset(PRINCIPLE_ACTIVE_IDS)


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    p = Path(db_path) if db_path else Path(DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"DB introuvable : {p}")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def _build_vote(
    rows: list[sqlite3.Row], active_ids: frozenset, confiance_horizon_court: int
) -> dict[str, Any]:
    """Reproduit SignalGenerator._build_active_signal (core/v9/signal_generator.py),
    filtré sur `active_ids` au lieu de la colonne v9_status persistée."""
    triggered = [r for r in rows if r["principle_id"] in active_ids and r["triggered"]]
    directions = [r["direction"] for r in triggered if r["direction"]]
    vote = Counter(directions)
    if not vote:
        direction = "neutre"
    else:
        top_count = max(vote.values())
        leaders = [d for d, c in vote.items() if c == top_count]
        direction = leaders[0] if len(leaders) == 1 else "neutre"

    confidences = [r["confidence"] for r in triggered if r["confidence"] is not None]
    confiance = round(sum(confidences) / len(confidences)) if confidences else 0
    confiance = max(0, min(100, confiance))
    horizon = "court_terme" if confiance >= confiance_horizon_court else "surveillance"

    return {
        "direction": direction,
        "confiance": confiance,
        "horizon": horizon,
        "n_triggered": len(triggered),
        "principes_source": sorted({r["principle_id"] for r in triggered}),
    }


def replay_snapshot(
    conn: sqlite3.Connection, snapshot_id: str, symbol: str, confiance_horizon_court: int
) -> dict[str, Any]:
    currencies = SymbolCurrencies.from_symbol(symbol)
    rows = conn.execute(
        "SELECT principle_id, currency, triggered, direction, confidence "
        "FROM principle_evaluations WHERE snapshot_id = ? AND currency IN (?, ?)",
        (snapshot_id, currencies.base, currencies.quote),
    ).fetchall()

    pre = _build_vote(rows, PRE_PATCH_ACTIVE_IDS, confiance_horizon_court)
    post = _build_vote(rows, POST_PATCH_ACTIVE_IDS, confiance_horizon_court)

    return {
        "snapshot_id": snapshot_id,
        "pre": pre,
        "post": post,
        "identique": pre["direction"] == post["direction"] and pre["confiance"] == post["confiance"],
    }


def replay_window(
    conn: sqlite3.Connection, ts_from: str, ts_to: str, symbol: str, confiance_horizon_court: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT DISTINCT snapshot_id FROM principle_evaluations "
        "WHERE timestamp >= ? AND timestamp <= ? AND symbol = ? "
        "ORDER BY timestamp ASC",
        (ts_from, ts_to, symbol),
    ).fetchall()
    return [
        replay_snapshot(conn, r["snapshot_id"], symbol, confiance_horizon_court)
        for r in rows
    ]


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Replay doctrine realign — SignalGenerator pré-patch "
                     "(10 ACTIVE) vs post-patch (27 ACTIVE).",
    )
    parser.add_argument("--hours", type=float, default=24.0, help="Fenêtre en heures (défaut 24).")
    parser.add_argument("--days", type=float, help="Fenêtre en jours (prioritaire sur --hours).")
    parser.add_argument("--symbol", default="GBPUSD", help="Symbole (défaut GBPUSD).")
    parser.add_argument("--db", metavar="PATH", help="Chemin DB alternative (défaut DB_PATH).")
    parser.add_argument("--from", dest="ts_from", metavar="ISO",
                        help="Borne inférieure explicite (remplace --hours/--days).")
    parser.add_argument("--to", dest="ts_to", metavar="ISO",
                        help="Borne supérieure explicite (défaut: maintenant).")
    args = parser.parse_args()

    if args.ts_from:
        ts_from = args.ts_from
        ts_to = args.ts_to or datetime.now(timezone.utc).isoformat()
    else:
        hours = args.days * 24 if args.days else args.hours
        now = datetime.now(timezone.utc)
        ts_from = (now - timedelta(hours=hours)).isoformat()
        ts_to = now.isoformat()

    conn = _connect(Path(args.db) if args.db else None)
    try:
        results = replay_window(conn, ts_from, ts_to, args.symbol, SIGNAL_CONFIANCE_HORIZON_COURT)

        print(
            f"=== Replay doctrine realign : {len(results)} snapshot(s) {args.symbol} "
            f"{ts_from} -> {ts_to} ==="
        )
        print(f"Pré-patch  ACTIVE ({len(PRE_PATCH_ACTIVE_IDS)}) : {sorted(PRE_PATCH_ACTIVE_IDS)}")
        print(f"Post-patch ACTIVE ({len(POST_PATCH_ACTIVE_IDS)}) : {len(POST_PATCH_ACTIVE_IDS)} principes\n")

        n_diff = 0
        for r in results:
            if not r["identique"]:
                n_diff += 1
                print(
                    f"[DIFF] {r['snapshot_id']} | "
                    f"pre={r['pre']['direction']}/{r['pre']['confiance']} | "
                    f"post={r['post']['direction']}/{r['post']['confiance']}"
                )

        print("\n--- Bilan ---")
        print(f"  Snapshots comparés : {len(results)}")
        print(f"  Divergences pré/post-patch : {n_diff}")
        if results and n_diff == 0:
            print(
                "  -> Aucune divergence : le patch doctrine realign n'a modifié aucun "
                "signal déjà produit (attendu : les 17 principes nouvellement ACTIVE "
                "sont kind=grammar, conditions vides, structurellement non-émetteurs)."
            )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
