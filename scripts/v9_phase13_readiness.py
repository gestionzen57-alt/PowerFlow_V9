"""v9_phase13_readiness.py — Audit READINESS des SHADOW (Phase 13).

Pour chaque principe SHADOW du catalogue YAML, calcule les 4 critères
R25' de promotion structurelle :
1. conditions écrites (YAML non vide)
2. n_evaluations > 0 (déjà évalué au moins 1 fois)
3. n_triggers > 0 (a déclenché au moins 1 fois)
4. hit_rate calculable (WIN/LOSS résolus disponibles pour les triggers)

Verdict par principe :
- READY_STRUCTURAL : 1+2+3 OK, 4 manquant (WIN/LOSS data absente = bloqué)
- READY_FULL       : 1+2+3+4 OK (toutes conditions remplies)
- BLOCKED_DATA     : WIN/LOSS = 0, empêche hit_rate
- BLOCKED_NO_TRIGGER : 1 OK mais 3 = 0 (jamais déclenché → refactor YAML ?)
- INERT_NO_CONDITIONS: 1 manquant (YAML conditions vides — classe C R30)

Usage :
    python scripts/v9_phase13_readiness.py
    python scripts/v9_phase13_readiness.py --json
    python scripts/v9_phase13_readiness.py --report path.md

Sortie standard : tableau markdown + verdict global Phase 13.
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

# Seuils R30 (repères initiaux révisables par Søn)
THRESHOLD_TRIGGERS = 50
THRESHOLD_HIT_RATE = 60  # %
# Seuil de rentabilité pips (filtre le bruit du marché). Défaut 0 = is_win strict.
# Un seuil > 0 filtre les résolutions pips=0 (cochonnet, faux signal).
THRESHOLD_PIPS = 0.0


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _eval_principle(spec: dict, conn: sqlite3.Connection) -> dict:
    """Pour un principe (depuis YAML), retourne ses compteurs DB."""
    pid = spec["id"]
    # n_evaluations
    cur = conn.execute(
        "SELECT COUNT(*) FROM principle_evaluations WHERE principle_id = ?",
        (pid,),
    )
    n_eval = cur.fetchone()[0]
    # n_triggers
    cur = conn.execute(
        "SELECT COUNT(*) FROM principle_evaluations "
        "WHERE principle_id = ? AND triggered = 1",
        (pid,),
    )
    n_trig = cur.fetchone()[0]
    # hit_rate : pour les triggers, on regarde s'il existe des decisions
    # correspondantes avec is_win résolu. C'est heuristique — on compte
    # les principle_evaluations.triggered=1 qui ont un snapshot_id référencé
    # par decisions.is_win IS NOT NULL.
    if n_trig == 0:
        hit_rate_pct = None
        n_resolved = 0
        # Hit rate filtré (avec seuil pips) : identique à brut si pas de trigger
        hit_rate_filtered_pct = None
        n_resolved_filtered = 0
    else:
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM principle_evaluations pe
            JOIN decisions d ON d.snapshot_id = pe.snapshot_id
            WHERE pe.principle_id = ? AND pe.triggered = 1
              AND d.is_win IS NOT NULL
            """,
            (pid,),
        )
        n_resolved = cur.fetchone()[0]
        if n_resolved > 0:
            cur = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN d.is_win = 1 THEN 1 ELSE 0 END) * 100.0
                    / COUNT(*)
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ? AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                """,
                (pid,),
            )
            hit_rate_pct = round(cur.fetchone()[0], 1)
        else:
            hit_rate_pct = None
        # Hit rate FILTRÉ par seuil de rentabilité pips (filtre le bruit marché)
        if THRESHOLD_PIPS > 0:
            cur = conn.execute(
                """
                SELECT COUNT(*) FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ? AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                  AND ABS(d.resolution_pips) >= ?
                """,
                (pid, THRESHOLD_PIPS),
            )
            n_resolved_filtered = cur.fetchone()[0]
            if n_resolved_filtered > 0:
                cur = conn.execute(
                    """
                    SELECT
                        SUM(CASE WHEN d.is_win = 1 THEN 1 ELSE 0 END) * 100.0
                        / COUNT(*)
                    FROM principle_evaluations pe
                    JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                    WHERE pe.principle_id = ? AND pe.triggered = 1
                      AND d.is_win IS NOT NULL
                      AND ABS(d.resolution_pips) >= ?
                    """,
                    (pid, THRESHOLD_PIPS),
                )
                hit_rate_filtered_pct = round(cur.fetchone()[0], 1)
            else:
                hit_rate_filtered_pct = None
        else:
            hit_rate_filtered_pct = hit_rate_pct
            n_resolved_filtered = n_resolved
    return {
        "n_evaluations": n_eval,
        "n_triggers": n_trig,
        "n_resolved": n_resolved,
        "hit_rate_pct": hit_rate_pct,
        "n_resolved_filtered": n_resolved_filtered,
        "hit_rate_filtered_pct": hit_rate_filtered_pct,
    }


def _verdict(conditions_written: bool, counters: dict) -> str:
    """Combine les critères R25'/R30 en un verdict par principe.

    Utilise hit_rate_filtered_pct (filtré par pips si THRESHOLD_PIPS > 0)
    si disponible, sinon hit_rate_pct brut. Cela évite de promouvoir
    sur du bruit de marché (pips proches de 0).
    """
    if not conditions_written:
        return "INERT_NO_CONDITIONS"
    if counters["n_triggers"] == 0:
        return "BLOCKED_NO_TRIGGER"
    if counters["n_triggers"] < THRESHOLD_TRIGGERS:
        return "EARLY_TRIGGERS"
    # Utiliser le hit_rate filtré si dispo
    hr = counters.get("hit_rate_filtered_pct")
    if hr is None:
        hr = counters.get("hit_rate_pct")
    if hr is None:
        return "READY_STRUCTURAL"
    if hr >= THRESHOLD_HIT_RATE:
        return "READY_FULL"
    return "READY_LOW_HIT_RATE"


def audit(
    db_path: Path = DB_PATH,
    principles_dir: Path | None = None,
    threshold_pips: float = 0.0,
) -> dict[str, Any]:
    """Pour chaque SHADOW, calcule les compteurs et le verdict.
    `principles_dir` est paramétrable pour les tests (défaut: ROOT_DIR/core/v9/principles).
    `threshold_pips` : filtre le hit_rate sur les décisions avec |pips| >= seuil
    (défaut 0 = pas de filtre, hit_rate brut)."""
    if principles_dir is None:
        principles_dir = ROOT_DIR / "core" / "v9" / "principles"
    # Mettre à jour le seuil global (utilisé par _eval_principle)
    global THRESHOLD_PIPS
    THRESHOLD_PIPS = threshold_pips
    # Lister les YAML directement (PrincipleRecord ne stocke pas le path source,
    # et on a besoin de recharger le spec complet pour vérifier conditions).
    yaml_files = sorted(principles_dir.glob("*.yaml"))
    shadow_specs = []
    for yf in yaml_files:
        spec = yaml.safe_load(yf.read_text(encoding="utf-8"))
        pid = spec.get("id")
        if not pid:
            continue
        if pid in PRINCIPLE_ACTIVE_IDS:
            continue
        spec["_yaml_path"] = yf
        shadow_specs.append(spec)
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        rows = []
        n_wins = conn.execute("SELECT COUNT(*) FROM decisions WHERE is_win=1").fetchone()[0]
        n_losses = conn.execute("SELECT COUNT(*) FROM decisions WHERE is_win=0").fetchone()[0]
        n_open = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE is_win IS NULL AND action<>'aucune_action'"
        ).fetchone()[0]
        for spec in shadow_specs:
            conditions_written = bool(spec.get("conditions"))
            counters = _eval_principle(spec, conn)
            v = _verdict(conditions_written, counters)
            rows.append({
                "principle_id": spec["id"],
                "kind": spec.get("kind", "?"),
                "conditions_written": conditions_written,
                **counters,
                "verdict": v,
            })
        # Compteur global
        verdict_counts = Counter(r["verdict"] for r in rows)
        global_verdict = "PHASE_13_BLOCKED_NO_WINLOSS"
        if n_wins + n_losses == 0:
            global_verdict = "PHASE_13_BLOCKED_NO_WINLOSS"
        elif verdict_counts.get("READY_FULL", 0) == 0:
            global_verdict = "PHASE_13_PARTIAL_NO_PROMOTABLE"
        else:
            global_verdict = "PHASE_13_PROMOTABLE"

        return {
            "global_verdict": global_verdict,
            "n_shadows": len(rows),
            "n_wins": n_wins,
            "n_losses": n_losses,
            "n_open": n_open,
            "verdict_counts": dict(verdict_counts),
            "thresholds": {
                "triggers_min": THRESHOLD_TRIGGERS,
                "hit_rate_pct_min": THRESHOLD_HIT_RATE,
                "pips_filter_min": THRESHOLD_PIPS,
            },
            "per_principle": rows,
        }
    finally:
        conn.close()


def render_text(report: dict) -> str:
    lines = []
    lines.append(f"[.. ] SHADOW audités : {report['n_shadows']}")
    lines.append(f"[.. ] WIN/LOSS : {report['n_wins']} wins / {report['n_losses']} losses / {report['n_open']} open")
    lines.append(f"[.. ] Seuils R30 : ≥{report['thresholds']['triggers_min']} triggers, ≥{report['thresholds']['hit_rate_pct_min']}% hit_rate")
    if report['thresholds'].get('pips_filter_min', 0) > 0:
        lines.append(f"[.. ] Filtre pips : |pips| ≥ {report['thresholds']['pips_filter_min']} (HR filtré actif)")
    lines.append("")
    lines.append("[.. ] Verdict par principe :")
    header = f"        {'PRINCIPE':<28} {'COND':<5} {'EVAL':>6} {'TRIG':>5} {'HR%':>7} {'HR_FILT%':>9}  VERDICT"
    lines.append(header)
    for r in report["per_principle"]:
        cond = "OUI" if r["conditions_written"] else "non"
        hr = f"{r['hit_rate_pct']:.1f}" if r.get("hit_rate_pct") is not None else "—"
        hr_filt = f"{r['hit_rate_filtered_pct']:.1f}" if r.get("hit_rate_filtered_pct") is not None else "—"
        lines.append(
            f"        {r['principle_id']:<28} {cond:<5} {r['n_evaluations']:>6} {r['n_triggers']:>5} {hr:>7} {hr_filt:>9}  {r['verdict']}"
        )
    lines.append("")
    lines.append("[.. ] Compteurs verdict :")
    for v, n in sorted(report["verdict_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"        {v}: {n}")
    lines.append("")
    lines.append(f"[VERDICT GLOBAL] {report['global_verdict']}")
    return "\n".join(lines) + "\n"


def render_markdown(report: dict) -> str:
    lines = [
        f"# Phase 13 Readiness — {report['n_shadows']} SHADOW audités",
        "",
        f"- **Date** : généré par `v9_phase13_readiness.py`",
        f"- **Verdict global** : **{report['global_verdict']}**",
        f"- **WIN/LOSS résolus** : {report['n_wins']} wins / {report['n_losses']} losses / {report['n_open']} open",
        f"- **Seuils R30** : ≥{report['thresholds']['triggers_min']} triggers, ≥{report['thresholds']['hit_rate_pct_min']}% hit_rate",
    ]
    if report['thresholds'].get('pips_filter_min', 0) > 0:
        lines.append(f"- **Filtre pips** : |pips| ≥ {report['thresholds']['pips_filter_min']} (HR filtré actif)")
    lines += [
        "",
        "## Verdict par principe",
        "",
        "| Principe | kind | Conditions | Eval | Triggers | Résolus | Hit rate | Hit rate filtré | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["per_principle"]:
        cond = "OUI" if r["conditions_written"] else "non"
        hr = f"{r['hit_rate_pct']:.1f}%" if r.get("hit_rate_pct") is not None else "—"
        hr_filt = f"{r['hit_rate_filtered_pct']:.1f}%" if r.get("hit_rate_filtered_pct") is not None else "—"
        n_resolved_filt = r.get("n_resolved_filtered", r.get("n_resolved", 0))
        lines.append(
            f"| {r['principle_id']} | {r['kind']} | {cond} | {r['n_evaluations']} | {r['n_triggers']} | {r['n_resolved']} | {hr} | {hr_filt} ({n_resolved_filt}) | {r['verdict']} |"
        )
    lines += [
        "",
        "## Compteurs verdict",
        "",
    ]
    for v, n in sorted(report["verdict_counts"].items(), key=lambda x: -x[1]):
        lines.append(f"- **{v}** : {n}")
    lines += [
        "",
        "## Légende",
        "",
        "- `INERT_NO_CONDITIONS` : YAML conditions vides (classe C R30)",
        "- `BLOCKED_NO_TRIGGER` : jamais déclenché, refactor YAML nécessaire",
        "- `EARLY_TRIGGERS` : <50 triggers, attendre accumulation",
        "- `READY_STRUCTURAL` : ≥50 triggers mais 0 WIN/LOSS résolu (bloqué data)",
        "- `READY_FULL` : ≥50 triggers + hit_rate ≥ 60% (promotion possible)",
        "- `READY_LOW_HIT_RATE` : ≥50 triggers + hit_rate < 60% (à analyser)",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Audit READINESS des principes SHADOW (Phase 13 promotion)"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument(
        "--principles-dir", type=Path, default=None,
        help="Dossier YAML des principes (défaut: core/v9/principles)",
    )
    parser.add_argument(
        "--threshold-pips", type=float, default=0.0,
        help="Filtre hit_rate sur |pips| >= seuil (défaut 0 = pas de filtre)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    report = audit(args.db, principles_dir=args.principles_dir, threshold_pips=args.threshold_pips)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.report:
        args.report.write_text(render_markdown(report), encoding="utf-8")
        print(f"[OK ] Rapport Markdown écrit : {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
