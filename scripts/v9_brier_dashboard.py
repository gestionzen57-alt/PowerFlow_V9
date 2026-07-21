#!/usr/bin/env python
"""v9_brier_dashboard.py — Dashboard CLI de calibration bayésienne live.

Affiche en CLI la qualité de calibration de la confiance déclarée par le
signal_generator, vs la probabilité réelle observée (WIN/LOSS).

Doctrine : R8 (traçabilité calibration), R13 (observer d'abord).

Métriques :
- Brier score global (0 = parfait, 0.25 = aléatoire, cible <0.20)
- Table de fiabilité par décile de confiance déclarée
- Top 5 buckets sur-confiants (gap = pred - obs le plus négatif)
- Top 5 buckets sous-confiants (gap le plus positif)
- WR par bucket de confiance

Usage :
    python scripts/v9_brier_dashboard.py                  # fenêtre 7j par défaut
    python scripts/v9_brier_dashboard.py --window-days 30
    python scripts/v9_brier_dashboard.py --json          # sortie JSON
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"


def fetch_decisions(window_days: int, min_n: int = 5) -> list[dict]:
    """Lit les décisions résolues avec confiance déclarée dans la fenêtre."""
    if not DB_PATH.exists():
        return []
    sql = """
        SELECT confiance, is_win
        FROM decisions
        WHERE timestamp > datetime('now', ?)
          AND confiance IS NOT NULL
          AND is_win IS NOT NULL
          AND resolution_strategy = 'DYNAMIC'
        ORDER BY timestamp DESC
    """
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            cur = conn.execute(sql, (f"-{window_days} days",))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:
        return []
    # Filtre n minimum
    if len(rows) < min_n:
        return []
    return rows


def compute_brier(decisions: list[dict]) -> float:
    """Brier = mean((p_pred - y_obs)^2). y ∈ {0, 1}."""
    if not decisions:
        return float("nan")
    s = 0.0
    for d in decisions:
        p = d["confiance"] / 100.0
        y = 1.0 if d["is_win"] else 0.0
        s += (p - y) ** 2
    return s / len(decisions)


def base_rate(decisions: list[dict]) -> float:
    """Taux de gain observé (base_rate)."""
    if not decisions:
        return float("nan")
    return sum(1 for d in decisions if d["is_win"]) / len(decisions)


def reliability_table(decisions: list[dict], n_bins: int = 10) -> list[dict]:
    """Table de fiabilité par décile de confiance déclarée."""
    if not decisions:
        return []
    # Tri par confiance
    sorted_d = sorted(decisions, key=lambda d: d["confiance"])
    bins = []
    bin_size = len(sorted_d) // n_bins
    if bin_size == 0:
        return []

    for i in range(n_bins):
        start = i * bin_size
        end = (i + 1) * bin_size if i < n_bins - 1 else len(sorted_d)
        chunk = sorted_d[start:end]
        if not chunk:
            continue
        conf_min = min(d["confiance"] for d in chunk)
        conf_max = max(d["confiance"] for d in chunk)
        pred = sum(d["confiance"] for d in chunk) / len(chunk) / 100.0
        obs_wr = sum(1 for d in chunk if d["is_win"]) / len(chunk)
        bins.append({
            "bin": f"[{conf_min}-{conf_max}]",
            "n": len(chunk),
            "pred": round(pred, 3),
            "obs_wr": round(obs_wr, 3),
            "gap": round(pred - obs_wr, 3),
        })
    return bins


def find_over_under_confident(table: list[dict], top: int = 5) -> tuple[list, list]:
    """Top buckets sur-confiants (gap négatif) et sous-confiants (gap positif)."""
    over = sorted([b for b in table if b["gap"] < 0], key=lambda b: b["gap"])[:top]
    under = sorted([b for b in table if b["gap"] > 0], key=lambda b: -b["gap"])[:top]
    return over, under


def render_text(report: dict) -> str:
    """Génère la sortie texte lisible en CLI."""
    lines = []
    lines.append("=" * 70)
    lines.append("🎯 Brier Dashboard — Calibration de la confiance déclarée")
    lines.append("=" * 70)
    lines.append(f"Source      : data/v9_forces.db (table decisions, filtre DYNAMIC)")
    lines.append(f"Fenêtre     : {report['window_days']} jours")
    lines.append(f"N décisions : {report['n_decisions']}")
    lines.append("")

    if report["n_decisions"] == 0:
        lines.append("⚠️  Aucune décision résolue dans la fenêtre.")
        return "\n".join(lines)

    lines.append(f"Brier score : {report['brier_score']:.4f}")
    lines.append(f"  → 0.00 = parfait | 0.25 = aléatoire | cible < 0.20")
    lines.append(f"  → ACTUEL : {report['brier_qualitative']}")
    lines.append(f"Base rate   : {report['base_rate']:.3f} (WR observé)")
    lines.append("")

    lines.append("📊 Table de fiabilité (par décile de confiance déclarée) :")
    lines.append(f"  {'bin':<14} {'n':>5} {'pred':>6} {'obs_WR':>7} {'gap':>7}")
    lines.append(f"  {'-'*14} {'-'*5} {'-'*6} {'-'*7} {'-'*7}")
    for row in report["reliability_table"]:
        lines.append(
            f"  {row['bin']:<14} {row['n']:>5} {row['pred']:>6.3f} {row['obs_wr']:>7.3f} {row['gap']:>+7.3f}"
        )
    lines.append("")

    if report["over_confident"]:
        lines.append("🔴 Top buckets SUR-CONFIANTS (gap négatif = on s'over-estime) :")
        for row in report["over_confident"]:
            lines.append(
                f"  {row['bin']:<14} n={row['n']:>4} pred={row['pred']:.3f} obs={row['obs_wr']:.3f} gap={row['gap']:+.3f}"
            )
        lines.append("")

    if report["under_confident"]:
        lines.append("🟢 Top buckets SOUS-CONFIANTS (gap positif = on s'under-estime) :")
        for row in report["under_confident"]:
            lines.append(
                f"  {row['bin']:<14} n={row['n']:>4} pred={row['pred']:.3f} obs={row['obs_wr']:.3f} gap={row['gap']:+.3f}"
            )
        lines.append("")

    lines.append("=" * 70)
    lines.append("💡 Action recommandée :")
    lines.append(f"   {report['recommendation']}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Brier Dashboard — calibration live")
    parser.add_argument("--window-days", type=int, default=7, help="fenêtre jours (défaut 7)")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args()

    decisions = fetch_decisions(args.window_days)
    brier = compute_brier(decisions)
    rate = base_rate(decisions)
    table = reliability_table(decisions)
    over, under = find_over_under_confident(table)

    # Qualitatif
    if brier < 0.10:
        qual = "✅ EXCELLENT — calibration fine, Kelly utilisable en confiance"
    elif brier < 0.20:
        qual = "🟢 BON — calibration utilisable, légère sur-confiance"
    elif brier < 0.25:
        qual = "🟡 ACCEPTABLE — proche de l'aléatoire, sizing prudent requis"
    elif brier < 0.40:
        qual = "🔴 MAUVAIS — sur-confiance significative, anti-Kelly"
    else:
        qual = "🔴 CRITIQUE — anti-calibré, sizing actuel AMPLIFIE le risque"

    # Recommandation
    if brier < 0.20:
        rec = "Activer V9_BAYESIAN_CALIBRATOR_ENABLED=1 (motion CEO, R25')."
    elif brier < 0.40:
        rec = ("Étudier l'activation Bayesian après recalibrage 30j. "
               "En attendant, sizing conservateur (Kelly × 0.25).")
    else:
        rec = ("Sizing actuel DANGEREUX. Activer Bayesian dès que possible "
               "(motion CEO urgente). En attendant, sizer=0 (no live).")

    report = {
        "window_days": args.window_days,
        "n_decisions": len(decisions),
        "brier_score": round(brier, 4) if not (brier != brier) else None,  # NaN check
        "brier_qualitative": qual,
        "base_rate": round(rate, 4),
        "reliability_table": table,
        "over_confident": over,
        "under_confident": under,
        "recommendation": rec,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
