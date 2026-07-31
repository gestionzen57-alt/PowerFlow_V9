"""tests/test_dynamic_risk_manager_j5_human_scalp.py — J5 2026-07-28 profil skewed.

Additif (R2). Le profil HUMAN_SCALP écrase les profils PHASE_PROFILES si
le kill switch V9_DRM_HUMAN_PROFILE_ENABLED est ON. Sinon fallback R6.
"""
import pytest


def test_human_scalp_profiles_defined():
    """Le profil HUMAN_SCALP_PROFILES couvre les 6 phases canoniques."""
    from core.v9.dynamic_risk_manager import (
        HUMAN_SCALP_PROFILES,
        MarketPhase,
    )
    assert MarketPhase.ACCUMULATION in HUMAN_SCALP_PROFILES
    assert MarketPhase.CASSURE in HUMAN_SCALP_PROFILES
    assert MarketPhase.TREND in HUMAN_SCALP_PROFILES
    assert MarketPhase.DISTRIBUTION in HUMAN_SCALP_PROFILES
    assert MarketPhase.CLIMAX in HUMAN_SCALP_PROFILES
    assert MarketPhase.RETOUR in HUMAN_SCALP_PROFILES


def test_human_scalp_geometry_is_skewed():
    """RR TP/SL skewed ≥ 1.5 sur les phases trend/cassure."""
    from core.v9.dynamic_risk_manager import (
        HUMAN_SCALP_PROFILES,
        MarketPhase,
    )
    for phase in [MarketPhase.CASSURE, MarketPhase.TREND,
                   MarketPhase.ACCUMULATION, MarketPhase.RETOUR]:
        p = HUMAN_SCALP_PROFILES[phase]
        rr = p["tp_pips"] / p["sl_pips"]
        assert rr >= 1.5, f"{phase.name} RR={rr:.2f} < 1.5"


def test_human_scalp_climax_blocks_new_positions():
    """Phase CLIMAX : allow_new_position=False (règle R32)."""
    from core.v9.dynamic_risk_manager import (
        HUMAN_SCALP_PROFILES,
        MarketPhase,
    )
    p = HUMAN_SCALP_PROFILES[MarketPhase.CLIMAX]
    assert p["allow_new_position"] is False


def test_active_profiles_kill_switch_off_returns_phase_profiles(monkeypatch):
    """V9_DRM_HUMAN_PROFILE_ENABLED=0 → fallback PHASE_PROFILES."""
    from core.v9.dynamic_risk_manager import (
        PHASE_PROFILES,
        _active_profiles,
    )
    monkeypatch.setenv("V9_DRM_HUMAN_PROFILE_ENABLED", "0")
    assert _active_profiles() is PHASE_PROFILES


def test_active_profiles_kill_switch_on_returns_human_scalp(monkeypatch):
    """V9_DRM_HUMAN_PROFILE_ENABLED=1 → HUMAN_SCALP_PROFILES."""
    from core.v9.dynamic_risk_manager import (
        HUMAN_SCALP_PROFILES,
        _active_profiles,
    )
    monkeypatch.setenv("V9_DRM_HUMAN_PROFILE_ENABLED", "1")
    assert _active_profiles() is HUMAN_SCALP_PROFILES


def test_kill_switch_helper_default():
    """drm_human_profile_enabled lit l'env, défaut ON."""
    from core.v9.kill_switches import drm_human_profile_enabled
    val = drm_human_profile_enabled()
    assert val is True  # défaut ON autopilot CEO


def test_profile_sl_within_bounds():
    """SL borné par SL_MIN/SL_MAX (6..25)."""
    from core.v9.dynamic_risk_manager import (
        HUMAN_SCALP_PROFILES,
        SL_MIN, SL_MAX,
    )
    for phase, p in HUMAN_SCALP_PROFILES.items():
        assert SL_MIN <= p["sl_pips"] <= SL_MAX, f"{phase.name}"


def test_profile_tp_within_bounds():
    """TP borné par TP_MIN/TP_MAX (4..40)."""
    from core.v9.dynamic_risk_manager import (
        HUMAN_SCALP_PROFILES,
        TP_MIN, TP_MAX,
    )
    for phase, p in HUMAN_SCALP_PROFILES.items():
        assert TP_MIN <= p["tp_pips"] <= TP_MAX, f"{phase.name}"
