#!/usr/bin/env python3
"""v9_paper_trade_offline.py — Paper trade offline sur décisions résolues (lecture seule).

Réapplique le RiskManager sur les décisions historiques résolues (is_win != NULL)
pour mesurer combien auraient passé le gate paper-trade a posteriori.

Différent de v9_paper_trade_run.py (qui travaille sur snapshots LIVE récents) :
celui-ci prend TOUTES les décisions résolues et regarde combien, au moment où
elles ont été loggées, auraient ouvert un paper trade selon le RiskManager.

Doctrine :
- R8 : 0 modif core/v9/* (script externe + rapport)
- R18 : 0 LLM (calcul stdlib pur)
- Lecture seule : aucune INSERT en DB

Usage :
    python scripts/v9_paper_trade_offline.py
    python scripts/v9_paper_trade_offline.py --limit 500
    python scripts/v9_paper_trade_offline.py --output docs/reports/H24_PAPER_OFFLINE_<date>.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402

# Seuils RiskManager (cf. core/v9/risk_manager.py) — duplicata lecture seule.
RISK_GATE_CONFIANCE_MIN = 80
RISK_GATE_NB_PRINCIPES_MIN = 2


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Paper trade offline — réapplique RiskManager sur décisions résolues."
    )
    p.add_argument("--limit", type=int, default=1000,
                   help="Limite le nombre de décisions analysées (défaut 1000).")
    p.add_argument("--timeframe", type=str, default=None,
                   help="Filtre TF (M5/M15/H1/...).")
    p.add_argument("--action", type=str, default="preparer_entree",
                   help="Filtre action (défaut preparer_entree).")
    p.add_argument("--output", type=Path, default=None,
                   help="Fichier JSON de sortie (rapport complet).")
    return p.parse_args(argv)


def _load_resolved_decisions(conn: sqlite3.Connection, limit: int,
                             timeframe: str | None, action: str) -> list[dict]:
    """Charge les décisions résolues avec leur contexte décompressé."""
    where = ["d.is_win IS NOT NULL", "d.action = ?"]
    params: list = [action]
    if timeframe:
        where.append("d.timeframe = ?")
        params.append(timeframe)
    sql = f"""
        SELECT d.decision_id, d.timestamp, d.symbol, d.timeframe, d.direction,
               d.confiance, d.is_win, d.resolution_pips, d.contexte_complet_json
        FROM decisions d
        WHERE {' AND '.join(where)}
        ORDER BY d.timestamp DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()

    out = []
    for r in rows:
        ctx = _safe_decompress(r[8])
        out.append({
            "decision_id": r[0],
            "timestamp": r[1],
            "symbol": r[2],
            "timeframe": r[3],
            "direction": r[4],
            "confiance": r[5],
            "is_win": bool(r[6]),
            "pips": r[7],
            "ctx": ctx,
        })
    return out


def _safe_decompress(data) -> dict | None:
    """Décompresse contexte_complet_json (zlib) avec fallbacks."""
    if not data:
        return None
    try:
        if isinstance(data, bytes):
            return json.loads(zlib.decompress(data))
        if isinstance(data, str):
            return json.loads(data)
    except (zlib.error, json.JSONDecodeError):
        return None
    return None


def _gate_passes(decision: dict) -> tuple[bool, list[str]]:
    """Réapplique le gate RiskManager (duplicata simplifié pour audit).

    Returns (passed, reasons_blocked).
    """
    blocked = []
    ctx = decision.get("ctx") or {}

    # Gate 1 : confiance ≥ 80
    if decision["confiance"] < RISK_GATE_CONFIANCE_MIN:
        blocked.append(f"confiance={decision['confiance']} < {RISK_GATE_CONFIANCE_MIN}")

    # Gate 2 : nb principes ACTIVE ≥ 2
    pe = ctx.get("principle_evaluations") or []
    if isinstance(pe, list):
        n_active = sum(1 for p in pe if p.get("triggered"))
    elif isinstance(pe, dict):
        n_active = sum(1 for v in pe.values() if isinstance(v, dict) and v.get("triggered"))
    else:
        n_active = 0
    if n_active < RISK_GATE_NB_PRINCIPES_MIN:
        blocked.append(f"principes_actifs={n_active} < {RISK_GATE_NB_PRINCIPES_MIN}")

    # Gate 3 : window_status = exploitable
    expl = ctx.get("exploitability") or {}
    if isinstance(expl, dict):
        expl_statut = expl.get("statut") or ""
    else:
        expl_statut = ""
    if expl_statut not in ("exploitable", "watchlist"):
        blocked.append(f"window_status={expl_statut or 'absent'}")

    # Gate 4 : news_phase != NEWS_SHOCK
    news = ctx.get("news") or {}
    if isinstance(news, dict) and news.get("news_phase") == "NEWS_SHOCK":
        blocked.append("news_phase=NEWS_SHOCK")

    return (len(blocked) == 0), blocked


def _build_report(decisions: list[dict]) -> dict:
    """Construit le rapport d'audit."""
    n = len(decisions)
    n_passed = 0
    n_blocked_conf = 0
    n_blocked_principes = 0
    n_blocked_window = 0
    n_blocked_news = 0
    wr_passed = []
    wr_blocked = []

    for d in decisions:
        passed, blocked = _gate_passes(d)
        if passed:
            n_passed += 1
            wr_passed.append(d["is_win"])
        else:
            wr_blocked.append(d["is_win"])
            for b in blocked:
                if b.startswith("confiance"):
                    n_blocked_conf += 1
                elif b.startswith("principes"):
                    n_blocked_principes += 1
                elif b.startswith("window"):
                    n_blocked_window += 1
                elif b.startswith("news"):
                    n_blocked_news += 1

    def _rate(wins, total):
        return round(wins / total * 100, 2) if total else 0.0

    wr_passed_pct = _rate(sum(wr_passed), len(wr_passed))
    wr_blocked_pct = _rate(sum(wr_blocked), len(wr_blocked))
    wr_global_pct = _rate(sum(wr_passed) + sum(wr_blocked), n)

    by_tf_passed = Counter()
    by_tf_blocked = Counter()
    by_tf_wr = {}
    for d in decisions:
        passed, _ = _gate_passes(d)
        if passed:
            by_tf_passed[d["timeframe"]] += 1
            by_tf_wr.setdefault(d["timeframe"], []).append(d["is_win"])
        else:
            by_tf_blocked[d["timeframe"]] += 1

    by_tf_summary = {
        tf: {
            "passed": by_tf_passed.get(tf, 0),
            "blocked": by_tf_blocked.get(tf, 0),
            "wr_pct_on_passed": _rate(sum(by_tf_wr.get(tf, [])), len(by_tf_wr.get(tf, []))),
        }
        for tf in set(list(by_tf_passed.keys()) + list(by_tf_blocked.keys()))
    }

    # Confidence distribution
    conf_dist = Counter()
    for d in decisions:
        bucket = (d["confiance"] // 10) * 10
        conf_dist[bucket] += 1

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "db_path": str(DB_PATH),
        "n_total": n,
        "n_passed": n_passed,
        "n_blocked": n - n_passed,
        "pct_passed": round(n_passed / n * 100, 2) if n else 0.0,
        "blockers": {
            "confiance": n_blocked_conf,
            "principes": n_blocked_principes,
            "window_status": n_blocked_window,
            "news_phase": n_blocked_news,
        },
        "wr_global_pct": wr_global_pct,
        "wr_passed_pct": wr_passed_pct,
        "wr_blocked_pct": wr_blocked_pct,
        "by_timeframe": by_tf_summary,
        "confidence_distribution": dict(sorted(conf_dist.items())),
    }


def _print_console(report: dict) -> None:
    print("=" * 70)
    print("V9 — PAPER TRADE OFFLINE (lecture seule, audit RiskManager)")
    print("=" * 70)
    print(f"Timestamp UTC      : {report['timestamp_utc']}")
    print(f"Décisions analysées: {report['n_total']}")
    print()
    print(f"  PASSED GATE : {report['n_passed']} ({report['pct_passed']}%)")
    print(f"    → WR sur passed  : {report['wr_passed_pct']}%")
    print(f"  BLOCKED     : {report['n_blocked']}")
    print(f"    → WR sur blocked : {report['wr_blocked_pct']}%")
    print()
    print("Blockers (occurrences) :")
    for k, v in report["blockers"].items():
        print(f"  - {k:18s}: {v}")
    print()
    print("Par TF :")
    for tf, b in sorted(report["by_timeframe"].items()):
        print(f"  {tf:4s}: passed={b['passed']:4d} blocked={b['blocked']:4d} WR_passed={b['wr_pct_on_passed']:.1f}%")
    print()
    print("Distribution confiance :")
    for bucket, n in report["confidence_distribution"].items():
        bar = "█" * (n // 20)
        print(f"  {bucket:3d}-{bucket+9:3d}: {n:4d} {bar}")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = _parse_args(argv)

    if not DB_PATH.exists():
        print(f"ERREUR : DB absente à {DB_PATH}", file=sys.stderr)
        return 2

    conn = get_connection(DB_PATH)
    try:
        decisions = _load_resolved_decisions(conn, args.limit, args.timeframe, args.action)
    finally:
        conn.close()

    if not decisions:
        print(f"Aucune décision résolue pour critères.", file=sys.stderr)
        return 1

    report = _build_report(decisions)
    _print_console(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print()
        print(f"Rapport complet écrit : {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())