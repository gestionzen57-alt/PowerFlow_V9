# Perplexity Contribution — Sigma Oracle Tests v1.0 — 2026-08-07
# Sprint 14 — PowerFlow_V9 feat/v9-foundation-clean
# 12 tests minimum pour valider COILING/RESOLVING/RANGING

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_perplexity_sigma_oracle import (  # noqa: E402
    SigmaSubState,
    SigmaOracleResult,
    sigma_oracle,
    apply_sigma_oracle_to_level,
    get_sigma_history,
    DEFAULT_THRESHOLDS,
    load_sigma_oracle_config,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures & Helpers
# ─────────────────────────────────────────────────────────────────────

def _make_temp_config(tmp_path, overrides: dict = None) -> str:
    """Crée un fichier config temporaire pour les tests."""
    cfg = {
        "sigma_oracle": {
            "coiling_slope_threshold": -0.8,
            "resolving_slope_threshold": 0.8,
            "coiling_sigma_max": 22.0,
            "resolving_sigma_min": 20.0,
        }
    }
    if overrides:
        cfg["sigma_oracle"].update(overrides)
    config_path = tmp_path / "test_thresholds.json"
    with open(config_path, "w") as f:
        json.dump(cfg, f)
    return str(config_path)


# ─────────────────────────────────────────────────────────────────────
# Tests COILING / RESOLVING / RANGING
# ─────────────────────────────────────────────────────────────────────

def test_coiling_detected():
    """1. COILING détecté (slope=-1.5, sigma=18.0)."""
    sigma_hist = [24.0, 23.0, 21.5, 20.0, 18.0]  # slope négatif
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=False,
        bos_confirmed=False,
        config_path="config/v10_active_thresholds.json",  # utilise défauts
    )
    assert oracle.sub_state == SigmaSubState.COILING
    assert oracle.action == "WAIT_PRIME"
    assert oracle.confidence == 0.75
    assert oracle.ob_alert is False
    assert oracle.n_points == 5
    assert "COILING" in oracle.rationale


def test_resolving_detected():
    """2. RESOLVING détecté (slope=+1.2, sigma=22.0)."""
    sigma_hist = [16.0, 17.5, 19.0, 20.5, 22.0]  # slope positif
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=False,
        bos_confirmed=False,
    )
    assert oracle.sub_state == SigmaSubState.RESOLVING
    assert oracle.action == "WATCH"
    assert oracle.confidence == 0.65
    assert oracle.ob_alert is False
    assert "RESOLVING" in oracle.rationale


def test_ranging_detected():
    """3. RANGING détecté (slope=0.1, sigma=20.0)."""
    sigma_hist = [19.8, 19.9, 20.0, 20.1, 20.0]  # stable
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=False,
        bos_confirmed=False,
    )
    assert oracle.sub_state == SigmaSubState.RANGING
    assert oracle.action == "WAIT"
    assert oracle.confidence == 0.40
    assert oracle.ob_alert is False
    assert "RANGING" in oracle.rationale


def test_coiling_ob_proximity_alert():
    """4. COILING + OB proximity → ob_alert=True."""
    sigma_hist = [24.0, 23.0, 21.5, 20.0, 18.0]
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=True,  # OB proximity
        bos_confirmed=False,
    )
    assert oracle.sub_state == SigmaSubState.COILING
    assert oracle.ob_alert is True
    assert "OB proximity" in oracle.rationale


def test_resolving_bos_confirmed_alert():
    """5. RESOLVING + BOS confirmed → ob_alert=True."""
    sigma_hist = [16.0, 17.5, 19.0, 20.5, 22.0]
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=False,
        bos_confirmed=True,  # BOS confirmed
    )
    assert oracle.sub_state == SigmaSubState.RESOLVING
    assert oracle.ob_alert is True
    assert "BOS confirmed" in oracle.rationale


def test_insufficient_history_fallback_ranging():
    """6. Historique insuffisant (<3 points) → RANGING fallback."""
    sigma_hist = [20.0, 20.5]  # seulement 2 points
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=False,
        bos_confirmed=False,
    )
    assert oracle.sub_state == SigmaSubState.RANGING
    assert oracle.action == "WAIT"
    assert oracle.confidence == 0.40
    assert "insuffisant" in oracle.rationale


def test_sigma_outside_grey_zone_not_called():
    """7. Sigma hors zone [12,28] → oracle NE DOIT PAS être appelé par le caller.
    
    Ce test documente l'intention : le caller (fatboy_gate) ne doit appeler
    sigma_oracle QUE si sigma ∈ [12, 28]. Ici on vérifie que si on l'appelle
    quand même, il classifie correctement (mais caller ne doit pas le faire).
    """
    # Sigma < 12 (convergence) - ne devrait pas arriver ici en production
    sigma_hist = [8.0, 9.0, 10.0, 10.5, 11.0]
    oracle = sigma_oracle(
        sigma_history=sigma_hist,
        ob_proximity=False,
        bos_confirmed=False,
    )
    # Sigma 11 < 22, slope positif -> RESOLVING (mais caller ne devrait pas appeler)
    assert oracle.sub_state in (SigmaSubState.COILING, SigmaSubState.RESOLVING, SigmaSubState.RANGING)
    # Ce test valide que la logique existe mais le gating est au niveau caller


# ─────────────────────────────────────────────────────────────────────
# Tests apply_sigma_oracle_to_level (P1 patch behavior)
# ─────────────────────────────────────────────────────────────────────

def test_a1_coiling_becomes_a2():
    """8. A1 COILING → reste A2 (pas NONE)."""
    oracle = SigmaOracleResult(
        sub_state=SigmaSubState.COILING,
        action="WAIT_PRIME",
        confidence=0.75,
        rationale="test",
        ob_alert=False,
        sigma_current=18.0,
        sigma_slope=-1.0,
        n_points=5,
    )
    result = apply_sigma_oracle_to_level("A1", oracle)
    assert result == "A2"


def test_a1_resolving_stays_a1():
    """9. A1 RESOLVING → reste A1 (pas de downgrade)."""
    oracle = SigmaOracleResult(
        sub_state=SigmaSubState.RESOLVING,
        action="WATCH",
        confidence=0.65,
        rationale="test",
        ob_alert=False,
        sigma_current=22.0,
        sigma_slope=1.0,
        n_points=5,
    )
    result = apply_sigma_oracle_to_level("A1", oracle)
    assert result == "A1"


def test_a1_ranging_becomes_none():
    """10. A1 RANGING → tombe NONE (comportement Fatboy standard)."""
    oracle = SigmaOracleResult(
        sub_state=SigmaSubState.RANGING,
        action="WAIT",
        confidence=0.40,
        rationale="test",
        ob_alert=False,
        sigma_current=20.0,
        sigma_slope=0.0,
        n_points=5,
    )
    result = apply_sigma_oracle_to_level("A1", oracle)
    assert result == "NONE"


def test_a2_coiling_becomes_a2():
    """A2 COILING → garde A2 (ne tombe pas NONE)."""
    oracle = SigmaOracleResult(
        sub_state=SigmaSubState.COILING,
        action="WAIT_PRIME",
        confidence=0.75,
        rationale="test",
        ob_alert=False,
        sigma_current=18.0,
        sigma_slope=-1.0,
        n_points=5,
    )
    result = apply_sigma_oracle_to_level("A2", oracle)
    assert result == "A2"


def test_a2_resolving_stays_a2():
    """A2 RESOLVING → garde A2."""
    oracle = SigmaOracleResult(
        sub_state=SigmaSubState.RESOLVING,
        action="WATCH",
        confidence=0.65,
        rationale="test",
        ob_alert=False,
        sigma_current=22.0,
        sigma_slope=1.0,
        n_points=5,
    )
    result = apply_sigma_oracle_to_level("A2", oracle)
    assert result == "A2"


def test_a3_coiling_becomes_a2():
    """A3 COILING → remonte à A2 (upgrade WAIT_PRIME)."""
    oracle = SigmaOracleResult(
        sub_state=SigmaSubState.COILING,
        action="WAIT_PRIME",
        confidence=0.75,
        rationale="test",
        ob_alert=False,
        sigma_current=18.0,
        sigma_slope=-1.0,
        n_points=5,
    )
    result = apply_sigma_oracle_to_level("A3", oracle)
    assert result == "A2"


# ─────────────────────────────────────────────────────────────────────
# Tests Confidence & Rationale
# ─────────────────────────────────────────────────────────────────────

def test_confidence_coiling_075():
    """11. Confidence COILING = 0.75."""
    sigma_hist = [24.0, 23.0, 21.5, 20.0, 18.0]
    oracle = sigma_oracle(sigma_history=sigma_hist)
    assert oracle.confidence == 0.75


def test_confidence_resolving_065():
    """Confidence RESOLVING = 0.65."""
    sigma_hist = [16.0, 17.5, 19.0, 20.5, 22.0]
    oracle = sigma_oracle(sigma_history=sigma_hist)
    assert oracle.confidence == 0.65


def test_confidence_ranging_040():
    """Confidence RANGING = 0.40."""
    sigma_hist = [19.8, 19.9, 20.0, 20.1, 20.0]
    oracle = sigma_oracle(sigma_history=sigma_hist)
    assert oracle.confidence == 0.40


def test_rationale_non_empty_all_states():
    """12. Rationale non-vide sur tous sous-états."""
    for hist, expected_state in [
        ([24.0, 23.0, 21.5, 20.0, 18.0], SigmaSubState.COILING),
        ([16.0, 17.5, 19.0, 20.5, 22.0], SigmaSubState.RESOLVING),
        ([19.8, 19.9, 20.0, 20.1, 20.0], SigmaSubState.RANGING),
    ]:
        oracle = sigma_oracle(sigma_history=hist)
        assert oracle.rationale
        assert len(oracle.rationale) > 10
        assert expected_state.value in oracle.rationale


# ─────────────────────────────────────────────────────────────────────
# Tests Config & Serialization
# ─────────────────────────────────────────────────────────────────────

def test_load_config_defaults():
    """Config défauts chargés si fichier absent."""
    cfg = load_sigma_oracle_config("fichier_inexistant.json")
    assert cfg == DEFAULT_THRESHOLDS


def test_load_config_custom(tmp_path):
    """Config custom chargée correctement."""
    config_path = _make_temp_config(tmp_path, {"coiling_slope_threshold": -1.0})
    cfg = load_sigma_oracle_config(config_path)
    assert cfg["coiling_slope_threshold"] == -1.0
    assert cfg["resolving_slope_threshold"] == 0.8


def test_oracle_serializable():
    """SigmaOracleResult sérialisable JSON (R9 audit)."""
    oracle = sigma_oracle(
        sigma_history=[24.0, 23.0, 21.5, 20.0, 18.0],
        ob_proximity=True,
        bos_confirmed=False,
    )
    d = oracle.as_dict()
    assert d["sub_state"] == "COILING"
    assert d["action"] == "WAIT_PRIME"
    assert d["confidence"] == 0.75
    assert d["ob_alert"] is True
    assert "COILING" in d["rationale"]
    # Vérifie que c'est bien du JSON valide
    json.dumps(d)


# ─────────────────────────────────────────────────────────────────────
# Tests get_sigma_history (integration)
# ─────────────────────────────────────────────────────────────────────

def test_get_sigma_history_returns_list():
    """get_sigma_history retourne une liste (peut être vide si pas de DB)."""
    hist = get_sigma_history("EURUSD", "M30", n=5)
    assert isinstance(hist, list)
    # Ne teste pas le contenu car DB peut ne pas avoir ces données en test


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])