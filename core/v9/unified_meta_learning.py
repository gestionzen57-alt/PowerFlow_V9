"""UnifiedMetaLearningLoop — Orchestrateur unique des 4 boucles d'optimisation V9.

Remplace les 4 crons séparés :
  - auto_calibrator (V9_AUTO_CALIBRATOR_ENABLED)
  - auto_optimizer (V9_AUTO_OPTIMIZER_ENABLED)
  - learn_loop (V9_LEARN_LOOP_ENABLED)
  - walk_forward (V9_WALK_FORWARD_ENABLED)

Par un SEUL cycle unifié avec état partagé, kill switch unique, et gatings croisés.

Doctrine : R2 additif, R6 défensif, R18 code pur, R30 boucle fermée, R33 Système Prédictif.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, ROOT_DIR
from core.v9.db_schema import get_connection
from core.v9.kill_switches import get as ks_get

# Imports défensifs (R6) — modules optionnels
try:
    from core.v9.auto_calibrator import run_calibration_cycle as _run_calibration_cycle
    from core.v9.auto_calibrator import auto_calibrator_enabled
    AUTO_CALIBRATOR_AVAILABLE = True
except ImportError:
    AUTO_CALIBRATOR_AVAILABLE = False

try:
    from core.v9.auto_optimizer import run_optimization_cycle as _run_optimization_cycle
    from core.v9.auto_optimizer import auto_optimizer_enabled
    AUTO_OPTIMIZER_AVAILABLE = True
except ImportError:
    AUTO_OPTIMIZER_AVAILABLE = False

try:
    from core.v9.v9_learn_loop import run_learn_cycle as _run_learn_cycle
    from core.v9.v9_learn_loop import learn_loop_enabled, LearnReport
    LEARN_LOOP_AVAILABLE = True
except ImportError:
    LEARN_LOOP_AVAILABLE = False

try:
    from core.v9.walk_forward import run_walk_forward as _run_walk_forward
    from core.v9.walk_forward import walk_forward_enabled
    WALK_FORWARD_AVAILABLE = True
except ImportError:
    WALK_FORWARD_AVAILABLE = False

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Kill switch unique
# ──────────────────────────────────────────────────────────────────────────────

META_LEARNING_ENABLED_ENV = "V9_META_LEARNING_ENABLED"
UNIFIED_SIZING_ENABLED_ENV = "V9_UNIFIED_SIZING_ENABLED"

# Fichier d'état partagé
SHARED_STATE_PATH = ROOT_DIR / "config" / "v9_meta_learning_state.json"


def meta_learning_enabled() -> bool:
    """Kill switch unique pour toute la meta-apprentissage."""
    return ks_get(META_LEARNING_ENABLED_ENV, "1") == "1"


def unified_sizing_enabled() -> bool:
    """Kill switch pour le moteur de sizing unifié."""
    return ks_get(UNIFIED_SIZING_ENABLED_ENV, "1") == "1"


# ──────────────────────────────────────────────────────────────────────────────
# État partagé (persisté JSON)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MetaLearningState:
    """État global partagé entre toutes les boucles."""
    version: str = "1.0"
    last_cycle_ts: float = 0.0
    last_cycle_iso: str = ""
    cycle_count: int = 0
    
    # Résultats dernière exécution par module
    calibration_report: dict[str, Any] = field(default_factory=dict)
    optimization_report: dict[str, Any] = field(default_factory=dict)
    learn_report: dict[str, Any] = field(default_factory=dict)
    walk_forward_report: dict[str, Any] = field(default_factory=dict)
    
    # Gatings croisés
    kelly_gated: bool = False
    bayesian_predictor_gated: bool = False
    meta_strategy_gated: bool = False
    auto_optimizer_gated: bool = False
    gating_rationale: list[str] = field(default_factory=list)
    
    # Métriques agrégées
    global_wr: float | None = None
    global_expectancy: float | None = None
    total_trades_analyzed: int = 0
    
    # Alertes
    alerts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls) -> "MetaLearningState":
        if SHARED_STATE_PATH.exists():
            try:
                data = json.loads(SHARED_STATE_PATH.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        SHARED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SHARED_STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SHARED_STATE_PATH)


# ──────────────────────────────────────────────────────────────────────────────
# Gating Walk-Forward (auto-désactivation modules quantiques)
# ──────────────────────────────────────────────────────────────────────────────

class WalkForwardGate:
    """Évalue les résultats walk-forward et module les kill switches quantiques."""
    
    THRESHOLDS = {
        "oos_edge_min_pips": 2.0,
        "wr_inter_fold_max_gap": 15.0,
        "oos_is_ratio_min": 0.8,
        "n_folds_positive_min": 3,
    }
    
    KILL_SWITCH_MAP = {
        "V9_KELLY_FRACTIONAL_ENABLED": "kelly",
        "V9_BAYESIAN_PREDICTOR_ENABLED": "bayesian_predictor",
        "V9_META_STRATEGY_OPTIMIZER_ENABLED": "meta_strategy",
        "V9_AUTO_OPTIMIZER_ENABLED": "auto_optimizer",
    }
    
    def __init__(self, state: MetaLearningState):
        self.state = state
    
    def evaluate(self, wf_report: dict) -> dict[str, bool]:
        """Retourne {kill_switch: new_state} + met à jour state.gating_*."""
        actions = {}
        rationale = []
        
        if not wf_report or wf_report.get("enabled") is False:
            return actions
        
        oos_edge = wf_report.get("oos_expectancy_pips", 0)
        if oos_edge < self.THRESHOLDS["oos_edge_min_pips"]:
            rationale.append(f"OOS edge {oos_edge:.1f} < {self.THRESHOLDS['oos_edge_min_pips']}")
            for ks, module in self.KILL_SWITCH_MAP.items():
                if module in ("kelly", "meta_strategy", "auto_optimizer"):
                    actions[ks] = False
        
        wr_gap = wf_report.get("wr_inter_fold_stddev", 0) * 2
        if wr_gap > self.THRESHOLDS["wr_inter_fold_max_gap"]:
            rationale.append(f"WR inter-fold gap {wr_gap:.1f} > {self.THRESHOLDS['wr_inter_fold_max_gap']}")
            actions["V9_BAYESIAN_PREDICTOR_ENABLED"] = False
        
        oos_is_ratio = wf_report.get("oos_is_ratio", 1.0)
        if oos_is_ratio < self.THRESHOLDS["oos_is_ratio_min"]:
            rationale.append(f"OOS/IS ratio {oos_is_ratio:.2f} < {self.THRESHOLDS['oos_is_ratio_min']}")
            actions["V9_KELLY_FRACTIONAL_ENABLED"] = False
        
        n_positive = wf_report.get("n_folds_positive", 5)
        if n_positive < self.THRESHOLDS["n_folds_positive_min"]:
            rationale.append(f"Seulement {n_positive}/5 folds positifs")
            for ks in self.KILL_SWITCH_MAP:
                actions[ks] = False
        
        # Appliquer les changements (écrire dans .env via kill_switches)
        for ks, new_state in actions.items():
            self._write_kill_switch(ks, "1" if new_state else "0")
        
        # Mettre à jour l'état
        self.state.kelly_gated = actions.get("V9_KELLY_FRACTIONAL_ENABLED", False) is False
        self.state.bayesian_predictor_gated = actions.get("V9_BAYESIAN_PREDICTOR_ENABLED", False) is False
        self.state.meta_strategy_gated = actions.get("V9_META_STRATEGY_OPTIMIZER_ENABLED", False) is False
        self.state.auto_optimizer_gated = actions.get("V9_AUTO_OPTIMIZER_ENABLED", False) is False
        self.state.gating_rationale = rationale
        
        return actions
    
    def _write_kill_switch(self, key: str, value: str) -> None:
        """Écrit le kill switch dans config/v9_kill_switches.env (atomique)."""
        env_path = ROOT_DIR / "config" / "v9_kill_switches.env"
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        
        # Update or add
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(key + "="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        
        tmp = env_path.with_suffix(".env.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(env_path)
        
        # Invalider le cache process-local de kill_switches
        import core.v9.kill_switches as ks_module
        ks_module._switches = None
        logger.info(f"WalkForwardGate: {key}={value} (rationale: {'; '.join(self.state.gating_rationale)})")


# ──────────────────────────────────────────────────────────────────────────────
# Boucle unifiée
# ──────────────────────────────────────────────────────────────────────────────

class UnifiedMetaLearningLoop:
    """Orchestrateur unique des 4 boucles d'optimisation."""
    
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.state = MetaLearningState.load()
    
    def run_cycle(self, force: bool = False) -> dict[str, Any]:
        """Exécute un cycle complet des 4 boucles dans l'ordre optimal.
        
        Ordre : WalkForward (diagnostic) → LearnLoop (apprentissage) → 
                Calibration (ajustement seuils) → Optimizer (TP/SL)
        """
        if not meta_learning_enabled() and not force:
            return {"enabled": False, "message": "V9_META_LEARNING_ENABLED=0"}
        
        cycle_start = time.time()
        report = {
            "meta_learning_version": "1.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "cycle_duration_sec": 0.0,
            "modules_run": [],
            "modules_skipped": [],
            "errors": [],
            "global_metrics": {},
            "gating_actions": {},
        }
        
        # 1. WALK-FORWARD FIRST (diagnostic global, gate les autres)
        if WALK_FORWARD_AVAILABLE and walk_forward_enabled():
            try:
                logger.info("UnifiedMetaLearning: Running walk-forward...")
                wf_report = _run_walk_forward(db_path=self.db_path)
                report["walk_forward_report"] = wf_report
                report["modules_run"].append("walk_forward")
                
                # Gate les autres modules
                gate = WalkForwardGate(self.state)
                gating_actions = gate.evaluate(wf_report)
                report["gating_actions"] = gating_actions
            except Exception as e:
                report["errors"].append(f"walk_forward: {e}")
                logger.error(f"Walk-forward failed: {e}")
        else:
            report["modules_skipped"].append("walk_forward (unavailable or disabled)")
        
        # 2. LEARN LOOP (apprentissage continu - fit Platt/Beta + walk-forward interne)
        if LEARN_LOOP_AVAILABLE and learn_loop_enabled() and not self.state.kelly_gated:
            try:
                logger.info("UnifiedMetaLearning: Running learn loop...")
                learn_report = _run_learn_cycle(db_path=self.db_path)
                report["learn_report"] = learn_report.to_dict() if hasattr(learn_report, 'to_dict') else learn_report
                report["modules_run"].append("learn_loop")
            except Exception as e:
                report["errors"].append(f"learn_loop: {e}")
                logger.error(f"Learn loop failed: {e}")
        else:
            reason = "unavailable/disabled" if not (LEARN_LOOP_AVAILABLE and learn_loop_enabled()) else "kelly_gated"
            report["modules_skipped"].append(f"learn_loop ({reason})")
        
        # 3. AUTO-CALIBRATOR (ajuste seuils, promme/démotte principes)
        if AUTO_CALIBRATOR_AVAILABLE and auto_calibrator_enabled() and not self.state.auto_optimizer_gated:
            try:
                logger.info("UnifiedMetaLearning: Running auto-calibrator...")
                cal_report = _run_calibration_cycle(db_path=self.db_path, auto_apply=True)
                report["calibration_report"] = cal_report
                report["modules_run"].append("auto_calibrator")
            except Exception as e:
                report["errors"].append(f"auto_calibrator: {e}")
                logger.error(f"Auto-calibrator failed: {e}")
        else:
            reason = "unavailable/disabled" if not (AUTO_CALIBRATOR_AVAILABLE and auto_calibrator_enabled()) else "auto_optimizer_gated"
            report["modules_skipped"].append(f"auto_calibrator ({reason})")
        
        # 4. AUTO-OPTIMIZER (grid search TP/SL par principe)
        if AUTO_OPTIMIZER_AVAILABLE and auto_optimizer_enabled() and not self.state.auto_optimizer_gated:
            try:
                logger.info("UnifiedMetaLearning: Running auto-optimizer...")
                opt_report = _run_optimization_cycle(db_path=self.db_path)
                report["optimization_report"] = opt_report
                report["modules_run"].append("auto_optimizer")
            except Exception as e:
                report["errors"].append(f"auto_optimizer: {e}")
                logger.error(f"Auto-optimizer failed: {e}")
        else:
            reason = "unavailable/disabled" if not (AUTO_OPTIMIZER_AVAILABLE and auto_optimizer_enabled()) else "auto_optimizer_gated"
            report["modules_skipped"].append(f"auto_optimizer ({reason})")
        
        # 5. Calcul métriques globales
        self._compute_global_metrics(report)
        
        # 6. Mise à jour état
        self.state.last_cycle_ts = cycle_start
        self.state.last_cycle_iso = datetime.fromtimestamp(cycle_start, tz=timezone.utc).isoformat()
        self.state.cycle_count += 1
        self.state.calibration_report = report.get("calibration_report", {})
        self.state.optimization_report = report.get("optimization_report", {})
        self.state.learn_report = report.get("learn_report", {})
        self.state.walk_forward_report = report.get("walk_forward_report", {})
        self.state.global_wr = report["global_metrics"].get("global_wr")
        self.state.global_expectancy = report["global_metrics"].get("global_expectancy")
        self.state.total_trades_analyzed = report["global_metrics"].get("total_trades", 0)
        self.state.save()
        
        report["cycle_duration_sec"] = round(time.time() - cycle_start, 2)
        report["state"] = self.state.to_dict()
        
        # 7. Notification Telegram (best-effort, anti-spam)
        self._notify_telegram(report)
        
        return report
    
    def _compute_global_metrics(self, report: dict) -> None:
        """Calcule WR global et expectancy sur décisions DYNAMIC résolues."""
        try:
            conn = get_connection(self.db_path)
            row = conn.execute("""
                SELECT 
                    COUNT(*) as n,
                    SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) as wins,
                    AVG(resolution_pips) as avg_pips
                FROM decisions
                WHERE action='preparer_entree' 
                  AND resolution_strategy='DYNAMIC'
                  AND is_win IS NOT NULL
            """).fetchone()
            conn.close()
            
            if row and row[0] and row[0] > 0:
                report["global_metrics"] = {
                    "global_wr": round(row[1] / row[0] * 100, 2),
                    "global_expectancy": round(row[2] or 0, 2),
                    "total_trades": row[0],
                }
        except Exception as e:
            logger.debug(f"Global metrics failed: {e}")
    
    def _notify_telegram(self, report: dict) -> None:
        """Notification Telegram anti-spam (seulement si changements réels)."""
        try:
            from core.v9.decision_logger import _load_telegram_config_safe
            from scripts.v9_telegram_notifier import send_telegram
            
            cfg = _load_telegram_config_safe()
            if not cfg:
                return
            
            # Anti-spam : notifier seulement si actions de gating ou modules ont tourné
            has_gating = bool(report.get("gating_actions"))
            has_modules = len(report.get("modules_run", [])) > 0
            has_errors = len(report.get("errors", [])) > 0
            
            if not (has_gating or has_modules or has_errors):
                return
            
            lines = ["[V9] Unified Meta-Learning Cycle", f"Durée: {report['cycle_duration_sec']}s"]
            if report["modules_run"]:
                lines.append(f"✅ Exécutés: {', '.join(report['modules_run'])}")
            if report["modules_skipped"]:
                lines.append(f"⏭️ Skippés: {', '.join(report['modules_skipped'])}")
            if report["gating_actions"]:
                lines.append(f"🚦 Gating: {report['gating_actions']}")
            if report["errors"]:
                lines.append(f"❌ Erreurs: {len(report['errors'])}")
            if report["global_metrics"]:
                gm = report["global_metrics"]
                lines.append(f"📊 WR Global: {gm.get('global_wr')}% | Expectancy: {gm.get('global_expectancy')} pips | Trades: {gm.get('total_trades')}")
            
            send_telegram("\n".join(lines), cfg, timeout=5)
        except Exception:
            pass  # Best-effort


# ──────────────────────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────────────────────

def run_unified_meta_learning_cycle(
    db_path: Path | str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Point d'entrée unique pour le cron V9_MetaLearningLoop."""
    loop = UnifiedMetaLearningLoop(db_path)
    return loop.run_cycle(force=force)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Unified Meta-Learning Loop V9")
    parser.add_argument("--force", action="store_true", help="Force execution even if kill switch OFF")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    
    report = run_unified_meta_learning_cycle(force=args.force)
    
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Meta-Learning Cycle: {'OK' if not report.get('errors') else 'ERRORS'}")
        print(f"  Modules run: {report['modules_run']}")
        print(f"  Modules skipped: {report['modules_skipped']}")
        print(f"  Duration: {report['cycle_duration_sec']}s")
        if report["gating_actions"]:
            print(f"  Gating actions: {report['gating_actions']}")
    
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())