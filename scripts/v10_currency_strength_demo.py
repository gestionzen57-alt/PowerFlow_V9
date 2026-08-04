#!/usr/bin/env python3
"""V10 Currency Strength Demo — validation CLI du moteur Fatman Hawkeye par devise.

Lit la DB v9_forces.db (lecture seule R2 additif), extrait les 6 paires USD
sur 7 TF (M1/M5/M15/M30/H1/H4/D1), et affiche le CurrencyStrength snapshot
le plus récent pour chaque timeframe.

Doctrine V10 :
  R2 additif pur (lecture seule DB V9)
  R6 fail-open (DB absente ou TF manquant → fallback fixtures synthétiques + log)
  R10 zéro ordre réel (compute only)
  R9 auditable (sortie JSON sérialisable)

USAGE
  python scripts/v10_currency_strength_demo.py [--db PATH] [--tf H1] [--pairs EURUSD,GBPUSD,...]
  python scripts/v10_currency_strength_demo.py --fixture-only   # test synthétique
  python scripts/v10_currency_strength_demo.py --json           # sortie JSON

EXIT CODES
  0 : OK (au moins 1 snapshot calculé)
  1 : erreur fatale (DB inaccessible + fixture-only off)
  2 : aucun snapshot utilisable (data insuffisante partout)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10.v10_currency_pairs import PAIRS_USD, CURRENCIES
from core.v10.v10_currency_strength import compute_currency_strength, CurrencyStrength


DEFAULT_DB = ROOT / "data" / "v9_forces.db"
TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
N_BARS = 100  # bougies à charger par (pair, TF)


# ─────────────────────────────────────────────────────────────────────
# Lecture DB
# ─────────────────────────────────────────────────────────────────────
def fetch_pair_bars(
    conn: sqlite3.Connection,
    symbol: str,
    timeframe: str,
    n: int = N_BARS,
) -> List[dict]:
    """Lit les N dernières bougies OHLCV pour (symbol, timeframe). Tri croissant par temps."""
    rows = conn.execute(
        """
        SELECT timestamp, open, high, low, close, tick_volume, spread_points
        FROM forces_snapshots
        WHERE symbol = ? AND timeframe = ? AND is_closed_bar = 1
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (symbol, timeframe, n),
    ).fetchall()
    rows.reverse()  # croissance temporelle (engine attend ça)
    bars = []
    for ts, o, h, l, c, v, sp in rows:
        bars.append({
            "timestamp": ts,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "tick_volume": float(v) if v is not None else 0.0,
            "spread_points": float(sp) if sp is not None else 0.0,
        })
    return bars


def fetch_history_window(conn: sqlite3.Connection, currency: str, tf: str, n: int = 50) -> List[float]:
    """Construit une fenêtre history pour percentile rank depuis DB.

    Heuristique : on prend les N timestamps récents pour le TF et on
    calcule un proxy moment (close[i] - close[i-ema_long]) pour USD/currency.
    Pour Phase 1, fallback à fenêtre synthétique monotone (le history
    sera réinjecté proprement en Phase 2 — VSA Engine alimentera history
    depuis snapshots successifs).
    """
    # Lecture directe : on prend close[t] - close[t-1] sur les N bougies récentes
    # comme proxy "moment courant". Pour Phase 1, on sature avec une
    # fenêtre monotone neutre — sera remplacé par vrai calcul en Phase 2+.
    base = ord(currency[0]) % 7 - 3
    return [base * 0.001 + 0.0001 * i for i in range(n)]


# ─────────────────────────────────────────────────────────────────────
# Fallback fixtures synthétiques (DB absente ou TF manquant)
# ─────────────────────────────────────────────────────────────────────
def _fixture_bars(n: int = 100, trend: str = "neutral", seed: int = 42) -> List[dict]:
    """Génère N bougies synthétiques OHLCV. trend ∈ {neutral, up, down}."""
    base = [1.0] * n
    if trend == "up":
        base = [1.0 + 0.0005 * i for i in range(n)]
    elif trend == "down":
        base = [1.10 - 0.0005 * i for i in range(n)]
    bars = []
    for i, c in enumerate(base):
        bars.append({
            "timestamp": f"2026-08-04T{(i // 60) % 24:02d}:{i % 60:02d}:00Z",
            "open": c - 0.0002,
            "high": c + 0.0005,
            "low": c - 0.0005,
            "close": c,
            "tick_volume": 100.0,
            "spread_points": 1.0,
        })
    return bars


def fixture_pairs_bars(trend: str = "neutral") -> Dict[str, List[dict]]:
    """6 paires USD avec bars synthétiques (test/demo)."""
    return {p: _fixture_bars(100, trend=trend) for p in PAIRS_USD}


# ─────────────────────────────────────────────────────────────────────
# Affichage
# ─────────────────────────────────────────────────────────────────────
def render_strength_console(res: CurrencyStrength, tf: str) -> str:
    """Format ASCII-friendly affichage scores par devise."""
    lines = [
        f"\n=== Currency Strength V10 :: TF={tf} :: {res.timestamp} ===",
        f"Source       : {'DB v9_forces.db' if res.pairs_used else 'fixtures synthétiques'}",
        f"Paires       : {len(res.pairs_used)}/6 USD",
        f"Insufficient : {len(res.insufficient_data_currencies)} ({', '.join(res.insufficient_data_currencies) if res.insufficient_data_currencies else '—'})",
        f"n_bars_used  : {res.n_bars_used}",
        f"---",
        f"{'DEVISE':<8} {'SCORE':>7} {'VELOCITY':>10} {'RANK':>5}  {'BAR':<30}",
    ]
    # Tri par rank
    sorted_pairs = sorted(res.ranks.items(), key=lambda kv: kv[1])
    for cur, rank in sorted_pairs:
        score = res.scores[cur]
        vel = res.velocities.get(cur, 0.0)
        # bar ASCII 30 chars : 5..95 → 0..30
        bar_len = int((score - 5) * 30 / 90)
        bar_len = max(0, min(30, bar_len))
        bar = "█" * bar_len + "·" * (30 - bar_len)
        marker = " ◀ TOP" if cur == res.strongest else (" ◀ BOT" if cur == res.weakest else "")
        lines.append(f"{cur:<8} {score:>7.2f} {vel:>+10.4f} {rank:>5}  |{bar}|{marker}")
    lines.append(f"---")
    lines.append(f"Strongest    : {res.strongest} | Weakest: {res.weakest} | Spread: {res.spread_score:.2f}")
    lines.append(f"Audit        : seed={res.seed} | invert_sign={res.invert_sign}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="V10 Currency Strength Demo (Fatman Hawkeye par devise)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help=f"Chemin DB V9 (défaut: {DEFAULT_DB})")
    parser.add_argument("--tf", type=str, default="H1",
                        choices=TIMEFRAMES,
                        help="Timeframe unique (défaut: H1)")
    parser.add_argument("--all-tf", action="store_true",
                        help="Calculer sur les 7 TF")
    parser.add_argument("--fixture-only", action="store_true",
                        help="N'utilise pas la DB, fixtures synthétiques")
    parser.add_argument("--json", action="store_true",
                        help="Sortie JSON sérialisable")
    args = parser.parse_args()

    snapshots: List[CurrencyStrength] = []
    db_used_count = 0
    fixture_used_count = 0

    if not args.fixture_only and args.db.exists():
        try:
            conn = sqlite3.connect(str(args.db), timeout=5)
            conn.row_factory = None
            tfs_calc = TIMEFRAMES if args.all_tf else (args.tf,)
            for tf in tfs_calc:
                pairs_bars = {}
                history = {}
                for pair in PAIRS_USD:
                    bars = fetch_pair_bars(conn, pair, tf)
                    if bars and len(bars) >= 30:
                        pairs_bars[pair] = bars
                if not pairs_bars:
                    # Pas de données DB pour ce TF → fallback fixture
                    pairs_bars = fixture_pairs_bars(trend="neutral")
                    fixture_used_count += 1
                    history = {c: [0.001 * i for i in range(50)] for c in CURRENCIES}
                else:
                    db_used_count += 1
                    # History windowed : on synthétise pour Phase 1 (à remplacer Phase 2+)
                    history = {c: [0.0 + 0.0001 * i for i in range(50)] for c in CURRENCIES}

                if not pairs_bars:
                    print(f"[WARN] {tf}:0 snapshot (fail-open R6)", file=sys.stderr)
                    continue

                # Last timestamp from any pair
                last_ts = max(b[-1]["timestamp"] for b in pairs_bars.values() if b)
                res = compute_currency_strength(
                    timestamp=last_ts,
                    timeframe=tf,
                    pairs_bars=pairs_bars,
                    history=history,
                    seed=42,
                )
                snapshots.append(res)

            conn.close()
        except sqlite3.Error as e:
            print(f"[WARN] DB inaccessible ({e}) — fallback fixtures synthétiques",
                  file=sys.stderr)
            args.fixture_only = True

    if args.fixture_only or not snapshots:
        # Mode fixture complet
        tfs_calc = TIMEFRAMES if args.all_tf else (args.tf,)
        for tf in tfs_calc:
            pairs_bars = fixture_pairs_bars(trend="neutral")
            history = {c: [0.001 * i for i in range(50)] for c in CURRENCIES}
            res = compute_currency_strength(
                timestamp=f"2026-08-04T20:00:00Z",
                timeframe=tf,
                pairs_bars=pairs_bars,
                history=history,
                seed=42,
            )
            snapshots.append(res)
            fixture_used_count += 1

    if not snapshots:
        print("[ERROR] Aucun snapshot calculable", file=sys.stderr)
        return 2

    if args.json:
        out = {
            "snapshots": [s.as_dict() for s in snapshots],
            "db_used": db_used_count,
            "fixture_used": fixture_used_count,
            "pairs_total": len(PAIRS_USD),
            "currencies_total": len(CURRENCIES),
        }
        print(json.dumps(out, indent=2))
    else:
        for s in snapshots:
            print(render_strength_console(s, s.timeframe))
        print(f"\n[STATS] DB-snapshots={db_used_count} | fixture-snapshots={fixture_used_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
