"""diagnose_shadow_no_trigger.py — Diagnostic des SHADOW 0-trigger malgré
conditions écrites (Phase 14a).

Pour chaque SHADOW listé en argument, charge les conditions, évalue sur
N snapshots récents, et identifie quelle condition fail systématiquement.
Sortie : distribution par condition failed → insight pour refonte.

Usage :
    python scripts/diagnose_shadow_no_trigger.py GRAMMAR_BREAK GRAMMAR_PULLBACK
    python scripts/diagnose_shadow_no_trigger.py GRAMMAR_BREAK --limit 100
    python scripts/diagnose_shadow_no_trigger.py --all-shadow-no-trigger
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, PRINCIPLE_ACTIVE_IDS  # noqa: E402
from core.v9.principle_engine import (  # noqa: E402
    PrincipleEngine,
    evaluate_condition,
)


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def diagnose_principle(
    pname: str,
    db_path: Path = DB_PATH,
    limit: int = 50,
    principles_dir: Path | None = None,
) -> dict[str, Any]:
    """Pour un SHADOW donné, évalue sur les N derniers snapshots M5 GBPUSD.
    Retourne la distribution des conditions failed (les plus failées
    sont les bottlenecks de la refonte).

    `principles_dir` paramétrable pour les tests (défaut: core/v9/principles).
    """
    if principles_dir is None:
        principles_dir = ROOT_DIR / "core" / "v9" / "principles"
    yaml_path = principles_dir / f"{pname}.yaml"
    if not yaml_path.exists():
        return {"principle": pname, "error": "yaml_not_found"}
    spec = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    conds = spec.get("conditions", [])
    if not conds:
        return {"principle": pname, "error": "no_conditions", "n_conditions": 0}

    eng = PrincipleEngine()
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT snapshot_id FROM forces_snapshots "
            "WHERE symbol='GBPUSD' AND timeframe='M5' "
            "ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

        n_total = 0
        n_triggered = 0
        n_per_cond_pass: Counter = Counter()  # combien de snapshots passent chaque cond
        n_per_cond_fail: Counter = Counter()  # combien de snapshots fail chaque cond
        cond_results: list[list[bool]] = []
        for (sid,) in rows:
            shared = eng._load_shared_context(conn, sid)
            ctx = shared["context"]
            res = [evaluate_condition(c, ctx) for c in conds]
            cond_results.append(res)
            n_total += 1
            for i, r in enumerate(res):
                if r:
                    n_per_cond_pass[i] += 1
                else:
                    n_per_cond_fail[i] += 1
            if all(res):
                n_triggered += 1

        # Distribution failed : pour chaque snapshot, lister les cond qui fail
        always_failing = [
            i for i in range(len(conds))
            if n_per_cond_fail[i] == n_total
        ]
        return {
            "principle": pname,
            "n_conditions": len(conds),
            "n_snapshots_tested": n_total,
            "n_triggered": n_triggered,
            "trigger_rate_pct": round(n_triggered / max(1, n_total) * 100, 1),
            "conditions": conds,
            "n_per_cond_pass": dict(n_per_cond_pass),
            "n_per_cond_fail": dict(n_per_cond_fail),
            "always_failing_idx": always_failing,
            "verdict": (
                "BOTTLE_NECK_IDENTIFIED" if always_failing
                else "NO_SINGLE_BOTTLENECK" if n_triggered == 0
                else "OK_TRIGGERS_RARELY"
            ),
        }
    finally:
        conn.close()


def list_no_trigger_shadows(
    db_path: Path = DB_PATH,
    principles_dir: Path | None = None,
) -> list[str]:
    """Liste les SHADOW qui n'ont jamais déclenché (0 triggers en DB).
    Utilise les counters globaux, pas une évaluation snapshot par snapshot.
    `principles_dir` paramétrable pour les tests."""
    if principles_dir is None:
        principles_dir = ROOT_DIR / "core" / "v9" / "principles"
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        cur = conn.execute(
            "SELECT DISTINCT principle_id FROM principle_evaluations "
            "WHERE triggered=1 AND principle_id NOT IN "
            "(SELECT principle_id FROM principles WHERE v9_status='ACTIVE')"
        )
        triggered = {r[0] for r in cur.fetchall()}
        # Tous les SHADOW
        all_shadows = []
        for f in principles_dir.glob("*.yaml"):
            spec = yaml.safe_load(f.read_text(encoding="utf-8"))
            pid = spec.get("id")
            if not pid:
                continue
            if pid in PRINCIPLE_ACTIVE_IDS:
                continue
            if spec.get("conditions"):  # avec conditions écrites
                all_shadows.append(pid)
        return [s for s in all_shadows if s not in triggered]
    finally:
        conn.close()


def render_text(report: dict) -> str:
    lines = [
        f"[.. ] Principe : {report['principle']}",
        f"[.. ] Conditions : {report['n_conditions']}",
        f"[.. ] Snapshots testés : {report['n_snapshots_tested']}",
        f"[.. ] Triggers : {report['n_triggered']} ({report['trigger_rate_pct']}%)",
        "",
    ]
    if "error" in report:
        lines.append(f"[ERR] {report['error']}")
        return "\n".join(lines) + "\n"

    for i, c in enumerate(report["conditions"]):
        n_pass = report["n_per_cond_pass"].get(i, 0)
        n_fail = report["n_per_cond_fail"].get(i, 0)
        marker = " ⚠️ TOUJOURS FAIL" if i in report["always_failing_idx"] else ""
        lines.append(
            f"        cond[{i}] {c['field']} {c['op']} {c.get('value', c.get('value_field'))} "
            f"-> pass={n_pass}/{report['n_snapshots_tested']}{marker}"
        )
    lines.append("")
    lines.append(f"[VERDICT] {report['verdict']}")
    if report["always_failing_idx"]:
        lines.append(
            f"          Conditions toujours fail : {report['always_failing_idx']} — "
            f"refonte nécessaire (fallback ou recalibrage)"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Diagnostic SHADOW 0-trigger (Phase 14a)"
    )
    parser.add_argument(
        "principles", nargs="*",
        help="Noms des principes à diagnostiquer (ex: GRAMMAR_BREAK GRAMMAR_PULLBACK)",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Nombre de snapshots M5 GBPUSD à tester (défaut 50)",
    )
    parser.add_argument(
        "--all-shadow-no-trigger", action="store_true",
        help="Diagnostiquer tous les SHADOW avec conditions qui n'ont jamais déclenché",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.all_shadow_no_trigger:
        targets = list_no_trigger_shadows()
    elif args.principles:
        targets = args.principles
    else:
        print("ERREUR: fournir au moins un principe OU --all-shadow-no-trigger",
              file=sys.stderr)
        return 2

    reports = [diagnose_principle(p, limit=args.limit) for p in targets]
    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        for r in reports:
            print(render_text(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
