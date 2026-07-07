#!/usr/bin/env python3
"""validate-coherence.py — Contrôle logique/cohérence de la DB V9 live.

Doctrine : lecture seule — n'altère aucune table. Détecte les anomalies
de données (pas les bugs de code) entre les 8 tables dérivées.

7 checks :
  1. Orphelins de chaîne (scene→snapshot, behavior→scene, window→behavior,
     exploitability→window)
  2. Décisions sans signal_id
  3. Signaux directionnels sans principes_source_json
  4. source_type='live' avec snapshot > 24h (stale potentiel)
  5. Décisions doublons (snapshot_id × direction × confiance)
  6. Principes ACTIVE jamais évalués récemment (12h UTC glissantes)
  7. Confiance hors plage [1..100] pour décisions directionnelles

Usage :
    python scripts/validate-coherence.py            # console, exit 0/1/2
    python scripts/validate-coherence.py --json     # sortie JSON
    python scripts/validate-coherence.py --fix-report   # liste IDs à corriger

Exit codes :
    0 = tout OK
    1 = au moins 1 WARNING (incohérence mineure)
    2 = au moins 1 ERREUR (incohérence bloquante)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.db_schema import get_connection  # noqa: E402


# ---------- Constantes de cohérence ----------


# Fenêtre "marché ouvert" pour CHECK 6 — sur les 12 dernières heures UTC.
# Couvre les sessions Londres + NY. Un principe ACTIVE non évalué sur 12h
# est un signal fort que la couche principe ne tourne pas (bug ou silence).
PRINCIPLE_RECENT_WINDOW_HOURS = 12

# Fenêtre "snapshot live < 24h" pour CHECK 4.
LIVE_SNAPSHOT_STALE_HOURS = 24


# ---------- Helpers ----------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse un timestamp ISO UTC, tolérant les variantes avec/sans timezone."""
    if ts is None:
        return None
    try:
        # Remplace le +00:00 par Z si absent (cas de sqlite TEXT).
        s = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _rows(conn) -> list:
    """Helper — pose row_factory=Row et renvoie la connexion.

    Les check_* utilisent r["col"] qui n'existe pas si row_factory
    n'est pas posé. get_connection() du projet ne le fait pas par défaut
    (cohérent avec les modules qui posent leur propre row_factory).
    Cette pose locale évite qu'un appel direct check_X(conn) sans
    run_all_checks plante.
    """
    conn.row_factory = sqlite3.Row
    return conn


# ---------- Checks ----------


def check1_orphans(conn) -> dict:
    """Orphelins de chaîne : scene→snapshot, behavior→scene, window→behavior,
    exploitability→window. ERREUR si orphelin détecté."""
    conn = _rows(conn)
    issues: list[dict] = []

    if _table_exists(conn, "scenes") and _table_exists(conn, "forces_snapshots"):
        rows = conn.execute(
            "SELECT scene_id, forces_snapshot_ref FROM scenes "
            "WHERE forces_snapshot_ref IS NOT NULL "
            "AND forces_snapshot_ref NOT IN (SELECT snapshot_id FROM forces_snapshots)"
        ).fetchall()
        for r in rows:
            issues.append({
                "table": "scenes", "id": r["scene_id"],
                "missing_ref": r["forces_snapshot_ref"], "fk": "forces_snapshot_ref",
            })

    if _table_exists(conn, "behaviors") and _table_exists(conn, "scenes"):
        rows = conn.execute(
            "SELECT behavior_id, scene_id_ref FROM behaviors "
            "WHERE scene_id_ref IS NOT NULL "
            "AND scene_id_ref NOT IN (SELECT scene_id FROM scenes)"
        ).fetchall()
        for r in rows:
            issues.append({
                "table": "behaviors", "id": r["behavior_id"],
                "missing_ref": r["scene_id_ref"], "fk": "scene_id_ref",
            })

    if _table_exists(conn, "windows") and _table_exists(conn, "behaviors"):
        rows = conn.execute(
            "SELECT window_id, behavior_id FROM windows "
            "WHERE behavior_id IS NOT NULL "
            "AND behavior_id NOT IN (SELECT behavior_id FROM behaviors)"
        ).fetchall()
        for r in rows:
            issues.append({
                "table": "windows", "id": r["window_id"],
                "missing_ref": r["behavior_id"], "fk": "behavior_id",
            })

    if _table_exists(conn, "exploitability") and _table_exists(conn, "windows"):
        rows = conn.execute(
            "SELECT exploitability_id, window_id FROM exploitability "
            "WHERE window_id IS NOT NULL "
            "AND window_id NOT IN (SELECT window_id FROM windows)"
        ).fetchall()
        for r in rows:
            issues.append({
                "table": "exploitability", "id": r["exploitability_id"],
                "missing_ref": r["window_id"], "fk": "window_id",
            })

    return {
        "check": "1_orphans",
        "label": "Orphelins de chaîne (FK logiques)",
        "status": "ERROR" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }


def check2_decisions_without_signal(conn) -> dict:
    """Toute decision doit référencer un signal_id existant. ERREUR sinon."""
    conn = _rows(conn)
    if not _table_exists(conn, "decisions"):
        return {"check": "2_decisions_no_signal", "label": "Décisions sans signal",
                "status": "OK", "issues": [], "count": 0, "skipped": "no decisions table"}
    if not _table_exists(conn, "signals"):
        return {"check": "2_decisions_no_signal", "label": "Décisions sans signal",
                "status": "OK", "issues": [], "count": 0, "skipped": "no signals table"}

    rows = conn.execute(
        "SELECT decision_id, signal_id FROM decisions "
        "WHERE signal_id IS NOT NULL "
        "AND signal_id NOT IN (SELECT signal_id FROM signals)"
    ).fetchall()
    issues = [{"decision_id": r["decision_id"], "missing_signal_id": r["signal_id"]}
              for r in rows]

    return {
        "check": "2_decisions_no_signal",
        "label": "Décisions sans signal",
        "status": "ERROR" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }


def check3_signals_without_principles(conn) -> dict:
    """Tout signal directionnel (direction NOT NULL et != 'neutre') doit
    avoir principes_source_json non vide. ERREUR sinon."""
    conn = _rows(conn)
    if not _table_exists(conn, "signals"):
        return {"check": "3_signals_no_principles", "label": "Signaux sans principe",
                "status": "OK", "issues": [], "count": 0, "skipped": "no signals table"}

    rows = conn.execute(
        "SELECT signal_id, snapshot_id, direction, confiance, "
        "principes_source_json FROM signals "
        "WHERE direction IS NOT NULL AND direction != 'neutre'"
    ).fetchall()
    issues = []
    for r in rows:
        pj = r["principes_source_json"]
        if pj is None or pj.strip() in ("", "[]", "null"):
            issues.append({
                "signal_id": r["signal_id"],
                "snapshot_id": r["snapshot_id"],
                "direction": r["direction"],
                "confiance": r["confiance"],
                "principes_source_json": pj,
            })

    return {
        "check": "3_signals_no_principles",
        "label": "Signaux directionnels sans principes",
        "status": "ERROR" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }


def check4_live_stale_snapshots(conn) -> dict:
    """Toute rangée live (source_type='live') doit avoir un timestamp dans
    les dernières 24h. WARNING sinon (stale potentiel — pas forcément
    bloquant, mais à inspecter).

    Cible les 8 tables dérivées (forces_snapshots n'a pas source_type ;
    son marquage est `source`='MT4_SDI' et toutes les bougies live
    actuelles sont par définition récentes).
    """
    conn = _rows(conn)
    derived_tables = [
        "scenes", "behaviors", "windows", "exploitability",
        "regime_snapshots", "principle_evaluations", "signals", "decisions",
    ]
    cutoff = (_now_utc() - timedelta(hours=LIVE_SNAPSHOT_STALE_HOURS)).isoformat()
    issues: list[dict] = []
    skipped: list[str] = []
    for table in derived_tables:
        if not _table_exists(conn, table):
            skipped.append(table)
            continue
        # PRAGMA table_info pour vérifier la présence de source_type ET timestamp.
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "source_type" not in cols or "timestamp" not in cols:
            skipped.append(table)
            continue
        rows = conn.execute(
            f"SELECT timestamp, source_type FROM {table} "
            f"WHERE source_type = 'live' AND timestamp < ?",
            (cutoff,),
        ).fetchall()
        for r in rows:
            issues.append({"table": table, "timestamp": r["timestamp"]})

    out = {
        "check": "4_live_stale",
        "label": f"Rangées live > {LIVE_SNAPSHOT_STALE_HOURS}h (stale)",
        "status": "WARNING" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }
    if skipped and not issues:
        out["skipped"] = f"tables absentes/sans source_type : {', '.join(skipped)}"
    return out


def check5_decision_duplicates(conn) -> dict:
    """Aucun snapshot_id ne doit apparaître 2 fois dans decisions avec la
    même direction et la même confiance. WARNING (idempotence à vérifier
    côté logger — ne devrait pas se produire avec le fix 2026-07-06)."""
    conn = _rows(conn)
    if not _table_exists(conn, "decisions"):
        return {"check": "5_decision_dup", "label": "Décisions doublons",
                "status": "OK", "issues": [], "count": 0, "skipped": "no decisions"}

    rows = conn.execute(
        "SELECT snapshot_id, direction, confiance, COUNT(*) AS nb, "
        "       GROUP_CONCAT(decision_id, ',') AS decision_ids "
        "FROM decisions "
        "WHERE snapshot_id IS NOT NULL "
        "GROUP BY snapshot_id, direction, confiance "
        "HAVING COUNT(*) > 1"
    ).fetchall()
    issues = [{
        "snapshot_id": r["snapshot_id"],
        "direction": r["direction"],
        "confiance": r["confiance"],
        "count": r["nb"],
        "decision_ids": r["decision_ids"],
    } for r in rows]

    return {
        "check": "5_decision_dup",
        "label": "Décisions doublons (snapshot×direction×confiance)",
        "status": "WARNING" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }


def check6_principles_no_recent_eval(conn) -> dict:
    """Tout principe v9_status=ACTIVE doit avoir au moins 1 évaluation dans
    principle_evaluations sur les N dernières heures UTC. WARNING sinon."""
    conn = _rows(conn)
    if not _table_exists(conn, "principles") or not _table_exists(conn, "principle_evaluations"):
        return {"check": "6_principles_no_eval", "label": "Principes ACTIVE muets",
                "status": "OK", "issues": [], "count": 0,
                "skipped": "no principles or principle_evaluations"}

    cutoff = (_now_utc() - timedelta(hours=PRINCIPLE_RECENT_WINDOW_HOURS)).isoformat()
    rows = conn.execute(
        "SELECT p.principle_id, p.v9_status "
        "FROM principles p "
        "WHERE p.v9_status = 'ACTIVE' "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM principle_evaluations pe "
        "  WHERE pe.principle_id = p.principle_id "
        "  AND pe.timestamp >= ?"
        ")",
        (cutoff,),
    ).fetchall()
    issues = [{"principle_id": r["principle_id"], "v9_status": r["v9_status"]}
              for r in rows]

    return {
        "check": "6_principles_no_eval",
        "label": f"Principes ACTIVE sans évaluation ({PRINCIPLE_RECENT_WINDOW_HOURS}h)",
        "status": "WARNING" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }


def check7_confiance_out_of_range(conn) -> dict:
    """Toute decision avec direction != NULL doit avoir confiance ∈ [1..100].
    ERREUR si confiance=0 avec direction!=NULL, ou confiance > 100."""
    conn = _rows(conn)
    if not _table_exists(conn, "decisions"):
        return {"check": "7_confiance_range", "label": "Confiance hors plage",
                "status": "OK", "issues": [], "count": 0, "skipped": "no decisions"}

    # directionnel + confiance=0
    rows_zero = conn.execute(
        "SELECT decision_id, direction, confiance FROM decisions "
        "WHERE direction IS NOT NULL AND direction != 'neutre' "
        "AND (confiance IS NULL OR confiance = 0)"
    ).fetchall()
    # confiance > 100
    rows_over = conn.execute(
        "SELECT decision_id, direction, confiance FROM decisions "
        "WHERE confiance > 100"
    ).fetchall()
    # confiance < 0 (cas dégénéré)
    rows_neg = conn.execute(
        "SELECT decision_id, direction, confiance FROM decisions "
        "WHERE confiance < 0"
    ).fetchall()

    issues = []
    for r in rows_zero:
        issues.append({
            "decision_id": r["decision_id"], "direction": r["direction"],
            "confiance": r["confiance"], "reason": "directionnel avec confiance=0/NULL",
        })
    for r in rows_over:
        issues.append({
            "decision_id": r["decision_id"], "direction": r["direction"],
            "confiance": r["confiance"], "reason": "confiance > 100",
        })
    for r in rows_neg:
        issues.append({
            "decision_id": r["decision_id"], "direction": r["direction"],
            "confiance": r["confiance"], "reason": "confiance < 0",
        })

    return {
        "check": "7_confiance_range",
        "label": "Confiance décisions hors plage [1..100]",
        "status": "ERROR" if issues else "OK",
        "issues": issues,
        "count": len(issues),
    }


# ---------- Orchestration ----------


ALL_CHECKS = [
    check1_orphans,
    check2_decisions_without_signal,
    check3_signals_without_principles,
    check4_live_stale_snapshots,
    check5_decision_duplicates,
    check6_principles_no_recent_eval,
    check7_confiance_out_of_range,
]


def run_all_checks(conn) -> list[dict]:
    # Pose row_factory sur la connexion — toutes les fonctions check_* en
    # dépendent (accès par clé sur fetchall).
    conn.row_factory = sqlite3.Row
    results = []
    for check_fn in ALL_CHECKS:
        try:
            results.append(check_fn(conn))
        except Exception as exc:  # noqa: BLE001
            results.append({
                "check": check_fn.__name__,
                "label": check_fn.__name__,
                "status": "ERROR",
                "issues": [{"exception": str(exc), "type": type(exc).__name__}],
                "count": 1,
                "exception": True,
            })
    return results


def summarize(results: list[dict]) -> dict:
    """Agrège en {ok: N, warning: N, error: N} + exit_code."""
    counts = {"ok": 0, "warning": 0, "error": 0}
    for r in results:
        s = r["status"]
        if s == "OK":
            counts["ok"] += 1
        elif s == "WARNING":
            counts["warning"] += 1
        else:
            counts["error"] += 1
    exit_code = 0
    if counts["error"] > 0:
        exit_code = 2
    elif counts["warning"] > 0:
        exit_code = 1
    return {"counts": counts, "exit_code": exit_code}


def format_console(results: list[dict], summary: dict) -> str:
    lines = ["=" * 70, "V9 DB coherence check", "=" * 70]
    for r in results:
        icon = {"OK": "✅ OK", "WARNING": "⚠️  WARN", "ERROR": "❌ ERR"}.get(r["status"], "?")
        skipped = f"  (skipped: {r['skipped']})" if r.get("skipped") else ""
        lines.append(f"  {icon}  [{r['check']}] {r['label']} — {r['count']} issue(s){skipped}")
        if r["issues"]:
            for i, issue in enumerate(r["issues"][:5]):
                lines.append(f"           - {issue}")
            if len(r["issues"]) > 5:
                lines.append(f"           ... et {len(r['issues']) - 5} autre(s)")
    lines.append("-" * 70)
    c = summary["counts"]
    lines.append(
        f"  Résumé : OK={c['ok']}  WARNING={c['warning']}  ERROR={c['error']}"
    )
    lines.append("=" * 70)
    return "\n".join(lines)


def format_fix_report(results: list[dict]) -> str:
    """Liste plate des IDs à corriger (sans corriger — lecture seule)."""
    lines = ["# V9 DB — Fix report (lecture seule)"]
    for r in results:
        if r["status"] == "OK":
            continue
        lines.append(f"\n## {r['check']} — {r['label']} ({r['status']})")
        if not r["issues"]:
            lines.append("  (aucun)")
            continue
        for issue in r["issues"]:
            lines.append(f"  - {issue}")
    return "\n".join(lines)


# ---------- CLI ----------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Contrôle cohérence DB V9 live (lecture seule).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Sortie JSON structurée (pour intégration future).",
    )
    parser.add_argument(
        "--fix-report", action="store_true",
        help="Liste les IDs à corriger sans corriger (rapport lecture seule).",
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        results = run_all_checks(conn)
    finally:
        conn.close()

    summary = summarize(results)

    if args.json:
        print(json.dumps(
            {"summary": summary, "checks": results},
            indent=2, ensure_ascii=False, default=str,
        ))
    elif args.fix_report:
        print(format_fix_report(results))
    else:
        print(format_console(results, summary))

    return summary["exit_code"]


if __name__ == "__main__":
    sys.exit(main())