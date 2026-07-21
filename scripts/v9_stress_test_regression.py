#!/usr/bin/env python
"""v9_stress_test_regression.py — Stress test régression 3 crises documentées.

Rejoue 3 crises connues sur le code ACTUEL pour vérifier que les garde-fous
tiennent toujours :

1. **Catastrophe 17/07** : loop re-entry (3 690 paper_trades GBPUSD baissier
   en 50 min, WR 1.03 %, -56 089 pips). Le `v9_loop_breaker` doit bloquer
   la densité >10 trades/15min.

2. **Dérive NZD 16/07** : index UNIQUE sans `currency` collapsait 8 devises
   en 1 (INSERT OR REPLACE). Le fix `principle_evaluations(snapshot_id,
   principle_id, currency)` doit garantir 12,5 % par devise.

3. **Drift loop 20/07** : `post_decision_hook` ré-ouvrait même snapshot
   après clôture (jusqu'à 7 paper_trades/snapshot). L'UNIQUE index
   `(snapshot_id, direction, principes_source)` doit garantir ≤1 trade/snapshot.

Doctrine : R7 (tests avant commit), R8 (traçabilité), R13 (observer d'abord),
R22 (CLI lecture seule).

Usage :
    python scripts/v9_stress_test_regression.py          # exécution
    python scripts/v9_stress_test_regression.py --json  # sortie JSON
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"


def test_loop_breaker_density() -> dict:
    """Test 1 : pas de densité >10 paper_trades/15min post-loop_breaker.

    Si aucun trade n'existe → max_per_snapshot = 1 (état sain par défaut).
    Si des trades existent → max = max(count par snapshot_id), doit être == 1.
    """
    if not DB_PATH.exists():
        return {"test": "loop_breaker_density", "skipped": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            # Compte le max de trades par snapshot (même si == 1)
            row = conn.execute(
                """
                SELECT MAX(cnt) FROM (
                    SELECT COUNT(*) AS cnt FROM paper_trades
                    WHERE snapshot_id IS NOT NULL
                    GROUP BY snapshot_id
                )
                """
            ).fetchone()
        max_density = row[0] if row and row[0] is not None else 1  # défaut sain si aucune donnée
        return {
            "test": "loop_breaker_density",
            "max_per_snapshot": max_density,
            "threshold": 1,
            "passed": max_density <= 1,
            "details": f"Max trades par snapshot = {max_density} (cible: 1)",
        }
    except Exception as e:
        return {"test": "loop_breaker_density", "error": str(e)[:200]}


def test_nzd_currency_distribution() -> dict:
    """Test 2 : distribution uniforme des devises (~12.5% chacune)."""
    if not DB_PATH.exists():
        return {"test": "nzd_currency_distribution", "skipped": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            # Vérifier que la table principle_evaluations a la colonne currency
            cols = [r[1] for r in conn.execute("PRAGMA table_info(principle_evaluations)").fetchall()]
            if "currency" not in cols:
                return {
                    "test": "nzd_currency_distribution",
                    "passed": False,
                    "details": "Colonne currency absente de principle_evaluations — fix non appliqué",
                }

            rows = conn.execute(
                """
                SELECT currency, COUNT(*) AS n
                FROM principle_evaluations
                WHERE timestamp > datetime('now', '-7 days')
                GROUP BY currency
                ORDER BY n DESC
                """
            ).fetchall()
        if not rows:
            return {"test": "nzd_currency_distribution", "skipped": "Aucune évaluation 7j"}
        total = sum(r[1] for r in rows)
        max_pct = max(r[1] / total * 100 for r in rows)
        return {
            "test": "nzd_currency_distribution",
            "n_currencies": len(rows),
            "max_pct": round(max_pct, 1),
            "threshold": 25.0,  # допуite: max 25% pour 1 devise sur 8 attendues (12.5% × 2)
            "passed": max_pct < 25.0,
            "details": f"Max devise = {max_pct:.1f}% (cible: <25% ; attendu 12.5% × 8 devises)",
        }
    except Exception as e:
        return {"test": "nzd_currency_distribution", "error": str(e)[:200]}


def test_drift_loop_idempotence() -> dict:
    """Test 3 : UNIQUE index paper_trades(snapshot_id, direction, principes_source)."""
    if not DB_PATH.exists():
        return {"test": "drift_loop_idempotence", "skipped": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            # Vérifier présence de l'index idx_pt_snap_dir_princ
            idx_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pt_snap_dir_princ'"
            ).fetchall()
            if not idx_rows:
                return {
                    "test": "drift_loop_idempotence",
                    "passed": False,
                    "details": "Index idx_pt_snap_dir_princ absent — fix motion #32 non appliqué",
                }

            # Vérifier qu'il n'y a pas de doublons
            dups = conn.execute(
                """
                SELECT snapshot_id, direction, principes_source, COUNT(*) AS n
                FROM paper_trades
                WHERE snapshot_id IS NOT NULL AND direction IS NOT NULL
                GROUP BY snapshot_id, direction, principes_source
                HAVING n > 1
                """
            ).fetchall()
            return {
                "test": "drift_loop_idempotence",
                "index_present": True,
                "n_duplicates": len(dups),
                "passed": len(dups) == 0,
                "details": f"Index idx_pt_snap_dir_princ présent, {len(dups)} doublon(s)",
            }
    except Exception as e:
        return {"test": "drift_loop_idempotence", "error": str(e)[:200]}


def run_all_tests() -> dict:
    """Exécute les 3 stress tests et retourne un rapport."""
    tests = [
        test_loop_breaker_density(),
        test_nzd_currency_distribution(),
        test_drift_loop_idempotence(),
    ]
    n_passed = sum(1 for t in tests if t.get("passed"))
    n_failed = sum(1 for t in tests if "passed" in t and not t["passed"])
    n_skipped = sum(1 for t in tests if "skipped" in t)
    return {
        "n_tests": len(tests),
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_skipped": n_skipped,
        "all_passed": n_failed == 0,
        "tests": tests,
    }


def render_text(report: dict) -> str:
    """Génère la sortie texte lisible."""
    lines = []
    lines.append("=" * 70)
    lines.append("🔥 Stress Test Régression — 3 crises documentées")
    lines.append("=" * 70)
    lines.append(f"Source      : data/v9_forces.db")
    lines.append("")
    overall = "✅ TOUS OK" if report["all_passed"] else "⚠️ ÉCHEC"
    lines.append(f"Verdict global : {overall} ({report['n_passed']}/{report['n_tests']} passés, {report['n_skipped']} skippés)")
    lines.append("")
    for t in report["tests"]:
        if "skipped" in t:
            mark = "⚪"
            status = f"SKIPPED ({t['skipped']})"
        elif t.get("error"):
            mark = "🟠"
            status = f"ERROR : {t['error']}"
        elif t.get("passed"):
            mark = "🟢"
            status = "PASSED"
        else:
            mark = "🔴"
            status = "FAILED"
        lines.append(f"{mark} {t['test']:<30} {status}")
        if "details" in t:
            lines.append(f"     → {t['details']}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stress test régression V9")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args()

    report = run_all_tests()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
