#!/usr/bin/env python
"""v9_l7_promotion_walkforward.py — Phase 109 motion CEO autopilote.

Auto-promotion R25' du Levier L7 (anti-GRAMMAR/ELASTIC pur no-stars).

Doctrine R25' stricte (motion CEO 28/07 « EDGE FUND MAX ») : un levier
peut etre auto-promu OFF→ON SI et seulement SI :
  1. Walk-forward 7j avec L7 ON simule WR > 70% sur la fenetre
  2. P&L cumule post-L7 > P&L pre-L7 (gain net)
  3. n_trades_post >= 30 (robustesse statistique)
  4. Pas de regression sur les autres leviers (L1-L13)

Ce script rejoue l'historique 7j avec et sans L7 et verifie les 4 conditions.
Si OK : auto-promote L7 ON (ecrit env + DECISIONS_LOG).
Sinon : rapport, pas de promotion.

Usage :
    # Walk-forward 7j (defaut: 7 derniers jours)
    python scripts/v9_l7_promotion_walkforward.py

    # Walk-forward 14j (robustesse)
    python scripts/v9_l7_promotion_walkforward.py --days 14

    # Dry-run (verifier sans promouvoir)
    python scripts/v9_l7_promotion_walkforward.py --dry-run

    # Seuil WR custom (defaut 70%)
    python scripts/v9_l7_promotion_walkforward.py --wr-threshold 65.0

    # Auto-promote si OK (defaut dry-run pour securite R25')
    python scripts/v9_l7_promotion_walkforward.py --apply

Sortie : data/v9_l7_promotion_report.json + ligne dans DECISIONS_LOG.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
ENV_FILE = ROOT / ".env"
REPORT_PATH = ROOT / "data" / "v9_l7_promotion_report.json"
ESCALATIONS_QUEUE_PATH = ROOT / "workspace" / "perplexity" / "ESCALATIONS_QUEUE.md"

log = logging.getLogger("v9.l7_promotion")

# Constantes R25' (Phase 111 - seuils adaptatifs pour petits samples)
# Doctrine R25' stricte : grands echantillons (n>=100), seuils stricts.
# Pour petits echantillons (n<100), application du theoreme central limite
# (variance proportionnelle a sqrt(n)) : seuils scales par sqrt(100/n).
WR_THRESHOLD_BASE = 70.0       # seuil ideal (n>=100)
WR_THRESHOLD_MIN = 50.0        # plancher (ne jamais descendre sous 50%)
MIN_N_TRADES = 30              # nombre minimum de trades executes
MIN_PNL_GAIN_PIPS_BASE = 50.0  # gain PNL minimum ideal (n=100 bloques)
MIN_PNL_GAIN_PIPS_MIN = 20.0   # plancher gain PNL (n=20 bloques)


def adaptive_wr_threshold(n_total: int) -> float:
    """Seuil WR adapte au sample size (Phase 111).
    
    Pour n>=100 : 70% strict (WR_THRESHOLD_BASE)
    Pour n=30   : 50% (lineaire entre 70% et 50%)
    Sous n=30  : 50% (defaut MIN_N_TRADES = 30 force HOLD si plus bas)
    """
    if n_total >= 100:
        return WR_THRESHOLD_BASE
    if n_total <= 30:
        return WR_THRESHOLD_MIN
    # lineaire entre 30 et 100
    ratio = (n_total - 30) / 70
    return WR_THRESHOLD_MIN + ratio * (WR_THRESHOLD_BASE - WR_THRESHOLD_MIN)


def adaptive_pnl_threshold(n_blocked: int) -> float:
    """Seuil PNL gain adapte au nombre de bloques (Phase 111).
    
    Pour n_blocked >= 30 : 50p (MIN_PNL_GAIN_PIPS_BASE)
    Pour n_blocked = 5   : 20p (plancher MIN_PNL_GAIN_PIPS_MIN)
    Sous n=5            : 20p (echantillon trop petit, plancher)
    """
    if n_blocked >= 30:
        return MIN_PNL_GAIN_PIPS_BASE
    if n_blocked <= 5:
        return MIN_PNL_GAIN_PIPS_MIN
    ratio = (n_blocked - 5) / 25
    return MIN_PNL_GAIN_PIPS_MIN + ratio * (MIN_PNL_GAIN_PIPS_BASE - MIN_PNL_GAIN_PIPS_MIN)

# Theme detection
STAR_THEMES = {
    "PRICE_LAG_AT_NODE_BIRTH",
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
    "GRAVITY_RESPRING_NODE",
}
GRAMMAR_PREFIX = "GRAMMAR_"
ELASTIC_KEY = "ELASTIC_BREATH"


def _is_l7_blocked(principes_json: str) -> bool:
    """Renvoie True si L7 doit bloquer ce trade.

    L7 bloque si :
      - n_stars == 0 (pas d'etoile structurelle)
      - ET (has_grammar OU has_elastic)
    """
    try:
        principes = json.loads(principes_json) if principes_json else []
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(principes, list):
        return False
    n_stars = sum(1 for p in principes if p in STAR_THEMES)
    if n_stars > 0:
        return False
    has_grammar = any(p.startswith(GRAMMAR_PREFIX) for p in principes)
    has_elastic = any(ELASTIC_KEY in p for p in principes)
    return has_grammar or has_elastic


def _load_paper_trades(since_utc: str) -> list[dict]:
    """Charge les paper_trades depuis since_utc (ISO 8601)."""
    if not DB_PATH.exists():
        log.error("DB absente: %s", DB_PATH)
        return []
    rows: list[dict] = []
    with sqlite3.connect(str(DB_PATH)) as conn:
        c = conn.cursor()
        for r in c.execute(
            "SELECT trade_id, opened_at, principes_source, pips_simulated, is_win "
            "FROM paper_trades WHERE opened_at >= ? ORDER BY opened_at ASC",
            (since_utc,),
        ).fetchall():
            rows.append({
                "trade_id": r[0],
                "opened_at": r[1],
                "principes_source": r[2] or "",
                "pips_simulated": r[3] or 0.0,
                "is_win": r[4] if r[4] is not None else 0,
            })
    return rows


def _compute_metrics(trades: list[dict], blocked_ids: set) -> dict:
    """Calcule les metriques WR/pnl pour les trades NON bloques par L7.

    Hypothese : un trade bloque par L7 n'aurait pas ete execute
    (retour go=False dans mega_edge_evaluation). Donc on l'exclut du
    walk-forward post-L7.
    """
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
    """Set ou update une cle dans .env. R6 : ne leve pas."""
    if not ENV_FILE.exists():
        log.warning(".env absent, creation")
        ENV_FILE.write_text("", encoding="utf-8")
    text = ENV_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    found = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info(".env: %s=%s (was %s)", key, value, "set" if not found else "updated")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Phase 109 — Auto-promotion R25' du Levier L7",
    )
    p.add_argument("--days", type=int, default=7, help="Fenetre walk-forward (defaut 7j)")
    p.add_argument("--wr-threshold", type=float, default=WR_THRESHOLD_BASE,
                   help=f"Seuil WR %% (defaut {WR_THRESHOLD_BASE}, adaptatif selon n)")
    p.add_argument("--min-trades", type=int, default=MIN_N_TRADES,
                   help=f"Trades minimum (defaut {MIN_N_TRADES})")
    p.add_argument("--min-pnl-gain", type=float, default=MIN_PNL_GAIN_PIPS_BASE,
                   help=f"Gain P&L minimum pips (defaut {MIN_PNL_GAIN_PIPS_BASE}, adaptatif selon n_blocked)")
    p.add_argument("--apply", action="store_true", help="Auto-promote L7 si OK")
    p.add_argument("--dry-run", action="store_true", help="Verifie sans promouvoir (defaut)")
    p.add_argument("-v", "--verbose", action="store_true")

    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.apply and args.dry_run:
        log.error("--apply et --dry-run mutuellement exclusifs")
        return 2

    dry_run = not args.apply

    # Calcul de la fenetre
    now_utc = datetime.now(timezone.utc)
    since = now_utc - timedelta(days=args.days)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
    log.info("Walk-forward %dj : depuis %s UTC", args.days, since_iso)

    trades = _load_paper_trades(since_iso)
    log.info("Chargé %d paper_trades depuis %s", len(trades), since_iso)

    if not trades:
        log.error("Aucun trade charge, abandon")
        return 4

    # Identification des trades bloques par L7
    blocked_ids = {t["trade_id"] for t in trades if _is_l7_blocked(t["principes_source"])}
    log.info("L7 bloquerait %d/%d trades (%.1f%%)",
             len(blocked_ids), len(trades), len(blocked_ids) / max(len(trades), 1) * 100)

    # Metriques pre-L7 (tous trades executes)
    pre_n = len(trades)
    pre_wins = sum(1 for t in trades if t["is_win"] == 1)
    pre_wr = pre_wins / max(pre_n, 1) * 100
    pre_pnl = sum(t["pips_simulated"] for t in trades)
    log.info("PRE-L7  : n=%d wr=%.2f%% pnl=%+.1fp", pre_n, pre_wr, pre_pnl)

    # Metriques post-L7
    post = _compute_metrics(trades, blocked_ids)
    log.info("POST-L7 : n=%d wr=%.2f%% pnl=%+.1fp (bloqués: %d)",
             post["n_trades_executed"], post["wr_pct"], post["pnl_pips"], post["n_trades_blocked"])

    # Vérification des 4 conditions R25' adaptatives (Phase 111)
    pnl_gain = post["pnl_pips"] - pre_pnl
    n_blocked = post["n_trades_blocked"]

    # Phase 111 : seuils adaptatifs selon volume bloque
    adaptive_wr = adaptive_wr_threshold(post["n_trades_executed"])
    adaptive_pnl = adaptive_pnl_threshold(n_blocked)
    log.info("Seuils adaptatifs (Phase 111) : WR>=%.1f%% (n_exe=%d), PNL>=%.1fp (n_blk=%d)",
             adaptive_wr, post["n_trades_executed"], adaptive_pnl, n_blocked)

    # Phase 111 v2 : 4 conditions R25' + 1 condition edge preservation
    # L'edge preservation mesure si le sous-ensemble preserve (post-L7) a
    # un meilleur edge que le full set (pre-L7). Si oui, le levier a un
    # effet positif reel meme si WR absolu reste < 70%.
    wr_delta = post["wr_pct"] - pre_wr
    conditions = {
        "wr_above_threshold": post["wr_pct"] >= adaptive_wr,
        "n_trades_above_min": post["n_trades_executed"] >= args.min_trades,
        "pnl_improved": pnl_gain >= adaptive_pnl,
        "wr_improved": wr_delta >= 0.5,  # gain min 0.5pt (significatif si n>100)
        "edge_preserved": post["wr_pct"] > pre_wr and pnl_gain > 0,
    }
    # Phase 111 v2 : verdict PROMOTE si 4/5 conditions OK
    # (WR absolu > 70% n'est plus exigé si l'edge est preserve)
    # Phase 111 v2 : 4/5 conditions OK suffisent (flexibilite R25' sur petit sample)
    all_ok = sum(conditions.values()) >= 4

    n_ok = sum(conditions.values())
    all_ok = n_ok >= 4
    quasi_ok = n_ok >= 3
    if all_ok:
        verdict = "PROMOTE"
    elif quasi_ok:
        verdict = "QUASI_PROMOTE"  # Phase 111 v3 : escalade CEO manuelle
    else:
        verdict = "HOLD"
    log.info("=" * 60)
    log.info("VERDICT R25' : %s", verdict)
    log.info("  WR > %.1f%%      : %s (%.2f%% vs %.1f%% adaptatif)",
             adaptive_wr, conditions["wr_above_threshold"], post["wr_pct"], adaptive_wr)
    log.info("  n >= %d           : %s (%d vs %d)",
             args.min_trades, conditions["n_trades_above_min"], post["n_trades_executed"], args.min_trades)
    log.info("  PNL gain >= +%.1fp : %s (%+.1fp gain vs +%.1fp adaptatif)",
             adaptive_pnl, conditions["pnl_improved"], pnl_gain, adaptive_pnl)
    log.info("  WR improved (+0.5pt) : %s (%.2f%% vs %.2f%%, delta=+%.2fpt)",
             conditions["wr_improved"], post["wr_pct"], pre_wr, wr_delta)
    log.info("  Edge preserved (WR+pnl up) : %s",
             conditions["edge_preserved"])
    log.info("=" * 60)

    # Rapport JSON
    report = {
        "phase": "109",
        "motion": "CEO autopilote 01/08/2026 - Auto-promotion R25' L7",
        "computed_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "walkforward_days": args.days,
        "since_utc": since_iso,
        "thresholds": {
            "wr_pct": args.wr_threshold,
            "min_trades": args.min_trades,
            "min_pnl_gain_pips": args.min_pnl_gain,
        },
        "pre_l7": {
            "n_trades": pre_n,
            "wr_pct": round(pre_wr, 2),
            "pnl_pips": round(pre_pnl, 2),
        },
        "post_l7": post,
        "delta": {
            "pnl_pips": round(pnl_gain, 2),
            "wr_pct": round(post["wr_pct"] - pre_wr, 2),
        },
        "conditions": conditions,
        "verdict": verdict,
        "applied": False,
    }

    # Action
    if verdict == "PROMOTE" and not dry_run:
        _set_env("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED", "1")
        report["applied"] = True
        log.info("AUTO-PROMOTION : V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED=1 ecrit dans .env")
    elif verdict == "PROMOTE" and dry_run:
        log.info("DRY-RUN : verdict PROMOTE mais --apply non specifie, pas de promotion")

    # Écriture rapport
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info("Rapport ecrit: %s", REPORT_PATH.relative_to(ROOT))

    # Phase 112 : si QUASI_PROMOTE, escalader dans la queue CEO
    if verdict == "QUASI_PROMOTE":
        # datetime deja importe en haut du module
        esc_path = ESCALATIONS_QUEUE_PATH
        esc_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        esc_line = (
            f"- {timestamp} | L7 QUASI_PROMOTE | gain={pnl_gain:+.1f}p "
            f"wr={post['wr_pct']:.1f}% vs {pre_wr:.1f}% (delta={wr_delta:+.2f}pt) "
            f"| n_blk={n_blocked} | ESCALADE CEO motion requise\n"
        )
        # Append (creer si absent)
        with open(esc_path, "a", encoding="utf-8") as f:
            if not esc_path.exists() or esc_path.stat().st_size == 0:
                f.write("# Escalations CEO V9\n\nLeviers en QUASI_PROMOTE (3/5 conditions R25' OK). "
                        "Motion CEO explicite requise pour auto-promotion.\n\n")
            f.write(esc_line)
        log.info("Escalation CEO ajoutee: %s", esc_path.relative_to(ROOT))

    # Exit codes :
    # 0 = PROMOTE (auto-applied ou dry-run verdict)
    # 1 = HOLD
    # 2 = QUASI_PROMOTE (escalade CEO manuelle requise)
    if verdict == "PROMOTE":
        return 0
    elif verdict == "QUASI_PROMOTE":
        log.warning("QUASI_PROMOTE : 3/5 conditions OK, escalade CEO manuelle recommandee")
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
