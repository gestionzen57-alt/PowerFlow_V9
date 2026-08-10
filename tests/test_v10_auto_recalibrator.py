"""V10 Auto-Recalibrator — tests unitaires (Sprint 7 autopilote quant).

Mis à jour 2026-08-10 (Chantier 2 / HERMES_PROMPT_MAX) : le module live C9
retourne désormais un objet `RecalibDecision` (plus un tuple 3-éléments).
Les runtime `learning_loop`/`calibrate_apply` consomment déjà `RecalibDecision`.
On aligne les assertions sur l'API réelle — jamais de modification du module.

Obligations Sprint 7 :
  1. test_should_recalibrate_drift
  2. test_should_recalibrate_recommended_enough_data
  3. test_should_recalibrate_no_trigger
  4. test_should_recalibrate_recommended_not_enough
  5. test_run_auto_recalibration_no_trigger_hold
  6. test_run_auto_recalibration_error_hold
  7. test_decision_serialization
  8. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_auto_recalibrator import (  # noqa: E402
    RecalibDecision,
    should_recalibrate,
    run_auto_recalibration,
)


@pytest.fixture(autouse=True)
def _reset_cooldown():
    """Reset le cooldown global (600s) entre tests pour isoler chaque cas."""
    import core.v10.v10_auto_recalibrator as ar
    ar._last_recalib_ts = 0.0
    yield


class FakeState:
    """État learner minimal avec les attributs lus par run_auto_recalibration."""
    def __init__(self, drift=False, n_trades=0, n_wins=0, n_losses=0,
                 ewm_wr=0.5, sharpe_online=0.0, max_losing_streak=0,
                 recalibrate_setups=None, per_setup=None):
        self.drift_detected = drift
        self.drift_count = int(drift)
        self.n_trades = n_trades
        self.n_wins = n_wins
        self.n_losses = n_losses
        self.ewm_wr = ewm_wr
        self.sharpe_online = sharpe_online
        self.max_losing_streak = max_losing_streak
        self.recalibrate_setups = recalibrate_setups or []
        self.per_setup = per_setup or {}


def _drifted_state():
    """État avec dérive déclenchée + assez de trades pour un SOFT recalib."""
    return FakeState(
        drift=True, n_trades=10, n_wins=3, n_losses=7,
        ewm_wr=0.30, max_losing_streak=7,
    )


def test_should_recalibrate_drift():
    st = _drifted_state()
    dec = should_recalibrate(st)
    assert isinstance(dec, RecalibDecision)
    # drift → au moins SOFT, la raison mentionne drift_detected
    assert dec.decision in ("SOFT", "MEDIUM", "HARD")
    assert "drift_detected" in dec.reason


def test_should_recalibrate_recommended_enough_data():
    # WR faible sur assez de trades → déclenche une recalibration
    st = FakeState(n_trades=15, n_wins=4, n_losses=11, ewm_wr=0.27)
    dec = should_recalibrate(st, min_losses=10)
    assert isinstance(dec, RecalibDecision)
    assert dec.decision in ("SOFT", "MEDIUM", "HARD")


def test_should_recalibrate_no_trigger():
    # état sain → HOLD, pas de drift
    st = FakeState(n_trades=10, n_wins=6, n_losses=4, ewm_wr=0.60)
    dec = should_recalibrate(st)
    assert isinstance(dec, RecalibDecision)
    assert dec.decision == "HOLD"
    assert "drift_detected" not in dec.reason


def test_should_recalibrate_recommended_not_enough():
    # peu de trades (n_losses < min_losses) → pas de recalib déclenchée
    st = FakeState(n_trades=5, n_wins=3, n_losses=2, ewm_wr=0.40)
    dec = should_recalibrate(st, min_losses=10)
    assert isinstance(dec, RecalibDecision)
    assert dec.decision == "HOLD"


def test_run_auto_recalibration_no_trigger_hold():
    st = FakeState(n_trades=10, n_wins=6, n_losses=4, ewm_wr=0.60)
    dec = run_auto_recalibration(st, db_path="data/v9_forces.db")
    assert dec.decision == "HOLD"


def test_run_auto_recalibration_error_hold():
    # drift déclenché mais DB invalide → R6 fail-open : pas de crash,
    # décision bornée et toujours un RecalibDecision JSON-sérialisable.
    st = _drifted_state()
    dec = run_auto_recalibration(st, db_path="/nonexistent/db.sqlite")
    assert isinstance(dec, RecalibDecision)
    assert dec.decision in ("SOFT", "MEDIUM", "HARD", "HOLD")
    # R9 : as_dict() reste sérialisable même en fail-open
    json.dumps(dec.as_dict())


def test_decision_serialization():
    dec = RecalibDecision(
        decision="MEDIUM", reason="wr_low=0.30 | drift_detected",
        wr_ewm=0.30, sharpe=-0.7, wr_ci_low=0.20, wr_ci_high=0.45,
        stage="MEDIUM", regime_hint="UNKNOWN", cooldown_active=False,
    )
    d = dec.as_dict()
    json.dumps(d)  # R9
    assert d["decision"] == "MEDIUM"
    assert d["wr_ewm"] == 0.30
    assert d["stage"] == "MEDIUM"


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_auto_recalibrator.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
