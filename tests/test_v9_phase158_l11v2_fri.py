"""Tests Phase 158 L11v2 — Vendredi boost + kill switch helper."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_helper_fri_boost_default_off(monkeypatch):
    """V9_MEGA_EDGE_L11_DOW_GBPUSD_FRI_BOOST_ENABLED absent → False (R25')."""
    monkeypatch.delenv("V9_MEGA_EDGE_L11_DOW_GBPUSD_FRI_BOOST_ENABLED", raising=False)
    from core.v9.kill_switches import mega_edge_l11_dow_gbpusd_fri_boost_enabled
    # patch _load to empty (no file read for test)
    from core.v9 import kill_switches
    kill_switches._switches = None
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    assert mega_edge_l11_dow_gbpusd_fri_boost_enabled() is False


def test_helper_fri_boost_on(monkeypatch):
    """V9_MEGA_EDGE_L11_DOW_GBPUSD_FRI_BOOST_ENABLED=1 → True."""
    monkeypatch.setenv("V9_MEGA_EDGE_L11_DOW_GBPUSD_FRI_BOOST_ENABLED", "1")
    from core.v9.kill_switches import mega_edge_l11_dow_gbpusd_fri_boost_enabled
    from core.v9 import kill_switches
    kill_switches._switches = None
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    assert mega_edge_l11_dow_gbpusd_fri_boost_enabled() is True


def test_helper_fri_boost_off(monkeypatch):
    """V9_MEGA_EDGE_L11_DOW_GBPUSD_FRI_BOOST_ENABLED=0 → False."""
    monkeypatch.setenv("V9_MEGA_EDGE_L11_DOW_GBPUSD_FRI_BOOST_ENABLED", "0")
    from core.v9.kill_switches import mega_edge_l11_dow_gbpusd_fri_boost_enabled
    from core.v9 import kill_switches
    kill_switches._switches = None
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    assert mega_edge_l11_dow_gbpusd_fri_boost_enabled() is False


def test_mega_edge_filter_imports():
    """core/v9/v9_mega_edge_filter.py doit importer sans crash après Phase 158 patch."""
    from core.v9 import v9_mega_edge_filter  # noqa: F401


def test_mega_edge_filter_has_fri_boost_branch():
    """Le code doit contenir la branche Vendredi boost."""
    src = Path(_ROOT / "core" / "v9" / "v9_mega_edge_filter.py").read_text(encoding="utf-8")
    assert "L11_dow_gbpusd_fri_boost_x1.3" in src
    assert "_l11_fri_enabled" in src
    assert "_dow == 4" in src  # vendredi Python weekday


def test_mega_edge_filter_mer_boost_still_present():
    """Le code Mer boost est conservé (désactivé via env, mais module présent)."""
    src = Path(_ROOT / "core" / "v9" / "v9_mega_edge_filter.py").read_text(encoding="utf-8")
    assert "L11_dow_gbpusd_mer_boost_x1.3" in src
    assert "_l11_boost_enabled" in src
