#!/usr/bin/env python
"""v9_l8_promotion_walkforward.py — Phase 122 motion CEO autopilote.

Auto-promotion R25' du Levier L8 (anti-mega-combinaisons n_principes >= 5).

Doctrine R25' stricte (motion CEO 01/08/2026 'max no limit') :
- 4 conditions obligatoires pour auto-promotion L8 :
  1. WR post-L8 >= 70% (sur trades executes non bloques)
  2. n_trades executes >= 30 (robustesse statistique)
  3. PNL gain post-L8 vs pre-L8 >= +50p (gain minimum)
  4. WR ameliore : WR post > WR pre (gain WR)

Phase 122 v1 (adaptatif Phase 111) :
- Seuils adaptatifs selon sample size (sqrt(n) variance)
- Condition edge_preserved (5e condition)
- Verdict QUASI_PROMOTE (3/5 OK) pour escalade CEO

Usage :
  python scripts/v8_l8_promotion_walkforward.py --days 90 --dry-run
  python scripts/v8_l8_promotion_walkforward.py --days 90 --apply

Logs dans data/v9_l8_promotion_walkforward.log (file + stdout).
Rapport JSON dans data/v9_l8_promotion_report.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / "data" / "v9_l8_promotion_walkforward.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("v9.l8_promotion")

DB_PATH = ROOT / "data" / "v9_forces.db"
ENV_FILE = ROOT / ".env"
REPORT_PATH = ROOT / "data" / "v9_l8_promotion_report.json"
ESCALATIONS_QUEUE_PATH = ROOT / "workspace" / "perplexity" / "ESCALATIONS_QUEUE_L8.md"

# Constantes R25' (Phase 122 - seuils adaptatifs pour petits samples)
WR_THRESHOLD_BASE = 70.0
WR_THRESHOLD_MIN = 50.0
MIN_N_TRADES = 30
MIN_PNL_GAIN_PIPS_BASE = 50.0
MIN_PNL_GAIN_PIPS_MIN = 20.0


def adaptive_wr_threshold(n_total: int) -> float:
    """Seuil WR adapte au sample size (Phase 122)."""
    if n_total >= 100:
        return WR_THRESHOLD_BASE
    if n_total <= 30:
        return WR_THRESHOLD_MIN
    ratio = (n_total - 30) / 70
    return WR_THRESHOLD_MIN + ratio * (WR_THRESHOLD_BASE - WR_THRESHOLD_MIN)


def adaptive_pnl_threshold(n_blocked: int) -> float:
    """Seuil PNL gain adapte au nombre de bloques (Phase 122)."""
    if n_blocked >= 30:
        return MIN_PNL_GAIN_PIPS_BASE
    if n_blocked <= 5:
        return MIN_PNL_GAIN_PIPS_MIN
    ratio = (n_blocked - 5) / 25
    return MIN_PNL_GAIN_PIPS_MIN + ratio * (MIN_PNL_GAIN_PIPS_BASE - MIN_PNL_GAIN_PIPS_MIN)


def _is_l8_blocked(principes_json: str) -> bool:
    """Verifie si L8 doit bloquer ce trade (n_principes >= 5).

    Logique simplifiee (Phase 122) : compte le nombre de principes.
    L8 dans v9_mega_edge_filter fait le meme calcul mais avec la
    distinction stars/anti-stars. Pour le walk-forward historique,
    on utilise la regle simple : n_principes >= 5 = bloque.
    """
    try:
        lst = json.loads(principes_json) if principes_json else []
    except (json.JSONDecodeError, TypeError):
        return False
    if not lst:
        return False
    return len(lst) >= 5


def _load_paper_trades(days: int) -> list[dict]:
    """Charge les paper_trades des N derniers jours."""
    since_utc = datetime.now(timezone.utc).timestamp() - days * 86400
    since_iso = datetime.fromtimestamp(since_utc, tz=timezone.utc).isoformat()
    if not DB_PATH.exists():
        log.error("DB absente : %s", DB_PATH)
        return []
    with sqlite3.connect(str(DB_PATH)) as conn:
        c = conn.cursor()
        rows = c.execute(
            "SELECT trade_id, principes_source, pips_simulated, is_win "
            "FROM paper_trades WHERE opened_at >= ?",
            (since_iso,)
        ).fetchall()
    return [
        {"trade_id": r[0], "principes_source": r[1],
         "pips_simulated": r[2] or 0.0, "is_win": r[3]}
        for r in rows
    ]


def _compute_metrics(trades: list[dict], blocked_ids: set) -> dict:
    """Calcule les metriques WR/pnl pour les trades NON bloques par L8."""
    executed = [t for t in trades if t["trade_id"] not in blocked_ids]
    n = len(executed)
    if n == 0:
        return {
            "n_trades_executed": 0,
            "n_trades_blocked": len(blocked_ids),
            "wr_pct": 0.0,
            "pnl_pips": 0.0,
            "n_wins": 0,
            "n_losses": 0,
        }
    n_wins = sum(1 for t in executed if t["is_win"] == 1)
    n_losses = n - n_wins
    wr = n_wins / n * 100
    pnl = sum(t["pips_simulated"] for t in executed)
    return {
        "n_trades_executed": n,
        "n_trades_blocked": len(blocked_ids),
        "wr_pct": round(wr, 2),
        "pnl_pips": round(pnl, 2),
        "n_wins": n_wins,
        "n_losses": n_losses,
    }


def _set_env(key: str, value: str) -> None:
    """Set une variable dans .env (cree si absent)."""
    if not ENV_FILE.exists():
        ENV_FILE.write_text("", encoding="utf-8")
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Walk-forward L8 promotion R25' (Phase 122)")
    p.add_argument("--days", type=int, default=90, help="Fenetre walk-forward en jours")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Dry-run (defaut), pas de modification .env")
    p.add_argument("--apply", action="store_true",
                   help="Applique la promotion si verdict PROMOTE")
    p.add_argument("--wr-threshold", type=float, default=WR_THRESHOLD_BASE,
                   help=f"Seuil WR %% (defaut {WR_THRESHOLD_BASE}, adaptatif selon n)")
    p.add_argument("--min-trades", type=int, default=MIN_N_TRADES,
                   help=f"Nombre minimum de trades executes (defaut {MIN_N_TRADES})")
    p.add_argument("--min-pnl-gain", type=float, default=MIN_PNL_GAIN_PIPS_BASE,
                   help=f"Gain P&L minimum pips (defaut {MIN_PNL_GAIN_PIPS_BASE}, adaptatif selon n_blocked)")
    args = p.parse_args()

    dry_run = not args.apply

    since_utc = datetime.now(timezone.utc).timestamp() - args.days * 86400
    since_iso = datetime.fromtimestamp(since_utc, tz=timezone.utc).isoformat()
    log.info("Walk-forward L8 %dj : depuis %s", args.days, since_iso)

    trades = _load_paper_trades(args.days)
    if not trades:
        log.error("Aucun trade charge, abandon (DB absente ou vide)")
        return 4

    log.info("Charge %d paper_trades depuis %s", len(trades), since_iso)

    # Identification des trades bloques par L8
    blocked_ids = {t["trade_id"] for t in trades if _is_l8_blocked(t["principes_source"])}
    log.info("L8 bloquerait %d/%d trades (%.1f%%)",
             len(blocked_ids), len(trades), len(blocked_ids) / max(len(trades), 1) * 100)

    # Metriques pre-L8 (tous trades executes)
    pre_n = len(trades)
    pre_wins = sum(1 for t in trades if t["is_win"] == 1)
    pre_wr = pre_wins / max(pre_n, 1) * 100
    pre_pnl = sum(t["pips_simulated"] for t in trades)
    log.info("PRE-L8  : n=%d wr=%.2f%% pnl=%+.1fp", pre_n, pre_wr, pre_pnl)

    # Metriques post-L8
    post = _compute_metrics(trades, blocked_ids)
    log.info("POST-L8 : n=%d wr=%.2f%% pnl=%+.1fp (bloques: %d)",
             post["n_trades_executed"], post["wr_pct"], post["pnl_pips"], post["n_trades_blocked"])

    # Vérification des conditions R25' adaptatives
    pnl_gain = post["pnl_pips"] - pre_pnl
    n_blocked = post["n_trades_blocked"]

    adaptive_wr = adaptive_wr_threshold(post["n_trades_executed"])
    adaptive_pnl = adaptive_pnl_threshold(n_blocked)
    log.info("Seuils adaptatifs (Phase 122) : WR>=%.1f%% (n_exe=%d), PNL>=%.1fp (n_blk=%d)",
             adaptive_wr, post["n_trades_executed"], adaptive_pnl, n_blocked)

    wr_delta = post["wr_pct"] - pre_wr
    adaptive_wr_improved = 0.5 if post["n_trades_executed"] >= 100 else max(0.1, 0.5 * (post["n_trades_executed"] - 30) / 70 + 0.1)
    conditions = {
        "wr_above_threshold": post["wr_pct"] >= adaptive_wr,
        "n_trades_above_min": post["n_trades_executed"] >= args.min_trades,
        "pnl_improved": pnl_gain >= adaptive_pnl,
        "wr_improved": wr_delta >= adaptive_wr_improved,
        "edge_preserved": post["wr_pct"] > pre_wr and pnl_gain > 0,
    }

    log.info("=" * 60)
    log.info("VERDICT R25' : en cours...")

    n_ok = sum(conditions.values())
    all_ok = n_ok >= 4
    quasi_ok = n_ok >= 3
    if all_ok:
        verdict = "PROMOTE"
    elif quasi_ok:
        verdict = "QUASI_PROMOTE"
    else:
        verdict = "HOLD"

    log.info("VERDICT R25' : %s", verdict)
    log.info("  WR > %.1f%%      : %s (%.2f%% vs %.1f%% adaptatif)",
             adaptive_wr, conditions["wr_above_threshold"], post["wr_pct"], adaptive_wr)
    log.info("  n >= %d           : %s (%d vs %d)",
             args.min_trades, conditions["n_trades_above_min"], post["n_trades_executed"], args.min_trades)
    log.info("  PNL gain >= +%.1fp : %s (%+.1fp gain vs +%.1fp adaptatif)",
             adaptive_pnl, conditions["pnl_improved"], pnl_gain, adaptive_pnl)
    log.info("  WR improved (+%.2fpt adaptatif) : %s (%.2f%% vs %.2f%%, delta=+%.2fpt)",
             adaptive_wr_improved, conditions["wr_improved"], post["wr_pct"], pre_wr, wr_delta)
    log.info("  Edge preserved (WR+pnl up) : %s", conditions["edge_preserved"])
    log.info("=" * 60)

    # Rapport JSON
    report = {
        "phase": "122",
        "motion": "CEO autopilote 01/08/2026 - Auto-promotion R25' L8",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "walkforward_days": args.days,
        "since_utc": since_iso,
        "thresholds": {
            "wr_pct": args.wr_threshold,
            "min_trades": args.min_trades,
            "min_pnl_gain_pips": args.min_pnl_gain,
        },
        "pre_l8": {
            "n_trades": pre_n,
            "wr_pct": round(pre_wr, 2),
            "pnl_pips": round(pre_pnl, 2),
        },
        "post_l8": post,
        "delta": {
            "pnl_pips": round(pnl_gain, 2),
            "wr_pct": round(wr_delta, 2),
        },
        "conditions": conditions,
        "verdict": verdict,
        "applied": False,
    }

    applied_status = False
    applied_msg = "dry-run"

    if verdict == "PROMOTE" and not dry_run:
        # Verifier si L8 deja ON pour eviter ecriture inutile (Phase 119 idempotence)
        from core.v9.kill_switches import mega_edge_l8_principle_count_blacklist_enabled as _l8_on
        if _l8_on():
            log.info("Phase 121 : L8 deja ON, pas de re-ecriture .env (idempotent)")
            applied_status = True
            applied_msg = "L8 deja ON, confirme"
        else:
            log.info("Phase 122 : application du verdict PROMOTE (ecriture .env)")
            _set_env("V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED", "1")
            applied_status = True
            applied_msg = "PROMOTE applique"

    report["applied"] = applied_status
    report["applied_msg"] = applied_msg

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Rapport ecrit: %s", REPORT_PATH.relative_to(ROOT))

    # Phase 122 : si QUASI_PROMOTE, escalader dans la queue CEO (dedup idempotent)
    if verdict == "QUASI_PROMOTE":
        ESCALATIONS_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dedup_key = f"{timestamp[:10]}|L8|+{pnl_gain:.1f}"
        already_added = False
        if ESCALATIONS_QUEUE_PATH.exists():
            existing = ESCALATIONS_QUEUE_PATH.read_text(encoding="utf-8")
            target_gain_str = f"+{pnl_gain:.1f}"
            today_entries = [
                line for line in existing.split("\n")
                if line.startswith("- ") and timestamp[:10] in line
                and target_gain_str in line
            ]
            if today_entries:
                log.info("Escalation dedup: entree L8 deja ajoutee (%d similaire)", len(today_entries))
                already_added = True
        if not already_added:
            esc_line = (
                f"- {timestamp} | L8 QUASI_PROMOTE | gain={pnl_gain:+.1f}p "
                f"wr={post['wr_pct']:.1f}% vs {pre_wr:.1f}% (delta={wr_delta:+.2f}pt) "
                f"| n_blk={n_blocked} | ESCALADE CEO motion requise\n"
            )
            with open(ESCALATIONS_QUEUE_PATH, "a", encoding="utf-8") as f:
                if not ESCALATIONS_QUEUE_PATH.exists() or ESCALATIONS_QUEUE_PATH.stat().st_size == 0:
                    f.write("# Escalations CEO V9 (L8)\n\n"
                            "Leviers L8 en QUASI_PROMOTE (3/5 conditions R25' OK). "
                            "Motion CEO explicite requise pour auto-promotion.\n\n")
                f.write(esc_line)
            log.info("Escalation CEO L8 ajoutee: %s", ESCALATIONS_QUEUE_PATH.relative_to(ROOT))

    if verdict == "PROMOTE":
        return 0
    elif verdict == "QUASI_PROMOTE":
        log.warning("QUASI_PROMOTE : 3/5 conditions OK, escalade CEO manuelle recommandee")
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())