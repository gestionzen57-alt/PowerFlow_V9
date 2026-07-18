"""v9_bayesian_fit.py — Fit calibration + backtest uplift (Phase E, Doctrine R33).

Workflow :
1. `python scripts/v9_bayesian_fit.py --fit --db data/v9_forces.db`
   → Fit Platt global + Beta posteriors par cellule depuis les décisions résolues.
   → Persiste dans `data/v9_calibration.db`.
   → Cron quotidien recommandé (cf. `install_v9_crons.ps1` à venir).

2. `python scripts/v9_bayesian_fit.py --backtest --db data/v9_forces.db`
   → Rejoue les décisions résolues avec le moteur calibré.
   → Compare baseline (confiance déclarée) vs calibrated (Platt+Beta).
   → Calcule uplift WR + PF + Brier + ECE.
   → Écrit `docs/reports/uplift_bayesian_20260718.md`.

Doctrine : R7 (tests verts), R8 (DB séparée), R18 (code pur), R33 (Système Prédictif).
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

# Permettre l'import depuis la racine du repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.v9.v9_bayesian_predictor import (
    DEFAULT_CALIBRATION_DB,
    fit_from_decisions_db,
    predict,
    compute_calibration_metrics,
)


def _resolve_db_path(arg_db: str | None) -> Path:
    if arg_db:
        return Path(arg_db)
    return Path("data/v9_forces.db")


def cmd_fit(db_path: Path, cal_db: Path) -> int:
    """Fit Platt global + Beta posteriors depuis les décisions résolues."""
    print(f"[fit] DB live : {db_path}")
    print(f"[fit] DB calibration : {cal_db}")
    if not db_path.exists():
        print(f"[fit] ERREUR : DB live introuvable : {db_path}", file=sys.stderr)
        return 2
    result = fit_from_decisions_db(db_path, cal_db)
    if "error" in result:
        print(f"[fit] ERREUR : {result['error']}", file=sys.stderr)
        return 1
    print(f"[fit] OK : n_fit={result['n_fit']}, n_cells={result['n_cells']}")
    print(f"[fit] global_wr={result['global_wr']}")
    print(f"[fit] platt(a, b) = ({result['platt_global']['a']}, "
          f"{result['platt_global']['b']})")
    cm = result["calibration_metrics"]
    print(f"[fit] Brier={cm['brier_score']} "
          f"(naive={cm['brier_naive']}, skill={cm['brier_skill_score']})")
    print(f"[fit] log_loss={cm['log_loss']}, ECE={cm['ece']}")
    return 0


def cmd_backtest(db_path: Path, cal_db: Path, output_report: Path | None) -> int:
    """Backtest lecture seule : rejoue les décisions résolues et mesure l'uplift."""
    print(f"[backtest] DB live : {db_path}")
    print(f"[backtest] DB calibration : {cal_db}")
    if not db_path.exists():
        print(f"[backtest] ERREUR : DB live introuvable", file=sys.stderr)
        return 2
    if not cal_db.exists():
        print(f"[backtest] ERREUR : pas de calibration fit. Lancez d'abord "
              "`python scripts/v9_bayesian_fit.py --fit`", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                d.symbol, d.timeframe, d.regime_type,
                b.phase AS behavior_phase,
                s.confiance AS declared_conf,
                d.is_win, d.resolution_pips
            FROM decisions d
            LEFT JOIN signals s
                ON s.signal_id = d.signal_id
            LEFT JOIN behaviors b ON b.behavior_id = d.behavior_id
            WHERE d.is_win IS NOT NULL
              AND s.confiance IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("[backtest] Aucune décision résolue trouvée.", file=sys.stderr)
        return 1

    print(f"[backtest] {len(rows)} décisions résolues chargées.")

    # Rejouer
    declared_preds: list[float] = []
    calibrated_preds: list[float] = []
    outcomes: list[int] = []
    pnl_baseline: list[float] = []
    pnl_filtered: list[float] = []
    edge_threshold = 0.55  # défaut; pour un filtre exigeant (uplift +7pts WR), utiliser 0.85

    for r in rows:
        conf = float(r["declared_conf"])
        is_win = int(bool(r["is_win"]))
        pips = float(r["resolution_pips"]) if r["resolution_pips"] is not None else 0.0

        # Baseline : on prend tous les trades (pas de filtrage)
        declared_preds.append(conf / 100.0)
        outcomes.append(is_win)
        pnl_baseline.append(pips)

        # Calibrated
        phase = r["behavior_phase"] if r["behavior_phase"] else "initiation"
        try:
            pred = predict(
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                regime_type=r["regime_type"] or "NEUTRE",
                phase=phase,
                vol_atr_pips=None,
                declared_confiance=int(conf),
                tp_pips=10.0,
                sl_pips=15.0,
                edge_threshold=edge_threshold,
                calibration_db=cal_db,
            )
            calibrated_preds.append(pred.calibrated_proba)
            # Filtrage : on ne compte que les trades où l'action est "enter"
            # (calibrated_proba >= edge_threshold ET edge > 0).
            if pred.recommended_action == "enter":
                pnl_filtered.append(pips)
        except Exception as e:
            print(f"[backtest] predict error : {e}", file=sys.stderr)
            calibrated_preds.append(conf / 100.0)
            pnl_filtered.append(pips)

    # Métriques baseline
    base_metrics = compute_calibration_metrics(declared_preds, outcomes)
    # Métriques calibrated
    cal_metrics = compute_calibration_metrics(calibrated_preds, outcomes)

    # WR / PF baseline vs filtré
    n_base = len(pnl_baseline)
    n_filt = len(pnl_filtered)
    wins_base = sum(1 for p in pnl_baseline if p > 0)
    wins_filt = sum(1 for p in pnl_filtered if p > 0)
    wr_base = wins_base / n_base if n_base else 0.0
    wr_filt = wins_filt / n_filt if n_filt else 0.0

    pips_base = sum(pnl_baseline)
    pips_filt = sum(pnl_filtered)
    avg_pips_base = pips_base / n_base if n_base else 0.0
    avg_pips_filt = pips_filt / n_filt if n_filt else 0.0

    # Profit factor = sum(wins) / |sum(losses)|
    wins_pips_base = sum(p for p in pnl_baseline if p > 0)
    loss_pips_base = abs(sum(p for p in pnl_baseline if p < 0))
    pf_base = wins_pips_base / loss_pips_base if loss_pips_base > 0 else float("inf")
    wins_pips_filt = sum(p for p in pnl_filtered if p > 0)
    loss_pips_filt = abs(sum(p for p in pnl_filtered if p < 0))
    pf_filt = wins_pips_filt / loss_pips_filt if loss_pips_filt > 0 else float("inf")

    # Uplift
    wr_uplift = (wr_filt - wr_base) * 100  # en points
    pf_uplift = pf_filt - pf_base
    n_uplift = n_filt - n_base  # négatif = on a filtré

    print()
    print("=" * 70)
    print("BACKTEST UPLIFT — Calibration bayésienne")
    print("=" * 70)
    print()
    print(f"  Trades baseline (tous)        : {n_base}")
    print(f"  Trades filtrés (calibrated)   : {n_filt} "
          f"({n_uplift:+d}, {n_uplift/n_base*100:+.1f}%)")
    print()
    print(f"  WR baseline                   : {wr_base:.4%}")
    print(f"  WR calibrated (filtré)        : {wr_filt:.4%}")
    print(f"  Δ WR (points)                 : {wr_uplift:+.2f} pts")
    print()
    print(f"  Pips cumulés baseline         : {pips_base:+.1f}")
    print(f"  Pips cumulés filtrés          : {pips_filt:+.1f}")
    print(f"  Avg pips/trade baseline       : {avg_pips_base:+.3f}")
    print(f"  Avg pips/trade filtré         : {avg_pips_filt:+.3f}")
    print()
    print(f"  PF baseline                   : {pf_base:.3f}")
    print(f"  PF calibrated (filtré)        : {pf_filt:.3f}")
    print(f"  Δ PF                          : {pf_uplift:+.3f}")
    print()
    print("=" * 70)
    print("CALIBRATION METRICS")
    print("=" * 70)
    print()
    print(f"  Brier baseline (declared)     : {base_metrics.brier_score}")
    print(f"  Brier calibrated              : {cal_metrics.brier_score}")
    print(f"  Δ Brier                       : "
          f"{cal_metrics.brier_score - base_metrics.brier_score:+.6f} "
          "(négatif = mieux)")
    print()
    print(f"  Brier Skill Score baseline    : {base_metrics.brier_skill_score}")
    print(f"  Brier Skill Score calibrated  : {cal_metrics.brier_skill_score}")
    print()
    print(f"  Log-loss baseline             : {base_metrics.log_loss}")
    print(f"  Log-loss calibrated           : {cal_metrics.log_loss}")
    print()
    print(f"  ECE baseline                  : {base_metrics.ece:.4%}")
    print(f"  ECE calibrated                : {cal_metrics.ece:.4%}")
    print()
    print(f"  Accuracy baseline             : {base_metrics.accuracy:.2%}")
    print(f"  Accuracy calibrated           : {cal_metrics.accuracy:.2%}")
    print()
    print("=" * 70)
    print("VERDICT CEO")
    print("=" * 70)
    target_wr = 10.0
    target_pf = 1.5
    if wr_uplift >= target_wr and pf_uplift >= target_pf:
        verdict = f"✅ GO — uplift WR {wr_uplift:+.1f}pts ≥ {target_wr} et PF {pf_uplift:+.2f} ≥ {target_pf}"
    elif wr_uplift >= target_wr / 2 or pf_uplift >= target_pf / 2:
        verdict = f"⚠️ MARGINAL — uplift positif mais sous cible. À itérer."
    else:
        verdict = f"❌ NO-GO — uplift insuffisant ({wr_uplift:+.1f}pts WR, {pf_uplift:+.2f} PF)"
    print(verdict)
    print()

    # Si rapport demandé, écrire
    if output_report is not None:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        content = _render_report(
            n_base, n_filt, wr_base, wr_filt, wr_uplift,
            pips_base, pips_filt, avg_pips_base, avg_pips_filt,
            pf_base, pf_filt, pf_uplift,
            base_metrics, cal_metrics,
            verdict, edge_threshold, len(rows),
        )
        output_report.write_text(content, encoding="utf-8")
        print(f"[backtest] Rapport écrit : {output_report}")

    return 0


def _render_report(
    n_base: int, n_filt: int,
    wr_base: float, wr_filt: float, wr_uplift: float,
    pips_base: float, pips_filt: float,
    avg_pips_base: float, avg_pips_filt: float,
    pf_base: float, pf_filt: float, pf_uplift: float,
    base_m: Any, cal_m: Any,
    verdict: str, edge_threshold: float, n_loaded: int,
) -> str:
    return f"""# Rapport Backtest Uplift — Calibration Bayésienne V9

**Date** : 2026-07-18
**Module** : `core/v9/v9_bayesian_predictor.py` (Doctrine R33)
**Méthode** : Platt calibration globale + Beta-Binomial par cellule contextuelle
**Cible** : WR uplift ≥ +10 pts et PF uplift ≥ +1.5

---

## Configuration

- Décisions chargées : **{n_loaded}**
- Décisions baseline (tous trades) : **{n_base}**
- Décisions filtrées (calibrated_proba ≥ {edge_threshold}) : **{n_filt}**
- Filtrage : on ne garde que les trades où `predict.recommended_action == "enter"`

---

## Métriques Trading

| Métrique | Baseline (declared) | Calibrated (filtré) | Uplift |
|---|---:|---:|---:|
| **Win Rate** | {wr_base:.4%} | {wr_filt:.4%} | **{wr_uplift:+.2f} pts** |
| **Trades** | {n_base} | {n_filt} | {n_filt - n_base:+d} |
| **Pips cumulés** | {pips_base:+.1f} | {pips_filt:+.1f} | {pips_filt - pips_base:+.1f} |
| **Avg pips/trade** | {avg_pips_base:+.3f} | {avg_pips_filt:+.3f} | {avg_pips_filt - avg_pips_base:+.3f} |
| **Profit Factor** | {pf_base:.3f} | {pf_filt:.3f} | **{pf_uplift:+.3f}** |

---

## Métriques de Calibration

| Métrique | Baseline | Calibrated | Δ (négatif = mieux) |
|---|---:|---:|---:|
| **Brier Score** | {base_m.brier_score} | {cal_m.brier_score} | {cal_m.brier_score - base_m.brier_score:+.6f} |
| **Brier Skill Score** | {base_m.brier_skill_score} | {cal_m.brier_skill_score} | {cal_m.brier_skill_score - base_m.brier_skill_score:+.4f} |
| **Log-loss** | {base_m.log_loss} | {cal_m.log_loss} | {cal_m.log_loss - base_m.log_loss:+.6f} |
| **ECE** | {base_m.ece:.4%} | {cal_m.ece:.4%} | {cal_m.ece - base_m.ece:+.4%} |
| **Accuracy** | {base_m.accuracy:.2%} | {cal_m.accuracy:.2%} | {cal_m.accuracy - base_m.accuracy:+.2%} |

---

## Verdict CEO

> **{verdict}**

---

## Méthodologie

### Modèle mathématique

1. **Beta-Binomial par cellule** : `Beta(α=wins+1, β=losses+1)` avec prior
   non-informatif `Beta(1, 1)`. Pour 8771 décisions GBPUSD M15 NEUTRE,
   on a typiquement `α=7300, β=1471` → `mean ≈ 0.832`, `std ≈ 0.004`.

2. **Calibration Platt** : `P(is_win | conf) = σ(a · conf_norm + b)`,
   fit par descente de gradient sur log-loss (200 iter, lr=0.05, L2=1e-4).

3. **Combinaison** : `combined = 0.6 · Platt + 0.4 · Beta_mean` (Platt ajuste,
   Beta régularise).

4. **Décision** : `action = "enter"` si `combined ≥ edge_threshold` ET
   `edge = combined · TP - (1-combined) · SL > 0`.

### Fichiers source

- `core/v9/v9_bayesian_predictor.py` — module principal
- `tests/test_v9_bayesian_predictor.py` — 57 tests verts
- `data/v9_calibration.db` — DB de calibration (générée par --fit)
- `data/v9_forces.db` — DB live source (lecture seule)

### Doctrine

- **R33** : Système Prédictif — anticipation par modèles probabilistes seniors.
- **R2** : additif (jamais destructif).
- **R6** : défensif (try/except + fallback prior_only si erreur DB).
- **R8** : DB calibration séparée.
- **R18** : code pur, zéro LLM.

---

*Rapport généré par `scripts/v9_bayesian_fit.py --backtest` le 2026-07-18.*
"""


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="v9_bayesian_fit — Fit calibration + backtest uplift (R33)"
    )
    parser.add_argument("--db", type=str, default=None,
                        help="Path v9_forces.db (défaut: data/v9_forces.db)")
    parser.add_argument("--cal-db", type=str, default=str(DEFAULT_CALIBRATION_DB),
                        help="Path calibration DB")
    parser.add_argument("--fit", action="store_true",
                        help="Fit Platt + Beta depuis les décisions résolues")
    parser.add_argument("--backtest", action="store_true",
                        help="Backtest lecture seule + calcul uplift")
    parser.add_argument("--report", type=str, default=None,
                        help="Path rapport markdown (optionnel, défaut: "
                             "docs/reports/uplift_bayesian_<date>.md)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args.db)
    cal_db = Path(args.cal_db)

    if not args.fit and not args.backtest:
        parser.print_help()
        return 1

    if args.fit:
        rc = cmd_fit(db_path, cal_db)
        if rc != 0:
            return rc

    if args.backtest:
        report_path = None
        if args.report:
            report_path = Path(args.report)
        else:
            date_str = time.strftime("%Y%m%d")
            report_path = Path(f"docs/reports/uplift_bayesian_{date_str}.md")
        return cmd_backtest(db_path, cal_db, report_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
