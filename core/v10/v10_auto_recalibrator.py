"""V10 Auto-Recalibrator — Ultra-optimisé S25-OMEGA.

Améliorations vs version précédente :
  Sharpe-aware decision — recalib si Sharpe < seuil ET WR faible
  Regime-aware — adapte l'intensité selon le régime HMM détecté
  Hysteresis anti-ping-pong — cooldown 10 min entre recalibs
  Staged recalibration — 3 niveaux (SOFT/MEDIUM/HARD) selon gravité
  Graduated thresholds — seuils adaptatifs selon volume de trades
  Bayesian posterior update — confidence interval sur WR
  as_dict() enrichi — stade, régime, sharpe, confidence
  R6 fail-open sur tout

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Seuils ────────────────────────────────────────────────────────────────────
WR_HARD_THR       = 0.40   # WR < 40% → HARD recalibration
WR_MEDIUM_THR     = 0.46   # WR < 46% → MEDIUM
WR_SOFT_THR       = 0.50   # WR < 50% → SOFT
SHARPE_HARD_THR   = -0.8   # Sharpe < -0.8 → force HARD
SHARPE_SOFT_THR   = -0.3   # Sharpe < -0.3 → aggrave le stade
STREAK_MEDIUM     = 4      # streak ≥ 4 → force MEDIUM
STREAK_HARD       = 7      # streak ≥ 7 → force HARD
MIN_LOSSES_SOFT   = 5      # trades min avant SOFT
MIN_LOSSES_MEDIUM = 10     # trades min avant MEDIUM
MIN_LOSSES_HARD   = 20     # trades min avant HARD
COOLDOWN_S        = 600    # 10 min entre deux recalibs (hysteresis)
CONFIDENCE_Z      = 1.645  # z pour IC 90%

# ── Singletons de cooldown globaux ────────────────────────────────────────────────
_last_recalib_ts: float = 0.0


@dataclass
class RecalibDecision:
    decision:    str    # HOLD | SOFT | MEDIUM | HARD | REVERT | DEPLOY
    reason:      str
    wr_ewm:      float  = 0.0
    sharpe:      float  = 0.0
    wr_ci_low:   float  = 0.0
    wr_ci_high:  float  = 0.0
    stage:       str    = "HOLD"
    regime_hint: str    = "UNKNOWN"
    cooldown_active: bool = False
    # C9 compat: tests attendent triggered, timestamp, setups
    triggered:   bool   = False
    timestamp:   str    = ""
    setups:      list   = field(default_factory=list)
    # C9 compat: champs de la décision de recalibration (avant/après)
    before_wr:   float  = 0.0
    after_wr:    float  = 0.0
    threshold_path: str = ""

    def as_dict(self) -> dict:
        return {
            "decision":       self.decision,
            "reason":         self.reason,
            "wr_ewm":         round(self.wr_ewm, 4),
            "sharpe":         round(self.sharpe, 4),
            "wr_ci":          [round(self.wr_ci_low, 4), round(self.wr_ci_high, 4)],
            "stage":          self.stage,
            "regime_hint":    self.regime_hint,
            "cooldown_active":self.cooldown_active,
            "triggered":      self.triggered,
            "timestamp":      self.timestamp,
            "setups":         self.setups,
            "before_wr":      round(self.before_wr, 4),
            "after_wr":       round(self.after_wr, 4),
            "threshold_path": self.threshold_path,
        }


def _wilson_ci(n_wins: int, n_trials: int, z: float = CONFIDENCE_Z) -> tuple:
    """Intervalle de confiance de Wilson pour un taux de succès."""
    if n_trials == 0:
        return 0.0, 1.0
    p = n_wins / n_trials
    denom = 1 + z**2 / n_trials
    center = (p + z**2 / (2 * n_trials)) / denom
    margin = z * math.sqrt(p * (1 - p) / n_trials + z**2 / (4 * n_trials**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _detect_regime(db_path: Optional[str]) -> str:
    """Détecte le régime HMM actuel (R6 fail-open → UNKNOWN)."""
    if not db_path:
        return "UNKNOWN"
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        rows = conn.execute(
            "SELECT regime FROM forces_snapshots "
            "ORDER BY bar_time DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return rows[0] if rows else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def run_auto_recalibration(
    learner_state,
    db_path: Optional[str] = None,
    min_losses: int = MIN_LOSSES_SOFT,
) -> RecalibDecision:
    """Décide le stade de recalibration selon WR EWM, Sharpe, streak, régime."""
    global _last_recalib_ts

    n_trades  = getattr(learner_state, "n_trades", 0)
    n_losses  = getattr(learner_state, "n_losses", 0)
    n_wins    = getattr(learner_state, "n_wins", 0)
    streak    = getattr(learner_state, "max_losing_streak", 0)
    ewm_wr    = getattr(learner_state, "ewm_wr", 0.5)
    sharpe    = getattr(learner_state, "sharpe_online", 0.0)
    drift     = getattr(learner_state, "drift_detected", False)
    # C9: tests attendent drift_detected et recalibrate_setups sur learner_state
    recalibrate_setups = getattr(learner_state, "recalibrate_setups", [])
    per_setup = getattr(learner_state, "per_setup", {}) or {}

    ci_low, ci_high = _wilson_ci(n_wins, n_trades)
    regime          = _detect_regime(db_path)

    # Hysteresis cooldown (R6 fail-open : cooldown → HOLD sans crash)
    now = time.monotonic()
    if (now - _last_recalib_ts) < COOLDOWN_S:
        return RecalibDecision(
            decision="HOLD", reason="cooldown_active",
            wr_ewm=ewm_wr, sharpe=sharpe,
            wr_ci_low=ci_low, wr_ci_high=ci_high,
            stage="HOLD", regime_hint=regime,
            cooldown_active=True,
            triggered=False, timestamp="",
        )

    # Régime aggravant : VOLATILE ou DISTRIBUTION → seuils plus stricts
    regime_aggravates = regime in ("VOLATILE", "DISTRIBUTION", "MARKDOWN")

    # Détermination du stade
    stage = "HOLD"

    # C9: drift détecté force au moins SOFT (ou plus selon pertes)
    if drift:
        if n_losses >= MIN_LOSSES_HARD and (
            ewm_wr < WR_HARD_THR
            or sharpe < SHARPE_HARD_THR
        ):
            stage = "HARD"
        elif n_losses >= MIN_LOSSES_MEDIUM:
            stage = "MEDIUM"
        else:
            stage = "SOFT"
    elif n_losses >= MIN_LOSSES_HARD and (
        ewm_wr < WR_HARD_THR
        or sharpe < SHARPE_HARD_THR
        or streak >= STREAK_HARD
    ):
        stage = "HARD"
    elif n_losses >= MIN_LOSSES_MEDIUM and (
        ewm_wr < WR_MEDIUM_THR
        or sharpe < SHARPE_SOFT_THR
        or streak >= STREAK_MEDIUM
        or (regime_aggravates and ewm_wr < WR_SOFT_THR)
    ):
        stage = "MEDIUM"
    elif n_losses >= min_losses and (
        ewm_wr < WR_SOFT_THR
    ):
        stage = "SOFT"

    if stage == "HOLD":
        return RecalibDecision(
            decision="HOLD",
            reason="no_trigger",
            wr_ewm=ewm_wr, sharpe=sharpe,
            wr_ci_low=ci_low, wr_ci_high=ci_high,
            stage="HOLD", regime_hint=regime,
            triggered=False, timestamp="",
        )

    # Execute recalibration : compare le WR avant/après via le recalibrateur
    # bayésien (R6 fail-open : DB invalide → report vide → avg_wr=0 → REVERT safe).
    before_wr = ewm_wr if ewm_wr > 0.0 else max(
        (per_setup.get(s, {}).get("wr", 0.0) for s in recalibrate_setups),
        default=0.0,
    )
    after_wr = before_wr
    try:
        # Import paresseux : évite tout cycle d'import avec le package __init__
        from core.v10.v10_bayesian_recalibrator import compute_recalibration
        report = compute_recalibration(db_path or "data/v9_forces.db",
                                       blacklist=frozenset())
        if report is not None and report.pair_thresholds:
            wrs = [t.win_rate for t in report.pair_thresholds.values()
                   if getattr(t, "win_rate", 0) > 0]
            if wrs:
                after_wr = sum(wrs) / len(wrs)
            else:
                after_wr = 0.0  # report vide → aucune preuve d'amélioration → REVERT (safe)
        else:
            after_wr = 0.0  # R6 fail-open : DB invalide → after_wr=0 < before_wr → REVERT
    except Exception:
        # R6 fail-open : aucune donnée → after_wr=0 < before_wr → REVERT (safe)
        after_wr = 0.0

    # Décision finale : DEPLOY si amélioration, REVERT si régression, sinon le stade
    decision = stage
    if after_wr < before_wr:
        decision = "REVERT"
    elif after_wr > before_wr:
        decision = "DEPLOY"

    # Raisons
    reasons = []
    if ewm_wr < WR_HARD_THR:    reasons.append(f"wr_low={ewm_wr:.3f}")
    if sharpe < SHARPE_HARD_THR: reasons.append(f"sharpe_low={sharpe:.3f}")
    if streak >= STREAK_MEDIUM:  reasons.append(f"streak={streak}")
    if regime_aggravates:        reasons.append(f"regime={regime}")
    if drift:                    reasons.append("drift_detected")

    _last_recalib_ts = now
    return RecalibDecision(
        decision=decision,
        reason=" | ".join(reasons) or "threshold_crossed",
        wr_ewm=ewm_wr, sharpe=sharpe,
        wr_ci_low=ci_low, wr_ci_high=ci_high,
        stage=stage, regime_hint=regime,
        cooldown_active=False,
        triggered=True, timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        setups=recalibrate_setups,
        before_wr=before_wr,
        after_wr=after_wr,
        threshold_path="config/v10_active_thresholds.json",
    )


def should_recalibrate(
    learner_state,
    db_path: Optional[str] = None,
    min_losses: int = MIN_LOSSES_SOFT,
) -> tuple:
    """
    Décide si une recalibration est nécessaire (API C9, retour tuple).

    Retourne (triggered, reason, setups) :
      - triggered=True + reason="drift_detected" si le learner signale un drift
      - triggered=True + reason="recalibrate_recommended" si le learner le
        recommande ET que le setup a assez de trades (>= min_losses)
      - sinon (False, "no_trigger", [])
    """
    drift            = getattr(learner_state, "drift_detected", False)
    rec_recommended  = getattr(learner_state, "recalibrate_recommended", False)
    recal_setups     = getattr(learner_state, "recalibrate_setups", [])
    per_setup        = getattr(learner_state, "per_setup", {}) or {}

    if drift:
        return (True, "drift_detected", list(recal_setups))

    if rec_recommended:
        ok = [s for s in recal_setups if per_setup.get(s, {}).get("n", 0) >= min_losses]
        if ok:
            return (True, "recalibrate_recommended", ok)

    return (False, "no_trigger", [])
