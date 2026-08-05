"""V10 Walk-Forward Validator — Phase 28b Étape 4 (OPT-3 mission CEO).

Doctrine V10 :
  R1 : agit par défaut
  R2 : additif pur (n'altère pas les calibrators, lit uniquement)
  R6 : fail-open (data absente → gate=False, error explicite)
  R7 : tests verts
  R8 : gate configurable (live_ready si OOS WR >= seuil, défaut CEO brief 55%)
  R9 : audit metadata honnête, JSON sérialisable
  R10 : zéro capital (calcul seul, pas de trade)

Workflow :
  1. Charge signaux depuis data/v9_forces.db > table v10_signals_clean
  2. Split temporel 70/30 (chronologique, train = 70% plus ancien, test = 30% plus récent)
  3. Calcule WR + PnL + Sharpe-like sur train (et applique CalibratedParams si fourni)
  4. Calcule WR + PnL sur out-of-sample (OOS) test
  5. Gate CEO : si OOS WR >= live_ready_threshold (défaut 55%) → flag live_ready=True
  6. Émet report JSON dans reports/v10_walk_forward_YYYYMMDD.json

Limites honnêtes (R9) :
  - WR/PnL calculés sur proxy pnl_pips_proxy (seul historique disponible).
  - "Live ready" est une hypothèse — vrai live = paper micro-lot 30 trades
    puis ACTIVE (Phase 30 Phase 31).
  - Phase 21+ lira aussi WR natif recalibré si apply_calibrated_params fourni.

Usage :
  from core.v10.v10_walk_forward_validator import run_walk_forward
  rep = run_walk_forward(db_path="data/v9_forces.db",
                         pair="GBPUSD", tf="H4",
                         train_ratio=0.7,
                         live_ready_threshold=0.55)
  print(rep.live_ready, rep.wr_train, rep.wr_test)
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = "data/v9_forces.db"
DEFAULT_TRAIN_RATIO = 0.70
DEFAULT_TABLE_NAME = "v10_signals_clean"
DEFAULT_OOS_WR_THRESHOLD = 0.55
DEFAULT_OOS_MIN_TRADES = 30  # minimum OOS pour gate
DEFAULT_PAIRS = ("GBPUSD", "EURUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY")
DEFAULT_TFS = ("M30", "H1", "H4")


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class FoldMetrics:
    """Métriques pour un split train/OOS."""
    n_train: int = 0
    n_test: int = 0
    wr_train: float = 0.0
    wr_test: float = 0.0
    avg_pnl_train_pips: float = 0.0
    avg_pnl_test_pips: float = 0.0
    pnl_total_train_pips: float = 0.0
    pnl_total_test_pips: float = 0.0
    sharpe_like_train: float = 0.0
    sharpe_like_test: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SplitReport:
    """Rapport walk-forward pour 1 (paire, TF)."""
    pair: str = ""
    timeframe: str = ""
    n_total: int = 0
    cutoff_timestamp: str = ""
    cutoff_index: int = 0
    train_ratio: float = DEFAULT_TRAIN_RATIO
    metrics: FoldMetrics = field(default_factory=FoldMetrics)
    delta_wr_oos_minus_train: float = 0.0  # OOS - train (positif = maintien edge)
    shrink_pts: float = 0.0  # combien OOS WR a baissé vs train (%)
    gate_passed: bool = False
    gate_reason: str = ""
    live_ready: bool = False
    audit: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "n_total": self.n_total,
            "cutoff_timestamp": self.cutoff_timestamp,
            "cutoff_index": self.cutoff_index,
            "train_ratio": self.train_ratio,
            "metrics": self.metrics.as_dict(),
            "delta_wr_oos_minus_train": round(self.delta_wr_oos_minus_train, 4),
            "shrink_pts": round(self.shrink_pts, 4),
            "gate_passed": self.gate_passed,
            "gate_reason": self.gate_reason,
            "live_ready": self.live_ready,
            "audit": dict(self.audit),
        }


@dataclass
class WalkForwardReport:
    """Rapport global walk-forward (R9 JSON-sérialisable)."""
    timestamp_utc: str = ""
    db_path: str = ""
    table_name: str = DEFAULT_TABLE_NAME
    train_ratio: float = DEFAULT_TRAIN_RATIO
    oos_wr_threshold: float = DEFAULT_OOS_WR_THRESHOLD
    oos_min_trades: int = DEFAULT_OOS_MIN_TRADES
    n_pairs_evaluated: int = 0
    n_pairs_gate_passed: int = 0
    n_pairs_live_ready: int = 0
    splits: List[SplitReport] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "db_path": self.db_path,
            "table_name": self.table_name,
            "train_ratio": self.train_ratio,
            "oos_wr_threshold": self.oos_wr_threshold,
            "oos_min_trades": self.oos_min_trades,
            "n_pairs_evaluated": self.n_pairs_evaluated,
            "n_pairs_gate_passed": self.n_pairs_gate_passed,
            "n_pairs_live_ready": self.n_pairs_live_ready,
            "splits": [s.as_dict() for s in self.splits],
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ratio(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


def _safe_sharpe(pnls: List[float]) -> float:
    """Sharpe-like = mean(pnl) / stdev(pnl), 0 si undefined."""
    if len(pnls) < 2:
        return 0.0
    try:
        mean_p = statistics.mean(pnls)
        stdev_p = statistics.stdev(pnls)
        if stdev_p == 0:
            return 0.0
        return mean_p / stdev_p
    except Exception:
        return 0.0


def _connect_db(db_path: str) -> Optional[sqlite3.Connection]:
    try:
        path = Path(db_path)
        if not path.exists():
            return None
        con = sqlite3.connect(str(path), timeout=10)
        con.row_factory = sqlite3.Row
        return con
    except Exception:
        return None


def load_signals_for_pair_tf(
    db_path: str,
    pair: str,
    tf: str,
    table_name: str = DEFAULT_TABLE_NAME,
) -> List[Dict[str, Any]]:
    """Charge les signaux d'une (paire, TF) triés par timestamp asc.

    R6 fail-open : retourne [] si table absente ou erreur.
    """
    con = _connect_db(db_path)
    if con is None:
        return []

    try:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        if not cur.fetchone():
            con.close()
            return []

        # Colonnes attendues : timestamp, symbol, timeframe, pnl_pips_proxy, is_win_proxy
        cur.execute(
            f"""
            SELECT timestamp, symbol, timeframe, pair, direction,
                   pnl_pips_proxy, is_win_proxy, signal_id
            FROM {table_name}
            WHERE (symbol = ? OR pair = ?) AND timeframe = ?
            ORDER BY timestamp ASC
            """,
            (pair, pair, tf),
        )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        try:
            con.close()
        except Exception:
            pass
        return []


def _compute_fold_metrics(train: List[Dict], test: List[Dict]) -> FoldMetrics:
    """Calcule métriques train + OOS test."""
    n_train = len(train)
    n_test = len(test)

    n_train_wins = sum(1 for r in train if r.get("is_win_proxy") in (1, True))
    n_test_wins = sum(1 for r in test if r.get("is_win_proxy") in (1, True))

    pnl_train = [float(r.get("pnl_pips_proxy") or 0.0) for r in train]
    pnl_test = [float(r.get("pnl_pips_proxy") or 0.0) for r in test]

    pnl_train_total = sum(pnl_train)
    pnl_test_total = sum(pnl_test)

    return FoldMetrics(
        n_train=n_train,
        n_test=n_test,
        wr_train=_safe_ratio(n_train_wins, n_train),
        wr_test=_safe_ratio(n_test_wins, n_test),
        avg_pnl_train_pips=_safe_ratio(pnl_train_total, n_train),
        avg_pnl_test_pips=_safe_ratio(pnl_test_total, n_test),
        pnl_total_train_pips=round(pnl_train_total, 4),
        pnl_total_test_pips=round(pnl_test_total, 4),
        sharpe_like_train=_safe_sharpe(pnl_train),
        sharpe_like_test=_safe_sharpe(pnl_test),
    )


# ─────────────────────────────────────────────────────────────────────
# WALK-FORWARD D'UNE (paire, TF)
# ─────────────────────────────────────────────────────────────────────

def walk_forward_split(
    signals: List[Dict],
    *,
    pair: str,
    tf: str,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    oos_wr_threshold: float = DEFAULT_OOS_WR_THRESHOLD,
    oos_min_trades: int = DEFAULT_OOS_MIN_TRADES,
    calibrated_params: Optional[Dict[str, Any]] = None,
) -> SplitReport:
    """Split temporel + métriques + gate.

    Args:
        signals: rows triés par timestamp asc (cf load_signals_for_pair_tf)
        pair, tf: pour le rapport
        train_ratio: proportion du set train (défaut 0.70)
        oos_wr_threshold: seuil WR OOS pour live_ready (défaut 0.55)
        oos_min_trades: nb minimum OOS pour activer le gate (défaut 30)
        calibrated_params: CalibratedParams ou dict (R2 additif Phase 28b Étape 1).
            Si fourni, applique override avant calcul des métriques.

    Returns:
        SplitReport avec metrics + live_ready + audit.
    """
    n_total = len(signals)
    report = SplitReport(
        pair=pair,
        timeframe=tf,
        n_total=n_total,
        train_ratio=train_ratio,
    )

    # R6 fail-open si data absente
    if n_total < oos_min_trades * 2:
        report.gate_passed = False
        report.live_ready = False
        report.gate_reason = (
            f"insufficient_data (n={n_total}, need >= {2 * oos_min_trades})"
        )
        report.audit["error"] = "n_total_below_minimum"
        return report

    # Cutoff chronologique
    cutoff_idx = int(n_total * train_ratio)
    if cutoff_idx < 1 or cutoff_idx >= n_total:
        report.gate_reason = f"invalid_cutoff (cutoff_idx={cutoff_idx})"
        return report

    train = signals[:cutoff_idx]
    test = signals[cutoff_idx:]

    cutoff_ts = train[-1].get("timestamp", "")
    report.cutoff_timestamp = str(cutoff_ts)
    report.cutoff_index = cutoff_idx

    # R2 additif — appliquer CalibratedParams override (Phase 28b Étape 1)
    # Note : on ne peut pas recalculer is_win_proxy / pnl_pips_proxy nativement
    # car ces colonnes sont figées en DB. L'override n'affecte que l'audit
    # et le downstream — Phase 28b R9 honest.
    audit_overrides = {"applied_calibrated_params": calibrated_params is not None}
    if calibrated_params is not None:
        try:
            from core.v10.v10_force_native import apply_calibrated_params
            res = apply_calibrated_params(calibrated_params)
            audit_overrides["runtime_apply_result"] = res
        except Exception as e:
            audit_overrides["runtime_apply_error"] = f"{type(e).__name__}: {e}"

    # Métriques
    metrics = _compute_fold_metrics(train, test)
    report.metrics = metrics

    # Delta WR OOS - train
    report.delta_wr_oos_minus_train = metrics.wr_test - metrics.wr_train
    report.shrink_pts = (metrics.wr_train - metrics.wr_test) * 100.0

    # Gate CEO
    gate_reasons = []
    if metrics.n_test < oos_min_trades:
        gate_reasons.append(
            f"oos_n_too_low (n_oos={metrics.n_test}, need >= {oos_min_trades})"
        )
        report.gate_passed = False
        report.live_ready = False
    else:
        report.gate_passed = metrics.wr_test >= oos_wr_threshold
        report.live_ready = report.gate_passed
        if report.gate_passed:
            gate_reasons.append(
                f"oos_wr={metrics.wr_test:.4f} >= threshold={oos_wr_threshold}"
            )
        else:
            gate_reasons.append(
                f"oos_wr={metrics.wr_test:.4f} < threshold={oos_wr_threshold}"
            )

    report.gate_reason = " | ".join(gate_reasons) if gate_reasons else "no_reason_logged"

    # Audit exhaustif
    report.audit = {
        "doctrine": "V10 R1 + R2 + R6 + R8 + R9 + R10",
        "phase": "28b etape 4 (OPT-3 mission CEO)",
        "method": "walk-forward 70/30 chronologique (R9 honest)",
        "wr_source": "is_win_proxy column (proxy pnl — seule métrique historique)",
        "n_total_signals": n_total,
        "train_end_ts": report.cutoff_timestamp,
        "test_start_ts": str(test[0].get("timestamp", "")),
        "delta_wr_oos_minus_train_pts": round(report.delta_wr_oos_minus_train * 100, 2),
        "shrink_pts": round(report.shrink_pts, 2),
        "live_ready_threshold": oos_wr_threshold,
        "oos_min_trades_threshold": oos_min_trades,
        "r9_honest_caveats": [
            "WR/PnL calculés sur proxy pnl_pips_proxy (V9 heritage)",
            "Vrai edge natif : requires Phase 20++ recalibré + recompute (pas live)",
            "Live_ready flag = hypothèse paper → nécessite Phase 30/31 validation",
        ],
        **audit_overrides,
    }
    return report


# ─────────────────────────────────────────────────────────────────────
# WALK-FORWARD GLOBAL
# ─────────────────────────────────────────────────────────────────────

def run_walk_forward(
    *,
    db_path: str = DEFAULT_DB_PATH,
    pairs: Optional[Tuple[str, ...]] = None,
    tfs: Optional[Tuple[str, ...]] = None,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    oos_wr_threshold: float = DEFAULT_OOS_WR_THRESHOLD,
    oos_min_trades: int = DEFAULT_OOS_MIN_TRADES,
    calibrated_params: Optional[Dict[str, Any]] = None,
    table_name: str = DEFAULT_TABLE_NAME,
) -> WalkForwardReport:
    """Run walk-forward sur la grille (paires × TF)."""
    pairs = pairs or DEFAULT_PAIRS
    tfs = tfs or DEFAULT_TFS

    rep = WalkForwardReport(
        timestamp_utc=_now_iso(),
        db_path=db_path,
        table_name=table_name,
        train_ratio=train_ratio,
        oos_wr_threshold=oos_wr_threshold,
        oos_min_trades=oos_min_trades,
        audit={
            "doctrine": "V10 R1 + R2 + R6 + R8 + R9 + R10",
            "phase": "28b etape 4 (OPT-3 mission CEO)",
            "calibrated_params_applied": calibrated_params is not None,
        },
    )

    for p in pairs:
        for tf in tfs:
            signals = load_signals_for_pair_tf(db_path, p, tf, table_name=table_name)
            sp = walk_forward_split(
                signals,
                pair=p,
                tf=tf,
                train_ratio=train_ratio,
                oos_wr_threshold=oos_wr_threshold,
                oos_min_trades=oos_min_trades,
                calibrated_params=calibrated_params,
            )
            rep.splits.append(sp)
            rep.n_pairs_evaluated += 1
            if sp.gate_passed:
                rep.n_pairs_gate_passed += 1
            if sp.live_ready:
                rep.n_pairs_live_ready += 1

    return rep


# ─────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────────────

def report_filename(prefix: str = "v10_walk_forward") -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}_{today}.json"


def save_report(
    rep: WalkForwardReport,
    output_path: Path,
    *,
    reports_dir: Optional[Path] = None,
) -> Path:
    """Écrit le rapport walk-forward en JSON (R9).

    Args:
        rep: WalkForwardReport
        output_path: chemin (absolu ou relatif à reports/)
        reports_dir: répertoire par défaut si output_path relatif
    """
    output_path = Path(output_path)
    if not output_path.is_absolute():
        reports_dir = reports_dir or Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = reports_dir / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = rep.as_dict()
    payload["_meta"] = {
        "doctrine": "V10 R9 audit JSON-sérialisable",
        "generated_at_utc": _now_iso(),
        "output_path": str(output_path),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def _build_arg_parser():
    import argparse
    p = argparse.ArgumentParser(description="V10 Walk-Forward Validator (Phase 28b Étape 4)")
    p.add_argument("--db-path", default=DEFAULT_DB_PATH)
    p.add_argument("--table", default=DEFAULT_TABLE_NAME)
    p.add_argument("--pairs", nargs="*", default=None)
    p.add_argument("--tfs", nargs="*", default=None)
    p.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO)
    p.add_argument("--oos-wr-threshold", type=float, default=DEFAULT_OOS_WR_THRESHOLD)
    p.add_argument("--oos-min-trades", type=int, default=DEFAULT_OOS_MIN_TRADES)
    p.add_argument("--output", default=None, help="Path JSON output")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    import sys
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    rep = run_walk_forward(
        db_path=args.db_path,
        pairs=tuple(args.pairs) if args.pairs else None,
        tfs=tuple(args.tfs) if args.tfs else None,
        train_ratio=args.train_ratio,
        oos_wr_threshold=args.oos_wr_threshold,
        oos_min_trades=args.oos_min_trades,
        table_name=args.table,
    )

    output_path = Path(args.output or report_filename())
    saved = save_report(rep, output_path)

    if not args.quiet:
        print(
            f"[walk_forward] {rep.n_pairs_evaluated} splits — "
            f"{rep.n_pairs_gate_passed} gate OK, {rep.n_pairs_live_ready} live_ready"
        )
        print(f"[walk_forward] Sortie : {saved}")
        print("[walk_forward] Détail par split :")
        for s in rep.splits:
            print(
                f"  {s.pair:7s} {s.timeframe:3s} : "
                f"n={s.n_total:5d} train_wr={s.metrics.wr_train:.4f} "
                f"oos_wr={s.metrics.wr_test:.4f} "
                f"delta={s.delta_wr_oos_minus_train:+.4f} "
                f"shrink={s.shrink_pts:.1f}pts "
                f"live_ready={s.live_ready} ({s.gate_reason})"
            )

    # Exit codes
    if rep.n_pairs_live_ready >= 4:  # CEO brief : 4/6 paires live_ready
        return 0
    if rep.n_pairs_gate_passed >= 1:
        return 1
    return 2


__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_TRAIN_RATIO",
    "DEFAULT_TABLE_NAME",
    "DEFAULT_OOS_WR_THRESHOLD",
    "DEFAULT_PAIRS",
    "DEFAULT_TFS",
    "FoldMetrics",
    "SplitReport",
    "WalkForwardReport",
    "load_signals_for_pair_tf",
    "walk_forward_split",
    "run_walk_forward",
    "save_report",
    "report_filename",
    "main",
]


if __name__ == "__main__":
    import sys
    sys.exit(main())
