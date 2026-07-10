#!/usr/bin/env python3
"""v9_meta_agent_emit.py — Émetteur d'événements pour le bus V9 (R8 respectée).

Réveille l'angle mort #1 : le bus `agent_bus` existe mais personne n'émet.
Ce script scanne la DB live et publie 4 familles d'événements détectables
par `v9_meta_agent.py --scan` :

- signal_open : décision action=preparer_entree + confiance >= 80 (ouvre un trade virtuel)
- regime_change : régime détecté ≠ régime précédent pour le même (symbol, TF)
- principle_cluster : >= 3 principes triggered simultanément sur le même snapshot
- high_resolution_win : décision résolue avec WR significatif (post-WIN/LOSS)

Doctrine :
- R8 : lecture seule sur v9_forces.db, écriture uniquement sur agent_bus.db
- R18 : 0 LLM (stdlib pur)
- Best-effort : erreurs sur events individuels ne bloquent pas le batch

Usage :
    python scripts/v9_meta_agent_emit.py --once
    python scripts/v9_meta_agent_emit.py --once --lookback-hours 24
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.agent_bus import AGENT_BUS_DB_PATH, publish  # noqa: E402


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Émetteur d'événements bus V9 (réveille l'apprentissage meta-agent)."
    )
    p.add_argument("--once", action="store_true", required=True)
    p.add_argument("--lookback-hours", type=int, default=24,
                   help="Fenêtre temporelle de scan (défaut 24h).")
    p.add_argument("--dry-run", action="store_true",
                   help="N'émet pas, affiche seulement ce qui serait publié.")
    return p.parse_args(argv)


def _emit_signal_opens(conn: sqlite3.Connection, since: str, dry_run: bool) -> int:
    """Émet un event 'signal_open' pour chaque décision action=preparer_entree confiance>=80."""
    rows = conn.execute("""
        SELECT decision_id, snapshot_id, timestamp, symbol, timeframe,
               direction, confiance, action
        FROM decisions
        WHERE action = 'preparer_entree'
          AND confiance >= 80
          AND timestamp > ?
        ORDER BY timestamp DESC
        LIMIT 100
    """, (since,)).fetchall()

    n = 0
    for r in rows:
        payload = {
            "decision_id": r[0],
            "snapshot_id": r[1],
            "timestamp": r[2],
            "symbol": r[3],
            "timeframe": r[4],
            "direction": r[5],
            "confiance": r[6],
        }
        if dry_run:
            print(f"  [DRY] signal_open {r[0]} dir={r[5]} conf={r[6]}")
        else:
            try:
                publish("signal_open", "v9_meta_agent_emit", payload, severity="info")
                n += 1
            except Exception as e:
                print(f"  ERR signal_open {r[0]}: {e}", file=sys.stderr)
    return n


def _emit_regime_changes(conn: sqlite3.Connection, since: str, dry_run: bool) -> int:
    """Émet un event 'regime_change' quand le régime change entre 2 snapshots consécutifs du même (symbol, TF).

    Stratégie : charge tous les (symbol, TF, timestamp, regime_type) puis
    calcule le delta en Python (LAG() non autorisé dans WHERE en SQLite).
    contexte_complet_json est zlib-compressé → décompression Python.
    """
    rows = conn.execute("""
        SELECT d.snapshot_id, d.timestamp, d.symbol, d.timeframe, d.contexte_complet_json
        FROM decisions d
        WHERE d.timestamp > ?
          AND d.contexte_complet_json IS NOT NULL
        ORDER BY d.symbol, d.timeframe, d.timestamp ASC
    """, (since,)).fetchall()

    prev: dict[tuple[str, str], tuple[str, str]] = {}
    changes: list[tuple] = []
    for r in rows:
        key = (r[2], r[3])
        # Décode zlib → JSON → cherche regime_type
        try:
            data = r[4]
            if isinstance(data, bytes):
                ctx = json.loads(zlib.decompress(data))
            else:
                ctx = json.loads(data)
        except Exception:
            continue
        regimes = ctx.get("regime") or []
        regime = None
        if isinstance(regimes, list) and regimes:
            regime = regimes[0].get("regime_type")
        if regime is None:
            continue
        if key in prev:
            prev_regime, _ = prev[key]
            if prev_regime != regime:
                changes.append((r[0], r[1], r[2], r[3], regime, prev_regime))
        prev[key] = (regime, r[0])

    changes.sort(key=lambda x: x[1], reverse=True)
    changes = changes[:50]

    n = 0
    for r in changes:
        payload = {
            "snapshot_id": r[0],
            "timestamp": r[1],
            "symbol": r[2],
            "timeframe": r[3],
            "regime_new": r[4],
            "regime_prev": r[5],
        }
        if dry_run:
            print(f"  [DRY] regime_change {r[0]} {r[5]} → {r[4]}")
        else:
            try:
                publish("regime_change", "v9_meta_agent_emit", payload, severity="info")
                n += 1
            except Exception as e:
                print(f"  ERR regime_change {r[0]}: {e}", file=sys.stderr)
    return n


def _emit_principle_clusters(conn: sqlite3.Connection, since: str, dry_run: bool) -> int:
    """Émet un event 'principle_cluster' pour chaque snapshot avec >=3 principes triggered."""
    rows = conn.execute("""
        SELECT snapshot_id, COUNT(*) AS n_triggered
        FROM principle_evaluations
        WHERE triggered = 1
          AND timestamp > ?
        GROUP BY snapshot_id
        HAVING n_triggered >= 3
        ORDER BY n_triggered DESC
        LIMIT 50
    """, (since,)).fetchall()

    n = 0
    for r in rows:
        payload = {
            "snapshot_id": r[0],
            "n_triggered": r[1],
        }
        if dry_run:
            print(f"  [DRY] principle_cluster {r[0]} n={r[1]}")
        else:
            try:
                publish("principle_cluster", "v9_meta_agent_emit", payload, severity="info")
                n += 1
            except Exception as e:
                print(f"  ERR principle_cluster {r[0]}: {e}", file=sys.stderr)
    return n


def _emit_high_resolution_wins(conn: sqlite3.Connection, since: str, dry_run: bool) -> int:
    """Émet un event 'high_resolution_win' pour chaque décision résolue avec pips > 20 (significatif)."""
    rows = conn.execute("""
        SELECT decision_id, timestamp, symbol, timeframe, direction,
               resolution_pips, is_win
        FROM decisions
        WHERE is_win = 1
          AND resolution_pips > 20
          AND resolved_at > ?
        ORDER BY resolution_pips DESC
        LIMIT 50
    """, (since,)).fetchall()

    n = 0
    for r in rows:
        payload = {
            "decision_id": r[0],
            "timestamp": r[1],
            "symbol": r[2],
            "timeframe": r[3],
            "direction": r[4],
            "pips": r[5],
        }
        if dry_run:
            print(f"  [DRY] high_resolution_win {r[0]} +{r[5]:.1f} pips")
        else:
            try:
                publish("high_resolution_win", "v9_meta_agent_emit", payload, severity="info")
                n += 1
            except Exception as e:
                print(f"  ERR high_resolution_win {r[0]}: {e}", file=sys.stderr)
    return n


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = _parse_args(argv)

    since_dt = datetime.now(timezone.utc)
    cutoff = (since_dt - timedelta(hours=args.lookback_hours)).isoformat()
    print(f"=== v9_meta_agent_emit — lookback {args.lookback_hours}h (since {cutoff}) ===")
    if args.dry_run:
        print("(DRY-RUN : aucune publication)")
    print()

    if not DB_PATH.exists():
        print(f"ERREUR : DB absente à {DB_PATH}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        n_sig = _emit_signal_opens(conn, cutoff, args.dry_run)
        print(f"signal_open         : {n_sig} events")
        n_reg = _emit_regime_changes(conn, cutoff, args.dry_run)
        print(f"regime_change       : {n_reg} events")
        n_clus = _emit_principle_clusters(conn, cutoff, args.dry_run)
        print(f"principle_cluster   : {n_clus} events")
        n_win = _emit_high_resolution_wins(conn, cutoff, args.dry_run)
        print(f"high_resolution_win : {n_win} events")
        total = n_sig + n_reg + n_clus + n_win
        print()
        print(f"TOTAL : {total} events publiés sur {AGENT_BUS_DB_PATH}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())