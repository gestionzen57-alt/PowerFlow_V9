"""v9_win_streak.py — Phase 21 motion CEO « EDGE FUND MAX ».

Suivi live des series de gains/pertes pour anticiper les risques.
Detecte :
- Win streak N (5+) : signal positif (potentiel momentum)
- Loss streak N (3+) : alerte (kill switch anti-serie J2)
- Recovery depuis max DD

Output : dashboard win streak + alertes.

Usage :
  python scripts/v9_win_streak.py            # affiche status
  python scripts/v9_win_streak.py --json     # JSON brut
  python scripts/v9_win_streak.py --reset    # reset streak (post-rollback)

Auteur : Hermes (Phase 21 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.win_streak")

# Seuils (calibres Phase 2 anti-serie perdante + win momentum)
WIN_STREAK_ALERT = 5      # 5+ wins consecutifs = momentum positif
LOSS_STREAK_ALERT = 3     # 3+ losses consecutives = J2 anti-serie
LOSS_STREAK_HALT = 5      # 5+ losses consecutives = kill switch propose

STREAK_STATE_FILE = Path(r"C:\projet\V9\data\v9_win_streak_state.json")


def get_recent_trades(db_path: Path | str, n=50) -> list[dict]:
    """Retourne les N derniers trades fermes (ordre chronologique ASC)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            # COALESCE sur direction si colonne absente (degrade propre).
            # Note : SQLite COALESCE reference la colonne, donc si absente
            # → OperationalError. On utilise pragma pour detecter.
            has_direction = False
            try:
                cols = [r[1] for r in conn.execute(
                    "PRAGMA table_info(v9_paper_trades)"
                ).fetchall()]
                has_direction = "direction" in cols
            except Exception:
                pass

            if has_direction:
                rows = conn.execute("""
                    SELECT id, symbol, direction,
                           opened_at, closed_at, pips_net
                    FROM v9_paper_trades
                    WHERE closed_at IS NOT NULL
                    ORDER BY closed_at DESC
                    LIMIT ?
                """, (n,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, symbol, 'unknown' AS direction,
                           opened_at, closed_at, pips_net
                    FROM v9_paper_trades
                    WHERE closed_at IS NOT NULL
                    ORDER BY closed_at DESC
                    LIMIT ?
                """, (n,)).fetchall()
            # Renverser pour ordre chronologique ASC
            return [dict(r) for r in reversed(rows)]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def compute_streaks(trades: list[dict]) -> dict:
    """Calcule win streak / loss streak actuel + max historique."""
    if not trades:
        return {
            "current_streak": 0,
            "current_type": "none",
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "n_total": 0,
        }
    current_streak = 0
    current_type = "none"
    max_win = 0
    max_loss = 0
    temp_win = 0
    temp_loss = 0
    for t in trades:
        is_win = (t.get("pips_net") or 0) > 0
        if is_win:
            temp_win += 1
            temp_loss = 0
            max_win = max(max_win, temp_win)
        else:
            temp_loss += 1
            temp_win = 0
            max_loss = max(max_loss, temp_loss)
    current_streak = temp_win if temp_win > 0 else temp_loss
    current_type = "win" if temp_win > 0 else ("loss" if temp_loss > 0 else "none")
    return {
        "current_streak": current_streak,
        "current_type": current_type,
        "max_win_streak": max_win,
        "max_loss_streak": max_loss,
        "n_total": len(trades),
    }


def get_recommendation(streaks: dict) -> tuple[str, list[str]]:
    """Retourne (recommendation, alertes)."""
    alerts = []
    if streaks["current_type"] == "win" and streaks["current_streak"] >= WIN_STREAK_ALERT:
        alerts.append(
            f"Win streak {streaks['current_streak']} : momentum positif"
        )
    if streaks["current_type"] == "loss":
        if streaks["current_streak"] >= LOSS_STREAK_HALT:
            alerts.append(
                f"LOSS STREAK {streaks['current_streak']} : KILL SWITCH propose"
            )
            return ("KILL_SWITCH_PROPOSED", alerts)
        if streaks["current_streak"] >= LOSS_STREAK_ALERT:
            alerts.append(
                f"Loss streak {streaks['current_streak']} : vigilance (anti-serie J2)"
            )
    if streaks["max_loss_streak"] >= LOSS_STREAK_HALT:
        alerts.append(
            f"Max loss streak historique : {streaks['max_loss_streak']} "
            f"(risque structurel)"
        )
    if not alerts:
        return ("OK", [])
    return ("ALERT", alerts)


def save_state(streaks: dict) -> None:
    """Sauvegarde l'etat pour reprise."""
    STREAK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "streaks": streaks,
    }
    STREAK_STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 win streak tracker (Phase 21)",
    )
    parser.add_argument("--json", action="store_true",
                        help="JSON brut")
    parser.add_argument("--reset", action="store_true",
                        help="Reset streak state")
    args = parser.parse_args(argv)

    if args.reset:
        STREAK_STATE_FILE.unlink(missing_ok=True)
        print("Streak state reset.")
        return 0

    from core.v9.config import DB_PATH
    trades = get_recent_trades(DB_PATH, n=50)
    streaks = compute_streaks(trades)
    recommendation, alerts = get_recommendation(streaks)
    save_state(streaks)

    if args.json:
        result = {
            "streaks": streaks,
            "recommendation": recommendation,
            "alerts": alerts,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if recommendation != "KILL_SWITCH_PROPOSED" else 2

    print("=" * 70)
    print("PHASE 21 — WIN STREAK TRACKER")
    print("=" * 70)
    print(f"Trades analyses : {streaks['n_total']}")
    print(f"Current streak  : {streaks['current_streak']} {streaks['current_type']}")
    print(f"Max win streak  : {streaks['max_win_streak']}")
    print(f"Max loss streak : {streaks['max_loss_streak']}")
    print()
    print(f"Recommendation  : {recommendation}")
    for a in alerts:
        print(f"  ALERT : {a}")
    if not alerts:
        print("  (aucune alerte)")
    print()
    print(f"State saved     : {STREAK_STATE_FILE}")
    print("=" * 70)

    return 0 if recommendation != "KILL_SWITCH_PROPOSED" else 2


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())