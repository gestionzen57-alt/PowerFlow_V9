"""V10 Learning Loop — S25-OMEGA.

Boucle principale qui orchestre le cycle complet d'apprentissage :
  1. ReplayEngine.run()          — replay parallèle toutes paires/TF
  2. AutoRecalibrator            — décide HOLD/SOFT/MEDIUM/HARD
  3. MetaOptimizer.full_analysis — évolution population + Pareto + diversif
  4. LearningContinuum.update    — mise à jour drift + Sharpe continus
  5. LearningPersistence.save    — persistance JSON
  6. Audit trail R9              — toutes les décisions tracées

Utilisation :
    loop = LearningLoop(db_path="/path/fatman.db")
    report = loop.run_cycle()

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .v10_replay_engine        import ReplayEngine
from .v10_auto_recalibrator    import run_auto_recalibration
from .v10_meta_optimizer       import MetaOptimizer
from .v10_learning_continuum   import LearningContinuum
from .v10_learning_persistence import LearningPersistence

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "USDCHF", "NZDUSD", "USDCAD",
]
DEFAULT_TIMEFRAMES = ["M30", "H1"]
OUTPUT_DIR         = Path("outputs/learning")

# Pondérations des modules pour entropy fusion
MODULE_NAMES = [
    "cs_delta", "confluence", "vsa", "smc",
    "fractal", "liquidity", "session_filter",
]


class LearningLoop:
    """Orchestre le cycle complet d'apprentissage S25-OMEGA."""

    def __init__(
        self,
        db_path: str,
        pairs: Optional[List[str]]      = None,
        timeframes: Optional[List[str]] = None,
        output_dir: Path                = OUTPUT_DIR,
    ) -> None:
        self.db_path    = db_path
        self.pairs      = pairs or DEFAULT_PAIRS
        self.timeframes = timeframes or DEFAULT_TIMEFRAMES
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        self.replay   = ReplayEngine(
            db_path=db_path,
            pairs=self.pairs,
            timeframes=self.timeframes,
        )
        self.meta     = MetaOptimizer(
            output_path=output_dir / "meta_optimizer_state.json"
        )
        self.continuum   = LearningContinuum()
        self.persistence = LearningPersistence(
            output_path=str(output_dir / "learning_state.json")
        )
        self._cycle_count = 0
        self._audit: List[Dict] = []

    # ── Cycle principal ────────────────────────────────────────────────────────
    def run_cycle(
        self,
        return_decisions: bool = False,
        regime: str = "UNKNOWN",
    ) -> Dict:
        """Lance un cycle complet d'apprentissage et retourne le rapport."""
        t0 = time.monotonic()
        self._cycle_count += 1
        ts = datetime.now(timezone.utc).isoformat()

        # ── ÉTAPE 1 : Replay parallèle ────────────────────────────────────────
        replay_report = {"error": "not_run"}
        raw_results: List[Dict] = []
        try:
            replay_report = self.replay.run(return_decisions=return_decisions)
            raw_results   = replay_report.get("results", [])
        except Exception as exc:
            replay_report = {"error": str(exc), "results": []}

        learner_state = self.replay.learner.state

        # ── ÉTAPE 2 : Auto-recalibration ──────────────────────────────────────
        recalib_decision = {"decision": "HOLD", "reason": "not_run"}
        try:
            dec = run_auto_recalibration(
                learner_state, db_path=self.db_path
            )
            recalib_decision = dec.as_dict()
        except Exception as exc:
            recalib_decision = {"decision": "HOLD", "reason": str(exc)}

        # ── ÉTAPE 3 : MetaOptimizer ───────────────────────────────────────────
        meta_report = {"error": "not_run"}
        try:
            # Précisions estimées des modules (proxy : WR global)
            global_wr = replay_report.get("global_wr", 0.5)
            module_acc = {m: global_wr for m in MODULE_NAMES}
            meta_report = self.meta.full_analysis(
                replay_results  = [
                    {"symbol": r.get("symbol", ""),
                     "n_decisions": r.get("n_decisions", 0),
                     "wr": r.get("wr", 0.5),
                     "decisions": r.get("decisions", [])}
                    for r in raw_results
                ],
                module_accuracies = module_acc,
                regime            = regime,
            )
        except Exception as exc:
            meta_report = {"error": str(exc)}

        # ── ÉTAPE 4 : LearningContinuum ───────────────────────────────────────
        continuum_state = {}
        try:
            pnl_series = [
                d.get("pnl_pips", 0)
                for r in raw_results
                for d in r.get("decisions", [])
            ]
            continuum_state = self.continuum.update(
                wins   = learner_state.n_wins,
                losses = learner_state.n_losses,
                sharpe = learner_state.sharpe_online,
                pnl_series = pnl_series,
            )
        except Exception as exc:
            continuum_state = {"error": str(exc)}

        # ── ÉTAPE 5 : Persistance ─────────────────────────────────────────────
        try:
            self.persistence.save({
                "cycle":      self._cycle_count,
                "timestamp":  ts,
                "learner":    learner_state.as_dict(),
                "recalib":    recalib_decision,
                "meta":       meta_report,
                "continuum":  continuum_state,
            })
        except Exception:
            pass

        elapsed = round(time.monotonic() - t0, 3)

        # ── Rapport final ──────────────────────────────────────────────────────
        report = {
            "cycle":        self._cycle_count,
            "timestamp":    ts,
            "elapsed_s":    elapsed,
            "replay":       {
                "global_wr":         replay_report.get("global_wr", 0.0),
                "total_decisions":   replay_report.get("total_decisions", 0),
                "n_valid":           replay_report.get("n_valid", 0),
                "n_errors":          replay_report.get("n_errors", 0),
                "global_avg_reward": replay_report.get("global_avg_reward", 0.0),
            },
            "recalib":      recalib_decision,
            "meta":         {
                "generation":     meta_report.get("generation", 0),
                "best_fitness":   meta_report.get("best_fitness", 0.0),
                "best_wr":        meta_report.get("best_wr", 0.0),
                "pareto_front":   meta_report.get("pareto_front", 0),
                "regime":         meta_report.get("regime", "UNKNOWN"),
                "regime_preset":  meta_report.get("regime_preset", {}),
                "entropy_weights":meta_report.get("entropy_weights", {}),
                "diversification":meta_report.get("diversification", {}),
                "anomalies":      meta_report.get("anomalies_detected", 0),
                "leaderboard":    meta_report.get("leaderboard", []),
            },
            "learner":      learner_state.as_dict(),
            "continuum":    continuum_state,
            "r9_audit":     f"cycle {self._cycle_count} — {elapsed}s",
        }

        self._audit.append({
            "cycle":     self._cycle_count,
            "ts":        ts,
            "wr":        replay_report.get("global_wr", 0.0),
            "recalib":   recalib_decision.get("decision", "HOLD"),
            "elapsed_s": elapsed,
        })

        return report

    def audit_trail(self) -> List[Dict]:
        """Retourne l'historique de tous les cycles (R9)."""
        return self._audit
