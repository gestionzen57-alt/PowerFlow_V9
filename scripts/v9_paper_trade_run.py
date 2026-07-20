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
from core.v9.exit_simulator import infer_session_from_hour  # noqa: E402
from core.v9.paper_trade_logger import PaperTradeLogger  # noqa: E402
from core.v9.risk_manager import RiskManager  # noqa: E402
from core.v9.v9_paper_trade_resolver import (  # noqa: E402
    PaperTradeResolver,
    ResolutionContext,
)

DEFAULT_SNAPSHOT_LIMIT = 10


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr en UTF-8. Sans ceci, les emojis des logs
    (🔶/⏭) font planter le script sous console Windows cp1252 (crash
    avant toute écriture DB — cause racine du blocage paper-trade
    constatée le 2026-07-08, voir DECISIONS_LOG)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


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
      - window_status : decisions.contexte_complet_json → exploitability.statut
        (mapping : exploitable/watchlist → 'exploitable', sinon 'absente').
        NOTE (fix 2026-07-08) : `window.statut` (raw, cycle de vie fenêtre)
        est TOUJOURS 'absente' en donnée live, y compris sur les décisions
        action=preparer_entree — vérifié empiriquement sur 300 échantillons
        (voir DECISIONS_LOG). Le champ d'évaluation réel utilisé par
        SignalGenerator est `exploitability.statut` (exploitable/watchlist/
        non_exploitable), qu'il faut lire EN PRIORITÉ. L'ancienne priorité
        (window.statut d'abord) bloquait 100% des paper-trades — le
        fallback n'était jamais atteint car window.statut n'est jamais None.
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
        from core.v9.decision_logger import load_contexte_complet
        complet = load_contexte_complet(row["contexte_complet_json"])
    except Exception:
        return ctx

    if complet is None:
        return ctx

    # window_status : on regarde d'abord exploitability.statut (le champ
    # d'évaluation réel), fallback sur exploitability.window_statut puis
    # window.statut (raw) si exploitability absent du contexte.
    window = complet.get("window") or {}
    expl = complet.get("exploitability") or {}
    window_statut = expl.get("statut")
    if window_statut is None:
        window_statut = expl.get("window_statut") or window.get("statut")
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


# ---------- Shadow resolution (réconciliation 2026-07-20) ----------
#
# Le PaperTradeResolver paramétrique (tf × vol_regime × session × confiance)
# tourne en mode SHADOW : il *calcule* une résolution alternative pour les
# trades récemment clôturés et la *logge* pour comparaison, mais n'écrase
# JAMAIS `paper_trades` (R25' : promotion ACTIVE = motion CEO explicite).
# R6 : toute défaillance du resolver retombe sur un log WARNING et le loop
# continue avec la résolution effective (héritée) intacte.


def _build_resolution_context(row: dict) -> ResolutionContext:
    """Construit un ResolutionContext depuis une ligne (paper_trades ⋈ decisions).

    `paper_trades` n'a ni symbol ni timeframe ni vol_regime — ils viennent de
    la décision jointe via snapshot_id. La session est inférée de l'heure UTC
    d'ouverture ; le vol_regime est projeté depuis `regime_type`.
    """
    opened_at = row.get("opened_at") or ""
    utc_hour = 0
    try:
        utc_hour = datetime.fromisoformat(
            str(opened_at).replace("Z", "+00:00")
        ).astimezone(timezone.utc).hour
    except Exception:  # noqa: BLE001
        utc_hour = 0
    return ResolutionContext(
        vol_regime=PaperTradeResolver._regime_bucket(row.get("regime_type")),
        session=infer_session_from_hour(utc_hour),
        timeframe=(row.get("timeframe") or "M1"),
        confiance=int(row.get("confiance") or 0),
        symbol=(row.get("symbol") or "GBPUSD"),
        direction=(row.get("direction") or "haussiere"),
    )


def _resolver_enabled() -> bool:
    """Kill switch PaperTradeResolver ACTIVE.

    2026-07-20 (motion CEO #7, livrable dette ACTIVE resolver) :
    délégué à core.v9.kill_switches.paper_trade_resolver_enabled() si
    elle existe, sinon fallback sur lecture directe du fichier .env via
    kill_switches.get() (env > fichier > défaut "0" = OFF par défaut).

    Le mode ACTIVE n'écrase PAS paper_trades.is_win (R25' : la promotion
    ACTIVE doit être validée motion CEO distincte). Voir resolve_active()
    pour le contrat ACTIF.
    """
    try:
        from core.v9 import kill_switches
        return kill_switches.is_enabled("V9_PAPER_TRADE_RESOLVER_ENABLED")
    except Exception:  # noqa: BLE001
        return False


def resolve_active(
    trade: dict,
    ctx: ResolutionContext,
    resolver: PaperTradeResolver | None = None,
) -> dict:
    """Résout ACTIVE un trade selon son contexte (R25' promotion conditionnée).

    Args:
        trade: dict avec clé `pips_simulated` (excursion finale mesurée).
        ctx: contexte de résolution (vol_regime, session, timeframe, confiance,
            symbol, direction).
        resolver: instance PaperTradeResolver (défaut : nouvelle instance
            basée sur config.DB_PATH).

    Returns:
        dict avec clés `is_win`, `pips`, `exit_reason`, `tp_used`, `sl_used`.

    Doctrine :
    - R6 défensif : si le resolver lève, fallback legacy (pips tel quel,
      is_win = pips>0, exit_reason="legacy", tp/sl=10.0/10.0 par défaut).
    - R2 additif : n'écrase PAS paper_trades.is_win — appelant décide.
    - R18 : pure logique, zéro LLM.
    """
    # Construction lazy du resolver
    if resolver is None:
        try:
            from core.v9.config import DB_PATH
            resolver = PaperTradeResolver(db_path=str(DB_PATH))
        except Exception as exc:  # noqa: BLE001
            print(f"[resolve_active] resolver indisponible, fallback legacy : {exc}")
            pips_legacy = float(trade.get("pips_simulated") or 0.0)
            return {
                "is_win": 1 if pips_legacy > 0 else 0,
                "pips": pips_legacy,
                "exit_reason": "legacy",
                "tp_used": 10.0,
                "sl_used": 10.0,
            }

    try:
        outcome = resolver.resolve(trade, ctx)
        return {
            "is_win": outcome.is_win,
            "pips": outcome.pips,
            "exit_reason": outcome.exit_reason,
            "tp_used": outcome.tp_used,
            "sl_used": outcome.sl_used,
        }
    except Exception as exc:  # noqa: BLE001 — R6 fallback legacy
        print(f"[resolve_active] resolver raise, fallback legacy : {exc}")
        pips_legacy = float(trade.get("pips_simulated") or 0.0)
        return {
            "is_win": 1 if pips_legacy > 0 else 0,
            "pips": pips_legacy,
            "exit_reason": "legacy",
            "tp_used": 10.0,
            "sl_used": 10.0,
        }


def shadow_resolve_recent(
    db_path: Path | str | None = None,
    limit: int = 50,
    resolver: PaperTradeResolver | None = None,
) -> list[dict]:
    """Résout en SHADOW les `limit` derniers paper_trades clôturés.

    Retourne une liste de comparaisons {trade_id, effective_is_win,
    shadow_is_win, shadow_pips, exit_reason, tp_used, sl_used, agree}.
    N'écrit RIEN dans `paper_trades`. R6 : sur toute exception (DB, resolver),
    logge un WARNING et retourne [] — la résolution effective reste souveraine.
    """
    resolved_db = str(db_path) if db_path else "data/v9_forces.db"
    try:
        if resolver is None:
            resolver = PaperTradeResolver(db_path=resolved_db)
    except Exception as exc:  # noqa: BLE001 — fallback résolution héritée
        print(f"[SHADOW WARN] resolver indisponible, fallback résolution fixe : {exc}")
        return []

    conn = get_connection(db_path) if db_path else get_connection()
    conn = _row_factory_dicts(conn)
    try:
        rows = conn.execute(
            """
            SELECT pt.trade_id, pt.direction, pt.confiance, pt.opened_at,
                   pt.pips_simulated, pt.is_win,
                   d.symbol, d.timeframe, d.regime_type
            FROM paper_trades pt
            LEFT JOIN decisions d ON d.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL AND pt.pips_simulated IS NOT NULL
            ORDER BY pt.closed_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    except Exception as exc:  # noqa: BLE001 — DB muette, on abandonne le shadow
        print(f"[SHADOW WARN] lecture paper_trades échouée : {exc}")
        conn.close()
        return []
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    comparisons: list[dict] = []
    for row in rows:
        row = dict(row)
        try:
            ctx = _build_resolution_context(row)
            outcome = resolver.resolve(row, ctx)
        except Exception as exc:  # noqa: BLE001 — R6 : un trade foireux ne casse rien
            print(f"[SHADOW WARN] résolution shadow échouée trade={row.get('trade_id')} : {exc}")
            continue
        effective_is_win = int(row.get("is_win") or 0)
        agree = effective_is_win == outcome.is_win
        comparisons.append({
            "trade_id": row.get("trade_id"),
            "effective_is_win": effective_is_win,
            "shadow_is_win": outcome.is_win,
            "shadow_pips": outcome.pips,
            "exit_reason": outcome.exit_reason,
            "tp_used": outcome.tp_used,
            "sl_used": outcome.sl_used,
            "agree": agree,
        })
        print(
            f"[SHADOW] trade={row.get('trade_id')} effective_win={effective_is_win} "
            f"shadow_win={outcome.is_win} ({outcome.exit_reason}, "
            f"tp={outcome.tp_used}/sl={outcome.sl_used}) "
            f"{'✓ accord' if agree else '✗ divergence'}"
        )
    return comparisons


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
    _ensure_utf8_stdout()
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