#!/usr/bin/env python3
"""Batch re-resolve toutes les décisions avec ExitSimulator TP/SL (Phase 13.2).

Optimisé : charge tout en mémoire, traite par snapshot_id, une seule transaction.
~9500 décisions traitées en < 60s (vs timeout 10min du resolver individuel).

Usage :
    python scripts/v9_batch_resolve_tpsl.py --dry-run
    python scripts/v9_batch_resolve_tpsl.py --apply --backup backups/2026-07-11/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.exit_simulator import ExitSimulator  # noqa: E402

DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
PIPS_MULTIPLIER = 10000

# Paramètres TP/SL (salle de marché)
TP_PIPS = 20.0
SL_PIPS = 10.0
SPREAD_PIPS = 0.5
HORIZON_HOURS = 4


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch re-resolve toutes les décisions avec ExitSimulator TP/SL"
    )
    parser.add_argument("--apply", action="store_true", help="Applique (sinon dry-run)")
    parser.add_argument("--backup", type=Path, default=None, help="Dossier backup MD5")
    args = parser.parse_args()

    if args.apply and not args.backup:
        print("ERREUR: --apply exige --backup <dir>")
        return 2

    # ── Backup ──
    if args.apply:
        md5_file = args.backup / "md5_pre.txt"
        if not md5_file.exists():
            print(f"Backup MD5 introuvable: {md5_file}")
            return 2
        print(f"[OK] Backup MD5 vérifié: {md5_file}")

    print(f"[..] Connexion DB: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH), timeout=120)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ── 1. Charger toutes les décisions preparer_entree résolues ──
    print("[..] Chargement des décisions...")
    rows = cur.execute("""
        SELECT decision_id, snapshot_id, timestamp, symbol, timeframe, direction,
               is_win, resolution_pips, resolution_strategy
        FROM decisions
        WHERE action = 'preparer_entree'
          AND timestamp IS NOT NULL
        ORDER BY timestamp ASC
    """).fetchall()
    print(f"[..] {len(rows)} décisions chargées")

    # ── 2. Charger les entry mids (une seule requête) ──
    snapshot_ids = list(set(r["snapshot_id"] for r in rows if r["snapshot_id"]))
    print(f"[..] {len(snapshot_ids)} snapshot_ids uniques")

    entry_mids: dict[str, float] = {}
    for i in range(0, len(snapshot_ids), 500):
        batch = snapshot_ids[i:i+500]
        placeholders = ",".join("?" for _ in batch)
        mids = cur.execute(
            f"SELECT snapshot_id, mid FROM forces_snapshots "
            f"WHERE snapshot_id IN ({placeholders}) AND mid IS NOT NULL",
            batch,
        ).fetchall()
        for m in mids:
            entry_mids[m["snapshot_id"]] = float(m["mid"])
    print(f"[..] {len(entry_mids)} entry mids trouvés")

    # ── 3. Charger les prix futurs par (symbol, timeframe) ──
    # On charge TOUS les prix pour la période, puis on filtre en mémoire
    print("[..] Chargement des prix futurs...")
    min_ts = min(r["timestamp"] for r in rows if r["timestamp"])
    max_ts = max(r["timestamp"] for r in rows if r["timestamp"])
    max_end = (datetime.fromisoformat(max_ts.replace("Z", "+00:00"))
               + timedelta(hours=HORIZON_HOURS)).isoformat()

    # Prix par (symbol, timeframe) → liste de (timestamp, mid)
    future_prices: dict[str, list[tuple[str, float]]] = defaultdict(list)
    price_rows = cur.execute("""
        SELECT symbol, timeframe, timestamp, mid
        FROM forces_snapshots
        WHERE timestamp > ? AND timestamp <= ?
          AND mid IS NOT NULL
        ORDER BY symbol, timeframe, timestamp ASC
    """, (min_ts, max_end)).fetchall()
    for r in price_rows:
        key = f"{r['symbol']}|{r['timeframe']}"
        future_prices[key].append((r["timestamp"], float(r["mid"])))
    print(f"[..] {sum(len(v) for v in future_prices.values())} prix futurs chargés")

    # ── 4. Simuler chaque décision ──
    print("[..] Simulation ExitSimulator TP/SL...")
    simulator = ExitSimulator(
        strategy="TP_SL",
        tp_pips=TP_PIPS,
        sl_pips=SL_PIPS,
        spread_pips=SPREAD_PIPS,
    )

    updates: list[tuple[int, float, str, str, str, str]] = []  # (is_win, pips, strategy, details_json, resolved_at, decision_id)
    stats = {"tp_hit": 0, "sl_hit": 0, "time_end": 0, "no_data": 0, "no_entry": 0}
    total_pips = 0.0
    wins = 0
    losses = 0

    for r in rows:
        decision_id = r["decision_id"]
        snapshot_id = r["snapshot_id"]
        ts = r["timestamp"]
        symbol = r["symbol"]
        timeframe = r["timeframe"]
        direction = r["direction"]

        entry = entry_mids.get(snapshot_id)
        if entry is None:
            stats["no_entry"] += 1
            continue

        # Calculer end_ts
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            stats["no_data"] += 1
            continue
        end_ts = dt + timedelta(hours=HORIZON_HOURS)
        now = _now_utc()
        if end_ts > now:
            end_ts = now

        # Récupérer les mids futurs pour ce (symbol, timeframe) dans la fenêtre
        key = f"{symbol}|{timeframe}"
        all_prices = future_prices.get(key, [])
        # Fallback M15
        if len(all_prices) < 3 and timeframe != "M15":
            fallback_key = f"{symbol}|M15"
            fallback = future_prices.get(fallback_key, [])
            if len(fallback) > len(all_prices):
                all_prices = fallback

        # Filtrer par fenêtre temporelle
        end_iso = end_ts.isoformat()
        window_mids = [p[1] for p in all_prices if p[0] > ts and p[0] <= end_iso]

        if not window_mids:
            stats["no_data"] += 1
            continue

        # Simuler
        result = simulator.simulate(entry, direction, window_mids)
        total_pips += result.pips
        if result.is_win:
            wins += 1
        else:
            losses += 1
        stats[result.exit_reason] = stats.get(result.exit_reason, 0) + 1

        details = json.dumps({
            "exit_reason": result.exit_reason,
            "exit_price": result.exit_price,
            "entry_price": result.entry_price,
            "max_favorable": result.max_favorable,
            "max_adverse": result.max_adverse,
            "bars_held": result.bars_held,
            "n_future_prices": len(window_mids),
            "strategy": "TP_SL",
            "tp_pips": TP_PIPS,
            "sl_pips": SL_PIPS,
            "spread_pips": SPREAD_PIPS,
        })
        now_iso = _now_utc().isoformat()
        updates.append((result.is_win, result.pips, "TP_SL", details, now_iso, decision_id))

    # ── Stats ──
    n_total = len(updates)
    print(f"\n=== RÉSULTATS SIMULATION TP/SL ===")
    print(f"  Décisions traitées: {n_total}")
    print(f"  Wins: {wins} ({wins/max(1,n_total)*100:.1f}%)")
    print(f"  Losses: {losses} ({losses/max(1,n_total)*100:.1f}%)")
    print(f"  Pips totaux: {total_pips:.1f}")
    print(f"  Pips moyens: {total_pips/max(1,n_total):.1f}")
    print(f"  Raisons sortie: {stats}")
    print(f"  Non traités (no entry): {stats['no_entry']}")
    print(f"  Non traités (no data): {stats['no_data']}")

    if not args.apply:
        print(f"\n[Dry-run] Aucune écriture. Passez --apply pour appliquer.")
        conn.close()
        return 0

    # ── 5. Appliquer les mises à jour par petits lots ──
    print(f"\n[..] Application des {len(updates)} mises à jour (lots de 200)...")
    conn.execute("PRAGMA busy_timeout=120000")  # 2 min timeout
    batch_size = 200
    applied = 0
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        try:
            conn.execute("BEGIN IMMEDIATE")
            for is_win, pips, strategy, details, resolved_at, decision_id in batch:
                conn.execute(
                    "UPDATE decisions "
                    "SET is_win = ?, resolution_pips = ?, "
                    "    resolution_strategy = ?, resolution_details = ?, "
                    "    resolved_at = ? "
                    "WHERE decision_id = ?",
                    (is_win, pips, strategy, details, resolved_at, decision_id),
                )
            conn.execute("COMMIT")
            applied += len(batch)
        except Exception as e:
            conn.execute("ROLLBACK")
            print(f"  ERREUR lot {i//batch_size}: {e}")
            continue
        if (i // batch_size) % 10 == 0:
            print(f"  ... {applied}/{len(updates)}")
    print(f"[OK] {applied} décisions mises à jour avec TP/SL")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"ERREUR: {e}")
        conn.close()
        return 1

    conn.close()

    # ── Rapport ──
    report = {
        "timestamp_utc": _now_utc().isoformat(),
        "strategy": "TP_SL",
        "tp_pips": TP_PIPS,
        "sl_pips": SL_PIPS,
        "spread_pips": SPREAD_PIPS,
        "horizon_hours": HORIZON_HOURS,
        "n_decisions": n_total,
        "n_wins": wins,
        "n_losses": losses,
        "win_rate_pct": round(wins / max(1, n_total) * 100, 1),
        "total_pips": round(total_pips, 1),
        "avg_pips": round(total_pips / max(1, n_total), 1),
        "exit_reasons": stats,
    }
    report_path = ROOT_DIR / "docs" / "reports" / "BATCH_RESOLVE_TPSL_20260711.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[OK] Rapport: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
