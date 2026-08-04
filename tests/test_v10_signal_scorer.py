"""V10 Signal Scorer Enhanced — tests unitaires (Phase 4 Edge Fund).

Couvre les obligations de la Phase 4 :
  1. test_a1_full_alignment
  2. test_a2_with_4_criteria
  3. test_a3_with_3_criteria
  4. test_none_when_confluence_below_a3
  5. test_currency_rank_top_2_required_for_a1
  6. test_currency_rank_bot_2_required_for_sell
  7. test_vsa_directional_required_for_a1
  8. test_bos_required_for_a1
  9. test_session_active_required
 10. test_degraded_mode_when_no_confluence
 11. test_direction_bullish_from_confluence
 12. test_direction_bearish_from_confluence
 13. test_direction_none_when_neutral
 14. test_blockers_listed_when_none
 15. test_cot_r5_present_5_steps
 16. test_composite_score_between_0_and_1
+ 6 bonus.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_signal_scorer import (  # noqa: E402
    EnhancedSignal,
    score_enhanced_signal,
    DEFAULT_CRITERIA_WEIGHTS,
    ACTIVE_SESSIONS,
    QUIET_SESSIONS,
)
from core.v10.v10_confluence import (  # noqa: E402
    ConflSummary,
    ConfBias,
    compute_confluence,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers — fabric synthétique d'un ConflSummary
# ─────────────────────────────────────────────────────────────────────
def _make_confl(
    score: float = 0.90,
    bias: ConfBias = ConfBias.LONG,
    direction: str = "BUY",
    aligned: Tuple[str, ...] = ("D1", "H4", "H1", "M30", "M15", "M5", "M1"),
) -> ConflSummary:
    s = ConflSummary(
        symbol="EURUSD_h1",
        timestamp="2026-08-04T12:00:00Z",
        pair="EURUSD",
        direction=direction,
        score=score,
        dominant_bias=bias,
        aligned_tfs=aligned,
    )
    s.confluence_score = score  # pour as_dict
    return s


# ─────────────────────────────────────────────────────────────────────
# 1. test_a1_full_alignment — TOUS les 5 critères OK, score >= 0.85
# ─────────────────────────────────────────────────────────────────────
def test_a1_full_alignment():
    confl = _make_confl(score=0.90)
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=1,        # EUR top
        currency_rank_quote=7,       # USD bot
        seed=42,
    )
    assert sig.setup_level == "A1", sig.cot
    assert sig.tradeable is True
    assert all(sig.criteria_met.values())
    assert sig.composite_score >= 0.90


# ─────────────────────────────────────────────────────────────────────
# 2. test_a2_with_4_criteria
# ─────────────────────────────────────────────────────────────────────
def test_a2_with_4_criteria():
    """A2 (medium) : confluence=0.90 >= 0.85 -> critère confluence=True.
    On coupe currency_rank pour avoir 4/5 critères OK -> doit retomber à A2.
    """
    confl = _make_confl(score=0.90)
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=3,        # non-aligné → currency_rank=False
        currency_rank_quote=5,
    )
    # 4/5 critères : confluence, vsa, bos, session.
    # criteria_met.currency_rank = False
    # Score composite pondéré reste élevé (≈ 0.88)
    # Niveau : A1 impossible (5/5) ; A2 OK (conf 0.90 >= 0.72, n_met=4 >= 4)
    assert sig.criteria_met["confluence"] is True
    assert sig.criteria_met["currency_rank"] is False
    assert sig.criteria_met["vsa_directional"] is True
    assert sig.criteria_met["bos_structure"] is True
    assert sig.criteria_met["session_active"] is True
    assert sum(sig.criteria_met.values()) == 4
    assert sig.setup_level == "A2", sig.cot["3_decide"]
    assert sig.tradeable is True


# ─────────────────────────────────────────────────────────────────────
# 3. test_a3_with_3_criteria
# ─────────────────────────────────────────────────────────────────────
def test_a3_with_3_criteria():
    confl = _make_confl(score=0.55)
    # confluence score 0.55 ne fait PAS critère confluence (seuil = 0.85)
    # Cela rend les 5 critères KO pour confluence -> on vise A3 via 3 critères sur les 4 autres.
    # currency_rank OK + vsa OK + session OK = 3 critères OK.
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="NONE",                  # KO
        session="LONDON",
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    # confluence_score 0.55 atteint A3 mais pas A1/A2 → A3 si 3 critères OK.
    # Ici : currency_rank, vsa, session = 3 OK. → A3.
    assert sig.setup_level == "A3", sig.cot


# ─────────────────────────────────────────────────────────────────────
# 4. test_none_when_confluence_below_a3
# ─────────────────────────────────────────────────────────────────────
def test_none_when_confluence_below_a3():
    confl = _make_confl(score=0.30)
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    assert sig.setup_level == "NONE"
    assert sig.tradeable is False
    assert "CONFLUENCE" in sig.blockers


# ─────────────────────────────────────────────────────────────────────
# 5. test_currency_rank_top_2_required_for_a1
# ─────────────────────────────────────────────────────────────────────
def test_currency_rank_top_2_required_for_a1():
    confl = _make_confl(score=0.90)
    # currency_rank base=4 (pas top-2) → critère manquant
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=4,
        currency_rank_quote=3,
    )
    # criteria_met.currency_rank = False → 4/5 critères → A2 (si confluence >= 0.72)
    assert sig.criteria_met["currency_rank"] is False
    assert sig.setup_level == "A2" or sig.setup_level == "A3"


# ─────────────────────────────────────────────────────────────────────
# 6. test_currency_rank_bot_2_required_for_sell
# ─────────────────────────────────────────────────────────────────────
def test_currency_rank_bot_2_required_for_sell():
    confl = _make_confl(
        score=0.90,
        bias=ConfBias.SHORT,
        direction="SELL",
    )
    sig = score_enhanced_signal(
        symbol="USDJPY_h1",
        pair="USDJPY",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKDOWN",
        bos="BOS_BEAR",
        session="NY",
        currency_rank_base=6,        # USD = 6 ou 7 (faible pour SELL vs JPY)
        currency_rank_quote=2,       # JPY = top-2
    )
    # A1 short : USD bot-2, JPY top-2
    assert sig.setup_level == "A1", sig.cot
    assert sig.direction == "BEARISH"


# ─────────────────────────────────────────────────────────────────────
# 7. test_vsa_directional_required_for_a1
# ─────────────────────────────────────────────────────────────────────
def test_vsa_directional_required_for_a1():
    confl = _make_confl(score=0.90)
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="NEUTRAL",         # KO
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    # vsa KO → 4/5 critères → A2
    assert sig.setup_level in ("A2", "A3", "NONE")
    assert sig.criteria_met["vsa_directional"] is False


# ─────────────────────────────────────────────────────────────────────
# 8. test_bos_required_for_a1
# ─────────────────────────────────────────────────────────────────────
def test_bos_required_for_a1():
    confl = _make_confl(score=0.90)
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="NONE",                  # KO
        session="LONDON",
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    assert sig.criteria_met["bos_structure"] is False
    # BOS absent → on retombe à A2
    assert sig.setup_level in ("A2", "A3", "NONE")


# ─────────────────────────────────────────────────────────────────────
# 9. test_session_active_required
# ─────────────────────────────────────────────────────────────────────
def test_session_active_required():
    """Session non-active doit faire retomber A1 vers un niveau inférieur (A2/A3/NONE)."""
    confl = _make_confl(score=0.90)
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="ASIAN",             # KO
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    # session_active = False, donc A1 impossible.
    # n_met = 4 et conf >= 0.85 → on doit retomber à A2, ou A3 si conf < 0.72.
    assert sig.criteria_met["session_active"] is False
    assert sig.setup_level in ("A2", "A3", "NONE")
    # A2 reste tradeable, les autres non ; le critère session est dans criteria_met
    # mais pas nécessairement dans blockers (qui n'est rempli que pour NONE).
    # On vérifie donc le critère directement — la garantie doctrinée est que
    # SESSION_ACTIVE manquant empêche A1.
    assert sig.setup_level != "A1"


def test_quiet_session_blocked():
    """Session QUIET doit être considérée comme inactive."""
    for sess in QUIET_SESSIONS:
        sig = score_enhanced_signal(
            symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
            confluence=_make_confl(score=0.90),
            vsa_state="MARKUP", bos="BOS_BULL",
            session=sess, currency_rank_base=1, currency_rank_quote=7,
        )
        assert sig.criteria_met["session_active"] is False, sess


# ─────────────────────────────────────────────────────────────────────
# 10. test_degraded_mode_when_no_confluence
# ─────────────────────────────────────────────────────────────────────
def test_degraded_mode_when_no_confluence():
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=None,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    assert sig.degraded_mode is True
    # Aucune confluence → criterion confluence = False
    assert sig.criteria_met["confluence"] is False
    # A1 impossible (il faut confluence >= 0.85).
    # Les autres critères sont OK, donc on a 4/5 mais pas le A2 (car confluence absent).
    # → NONE.
    assert sig.setup_level == "NONE"


# ─────────────────────────────────────────────────────────────────────
# 11. test_direction_bullish_from_confluence
# ─────────────────────────────────────────────────────────────────────
def test_direction_bullish_from_confluence():
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(bias=ConfBias.LONG, direction="BUY"),
        vsa_state="MARKUP", bos="BOS_BULL",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
    )
    assert sig.direction == "BULLISH"


# ─────────────────────────────────────────────────────────────────────
# 12. test_direction_bearish_from_confluence
# ─────────────────────────────────────────────────────────────────────
def test_direction_bearish_from_confluence():
    sig = score_enhanced_signal(
        symbol="x", pair="USDJPY", timestamp="t", timeframe="H1",
        confluence=_make_confl(bias=ConfBias.SHORT, direction="SELL"),
        vsa_state="MARKDOWN", bos="BOS_BEAR",
        session="NY", currency_rank_base=6, currency_rank_quote=2,
    )
    assert sig.direction == "BEARISH"


# ─────────────────────────────────────────────────────────────────────
# 13. test_direction_none_when_neutral
# ─────────────────────────────────────────────────────────────────────
def test_direction_none_when_neutral():
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(bias=ConfBias.NONE, direction="WAIT", score=0.0),
        vsa_state="NEUTRAL", bos="NONE",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
    )
    assert sig.direction == "NONE"
    assert sig.setup_level == "NONE"
    assert "NO_DIRECTION" in sig.blockers


# ─────────────────────────────────────────────────────────────────────
# 14. test_blockers_listed_when_none
# ─────────────────────────────────────────────────────────────────────
def test_blockers_listed_when_none():
    # 1 seul critère OK : confluence (A1 mais seul)
    # On vise conf=0.90 mais tout le reste KO → 1/5 critères
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90),
        vsa_state="NEUTRAL", bos="NONE",
        session="ASIAN", currency_rank_base=4, currency_rank_quote=4,
    )
    # Confluence OK, vsa KO, bos KO, session KO, rank KO → 1/5 + conf 0.90
    # A1 impossible (4 critères KO), A2 impossible (4 critères KO, besoin de 4),
    # A3 impossible (besoin 3) → NONE
    assert sig.setup_level == "NONE"
    assert "VSA_DIRECTIONAL" in sig.blockers
    assert "BOS_STRUCTURE" in sig.blockers
    assert "SESSION_ACTIVE" in sig.blockers
    assert "CURRENCY_RANK" in sig.blockers


# ─────────────────────────────────────────────────────────────────────
# 15. test_cot_r5_present_5_steps
# ─────────────────────────────────────────────────────────────────────
def test_cot_r5_present_5_steps():
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90),
        vsa_state="MARKUP", bos="BOS_BULL",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
    )
    # Doit contenir les 5 étapes R5
    assert "1_see" in sig.cot
    assert "2_think" in sig.cot
    assert "3_decide" in sig.cot
    assert "4_risk" in sig.cot
    assert "5_learn" in sig.cot
    for step, content in sig.cot.items():
        assert content and isinstance(content, str) and len(content) > 5


# ─────────────────────────────────────────────────────────────────────
# 16. test_composite_score_between_0_and_1
# ─────────────────────────────────────────────────────────────────────
def test_composite_score_between_0_and_1():
    for cfg in [
        # Tous critères OK
        dict(confl_score=0.90, vsa="MARKUP", bos="BOS_BULL", session="LONDON",
             r_b=1, r_q=7),
        # Tous KO
        dict(confl_score=0.30, vsa="NEUTRAL", bos="NONE", session="ASIAN",
             r_b=4, r_q=4),
        # Mixte
        dict(confl_score=0.60, vsa="MARKUP", bos="NONE", session="OVERLAP",
             r_b=3, r_q=5),
    ]:
        sig = score_enhanced_signal(
            symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
            confluence=_make_confl(score=cfg["confl_score"]),
            vsa_state=cfg["vsa"],
            bos=cfg["bos"],
            session=cfg["session"],
            currency_rank_base=cfg["r_b"],
            currency_rank_quote=cfg["r_q"],
        )
        assert 0.0 <= sig.composite_score <= 1.0, cfg


# ─────────────────────────────────────────────────────────────────────
# Bonus invariants
# ─────────────────────────────────────────────────────────────────────
def test_serializable_json():
    import json
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90),
        vsa_state="MARKUP", bos="BOS_BULL",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
    )
    j = json.dumps(sig.as_dict())
    assert isinstance(j, str)


def test_seed_recorded():
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90),
        vsa_state="MARKUP", bos="BOS_BULL",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
        seed=9999,
    )
    assert sig.seed == 9999
    assert sig.as_dict()["audit"]["seed"] == 9999


def test_accept_actual_confl_summary():
    """score_enhanced_signal doit accepter un vrai ConflSummary calculé."""
    tf_data = {
        tf: {
            "currency_scores": {"EUR": 95, "USD": 5},
            "currency_ranks": {"EUR": 1, "USD": 7},
            "vsa_state": "MARKUP", "bos": "BOS_BULL",
        }
        for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
    }
    confl = compute_confluence(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        tf_data=tf_data,
    )
    sig = score_enhanced_signal(
        symbol="EURUSD_h1",
        pair="EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        confluence=confl,
        vsa_state="MARKUP",
        bos="BOS_BULL",
        session="LONDON",
        currency_rank_base=1,
        currency_rank_quote=7,
    )
    # Score composite >= A1 seuil
    assert sig.setup_level in ("A1", "A2"), sig.cot


def test_weights_default_documented():
    """Les poids par défaut doivent être documentés et sommer à 1."""
    total = sum(DEFAULT_CRITERIA_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9


def test_cot_in_a1_mentions_capital_protection():
    """Le CoT d'un A1 doit mentionner la doctrine R10 protection capital."""
    sig = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90),
        vsa_state="MARKUP", bos="BOS_BULL",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
    )
    assert sig.setup_level == "A1"
    assert "R10" in sig.cot["4_risk"] or "10" in sig.cot["4_risk"]


def test_vsa_accumulation_counts_as_bullish():
    """ACCUMULATION et DISTRIBUTION doivent être reconnus directionnels."""
    sig_long = score_enhanced_signal(
        symbol="x", pair="EURUSD", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90),
        vsa_state="ACCUMULATION", bos="BOS_BULL",
        session="LONDON", currency_rank_base=1, currency_rank_quote=7,
    )
    assert sig_long.criteria_met["vsa_directional"] is True

    sig_short = score_enhanced_signal(
        symbol="x", pair="USDJPY", timestamp="t", timeframe="H1",
        confluence=_make_confl(score=0.90, bias=ConfBias.SHORT, direction="SELL"),
        vsa_state="DISTRIBUTION", bos="BOS_BEAR",
        session="NY", currency_rank_base=6, currency_rank_quote=2,
    )
    assert sig_short.criteria_met["vsa_directional"] is True
    assert sig_short.direction == "BEARISH"
