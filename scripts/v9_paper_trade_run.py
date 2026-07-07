#!/usr/bin/env python3
"""v9_paper_trade_run.py — Orchestrateur paper-trade V9 (Phase 10).

Workflow à chaque appel :
  1. Lit les N derniers snapshot_id distincts avec decisions live.
  2. Pour chaque snapshot_id :
     a. Arbiter.consolidate(snapshot_id) → dict synthèse
     b. RiskManager.evaluate(arbiter_result, context) → go/no-go
     c. Si go=True → PaperTradeLogger.log_open() (sauf si trade déjà ouvert
        pour ce snapshot_id+direction)
  3. Résumé console.

Doctrine :
  - Zéro ordre réel — paper-trade = simulation uniquement.
  - Idempotent : ne rouvre jamais un trade pour le même (snapshot_id, direction).
  - Lecture seule sauf INSERT dans `paper_trades` (sauf --dry-run).

Usage :
    python scripts/v9_paper_trade_run.py              # run + INSERT
    python scripts/v9_paper_trade_run.py --dry-run   # affiche sans INSERT
    python scripts/v9_paper_trade_run.py --limit 5   # 5 derniers snapshots
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.arbiter import Arbiter  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.paper_trade_logger import PaperTradeLogger  # noqa: E402
from core.v9.risk_manager import RiskManager  # noqa: E402

DEFAULT_SNAPSHOT_LIMIT = 10


# ---------- Helpers ----------


def _row_factory_dicts(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    return conn


def fetch_recent_live_snapshot_ids(
    conn: sqlite3.Connection, limit: int
) -> list[str]:
    """Retourne les N derniers snapshot_id distincts avec AU MOINS UNE
    decision live directionnelle.

    Tri par MAX(timestamp DESC) pour traiter les snapshots les plus récents
    en premier. DISTINCT garantit qu'on ne rejoue pas 10× le même snapshot.
    Le filtre directionnelle évite de noyer l'arbiter sous des snapshots
    'aucune_action' (qui retourneraient direction='neutre' et bloqueraient
    le pipeline au 1er check du risk_manager).
    """
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT snapshot_id, MAX(timestamp) AS max_ts "
        "FROM decisions "
        "WHERE source_type = 'live' "
        "AND snapshot_id IS NOT NULL "
        "AND direction IS NOT NULL AND direction != 'neutre' "
        "GROUP BY snapshot_id "
        "ORDER BY max_ts DESC "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    return [r["snapshot_id"] for r in rows]


def fetch_context_for_snapshot(
    conn: sqlite3.Connection, snapshot_id: str
) -> dict[str, Any]:
    """Construit un shared_context RiskManager-compatible depuis decisions.

    Sources :
      - window_status : decisions.contexte_complet_json → window.statut
        (mapping : exploitable/watchlist → 'exploitable', sinon 'absente')
      - news_phase    : recalculé via NewsContext à la timestamp de la
        décision la plus récente du snapshot, fallback 'NEUTRE' si
        calendrier absent / module indisponible.
    """
    conn.row_factory = sqlite3.Row
    ctx: dict[str, Any] = {
        "news_phase": "NEUTRE",
        "window_status": "absente",  # défaut conservateur
    }

    row = conn.execute(
        "SELECT contexte_complet_json, timestamp FROM decisions "
        "WHERE snapshot_id = ? "
        "ORDER BY timestamp DESC LIMIT 1",
        (snapshot_id,),
    ).fetchone()

    if row is None or not row["contexte_complet_json"]:
        return ctx

    try:
        complet = json.loads(row["contexte_complet_json"])
    except (json.JSONDecodeError, TypeError):
        return ctx

    # window_status : on regarde d'abord window.statut (DB colonne),
    # fallback sur exploitability.window_statut si window absent.
    window = complet.get("window") or {}
    window_statut = window.get("statut")
    if window_statut is None:
        expl = complet.get("exploitability") or {}
        window_statut = expl.get("window_statut") or expl.get("statut")
    if window_statut in ("exploitable", "watchlist"):
        ctx["window_status"] = "exploitable"
    elif window_statut in ("absente", "non_exploitable", None):
        ctx["window_status"] = window_statut or "absente"
    else:
        ctx["window_status"] = "absente"

    # news_phase : recalcul via NewsContext à la timestamp de la décision.
    try:
        from core.v9.news_context import NewsContext  # noqa: PLC0415
        ts_str = row["timestamp"]
        if ts_str:
            ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ctx["news_phase"] = NewsContext().assess(ts_dt).get(
                "news_phase", "NEUTRE"
            )
    except Exception:  # noqa: BLE001
        # Calendrier absent, ts mal formé, ou module HS → NEUTRE
        # (le risk_manager bloquera de toute façon si NEWS_SHOCK réel).
        ctx["news_phase"] = "NEUTRE"

    return ctx


def is_trade_already_open(
    conn: sqlite3.Connection, snapshot_id: str, direction: str
) -> bool:
    """Vérifie qu'aucun trade ouvert n'existe pour (snapshot_id, direction)."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT 1 FROM paper_trades "
        "WHERE snapshot_id = ? AND direction = ? AND closed_at IS NULL "
        "LIMIT 1",
        (snapshot_id, direction),
    ).fetchone()
    return row is not None


# ---------- Run ----------


def run(
    limit: int = DEFAULT_SNAPSHOT_LIMIT,
    dry_run: bool = False,
    db_path: Path | str | None = None,
) -> dict:
    """Exécute le workflow paper-trade. Retourne un résumé structuré."""
    arbiter = Arbiter(db_path=db_path)
    risk = RiskManager()
    logger = PaperTradeLogger(db_path=db_path) if not dry_run else None

    conn = get_connection(db_path) if db_path else get_connection()
    conn = _row_factory_dicts(conn)

    summary: dict[str, Any] = {
        "limit": limit,
        "dry_run": dry_run,
        "snapshots_analyses": 0,
        "trades_ouverts": 0,
        "trades_ignores": 0,
        "details": [],
    }

    try:
        snapshot_ids = fetch_recent_live_snapshot_ids(conn, limit)
    finally:
        conn.close()

    for snapshot_id in snapshot_ids:
        summary["snapshots_analyses"] += 1

        arbiter_result = arbiter.consolidate(snapshot_id)
        direction = arbiter_result["direction"]
        confiance = arbiter_result["confiance_arbitree"]
        principes = arbiter_result["principes_source"]

        # Lecture context (connexion séparée pour découpler de celle d'arbiter)
        conn2 = get_connection(db_path) if db_path else get_connection()
        conn2 = _row_factory_dicts(conn2)
        try:
            context = fetch_context_for_snapshot(conn2, snapshot_id)
        finally:
            conn2.close()

        risk_result = risk.evaluate(arbiter_result, context)

        if not risk_result["go"]:
            summary["trades_ignores"] += 1
            summary["details"].append({
                "snapshot_id": snapshot_id,
                "direction": direction,
                "confiance": confiance,
                "go": False,
                "raison_blocage": risk_result["raison_blocage"],
            })
            print(f"⏭ Ignoré — {risk_result['raison_blocage']} "
                  f"(snap={snapshot_id[:30]}…, dir={direction}, conf={confiance})")
            continue

        # go=True : vérifier idempotence (déjà ouvert ?)
        conn3 = get_connection(db_path) if db_path else get_connection()
        conn3 = _row_factory_dicts(conn3)
        try:
            already_open = is_trade_already_open(conn3, snapshot_id, direction)
        finally:
            conn3.close()

        if already_open:
            summary["trades_ignores"] += 1
            summary["details"].append({
                "snapshot_id": snapshot_id,
                "direction": direction,
                "go": False,
                "raison_blocage": "trade déjà ouvert pour ce snapshot_id+direction",
            })
            print(f"⏭ Ignoré — trade déjà ouvert pour {snapshot_id[:30]}… "
                  f"({direction})")
            continue

        # Trade ouvert
        if dry_run:
            summary["trades_ouverts"] += 1
            summary["details"].append({
                "snapshot_id": snapshot_id,
                "direction": direction,
                "confiance": confiance,
                "principes_source": principes,
                "go": True,
                "dry_run": True,
            })
            print(
                f"🔶 PAPER TRADE OUVERT (DRY-RUN) — {direction} "
                f"conf={confiance} principes={principes} "
                f"snap={snapshot_id[:30]}…"
            )
        else:
            trade_id = logger.log_open(arbiter_result, context)
            summary["trades_ouverts"] += 1
            summary["details"].append({
                "snapshot_id": snapshot_id,
                "direction": direction,
                "confiance": confiance,
                "principes_source": principes,
                "go": True,
                "trade_id": trade_id,
            })
            print(
                f"🔶 PAPER TRADE OUVERT — {direction} "
                f"conf={confiance} principes={principes} "
                f"trade_id={trade_id}"
            )

    print("-" * 60)
    print(
        f"{summary['snapshots_analyses']} snapshots analysés — "
        f"{summary['trades_ouverts']} trades ouverts "
        f"({summary['trades_ignores']} ignorés)"
    )
    if dry_run:
        print("(mode dry-run : aucune écriture en DB)")
    return summary


# ---------- CLI ----------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orchestrateur paper-trade V9 (Phase 10).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche sans écrire en DB (paper_trades intact).",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_SNAPSHOT_LIMIT,
        help=f"Nombre de snapshots à traiter (défaut {DEFAULT_SNAPSHOT_LIMIT}).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Sortie JSON structurée (résumé + détails).",
    )
    args = parser.parse_args()

    summary = run(limit=args.limit, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())