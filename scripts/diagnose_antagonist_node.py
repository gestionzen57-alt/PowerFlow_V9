"""diagnose_antagonist_node.py — Diagnostic structurel d'ANTAGONIST_NODE.

ANTAGONIST_NODE a 0/256 triggers historiques (cf AUDIT_DB §5).
Trois causes possibles à départager :
1. BUG CODE : `_load_shared_context` ne peuple pas h1_dir/m5_dir
2. BUG YAML : les conditions sont mal formées / impossibles à satisfaire
3. RÉGIME MARCHÉ : H1 et M5 sont mécaniquement corrélés sur la période

Le script :
- Charge les 256 snapshots H1 GBPUSD
- Extrait h1_dir, m5_dir, h1_state, m5_state du contexte
- Dump les 5 premiers + distribution globale des couples (h1_dir, m5_dir)
- Teste chaque condition individuellement sur UN snapshot
- Rend un verdict : BUG_CODE / BUG_YAML / INERT_MARKET / OK

Usage :
    python scripts/diagnose_antagonist_node.py
    python scripts/diagnose_antagonist_node.py --json  (sortie JSON parsable)
    python scripts/diagnose_antagonist_node.py --report path.md

Sortie standard :
    [.. ] Chargement 256 snapshots H1 GBPUSD...
    [OK ] Contexte chargé pour 256 snapshots
    [.. ] Distribution couples (h1_dir, m5_dir):
            (HAUSSIERE, HAUSSIERE): 255
            (NEUTRE,    HAUSSIERE): 1
    [.. ] Test conditions sur 1 snapshot:
            cond[0] h1_state not_in [NEUTRAL,None]  ctx=HAUSSIERE result=True
            ...
    [VERDICT] INERT_MARKET : H1 et M5 strictement corrélés sur la période
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import yaml  # noqa: E402

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.principle_engine import (  # noqa: E402
    PrincipleEngine,
    evaluate_condition,
)


PRINCIPLE_PATH = ROOT_DIR / "core" / "v9" / "principles" / "ANTAGONIST_NODE.yaml"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _load_spec() -> dict[str, Any]:
    if not PRINCIPLE_PATH.exists():
        raise FileNotFoundError(f"YAML introuvable : {PRINCIPLE_PATH}")
    return yaml.safe_load(PRINCIPLE_PATH.read_text(encoding="utf-8"))


def diagnose(db_path: Path = DB_PATH) -> dict[str, Any]:
    """Effectue le diagnostic complet, retourne un dict structuré."""
    spec = _load_spec()
    conds = spec["conditions"]
    eng = PrincipleEngine()
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        snap_ids = [
            r[0]
            for r in conn.execute(
                "SELECT snapshot_id FROM forces_snapshots "
                "WHERE symbol='GBPUSD' AND timeframe='H1' "
                "ORDER BY timestamp DESC"
            ).fetchall()
        ]
        if not snap_ids:
            return {
                "verdict": "NO_DATA",
                "n_snapshots": 0,
                "details": "Aucun snapshot H1 GBPUSD en DB",
            }

        combos: Counter = Counter()
        samples: list[dict] = []
        cond_results_per_snap: list[list[bool]] = []
        for sid in snap_ids:
            shared = eng._load_shared_context(conn, sid)
            ctx = shared["context"]
            h1_dir = ctx.get("h1_dir")
            m5_dir = ctx.get("m5_dir")
            h1_state = ctx.get("h1_state")
            m5_state = ctx.get("m5_state")
            combos[(h1_dir, m5_dir)] += 1
            if len(samples) < 5:
                samples.append({
                    "snapshot_id_tail": sid[-12:],
                    "h1_dir": h1_dir,
                    "m5_dir": m5_dir,
                    "h1_state": h1_state,
                    "m5_state": m5_state,
                })
            cond_results = [evaluate_condition(c, ctx) for c in conds]
            cond_results_per_snap.append(cond_results)

        n_snap = len(snap_ids)
        n_divergent = sum(
            1 for sid in snap_ids
            if True  # placeholder, on calcule différemment
        )  # recalcul propre ci-dessous
        # Recompte divergence : h1_dir != m5_dir ET ni None, ni NEUTRE
        n_divergent = 0
        n_neutral_any = 0
        for sid in snap_ids:
            shared = eng._load_shared_context(conn, sid)
            ctx = shared["context"]
            h1 = ctx.get("h1_dir")
            m5 = ctx.get("m5_dir")
            if h1 in (None, "NEUTRE") or m5 in (None, "NEUTRE"):
                n_neutral_any += 1
                continue
            if h1 != m5:
                n_divergent += 1

        n_all_cond_true = sum(
            1 for results in cond_results_per_snap if all(results)
        )

        # Verdict
        ctx_loaded_ok = any(
            eng._load_shared_context(conn, sid)["context"].get("h1_dir") is not None
            for sid in snap_ids[:1]
        )
        if not ctx_loaded_ok:
            verdict = "BUG_CODE"
            reason = "h1_dir/m5_dir non populés par _load_shared_context"
        elif n_all_cond_true == 0 and n_divergent == 0:
            verdict = "INERT_MARKET"
            reason = (
                f"H1 et M5 strictement corrélés sur la période "
                f"({n_snap} snapshots, 0 divergent). ANTAGONIST_NODE attend "
                f"des fenêtres d'antagonisme (notes YAML : terrain optimal = "
                f"NEWS_SHOCK, divergence H1 vs M5 amplifiée par choc liquidité)."
            )
        elif n_all_cond_true == 0:
            verdict = "BUG_YAML"
            reason = (
                f"Conditions jamais satisfaites malgré {n_divergent} divergences "
                f"détectées. Vérifier l'opérateur de la condition finale "
                f"(h1_dir != m5_dir)."
            )
        else:
            verdict = "OK"
            reason = f"{n_all_cond_true}/{n_snap} snapshots déclenchent"

        # Test détaillé sur le 1er snapshot
        first_sid = snap_ids[0]
        shared = eng._load_shared_context(conn, first_sid)
        ctx = shared["context"]
        cond_dump = []
        for i, c in enumerate(conds):
            val = ctx.get(c["field"])
            target = c.get("value_field") or c.get("value")
            res = evaluate_condition(c, ctx)
            cond_dump.append({
                "idx": i,
                "field": c["field"],
                "op": c["op"],
                "target": str(target),
                "context_value": val,
                "result": res,
            })

        return {
            "verdict": verdict,
            "reason": reason,
            "n_snapshots": n_snap,
            "n_all_cond_true": n_all_cond_true,
            "n_divergent": n_divergent,
            "n_neutral_any": n_neutral_any,
            "distribution_dir_combos": [
                {"h1_dir": k[0], "m5_dir": k[1], "count": v}
                for k, v in combos.most_common()
            ],
            "samples": samples,
            "cond_dump": cond_dump,
            "yaml_path": str(PRINCIPLE_PATH),
            "n_conditions": len(conds),
        }
    finally:
        conn.close()


def render_text(report: dict) -> str:
    lines = []
    lines.append(f"[.. ] YAML : {report['yaml_path']}")
    lines.append(f"[.. ] Snapshots H1 GBPUSD analysés : {report['n_snapshots']}")
    if report.get("n_conditions"):
        lines.append(f"[.. ] Nombre de conditions YAML : {report['n_conditions']}")
    lines.append("")
    lines.append("[.. ] Distribution couples (h1_dir, m5_dir) :")
    for combo in report["distribution_dir_combos"]:
        lines.append(
            f"        ({combo['h1_dir']!r}, {combo['m5_dir']!r}): {combo['count']}"
        )
    lines.append("")
    lines.append(f"[.. ] Divergences H1 vs M5 : {report['n_divergent']}")
    lines.append(f"[.. ] Conditions satisfaites (toutes) : {report['n_all_cond_true']}")
    lines.append("")
    if report.get("samples"):
        lines.append("[.. ] Échantillons (5 premiers) :")
        for s in report["samples"]:
            lines.append(
                f"        {s['snapshot_id_tail']}  "
                f"h1_dir={s['h1_dir']!r}  m5_dir={s['m5_dir']!r}  "
                f"h1_state={s['h1_state']!r}  m5_state={s['m5_state']!r}"
            )
    if report.get("cond_dump"):
        lines.append("")
        lines.append("[.. ] Test des conditions sur 1 snapshot :")
        for c in report["cond_dump"]:
            lines.append(
                f"        cond[{c['idx']}] {c['field']} {c['op']} {c['target']}  "
                f"-> ctx={c['context_value']!r}  result={c['result']}"
            )
    lines.append("")
    lines.append(f"[VERDICT] {report['verdict']}")
    lines.append(f"          {report['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Diagnostic structurel d'ANTAGONIST_NODE (0/256 triggers)"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--report", type=Path, default=None,
                        help="Écrire rapport Markdown dans ce fichier")
    args = parser.parse_args(argv)

    report = diagnose(args.db)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.report:
        lines = [
            f"# Diagnostic ANTAGONIST_NODE — {args.db}",
            "",
            f"- **Date** : généré par `diagnose_antagonist_node.py`",
            f"- **Verdict** : **{report['verdict']}**",
            f"- **Raison** : {report['reason']}",
            f"- **Snapshots analysés** : {report['n_snapshots']}",
            f"- **Conditions satisfaites (toutes)** : {report['n_all_cond_true']}",
            f"- **Divergences H1 vs M5** : {report['n_divergent']}",
            f"- **N conditions YAML** : {report.get('n_conditions', '?')}",
            "",
            "## Distribution couples (h1_dir, m5_dir)",
            "",
            "| h1_dir | m5_dir | count |",
            "|---|---|---|",
        ]
        for combo in report["distribution_dir_combos"]:
            lines.append(
                f"| {combo['h1_dir']!r} | {combo['m5_dir']!r} | {combo['count']} |"
            )
        if report.get("samples"):
            lines += [
                "",
                "## Échantillons",
                "",
                "| snapshot | h1_dir | m5_dir | h1_state | m5_state |",
                "|---|---|---|---|---|",
            ]
            for s in report["samples"]:
                lines.append(
                    f"| `{s['snapshot_id_tail']}` | {s['h1_dir']!r} | {s['m5_dir']!r} "
                    f"| {s['h1_state']!r} | {s['m5_state']!r} |"
                )
        if report.get("cond_dump"):
            lines += [
                "",
                "## Évaluation des conditions (1 snapshot)",
                "",
                "| idx | field | op | target | ctx value | result |",
                "|---|---|---|---|---|---|",
            ]
            for c in report["cond_dump"]:
                lines.append(
                    f"| {c['idx']} | {c['field']} | {c['op']} | {c['target']} "
                    f"| {c['context_value']!r} | {c['result']} |"
                )
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[OK ] Rapport Markdown écrit : {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
