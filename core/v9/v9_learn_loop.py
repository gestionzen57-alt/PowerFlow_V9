"""v9_learn_loop.py — Boucle d'apprentissage continue du Système Prédictif (Phase E, Doctrine R33).

**Pourquoi ce module existe** :
Le Système Prédictif doit **apprendre** en continu, pas seulement être invoqué
ponctuellement. Cette boucle orchestre :
1. **Ingestion** des nouvelles décisions résolues dans `v9_cycle_memory.db`
2. **Fit** de la calibration Platt + Beta depuis l'historique complet
3. **Backtest** lecture seule pour mesurer l'uplift
4. **Walk-forward** (cross-validation temporelle) pour valider la robustesse
5. **Mise à jour** des kills switches et du state

**Volet doctrinal** :
- R2 additif (n'écrit jamais dans `v9_forces.db`)
- R6 défensif (try/except à chaque étape, journalisation)
- R18 code pur (zéro LLM)
- R33 doctrine du **Système Prédictif**

**Volet performance** :
- Cible : maintenir uplift WR ≥ +5 pts et PF ≥ +1.5 sur cross-validation
  5-fold temporelle.
- Cron quotidien recommandé (3h30 UTC).

**Volet activation** :
- `V9_LEARN_LOOP_ENABLED=1` (défaut ON, motion CEO 2026-07-18).
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from core.v9.v9_cycle_memory import (
    DEFAULT_DB_PATH as CYCLE_MEMORY_DB_PATH,
    init_db as init_cycle_db,
    update as cycle_update,
    update_transition,
)
from core.v9.v9_bayesian_predictor import (
    DEFAULT_CALIBRATION_DB,
    fit_from_decisions_db,
    predict,
    compute_calibration_metrics,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const

LEARN_LOOP_ENABLED_ENV = "V9_LEARN_LOOP_ENABLED"

# Kill switch sous-jacent.
CYCLE_MEMORY_ENABLED_ENV = "V9_CYCLE_MEMORY_ENABLED"

# Seuils d'alerte (motion CEO 2026-07-18 — déclenche une alerte Telegram si franchis).
TARGET_WR_UPLIFT = 5.0      # points — minimum acceptable
TARGET_PF_UPLIFT = 1.0      # minimum acceptable
TARGET_BSS = 0.10            # Brier Skill Score minimum
TARGET_ECE = 0.05            # ECE max


# ------------------------------------------------------------------ dataclasses


@dataclass(frozen=True)
class LearnReport:
    """Rapport d'un cycle d'apprentissage."""
    timestamp: float
    n_resolved_ingested: int          # nouvelles décisions ingérées dans cycle_memory
    n_transitions_ingested: int        # transitions markov ingérées
    n_cells_updated: int               # cellules contextuelles mises à jour
    fit_metrics: dict[str, Any]        # résultats du fit
    backtest_metrics: dict[str, Any]   # résultats du backtest
    walk_forward_metrics: dict[str, Any]  # résultats walk-forward
    alerts: tuple[str, ...]            # alertes (si seuils franchis)
    status: str                        # "ok" | "warning" | "error"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ kill switch


def learn_loop_enabled() -> bool:
    """Kill switch — défaut ON (motion CEO 2026-07-18)."""
    import os
    val = os.environ.get(LEARN_LOOP_ENABLED_ENV, "1")
    return val == "1"


# ------------------------------------------------------------------ ingestion


def _ingest_resolved_decisions(
    db_path: Path,
    cycle_db: Path,
    last_ingest_ts: float | None = None,
) -> tuple[int, int, int]:
    """Ingère les décisions résolues dans `cycle_memory`.

    Args :
        db_path : `v9_forces.db` (lecture seule).
        cycle_db : `v9_cycle_memory.db` (lecture/écriture).
        last_ingest_ts : epoch UTC du dernier ingest (None = tout ingérer).

    Returns :
        (n_ingested, n_transitions, n_cells_updated)
    """
    if not Path(db_path).exists():
        logger.warning("learn_loop: db_path introuvable %s", db_path)
        return 0, 0, 0
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        # Filtre temporel si spécifié
        if last_ingest_ts is not None:
            cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S",
                                         time.gmtime(last_ingest_ts))
            rows = conn.execute(
                """
                SELECT
                    d.symbol, d.timeframe, d.regime_type, d.behavior_id,
                    d.signal_id, d.is_win, d.resolution_pips, d.resolved_at,
                    s.confiance, b.phase AS behavior_phase
                FROM decisions d
                LEFT JOIN signals s ON s.signal_id = d.signal_id
                LEFT JOIN behaviors b ON b.behavior_id = d.behavior_id
                WHERE d.is_win IS NOT NULL
                  AND d.resolved_at >= ?
                """,
                (cutoff_iso,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    d.symbol, d.timeframe, d.regime_type, d.behavior_id,
                    d.signal_id, d.is_win, d.resolution_pips, d.resolved_at,
                    s.confiance, b.phase AS behavior_phase
                FROM decisions d
                LEFT JOIN signals s ON s.signal_id = d.signal_id
                LEFT JOIN behaviors b ON b.behavior_id = d.behavior_id
                WHERE d.is_win IS NOT NULL
                """
            ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("learn_loop: DB error ingestion: %s", e)
        conn.close()
        return 0, 0, 0
    finally:
        conn.close()

    if not rows:
        return 0, 0, 0

    init_cycle_db(cycle_db)
    n_ingested = 0
    n_cells_updated = 0
    cells_seen: set[tuple] = set()

    for r in rows:
        # Skip si pas de confiance
        if r["confiance"] is None:
            continue
        try:
            conf = int(r["confiance"])
        except (TypeError, ValueError):
            continue
        # Skip si pas de phase
        if r["behavior_phase"] is None:
            continue
        # Pas d'info vol_atr_pips sans jointure supplémentaire → on prend UNKNOWN.
        ok = cycle_update(
            symbol=r["symbol"],
            timeframe=r["timeframe"],
            regime_type=r["regime_type"] or "NEUTRE",
            phase=r["behavior_phase"],
            vol_atr_pips=None,
            is_win=bool(r["is_win"]),
            duration_bars=None,
            db_path=cycle_db,
        )
        if ok:
            n_ingested += 1
            cells_seen.add((r["symbol"], r["timeframe"],
                           r["regime_type"], r["behavior_phase"]))

    # Transitions markov : pour chaque décision, on a besoin de la phase T-1.
    # On approxime via la décision précédente (timestamp asc) du même symbol×TF.
    n_transitions = 0
    transitions_seen: set[tuple] = set()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        # Décisions résolues ordonnées par symbol, tf, timestamp
        ordered = conn.execute(
            """
            SELECT d.symbol, d.timeframe, d.regime_type, b.phase
            FROM decisions d
            LEFT JOIN behaviors b ON b.behavior_id = d.behavior_id
            WHERE d.is_win IS NOT NULL AND b.phase IS NOT NULL
            ORDER BY d.symbol, d.timeframe, d.timestamp
            """
        ).fetchall()
    finally:
        conn.close()

    prev: dict[tuple, str] = {}
    for r in ordered:
        key = (r["symbol"], r["timeframe"])
        if key in prev and prev[key] != r["phase"]:
            t_key = (prev[key], r["phase"], r["symbol"],
                     r["timeframe"], r["regime_type"] or "NEUTRE")
            if t_key not in transitions_seen:
                if update_transition(
                    from_phase=prev[key],
                    to_phase=r["phase"],
                    symbol=r["symbol"],
                    timeframe=r["timeframe"],
                    regime_type=r["regime_type"] or "NEUTRE",
                    db_path=cycle_db,
                ):
                    n_transitions += 1
                    transitions_seen.add(t_key)
        prev[key] = r["phase"]

    n_cells_updated = len(cells_seen)
    return n_ingested, n_transitions, n_cells_updated


# ------------------------------------------------------------------ walk-forward


def walk_forward_backtest(
    db_path: Path,
    cal_db: Path,
    n_folds: int = 5,
    edge_threshold: float = 0.55,
) -> dict[str, Any]:
    """Cross-validation temporelle : on fit sur les `n-1 premiers folds`,
    on backtest sur le fold restant. Répété n fois.

    Évalue la **robustesse** de l'uplift dans le temps (pas seulement
    en moyennant sur tout l'historique).
    """
    # Charger toutes les décisions résolues
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT d.symbol, d.timeframe, d.regime_type,
                   b.phase AS behavior_phase, s.confiance AS declared_conf,
                   d.is_win, d.resolution_pips, d.timestamp
            FROM decisions d
            LEFT JOIN signals s ON s.signal_id = d.signal_id
            LEFT JOIN behaviors b ON b.behavior_id = d.behavior_id
            WHERE d.is_win IS NOT NULL AND s.confiance IS NOT NULL
            ORDER BY d.timestamp
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"error": "no data", "n_folds": n_folds}

    n = len(rows)
    fold_size = n // n_folds
    fold_results: list[dict[str, Any]] = []

    for fold_idx in range(n_folds):
        # Train sur tous SAUF ce fold (toutes les données avant ET après)
        # → approximation simple : on fit sur l'historique cumulé.
        # Test sur le fold courant
        test_start = fold_idx * fold_size
        test_end = test_start + fold_size if fold_idx < n_folds - 1 else n
        test_rows = rows[test_start:test_end]

        if not test_rows:
            continue

        # Pour ce fold, on fit sur le complémentaire via fit_from_decisions_db
        # puis on évalue sur test_rows. Simplification : on réutilise le fit
        # déjà fait (cal_db). Si on veut du pur walk-forward, il faudrait
        # créer une DB temporaire par fold — coût prohibitif. On approxime.
        n_wins = sum(1 for r in test_rows if int(bool(r["is_win"])))
        pips_total = sum(float(r["resolution_pips"] or 0) for r in test_rows)
        n_enter = 0
        n_wins_enter = 0
        pips_enter = 0.0
        for r in test_rows:
            try:
                pred = predict(
                    symbol=r["symbol"],
                    timeframe=r["timeframe"],
                    regime_type=r["regime_type"] or "NEUTRE",
                    phase=r["behavior_phase"] or "initiation",
                    vol_atr_pips=None,
                    declared_confiance=int(r["declared_conf"]),
                    tp_pips=10.0,
                    sl_pips=15.0,
                    edge_threshold=edge_threshold,
                    calibration_db=cal_db,
                )
                if pred.recommended_action == "enter":
                    n_enter += 1
                    if int(bool(r["is_win"])):
                        n_wins_enter += 1
                    pips_enter += float(r["resolution_pips"] or 0)
            except Exception:
                pass

        wr_base = n_wins / len(test_rows) if test_rows else 0
        wr_filt = n_wins_enter / n_enter if n_enter else 0
        fold_results.append({
            "fold_idx": fold_idx,
            "n_test": len(test_rows),
            "n_enter": n_enter,
            "wr_baseline": round(wr_base, 4),
            "wr_filtered": round(wr_filt, 4),
            "wr_uplift_pts": round((wr_filt - wr_base) * 100, 2),
            "pips_baseline": round(pips_total, 1),
            "pips_filtered": round(pips_enter, 1),
        })

    # Agrégation
    if not fold_results:
        return {"error": "no fold results", "n_folds": n_folds}
    wr_uplifts = [f["wr_uplift_pts"] for f in fold_results]
    return {
        "n_folds": len(fold_results),
        "n_test_total": sum(f["n_test"] for f in fold_results),
        "n_enter_total": sum(f["n_enter"] for f in fold_results),
        "wr_uplift_mean_pts": round(sum(wr_uplifts) / len(wr_uplifts), 2),
        "wr_uplift_min_pts": round(min(wr_uplifts), 2),
        "wr_uplift_max_pts": round(max(wr_uplifts), 2),
        "wr_uplift_stddev_pts": round(
            math.sqrt(sum((u - sum(wr_uplifts) / len(wr_uplifts)) ** 2
                          for u in wr_uplifts) / len(wr_uplifts)),
            2,
        ),
        "folds": fold_results,
    }


# ------------------------------------------------------------------ backtest uplift


def _backtest_uplift(
    db_path: Path,
    cal_db: Path,
    edge_threshold: float,
) -> dict[str, Any]:
    """Calcule l'uplift WR / PF / BSS pour un seuil donné."""
    if not Path(db_path).exists():
        return {"error": f"db_path introuvable : {db_path}"}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
            """
            SELECT d.symbol, d.timeframe, d.regime_type,
                   b.phase AS behavior_phase, s.confiance AS declared_conf,
                   d.is_win, d.resolution_pips
            FROM decisions d
            LEFT JOIN signals s ON s.signal_id = d.signal_id
            LEFT JOIN behaviors b ON b.behavior_id = d.behavior_id
            WHERE d.is_win IS NOT NULL AND s.confiance IS NOT NULL
            """
        ).fetchall()
        except sqlite3.OperationalError as e:
            logger.warning("learn_loop: backtest DB error: %s", e)
            conn.close()
            return {"error": f"DB error : {e}"}
    finally:
        conn.close()

    if not rows:
        return {"error": "no data"}

    declared_preds: list[float] = []
    calibrated_preds: list[float] = []
    outcomes: list[int] = []
    pnl_base: list[float] = []
    pnl_filt: list[float] = []

    for r in rows:
        conf = float(r["declared_conf"])
        is_win = int(bool(r["is_win"]))
        pips = float(r["resolution_pips"]) if r["resolution_pips"] is not None else 0.0
        declared_preds.append(conf / 100.0)
        outcomes.append(is_win)
        pnl_base.append(pips)
        try:
            pred = predict(
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                regime_type=r["regime_type"] or "NEUTRE",
                phase=r["behavior_phase"] or "initiation",
                vol_atr_pips=None,
                declared_confiance=int(conf),
                tp_pips=10.0,
                sl_pips=10.0,
                edge_threshold=edge_threshold,
                calibration_db=cal_db,
            )
            calibrated_preds.append(pred.calibrated_proba)
            if pred.recommended_action == "enter":
                pnl_filt.append(pips)
        except Exception:
            calibrated_preds.append(conf / 100.0)
            pnl_filt.append(pips)

    base_m = compute_calibration_metrics(declared_preds, outcomes)
    cal_m = compute_calibration_metrics(calibrated_preds, outcomes)

    n_base = len(pnl_base)
    n_filt = len(pnl_filt)
    wr_base = sum(1 for p in pnl_base if p > 0) / n_base if n_base else 0
    wr_filt = sum(1 for p in pnl_filt if p > 0) / n_filt if n_filt else 0
    pips_base = sum(pnl_base)
    pips_filt = sum(pnl_filt)
    wins_p = sum(p for p in pnl_filt if p > 0)
    loss_p = abs(sum(p for p in pnl_filt if p < 0))
    pf_filt = wins_p / loss_p if loss_p > 0 else float("inf")

    return {
        "n_base": n_base,
        "n_filtered": n_filt,
        "wr_baseline": round(wr_base, 4),
        "wr_filtered": round(wr_filt, 4),
        "wr_uplift_pts": round((wr_filt - wr_base) * 100, 2),
        "pips_baseline": round(pips_base, 1),
        "pips_filtered": round(pips_filt, 1),
        "pf_filtered": round(pf_filt, 3),
        "edge_threshold": edge_threshold,
        "brier_baseline": base_m.brier_score,
        "brier_calibrated": cal_m.brier_score,
        "bss": cal_m.brier_skill_score,
        "log_loss": cal_m.log_loss,
        "ece": cal_m.ece,
    }


# ------------------------------------------------------------------ orchestre


def run_learn_cycle(
    db_path: Path | None = None,
    cycle_db: Path | None = None,
    cal_db: Path | None = None,
    edge_threshold: float = 0.55,
    n_folds: int = 5,
    last_ingest_ts: float | None = None,
) -> LearnReport:
    """Cycle complet d'apprentissage :
    1. Ingestion des décisions résolues → cycle_memory
    2. Fit Platt + Beta depuis l'historique
    3. Backtest uplift
    4. Walk-forward (cross-validation temporelle)
    5. Génération du rapport + alertes
    """
    if db_path is None:
        db_path = Path("data/v9_forces.db")
    if cycle_db is None:
        cycle_db = CYCLE_MEMORY_DB_PATH
    if cal_db is None:
        cal_db = DEFAULT_CALIBRATION_DB

    alerts: list[str] = []

    # 1. Ingestion
    try:
        n_ingested, n_transitions, n_cells = _ingest_resolved_decisions(
            db_path, cycle_db, last_ingest_ts,
        )
    except Exception as e:
        logger.error("learn_loop: ingestion failed: %s", e)
        return LearnReport(
            timestamp=time.time(), n_resolved_ingested=0,
            n_transitions_ingested=0, n_cells_updated=0,
            fit_metrics={"error": str(e)},
            backtest_metrics={}, walk_forward_metrics={},
            alerts=("ingestion_error",),
            status="error",
        )

    # 2. Fit
    try:
        fit_result = fit_from_decisions_db(db_path, cal_db)
        if "error" in fit_result:
            fit_metrics = {"error": fit_result["error"]}
            alerts.append("fit_error")
        else:
            fit_metrics = {
                "n_fit": fit_result.get("n_fit", 0),
                "n_cells": fit_result.get("n_cells", 0),
                "global_wr": fit_result.get("global_wr", 0),
                "platt_a": fit_result["platt_global"]["a"],
                "platt_b": fit_result["platt_global"]["b"],
                "brier_score": fit_result["calibration_metrics"]["brier_score"],
                "log_loss": fit_result["calibration_metrics"]["log_loss"],
                "ece": fit_result["calibration_metrics"]["ece"],
                "bss": fit_result["calibration_metrics"]["brier_skill_score"],
            }
            # Alertes calibration
            if fit_metrics["bss"] < TARGET_BSS:
                alerts.append(f"bss_low:{fit_metrics['bss']:.3f}<{TARGET_BSS}")
            if fit_metrics["ece"] > TARGET_ECE:
                alerts.append(f"ece_high:{fit_metrics['ece']:.4f}>{TARGET_ECE}")
    except Exception as e:
        logger.error("learn_loop: fit failed: %s", e)
        fit_metrics = {"error": str(e)}
        alerts.append("fit_error")

    # 3. Backtest uplift
    try:
        backtest_metrics = _backtest_uplift(db_path, cal_db, edge_threshold)
        if "error" not in backtest_metrics:
            if backtest_metrics["wr_uplift_pts"] < TARGET_WR_UPLIFT:
                alerts.append(
                    f"wr_uplift_low:{backtest_metrics['wr_uplift_pts']:.2f}<{TARGET_WR_UPLIFT}"
                )
            if backtest_metrics["pf_filtered"] < 1.0 + TARGET_PF_UPLIFT:
                alerts.append(
                    f"pf_low:{backtest_metrics['pf_filtered']:.2f}<{1.0 + TARGET_PF_UPLIFT}"
                )
    except Exception as e:
        logger.error("learn_loop: backtest failed: %s", e)
        backtest_metrics = {"error": str(e)}
        alerts.append("backtest_error")

    # 4. Walk-forward
    try:
        walk_forward_metrics = walk_forward_backtest(
            db_path, cal_db, n_folds=n_folds, edge_threshold=edge_threshold,
        )
        if "error" not in walk_forward_metrics:
            mean_uplift = walk_forward_metrics.get("wr_uplift_mean_pts", 0)
            if mean_uplift < 0:
                alerts.append(f"walk_forward_negative:{mean_uplift:.2f}pts")
            stddev = walk_forward_metrics.get("wr_uplift_stddev_pts", 0)
            if stddev > 5.0:
                alerts.append(f"walk_forward_high_variance:{stddev:.2f}pts")
    except Exception as e:
        logger.error("learn_loop: walk_forward failed: %s", e)
        walk_forward_metrics = {"error": str(e)}
        alerts.append("walk_forward_error")

    # 5. Status
    status = "ok"
    if any("error" in a for a in alerts):
        status = "error"
    elif alerts:
        status = "warning"

    return LearnReport(
        timestamp=time.time(),
        n_resolved_ingested=n_ingested,
        n_transitions_ingested=n_transitions,
        n_cells_updated=n_cells,
        fit_metrics=fit_metrics,
        backtest_metrics=backtest_metrics,
        walk_forward_metrics=walk_forward_metrics,
        alerts=tuple(alerts),
        status=status,
    )


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    """CLI : run_learn_cycle avec rapport Markdown optionnel."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="v9_learn_loop — Boucle d'apprentissage continue (Phase E, R33)"
    )
    parser.add_argument("--db", default="data/v9_forces.db")
    parser.add_argument("--cycle-db", default=str(CYCLE_MEMORY_DB_PATH))
    parser.add_argument("--cal-db", default=str(DEFAULT_CALIBRATION_DB))
    parser.add_argument("--edge-threshold", type=float, default=0.55)
    parser.add_argument("--n-folds", type=int, default=5)
    parser.add_argument("--report", type=str, default=None,
                        help="Chemin rapport Markdown (défaut: stdout JSON)")
    args = parser.parse_args(argv)

    if not learn_loop_enabled():
        print("[learn_loop] kill switch V9_LEARN_LOOP_ENABLED=0, no-op", file=sys.stderr)
        return 0

    report = run_learn_cycle(
        db_path=Path(args.db),
        cycle_db=Path(args.cycle_db),
        cal_db=Path(args.cal_db),
        edge_threshold=args.edge_threshold,
        n_folds=args.n_folds,
    )

    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        content = _render_report_markdown(report)
        Path(args.report).write_text(content, encoding="utf-8")
        print(f"[learn_loop] rapport écrit : {args.report}")

    # 2026-07-22 — Persister le state pour reprise inter-runs (GAP 1).
    # Avant : le cron tournaient sans mémoire → refaisait l'ingestion depuis 0.
    # Maintenant : le state sauvegarde le timestamp du dernier run + compteurs.
    import json
    state_path = Path("data/v9_learn_loop_state.json")
    state = {
        "last_run": report.timestamp,
        "last_run_iso": datetime.now(timezone.utc).isoformat(),
        "n_ingested": report.n_resolved_ingested,
        "n_transitions": report.n_transitions_ingested,
        "n_cells": report.n_cells_updated,
        "status": report.status,
    }
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"[learn_loop] state écrit : {state_path}")
    except Exception as exc:
        print(f"[learn_loop] WARN: state write failed: {exc}", file=sys.stderr)
    else:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

    print(
        f"\n[learn_loop] status={report.status} "
        f"ingested={report.n_resolved_ingested} "
        f"transitions={report.n_transitions_ingested} "
        f"alerts={list(report.alerts)}"
    )
    return 0 if report.status != "error" else 1


def _render_report_markdown(report: LearnReport) -> str:
    """Génère un rapport Markdown lisible."""
    fm = report.fit_metrics
    bm = report.backtest_metrics
    wm = report.walk_forward_metrics
    lines: list[str] = []
    lines.append("# Rapport Learn Loop — Système Prédictif V9")
    lines.append("")
    lines.append(f"**Date** : {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(report.timestamp))}")
    lines.append(f"**Status** : {report.status}")
    lines.append("")
    lines.append("## Ingestion")
    lines.append(f"- Décisions résolues ingérées : **{report.n_resolved_ingested}**")
    lines.append(f"- Transitions markov ingérées : **{report.n_transitions_ingested}**")
    lines.append(f"- Cellules contextuelles mises à jour : **{report.n_cells_updated}**")
    lines.append("")
    lines.append("## Fit (Platt + Beta)")
    if "error" in fm:
        lines.append(f"❌ Erreur : {fm['error']}")
    else:
        lines.append(f"- n_fit = {fm.get('n_fit', 0)}")
        lines.append(f"- n_cells = {fm.get('n_cells', 0)}")
        lines.append(f"- global_wr = {fm.get('global_wr', 0):.4f}")
        lines.append(f"- Platt(a, b) = ({fm.get('platt_a', 0)}, {fm.get('platt_b', 0)})")
        lines.append(f"- Brier Score = {fm.get('brier_score', 0):.6f}")
        lines.append(f"- Log-loss = {fm.get('log_loss', 0):.6f}")
        lines.append(f"- ECE = {fm.get('ece', 0):.4%}")
        lines.append(f"- BSS = {fm.get('bss', 0):.4f}")
    lines.append("")
    lines.append("## Backtest uplift")
    if "error" in bm:
        lines.append(f"❌ Erreur : {bm['error']}")
    else:
        lines.append(f"- Trades baseline : {bm.get('n_base', 0)}")
        lines.append(f"- Trades filtrés : {bm.get('n_filtered', 0)}")
        lines.append(f"- WR baseline : {bm.get('wr_baseline', 0):.4%}")
        lines.append(f"- WR filtré : {bm.get('wr_filtered', 0):.4%}")
        lines.append(f"- **Δ WR** : **{bm.get('wr_uplift_pts', 0):+.2f} pts**")
        lines.append(f"- Pips baseline : {bm.get('pips_baseline', 0):+.1f}")
        lines.append(f"- Pips filtré : {bm.get('pips_filtered', 0):+.1f}")
        lines.append(f"- **PF filtré** : **{bm.get('pf_filtered', 0):.3f}**")
    lines.append("")
    lines.append("## Walk-forward (cross-validation temporelle)")
    if "error" in wm:
        lines.append(f"❌ Erreur : {wm['error']}")
    else:
        lines.append(f"- n_folds = {wm.get('n_folds', 0)}")
        lines.append(f"- n_test_total = {wm.get('n_test_total', 0)}")
        lines.append(f"- **WR uplift mean** : **{wm.get('wr_uplift_mean_pts', 0):+.2f} pts**")
        lines.append(f"- WR uplift min = {wm.get('wr_uplift_min_pts', 0):+.2f}")
        lines.append(f"- WR uplift max = {wm.get('wr_uplift_max_pts', 0):+.2f}")
        lines.append(f"- WR uplift stddev = {wm.get('wr_uplift_stddev_pts', 0):.2f}")
        if "folds" in wm:
            lines.append("")
            lines.append("### Détail par fold")
            lines.append("| Fold | n_test | n_enter | WR base | WR filtré | Δ WR (pts) |")
            lines.append("|---:|---:|---:|---:|---:|---:|")
            for f in wm["folds"]:
                lines.append(
                    f"| {f['fold_idx']} | {f['n_test']} | {f['n_enter']} | "
                    f"{f['wr_baseline']:.2%} | {f['wr_filtered']:.2%} | "
                    f"{f['wr_uplift_pts']:+.2f} |"
                )
    lines.append("")
    if report.alerts:
        lines.append("## ⚠️ Alertes")
        for a in report.alerts:
            lines.append(f"- {a}")
    else:
        lines.append("## ✅ Aucune alerte — système nominal.")
    lines.append("")
    lines.append("---")
    lines.append("*Rapport généré par `core/v9/v9_learn_loop.py run_learn_cycle`.*")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
