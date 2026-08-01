"""tests/test_v9_phase78.py — Phase 78 motion CEO 48H (P3.1 audit Perplexity).

Tests pour ml_l2_calibrator.
"""
import pytest


def test_feature_names_count():
    from scripts.v9_ml_l2_calibrator import FEATURE_NAMES
    assert len(FEATURE_NAMES) == 10


def test_encode_features_default():
    from scripts.v9_ml_l2_calibrator import encode_features
    vec = encode_features({})
    assert len(vec) == 10
    assert vec[0] == 12.0  # hour_utc default


def test_encode_features_custom():
    from scripts.v9_ml_l2_calibrator import encode_features
    vec = encode_features({
        "hour_utc": 8, "symbol_encoded": 2, "direction_encoded": 1,
    })
    assert vec[0] == 8.0
    assert vec[1] == 2.0
    assert vec[2] == 1.0


def test_sigmoid_zero():
    from scripts.v9_ml_l2_calibrator import sigmoid
    assert sigmoid(0) == 0.5


def test_sigmoid_large():
    from scripts.v9_ml_l2_calibrator import sigmoid
    assert sigmoid(1000) == 1.0
    assert sigmoid(-1000) == 0.0


def test_heuristic_score_mega_edge():
    """L1 GBPUSD 11-13h haussiere doit avoir score eleve."""
    from scripts.v9_ml_l2_calibrator import heuristic_score
    feat = {
        "symbol_encoded": 0, "direction_encoded": 1,
        "hour_utc": 12, "n_principes": 2, "n_stars": 2,
        "regime_encoded": 1, "session_encoded": 1,
    }
    score = heuristic_score(feat)
    assert score >= 95.0  # base 50 + L1 25 + L4 30 + 2c 10 + regime 10 + session 5


def test_heuristic_score_bad_trade():
    """Trade mediocres doit avoir score bas."""
    from scripts.v9_ml_l2_calibrator import heuristic_score
    feat = {
        "symbol_encoded": 5, "direction_encoded": 0,
        "hour_utc": 3, "n_principes": 8, "n_stars": 0,
        "regime_encoded": 0, "vol_atr_pips": 150.0,
        "session_encoded": 0,
    }
    score = heuristic_score(feat)
    assert score < 70.0


def test_heuristic_score_bounded():
    """Score doit etre borne [0, 100]."""
    from scripts.v9_ml_l2_calibrator import heuristic_score
    # Beaucoup de boosts : score max 100
    feat = {
        "symbol_encoded": 0, "direction_encoded": 1,
        "hour_utc": 12, "n_principes": 1, "n_stars": 5,
        "regime_encoded": 1, "behavior_encoded": 2,
        "vol_atr_pips": 5.0, "session_encoded": 1,
    }
    score = heuristic_score(feat)
    assert 0.0 <= score <= 100.0


def test_calibrate_confidence_basic():
    from scripts.v9_ml_l2_calibrator import calibrate_confidence
    feat = {
        "symbol_encoded": 0, "direction_encoded": 1,
        "hour_utc": 12, "n_principes": 2, "n_stars": 1,
    }
    res = calibrate_confidence(feat)
    assert "raw_score" in res
    assert "calibrated_proba" in res
    assert "calibrated_conf" in res
    assert "method" in res


def test_calibrate_confidence_proba_bounded():
    from scripts.v9_ml_l2_calibrator import calibrate_confidence
    res = calibrate_confidence({})
    assert 0.0 <= res["calibrated_proba"] <= 1.0


def test_explain_mega_edge():
    from scripts.v9_ml_l2_calibrator import explain
    feat = {
        "symbol_encoded": 0, "direction_encoded": 1, "hour_utc": 12,
        "n_principes": 2, "n_stars": 2, "regime_encoded": 1,
        "session_encoded": 1, "behavior_encoded": 2,
    }
    levs = explain(feat)
    assert "L1_mega_edge_gbpusd_11_13" in levs
    assert "L4_stars(2)" in levs
    assert "L8_regime_bull" in levs
    assert "L9_session_london_ny" in levs


def test_explain_empty():
    from scripts.v9_ml_l2_calibrator import explain
    levs = explain({})
    # Avec defaults, n_stars=0, autres conditions False → liste vide
    # mais coalition peut etre ajoutee si encoded=2. Test strict : aucun mega
    mega_terms = [l for l in levs if l.startswith(("L1_", "L4_", "L8_", "L9_", "L11_"))]
    assert mega_terms == []


def test_lightgbm_status():
    """Verifie que LIGHTGBM_AVAILABLE est un bool."""
    from scripts.v9_ml_l2_calibrator import LIGHTGBM_AVAILABLE
    assert isinstance(LIGHTGBM_AVAILABLE, bool)


def test_main_demo(capsys):
    from scripts.v9_ml_l2_calibrator import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ML L2 CONFIDENCE CALIBRATOR" in captured.out
    assert "LightGBM available" in captured.out