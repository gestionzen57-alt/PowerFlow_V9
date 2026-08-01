"""tests/test_v9_phase93.py — Phase 93 motion CEO 48H (post-Plan C).

Tests pour llm_self_improvement.
"""
import pytest


def test_self_assess_empty():
    from scripts.v9_llm_self_improvement import self_assess
    res = self_assess({})
    assert "issues" in res
    assert "score" in res


def test_self_assess_with_metrics():
    from scripts.v9_llm_self_improvement import self_assess
    res = self_assess({"wr": 0.85, "n_trades": 100, "dd": -50.0})
    assert res["score"] >= 0
    assert res["score"] <= 100


def test_self_assess_low_wr_detects_issue():
    from scripts.v9_llm_self_improvement import self_assess
    res = self_assess({"wr": 0.40, "n_trades": 50, "dd": -50.0})
    assert len(res["issues"]) >= 1


def test_self_assess_high_dd_detects_issue():
    from scripts.v9_llm_self_improvement import self_assess
    res = self_assess({"wr": 0.85, "n_trades": 100, "dd": -200.0})
    # DD > 100p = problematique
    issues_str = " ".join(res["issues"])
    assert "drawdown" in issues_str.lower() or "dd" in issues_str.lower()


def test_generate_recommendations_basic():
    from scripts.v9_llm_self_improvement import generate_recommendations
    recs = generate_recommendations([
        "WR is too low",
        "DD exceeds threshold",
    ])
    assert len(recs) == 2


def test_generate_recommendations_empty():
    from scripts.v9_llm_self_improvement import generate_recommendations
    recs = generate_recommendations([])
    assert recs == []


def test_apply_recommendation_no_op():
    from scripts.v9_llm_self_improvement import apply_recommendation
    # Recommandation inconnue = no-op safe
    ok = apply_recommendation("noop_action", {})
    assert ok is False  # not implemented = safe fail


def test_score_quality_perfect():
    """Score parfait = 100."""
    from scripts.v9_llm_self_improvement import compute_quality_score
    s = compute_quality_score({"wr": 1.0, "dd": 0, "n_trades": 100})
    assert s >= 95


def test_score_quality_terrible():
    from scripts.v9_llm_self_improvement import compute_quality_score
    s = compute_quality_score({"wr": 0.0, "dd": -1000, "n_trades": 0})
    assert s <= 30


def test_score_quality_bounded():
    from scripts.v9_llm_self_improvement import compute_quality_score
    s = compute_quality_score({"wr": 0.85, "dd": -50, "n_trades": 100})
    assert 0 <= s <= 100


def test_run_self_improvement_cycle():
    from scripts.v9_llm_self_improvement import run_self_improvement_cycle
    res = run_self_improvement_cycle({"wr": 0.85, "dd": -50, "n_trades": 100})
    assert "assessment" in res
    assert "recommendations" in res


def test_main_demo(capsys):
    from scripts.v9_llm_self_improvement import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LLM SELF IMPROVEMENT" in captured.out or "SELF IMPROVEMENT" in captured.out