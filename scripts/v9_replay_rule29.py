"""Replay rule 29 — lecture des paramètres zone_type sur DB existante.

Règle 29 (DOCTRINE.md, import V8 §3.1+§3bis+§6+§8, 2026-07-07).
Lecture seule : aucune écriture dans v9_forces.db, aucun appel aux writers
(Arbiter / RiskManager / PaperTradeLogger).

Fonctions :
- ``--behavior <behavior_id>``         : affiche le zone_type d'un behavior précis.
- ``--from <iso> --to <iso>``          : replay sur fenêtre temporelle (par défaut
                                          behaviors M15 GBPUSD du jour).
- ``--snapshot <snapshot_id>``         : affiche le zone_type d'un snapshot
                                          (via _load_shared_context).

Sortie : tableau texte lisible en console. Aucun CSV/JSON auto — l'opérateur
copie-colle dans `workspace/perplexity/JOURNAL.md` ou telegram.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.principle_engine import (  # noqa: E402
    PrincipleEngine,
    _detect_zone_type,
)


# Instance partagée pour replay_snapshot() — `_load_shared_context` est une
# méthode d'instance (mais stateless dans le corps actuel, juste connect via self).
_REPLAY_ENGINE: Optional[PrincipleEngine] = None


def _get_engine(db_path: Optional[Path] = None) -> PrincipleEngine:
    """Instancie un PrincipleEngine en réutilisant l'instance si même chemin."""
    global _REPLAY_ENGINE
    p = Path(db_path) if db_path else Path(DB_PATH)
    if _REPLAY_ENGINE is None or _REPLAY_ENGINE.db_path != p:
        _REPLAY_ENGINE = PrincipleEngine(db_path=p, source_type="replay_rule29")
    return _REPLAY_ENGINE


def _load_context(engine: PrincipleEngine, conn: sqlite3.Connection,
                  snapshot_id: str) -> dict[str, Any]:
    """Wrapper sur l'appel d'instance — encapsule pour testabilité."""
    return engine._load_shared_context(conn, snapshot_id)


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    p = Path(db_path) if db_path else Path(DB_PATH)
    if not p.exists():
        raise FileNotFoundError(f"DB introuvable : {p}")
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def _format_row(ts: str, behavior_id: str, state: str, zone_type: str,
                statut: str, point_rupture: bool, intensite: str) -> str:
    rupture_flag = "RUPT" if point_rupture else "...."
    return (
        f"{ts} | {behavior_id[:30]:30} | state={state:14} | "
        f"zone={zone_type:14} | win={statut:18} | {rupture_flag} | "
        f"intensite={intensite}"
    )


def replay_for_behavior(conn: sqlite3.Connection, behavior_id: str) -> dict[str, Any]:
    """Calcule zone_type + statut fenêtre pour un behavior donné."""
    row = conn.execute(
        "SELECT * FROM behaviors WHERE behavior_id = ?", (behavior_id,)
    ).fetchone()
    if row is None:
        return {"behavior_id": behavior_id, "found": False}

    # Reproduit la logique de principle_engine._load_shared_context : on lit
    # la scène référencée par ce behavior pour calculer zone_type à partir
    # des mêmes champs que la chaîne live.
    ctx: dict[str, Any] = {
        "behavior_id": behavior_id,
        "behavior_qualification": row["qualification"],
        "phase": row["phase"],
        "intensite": row["intensite"],
        "est_variante": bool(row["est_variante"]),
    }
    if row["scene_id_ref"]:
        scene = conn.execute(
            "SELECT * FROM scenes WHERE scene_id = ?", (row["scene_id_ref"],)
        ).fetchone()
        if scene is not None:
            ctx["scene_id"] = scene["scene_id"]
            # Charge la scène précédente si elle existe pour prev_state.
            prev = conn.execute(
                "SELECT * FROM scenes WHERE timestamp < ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (scene["timestamp"],),
            ).fetchone()
            if prev is not None:
                ctx["prev_state"] = (prev["zone_json"] or "{}").strip()[:8] or "NEUTRAL"
            ctx["state"] = (scene["zone_json"] or "").strip()[:8] or "NEUTRAL"

    zone_type = _detect_zone_type(ctx)

    # Lecture du statut fenêtre courant (si déjà calculé) ou recalcul simple.
    win_row = conn.execute(
        "SELECT statut, niveau_confiance FROM windows WHERE behavior_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (behavior_id,),
    ).fetchone()
    statut = win_row["statut"] if win_row else "non_evaluee"
    confiance = win_row["niveau_confiance"] if win_row else None

    return {
        "behavior_id": behavior_id,
        "found": True,
        "ts": row["timestamp"],
        "qualification": row["qualification"],
        "intensite": row["intensite"],
        "state": ctx.get("state", "?"),
        "zone_type": zone_type,
        "window_statut": statut,
        "window_confiance": confiance,
        "point_de_rupture_detecte": bool(row["point_de_rupture_detecte"]),
    }


def replay_window(conn: sqlite3.Connection,
                  ts_from: Optional[str], ts_to: Optional[str],
                  symbol: str = "GBPUSD", timeframe: str = "M15",
                  limit: int = 50) -> list[dict[str, Any]]:
    """Replay des behaviors sur une fenêtre temporelle."""
    where = ["symbol = ?", "timeframe = ?"]
    params: list[Any] = [symbol, timeframe]
    if ts_from:
        where.append("timestamp >= ?")
        params.append(ts_from)
    if ts_to:
        where.append("timestamp <= ?")
        params.append(ts_to)
    rows = conn.execute(
        f"SELECT behavior_id FROM behaviors WHERE {' AND '.join(where)} "
        f"ORDER BY timestamp DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [replay_for_behavior(conn, r["behavior_id"]) for r in rows]


def replay_snapshot(conn: sqlite3.Connection, snapshot_id: str,
                    engine: Optional[PrincipleEngine] = None) -> dict[str, Any]:
    """Lecture zone_type sur un snapshot via _load_shared_context."""
    if engine is None:
        engine = _get_engine()
    ctx = _load_context(engine, conn, snapshot_id)
    return {
        "snapshot_id": snapshot_id,
        "zone_type": ctx.get("zone_type", "indetermine"),
        "state": ctx.get("state"),
        "qualification": ctx.get("qualification"),
        "phase": ctx.get("phase"),
    }


def _print_behavior_result(r: dict[str, Any]) -> None:
    if not r.get("found"):
        print(f"[introuvable] behavior_id={r['behavior_id']}")
        return
    print(
        _format_row(
            r["ts"], r["behavior_id"], r["state"], r["zone_type"],
            r["window_statut"], r["point_de_rupture_detecte"], r["intensite"],
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay rule 29 — lecture zone_type (DOCTRINE §29).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--behavior", metavar="BEHAVIOR_ID",
                       help="Affiche le zone_type d'un behavior précis.")
    group.add_argument("--from", dest="ts_from", metavar="ISO",
                       help="Borne inférieure timestamp ISO (ex: 2026-07-07T09:00).")
    group.add_argument("--snapshot", metavar="SNAPSHOT_ID",
                       help="Affiche le zone_type d'un snapshot via "
                            "_load_shared_context.")
    parser.add_argument("--to", metavar="ISO",
                        help="Borne supérieure (utilisée avec --from).")
    parser.add_argument("--symbol", default="GBPUSD",
                        help="Symbole pour --from (défaut GBPUSD).")
    parser.add_argument("--timeframe", default="M15",
                        help="Timeframe pour --from (défaut M15).")
    parser.add_argument("--limit", type=int, default=50,
                        help="Nombre max de behaviors (défaut 50).")
    parser.add_argument("--db", metavar="PATH",
                        help="Chemin DB alternative (défaut: DB_PATH core/v9/config.py).")
    args = parser.parse_args()

    conn = _connect(Path(args.db) if args.db else None)
    try:
        if args.behavior:
            _print_behavior_result(replay_for_behavior(conn, args.behavior))
            return 0
        if args.snapshot:
            engine = _get_engine(Path(args.db) if args.db else None)
            r = replay_snapshot(conn, args.snapshot, engine=engine)
            print(
                f"snapshot={r['snapshot_id']} | zone_type={r['zone_type']} | "
                f"state={r['state']} | qualification={r['qualification']} | "
                f"phase={r['phase']}"
            )
            return 0
        # --from [--to]
        results = replay_window(
            conn, args.ts_from, args.to,
            symbol=args.symbol, timeframe=args.timeframe, limit=args.limit,
        )
        print(f"=== Replay rule 29 : {len(results)} behavior(s) "
              f"{args.symbol}/{args.timeframe} "
              f"{args.ts_from or '*'} → {args.to or '*'} ===")
        for r in results:
            _print_behavior_result(r)
        # Mini-stats
        zt_counts: dict[str, int] = {}
        for r in results:
            if r.get("found"):
                zt = r.get("zone_type", "indetermine")
                zt_counts[zt] = zt_counts.get(zt, 0) + 1
        print("\n--- Distribution zone_type ---")
        for zt, n in sorted(zt_counts.items(), key=lambda x: -x[1]):
            print(f"  {zt:14} | n={n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
