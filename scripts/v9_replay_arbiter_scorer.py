#!/usr/bin/env python3
"""v9_replay_arbiter_scorer.py — Replay pré/post pondération PrincipleScorer (Brief O2).

Lecture seule. Pour chaque snapshot_id ayant une décision `preparer_entree`
résolue, exécute `Arbiter.consolidate()` deux fois : une fois avec le kill
switch désactivé (V9_ARBITER_SCORER_ENABLED=0, comportement PRÉ-brief —
confiance neutre intégrale) et une fois activé (POST-brief — pondération
PrincipleScorer réelle). Compare l'effet sur :
- Le nombre de décisions qui franchiraient le seuil RiskManager.CONFIANCE_MIN
  (70) avant/après.
- Le WR réalisé (déjà connu via `decisions.is_win`, résolu par le Brief O1)
  parmi celles qui franchiraient le seuil avant vs après.

N'écrit rien en DB. Ne modifie aucun seuil de production.

Usage :
    python scripts/v9_replay_arbiter_scorer.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.arbiter import SCORER_ENABLED_ENV, Arbiter  # noqa: E402
from core.v9.config import DB_PATH  # noqa: E402
from core.v9.risk_manager import CONFIANCE_MIN  # noqa: E402


def fetch_target_snapshots(db_path: Path) -> list[tuple[str, int, str]]:
    """snapshot_id, is_win, direction pour les décisions preparer_entree
    résolues avec source_type='live' (population exacte consommée par
    Arbiter.consolidate() en prod, cf. v9_paper_trade_run.py)."""
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT snapshot_id, is_win, direction FROM decisions "
            "WHERE action = 'preparer_entree' AND source_type = 'live' "
            "AND is_win IS NOT NULL AND snapshot_id IS NOT NULL"
        ).fetchall()
        return [(r["snapshot_id"], r["is_win"], r["direction"]) for r in rows]
    finally:
        conn.close()


def run_replay(db_path: Path) -> dict:
    targets = fetch_target_snapshots(db_path)
    arbiter = Arbiter(db_path=db_path)

    pre_results = []
    post_results = []
    basis_counts: dict[str, int] = {}

    for snapshot_id, is_win, _direction in targets:
        os.environ[SCORER_ENABLED_ENV] = "0"
        pre = arbiter.consolidate(snapshot_id)
        os.environ[SCORER_ENABLED_ENV] = "1"
        post = arbiter.consolidate(snapshot_id)

        pre_results.append((pre["confiance_arbitree"], is_win))
        post_results.append((post["confiance_arbitree"], is_win))
        basis_counts[post["scorer_basis"]] = basis_counts.get(post["scorer_basis"], 0) + 1

    os.environ.pop(SCORER_ENABLED_ENV, None)

    def _pass_stats(results: list[tuple[int, int]]) -> dict:
        passing = [is_win for conf, is_win in results if conf >= CONFIANCE_MIN]
        blocked = len(results) - len(passing)
        wins = sum(1 for w in passing if w == 1)
        return {
            "n_pass": len(passing),
            "n_blocked": blocked,
            "win_rate_pct": round(wins / max(1, len(passing)) * 100, 1),
        }

    pre_stats = _pass_stats(pre_results)
    post_stats = _pass_stats(post_results)

    newly_passing = sum(
        1 for (c_pre, _), (c_post, _) in zip(pre_results, post_results)
        if c_pre < CONFIANCE_MIN <= c_post
    )
    newly_blocked = sum(
        1 for (c_pre, _), (c_post, _) in zip(pre_results, post_results)
        if c_post < CONFIANCE_MIN <= c_pre
    )

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "confiance_min_threshold": CONFIANCE_MIN,
        "n_snapshots_analyzed": len(targets),
        "scorer_basis_distribution": basis_counts,
        "pre_kill_switch_off_neutral": pre_stats,
        "post_scorer_enabled": post_stats,
        "n_newly_passing_confiance_min": newly_passing,
        "n_newly_blocked_confiance_min": newly_blocked,
        "win_rate_delta_pct": round(post_stats["win_rate_pct"] - pre_stats["win_rate_pct"], 1),
    }


def main() -> int:
    report = run_replay(DB_PATH)
    out_path = ROOT_DIR / "docs" / "reports" / "ARBITER_SCORER_REPLAY_20260712.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"[OK] Rapport écrit : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
