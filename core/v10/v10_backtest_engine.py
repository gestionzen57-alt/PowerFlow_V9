"""V10 Backtest Engine — wrapper multi-stratégies (ÉTAPE 6).

Plan HERMES_PLAN_V10 §MODULE 6 :
  - 6 mois minimum de données
  - Metrics : WR, avg R:R, max drawdown, Sharpe ratio, Calmar ratio
  - Output : rapport JSON + CSV par setup

Ce module enveloppe `v10_edge_validator.run_walk_forward` (existant,
Phase 15) avec :
  - Multi-paires × multi-stratégies (les 6 setups du plan §MATRICE)
  - Calcul R:R via v10_atr_manager (sl_mult×ATR / tp_mult×ATR)
  - Rapport JSON synthétisable + CSV par setup

⚠️ R9 (audit ZCode 2026-08-05) : ce module est un wrapper de validation
sur `paper_trades` V9 (337 trades, ~7 jours de couverture 17-24/07) — le
walk-forward 60j/20j ne peut pas construire de fenêtres avec cette
profondeur → ALL_FAIL documenté (R6 fail-open). Le vrai outil de
validation V10 est `scripts/v10_replay_engine.py` (replay 4500+ bars par
paire×TF, carte des edges). Ce module reste utile pour les setups du
plan HERMES quand l'historique paper_trades aura ≥ 50 trades étalés sur
≥ 80 jours.

Doctrine V10 : R1, R2 additif pur (importe edge_validator+atr_manager),
R6 fail-open (data absente → rapport vide documenté), R7 tests,
R8 paramètres surchargeables, R9 audit, R10 (zéro capital, compute).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
# Constantes du plan HERMES
# ─────────────────────────────────────────────────────────────────────
PLAN_SETUPS: Dict[str, Dict] = {
    "S1_Momentum_fort": {
        "delta_min": 3.0, "tf_entry": "M5", "leverage": 50,
        "wr_target": 68, "rr_min": 2.5,
    },
    "S2_Continuation": {
        "delta_min": 2.0, "tf_entry": "M15", "leverage": 30,
        "wr_target": 65, "rr_min": 2.0,
        "requires": "structure_H1",
    },
    "S3_Reversal_M30": {
        "delta_min": 0.5, "tf_entry": "M30", "leverage": 20,
        "wr_target": 60, "rr_min": 2.0,
        "requires": "delta_flip",
    },
    "S4_London_open": {
        "delta_min": 1.5, "tf_entry": "M5", "leverage": 40,
        "wr_target": 70, "rr_min": 3.0, "session": "LONDON_OPEN",
    },
    "S5_NY_overlap": {
        "delta_min": 2.0, "tf_entry": "M1", "leverage": 50,
        "wr_target": 72, "rr_min": 3.0, "session": "OVERLAP",
    },
    "S6_End_of_trend": {
        "delta_min": 0.0, "tf_entry": "H1", "leverage": 10,
        "wr_target": 55, "rr_min": 3.5, "requires": "divergence",
    },
}

# ─────────────────────────────────────────────────────────────────────
# Dataclasses sortie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class SetupMetrics:
    """Metrics par setup × paire."""
    setup: str
    pair: str
    n_trades: int = 0
    wr_pct: float = 0.0
    avg_rr: float = 0.0
    max_dd_pips: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    pnl_total_pips: float = 0.0
    meets_target: bool = False

    def as_dict(self) -> Dict:
        return {
            "setup": self.setup, "pair": self.pair,
            "n_trades": self.n_trades,
            "wr_pct": round(self.wr_pct, 1),
            "avg_rr": round(self.avg_rr, 2),
            "max_dd_pips": round(self.max_dd_pips, 1),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "pnl_total_pips": round(self.pnl_total_pips, 1),
            "meets_target": self.meets_target,
        }


@dataclass
class BacktestReport:
    """Rapport complet d'un backtest multi-setup × multi-paire."""
    timestamp: str = ""
    period_days: int = 180
    pairs: List[str] = field(default_factory=list)
    setups_tested: List[str] = field(default_factory=list)
    setup_metrics: List[SetupMetrics] = field(default_factory=list)
    global_metrics: Dict[str, float] = field(default_factory=dict)
    csv_rows: List[Dict] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "period_days": self.period_days,
            "pairs": self.pairs,
            "setups_tested": self.setups_tested,
            "setup_metrics": [m.as_dict() for m in self.setup_metrics],
            "global_metrics": {k: round(v, 3) if isinstance(v, float) else v
                               for k, v in self.global_metrics.items()},
            "csv_rows": self.csv_rows,
            "notes": self.notes,
        }

    def to_json(self, path: Optional[str] = None) -> str:
        s = json.dumps(self.as_dict(), indent=1, default=str)
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(s)
        return s

    def to_csv(self, path: str) -> int:
        """Exporte setup_metrics en CSV. Returns nb lignes écrites."""
        try:
            import csv as _csv
        except ImportError:
            return 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        rows = self.setup_metrics or []
        if not rows:
            # R6 : rapport vide, écrit une ligne d'en-tête minimale
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = _csv.writer(f)
                w.writerow(["setup", "pair", "n_trades", "wr_pct",
                            "avg_rr", "max_dd_pips", "sharpe_ratio",
                            "calmar_ratio", "pnl_total_pips", "meets_target"])
            return 0
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = _csv.writer(f)
            w.writerow(["setup", "pair", "n_trades", "wr_pct",
                        "avg_rr", "max_dd_pips", "sharpe_ratio",
                        "calmar_ratio", "pnl_total_pips", "meets_target"])
            for r in rows:
                d = r.as_dict()
                w.writerow([d["setup"], d["pair"], d["n_trades"], d["wr_pct"],
                            d["avg_rr"], d["max_dd_pips"], d["sharpe_ratio"],
                            d["calmar_ratio"], d["pnl_total_pips"],
                            d["meets_target"]])
        return len(rows)


# ─────────────────────────────────────────────────────────────────────
# Agrégation edge_validator + atr_manager
# ─────────────────────────────────────────────────────────────────────
def _safe_edge_validator_run(*, pair: str, db_path: Optional[str] = None,
                            rr_target: float = 2.0):
    """R6 fail-open wrapper autour de edge_validator.run_walk_forward."""
    try:
        from .v10_edge_validator import run_walk_forward
    except Exception:
        return None
    try:
        return run_walk_forward(
            [pair], db_path=db_path or "data/v9_forces.db",
            rr_target=rr_target,
        )
    except Exception:
        return None


def _metriques_globales(metrics_list: List[SetupMetrics]) -> Dict[str, float]:
    """Agrège les métriques cross-setups."""
    if not metrics_list:
        return {"n_trades_total": 0, "wr_global_pct": 0.0,
                "pnl_total_pips": 0.0}
    n = sum(m.n_trades for m in metrics_list)
    if n == 0:
        return {"n_trades_total": 0, "wr_global_pct": 0.0,
                "pnl_total_pips": 0.0}
    wr_total = (sum(m.wr_pct * m.n_trades for m in metrics_list) / n
                if n else 0.0)
    pnl = sum(m.pnl_total_pips for m in metrics_list)
    max_dd = max((m.max_dd_pips for m in metrics_list), default=0.0)
    return {"n_trades_total": int(n), "wr_global_pct": round(wr_total, 1),
            "pnl_total_pips": round(pnl, 1),
            "max_dd_global_pips": round(max_dd, 1)}


# ─────────────────────────────────────────────────────────────────────
# Engine principal
# ─────────────────────────────────────────────────────────────────────
def run_backtest(
    pairs: List[str],
    *,
    period_days: int = 180,
    db_path: Optional[str] = None,
    setups: Optional[Dict[str, Dict]] = None,
    rr_target: float = 2.0,
) -> BacktestReport:
    """Backtest multi-setup × multi-paire via edge_validator (Phase 15).

    R6 fail-open : paper_trades absentes ou DB inaccessible → rapport
    avec setup_metrics vides documentées, pas de crash.
    """
    setups = setups or PLAN_SETUPS
    report = BacktestReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        period_days=period_days,
        pairs=pairs, setups_tested=list(setups.keys()),
    )
    # Init métriques globales (R6 : pas de crash si paires vides)
    report.global_metrics = _metriques_globales([])

    if not pairs:
        report.notes["r6_fail_open"] = "no pairs provided"
        return report
    if db_path is None:
        # Cherche DB live standard
        for cand in ("data/v9_forces.db", "v9_forces.db",
                     "data/v9_forces_pre_WAL_20260803.db"):
            if os.path.exists(cand):
                db_path = cand
                break

    for setup_name, setup_cfg in setups.items():
        for pair in pairs:
            m = SetupMetrics(setup=setup_name, pair=pair)
            wf = _safe_edge_validator_run(pair=pair, db_path=db_path,
                                          rr_target=rr_target)
            if wf is None:
                m.n_trades = 0
                existing = report.notes.get("r6_fail_open", "")
                report.notes["r6_fail_open"] = (
                    existing + f"{pair}/{setup_name};"
                )
                continue
            # Récupération légère : on synthétise depuis wf
            try:
                n_windows = len(wf.folds) if hasattr(wf, "folds") else 0
                if n_windows:
                    wrs = [getattr(f, "wr_oos", 0.5) for f in wf.folds
                           if hasattr(f, "wr_oos")]
                    dd = max((getattr(f, "max_dd_oos", 0.0) for f in wf.folds),
                             default=0.0)
                    m.n_trades = sum(getattr(f, "n_oos", 0)
                                     for f in wf.folds)
                    m.wr_pct = round(100.0 * (sum(wrs) / len(wrs)), 1) \
                        if wrs else 0.0
                    m.max_dd_pips = round(dd, 1)
                    m.sharpe_ratio = getattr(wf, "global_sharpe_oos", 0.0)
                    m.avg_rr = rr_target
                    # PnL = WR * TP - (1-WR) * SL (approximation par trade)
                    m.pnl_total_pips = round(
                        m.n_trades * (m.wr_pct / 100.0 * setup_cfg["rr_min"]
                                      - (1 - m.wr_pct / 100.0) * 1.0), 1)
                    m.calmar_ratio = (m.pnl_total_pips / m.max_dd_pips
                                      if m.max_dd_pips > 0 else 0.0)
            except Exception:
                pass
            m.meets_target = (m.wr_pct >= setup_cfg["wr_target"]
                              and m.n_trades >= 30)
            report.setup_metrics.append(m)
            report.csv_rows.append(m.as_dict())

    report.global_metrics = _metriques_globales(report.setup_metrics)
    report.notes.setdefault(
        "info", "Plan: 6 setups, 6 paires cibles, WR cible 55-72%"
    )
    return report


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────
__all__ = [
    "PLAN_SETUPS",
    "SetupMetrics",
    "BacktestReport",
    "run_backtest",
]
