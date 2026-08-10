"""
tests/test_v10_fatman_wave_predictor.py
Unit tests for v10_fatman_wave_predictor — H7 / Z11 (ZCode canonical API)
≥ 8 cases: compression, fail-open, neutral, edge cases

API (module ZCode conservé) :
  detect_pre_wave(sigma_history, *, window=10, ratio=0.60, min_history=20)
  → PreWaveAlert {pre_wave, direction, sigma_min, sigma_recent,
                  sigma_hist, compression_ratio, notes}
"""
import json

from core.v10.v10_fatman_wave_predictor import PreWaveAlert, detect_pre_wave

# ── COMPRESSION cases ────────────────────────────────────────────────────────

def test_compression_standard():
    """sigma récent nettement < historique → compression détectée."""
    history = [70.0, 68.0, 72.0, 65.0, 69.0, 66.0, 64.0, 61.0, 58.0,
               55.0, 52.0, 48.0, 42.0, 38.0, 34.0, 30.0, 27.0, 24.0,
               21.0, 18.0, 16.0, 14.0]
    result = detect_pre_wave(history)
    assert result.pre_wave is True
    assert result.compression_ratio <= 0.60


def test_compression_window_ratio():
    """Compression détectée avec window/ratio personnalisés (R8)."""
    # 8 valeurs : les 4 dernières (52,50,10,8) très en dessous des 4 premières
    history = [60.0, 58.0, 56.0, 54.0, 52.0, 50.0, 10.0, 8.0]
    result = detect_pre_wave(history, window=4, ratio=0.70, min_history=8)
    assert result.pre_wave is True
    assert result.compression_ratio <= 0.70


# ── FAIL-OPEN (R6) cases ──────────────────────────────────────────────────────

def test_fail_open_short_history():
    """Historique < min_history → pas de pré-vague (R6 fail-open)."""
    history = [50.0, 48.0, 46.0]
    result = detect_pre_wave(history)  # min_history=20 par défaut
    assert result.pre_wave is False
    assert any("historique trop court" in n for n in result.notes)


def test_fail_open_empty_history():
    """Liste vide → fail-open, jamais d'exception."""
    result = detect_pre_wave([])
    assert result.pre_wave is False
    assert any("historique trop court" in n for n in result.notes)


def test_fail_open_min_history_personnalise():
    """min_history personnalisé bas → compression détectée plus tôt."""
    history = [50.0, 40.0, 30.0, 10.0, 8.0, 6.0]
    result = detect_pre_wave(history, min_history=4, window=3)
    assert result.pre_wave is True
    assert result.compression_ratio <= 0.60


# ── NEUTRAL cases ─────────────────────────────────────────────────────────────

def test_neutral_sigma_stable():
    """Sigma stable (ratio ~1.0) → pas de pré-vague (NEUTRAL)."""
    history = [40.0] * 22
    result = detect_pre_wave(history)
    assert result.pre_wave is False
    assert result.compression_ratio > 0.60


def test_neutral_sigma_increasing():
    """Sigma qui augmente → pas de compression (NEUTRAL)."""
    history = [10.0, 12.0, 15.0, 18.0, 22.0, 26.0, 30.0, 34.0,
               38.0, 42.0, 46.0, 50.0, 54.0, 58.0, 62.0, 66.0,
               70.0, 74.0, 78.0, 82.0, 86.0, 90.0]
    result = detect_pre_wave(history)
    assert result.pre_wave is False


# ── EDGE / STRUCTURE cases ────────────────────────────────────────────────────

def test_pre_wave_alert_structure():
    """PreWaveAlert expose les champs ZCode (direction, compression_ratio)."""
    history = [50.0, 40.0, 30.0, 10.0, 8.0, 6.0]
    result = detect_pre_wave(history, min_history=4)
    assert isinstance(result, PreWaveAlert)
    assert hasattr(result, "direction")
    assert hasattr(result, "sigma_recent")
    assert hasattr(result, "sigma_hist")
    assert hasattr(result, "compression_ratio")
    assert hasattr(result, "as_dict")
    d = result.as_dict()
    assert "pre_wave" in d and "compression_ratio" in d


def test_as_dict_serializable():
    """as_dict() → dict JSON-sérialisable (R9 audit)."""
    history = [50.0, 40.0, 30.0, 10.0, 8.0, 6.0]
    result = detect_pre_wave(history, min_history=4)
    json.dumps(result.as_dict())  # pas d'exception
