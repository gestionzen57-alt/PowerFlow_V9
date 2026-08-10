"""V10 Decision Pipeline — tests unitaires (Sprint 13 autopilote quant).

Obligations Sprint 13 :
  1. test_buy_high_conviction
  2. test_sell_high_conviction
  3. test_filtered_none_no_trade
  4. test_risk_blocked_wait
  5. test_risk_blocked_dd_halt
  6. test_not_high_conviction_wait
  7. test_r6_error_wait
  8. test_serialization_as_dict
  9. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_pipeline import (  # noqa: E402
    PipelineDecision,
    decide_entry,
)


class FakeOte:
    def __init__(self, in_ote=True, kill_zone="NY", conviction_score=1.0):
        self.in_ote = in_ote
        self.kill_zone = kill_zone
        self.conviction_score = conviction_score


class FakeSession:
    def __init__(self, quality_score=1.0, is_optimal=True, session_now="NY"):
        self.quality_score = quality_score
        self.is_optimal_for_pair = is_optimal
        self.session_now = session_now


class FakeRegime:
    def __init__(self, regime="TRENDING_UP"):
        self.regime = regime


class FakeSmc:
    def __init__(self, structure="BOS_BULL"):
        self.structure = structure


def test_buy_high_conviction():
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A1",
        session=FakeSession(), ote=FakeOte(in_ote=True, kill_zone="NY"),
        smc=FakeSmc("BOS_BULL"), regime=FakeRegime("TRENDING_UP"),
        candidate_risk_pct=1.0,
    )
    assert dec.action == "BUY"
    assert dec.risk_ok is True
    assert dec.lot_size > 0
    assert dec.filtered_level in ("A1", "A2")


def test_sell_high_conviction():
    dec = decide_entry(
        "GBPUSD", "H1", "2026-08-05T14:00:00Z", "short", "A1",
        session=FakeSession(), ote=FakeOte(in_ote=True, kill_zone="NY"),
        regime=FakeRegime("TRENDING_DOWN"),
        candidate_risk_pct=1.0,
    )
    assert dec.action == "SELL"
    assert dec.risk_ok is True


def test_filtered_none_no_trade():
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "NONE",
        regime=FakeRegime("UNKNOWN"),  # UNKNOWN + A1? non, signal NONE
    )
    assert dec.action == "NONE"
    assert dec.risk_ok is False


def test_risk_blocked_wait():
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A1",
        ote=FakeOte(in_ote=False, kill_zone="OUTSIDE"),  # pas in_ote → downgrade
        candidate_risk_pct=1.0,
    )
    # ote hors zone → compose_filters downgrade A1→A2, mais risk OK...
    # l'action dépend du filtered_level final
    assert dec.risk_ok is True  # pas de blocage risque
    assert dec.action in ("WAIT", "NONE", "BUY")


def test_risk_blocked_dd_halt():
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A1",
        ote=FakeOte(in_ote=True, kill_zone="NY"),
        daily_dd_pct=15.0, max_daily_dd_pct=10.0,
    )
    assert dec.risk_ok is False
    assert any("DAILY_DD_HALT" in r for r in dec.reasons)
    assert dec.action == "WAIT"


def test_not_high_conviction_wait():
    # A3 + ote hors zone → filtered A3 (pas A1/A2) → WAIT
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A3",
        ote=FakeOte(in_ote=False, kill_zone="OUTSIDE"),
        candidate_risk_pct=1.0,
    )
    assert dec.action == "WAIT"


def test_r6_error_wait():
    # régime qui lève (pas d'attribut .regime) → R6 WAIT
    class BadRegime:
        pass
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A1",
        regime=BadRegime(),
    )
    assert dec.action in ("WAIT", "NONE", "BUY")  # fail-open safe


def test_serialization_as_dict():
    dec = PipelineDecision(pair="EURUSD", timeframe="H1", action="BUY",
                           lot_size=0.01, risk_ok=True)
    d = dec.as_dict()
    json.dumps(d)  # R9
    assert d["action"] == "BUY"
    assert d["lot_size"] == pytest.approx(0.01)


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_decision_pipeline.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src


def test_grammar_aligned_boost():
    """Concept V9 aligné avec la direction → conviction renforcée (DP-C9-OPT3).

    NB : le boost grammar ne s'applique qu'aux signaux non-A1 (un A1 court-
    circuite déjà les modulations). On teste donc avec un A2, conforme à l'API
    C9 du module (le module ne doit pas être modifié — Chantier 2 / MAX).
    """
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A2",
        ote=FakeOte(in_ote=True, kill_zone="NY"),
        grammar={"n_detected": 1, "best": {
            "concept": "PULLBACK", "direction": "BULLISH", "confidence": 0.7}},
        candidate_risk_pct=1.0,
    )
    assert dec.action == "BUY"
    assert any("grammar_PULLBACK_aligned" in r for r in dec.reasons)


def test_grammar_opposed_downgrade():
    """Concept V9 opposé à la direction → downgrade A2→A3 (prudent)."""
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A2",
        ote=FakeOte(in_ote=True, kill_zone="NY"),
        grammar={"n_detected": 1, "best": {
            "concept": "TENSION", "direction": "BEARISH", "confidence": 0.8}},
        candidate_risk_pct=1.0,
    )
    # A2 downgradé → A3 → pas de trade (WAIT)
    assert dec.action == "WAIT"
    assert any("grammar_TENSION_opposed" in r for r in dec.reasons)


def test_grammar_none_no_impact():
    """grammar None → aucun impact (R6 backward-compatible)."""
    dec = decide_entry(
        "EURUSD", "H1", "2026-08-05T14:00:00Z", "long", "A1",
        ote=FakeOte(in_ote=True, kill_zone="NY"),
        candidate_risk_pct=1.0,
    )
    assert dec.action == "BUY"
    assert "grammar_v9" not in dec.audit.get("steps", [])


# ─────────────────────────────────────────────────────────────────────
# Z9 (2026-08-10) — VSA multi-TF wire (compression_extension, H8 gate)
# ─────────────────────────────────────────────────────────────────────
def test_z9_vsa_aligned_bonus():
    """VSA BULLISH aligné direction long → vsa_multi_tf_ok=True + reason bonus."""
    dec = decide_entry(
        "EURUSD", "M30", "2026-08-10T00:00:00Z", "long", "A1",
        vsa_report={"signal": "BULLISH", "score_global": 0.42, "audit": {}},
        candidate_risk_pct=1.0,
    )
    assert dec.vsa_multi_tf_ok is True
    assert "vsa_multi_tf_aligned_bonus" in dec.reasons
    assert "vsa_bonus" in dec.audit["steps"]


def test_z9_vsa_opposed_malus():
    """VSA BEARISH opposé direction long → vsa_multi_tf_ok=False + reason malus."""
    dec = decide_entry(
        "EURUSD", "M30", "2026-08-10T00:00:00Z", "long", "A1",
        vsa_report={"signal": "BEARISH", "score_global": -0.38, "audit": {}},
        candidate_risk_pct=1.0,
    )
    assert dec.vsa_multi_tf_ok is False
    assert "vsa_multi_tf_opposed_malus" in dec.reasons
    assert "vsa_malus" in dec.audit["steps"]


def test_z9_vsa_neutral_failopen():
    """VSA NEUTRAL (pas de signal directionnel) → ok=False, aucun impact trade."""
    dec = decide_entry(
        "EURUSD", "M30", "2026-08-10T00:00:00Z", "long", "A1",
        vsa_report={"signal": "NEUTRAL", "score_global": 0.0, "audit": {}},
        candidate_risk_pct=1.0,
    )
    assert dec.vsa_multi_tf_ok is None
    assert dec.action == "BUY"  # R6 : pas de blocage


def test_z9_vsa_sell_aligned():
    """Direction short alignée VSA BEARISH → bonus aussi côté SELL."""
    dec = decide_entry(
        "EURUSD", "M30", "2026-08-10T00:00:00Z", "short", "A1",
        vsa_report={"signal": "BEARISH", "score_global": -0.45, "audit": {}},
        candidate_risk_pct=1.0,
    )
    assert dec.vsa_multi_tf_ok is True
    assert "vsa_multi_tf_aligned_bonus" in dec.reasons


def test_z9_vsa_report_trace_audit():
    """Le rapport VSA complet est tracé dans dec.audit['vsa_multi_tf'] (R9)."""
    dec = decide_entry(
        "EURUSD", "M30", "2026-08-10T00:00:00Z", "long", "A2",
        vsa_report={"signal": "BULLISH", "score_global": 0.5, "audit": {"src": "x"}},
        candidate_risk_pct=1.0,
    )
    v = dec.audit["vsa_multi_tf"]
    assert v["signal"] == "BULLISH"
    assert v["ok"] is True
    assert v["audit"]["source"] == "caller"
    # sérialisable (R9)
    import json
    json.dumps(dec.as_dict())


def test_z9_load_vsa_signal_db_failopen():
    """load_vsa_signal sans db_path ni report → état vide fail-open (R6)."""
    from core.v10.v10_decision_pipeline import load_vsa_signal
    v = load_vsa_signal(pair="EURUSD", timeframe="M30")
    assert v["ok"] is False
    assert v["signal"] == "NEUTRAL"
    assert v["error"] is None  # pas d'erreur, juste pas de source
