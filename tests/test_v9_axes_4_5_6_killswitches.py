"""Tests kill switches Axes 4 J16-J18 + 5 + 6.

Doctrine : R7 (tests verts), R25' (kill switch OFF par défaut).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Axe 4 — Learn Loop ──────────────────────────────────────────────

def test_learn_loop_kill_switch_default():
    """V9_LEARN_LOOP_ENABLED=1 par motion CEO antérieure."""
    from core.v9.kill_switches import learn_loop_enabled
    assert learn_loop_enabled() is True


def test_learn_loop_module_exists():
    """v9_learn_loop existe."""
    from core.v9 import v9_learn_loop
    assert hasattr(v9_learn_loop, "__file__")


def test_learn_loop_docstring():
    """Docstring kill switch R25'."""
    from core.v9.kill_switches import learn_loop_enabled
    assert "R25'" in learn_loop_enabled.__doc__


# ── Axe 4 — Cross-pair metrics ──────────────────────────────────────

def test_cross_pair_metrics_kill_switch_state():
    """V9_CROSS_PAIR_METRICS_ENABLED=1 (CEO motion 2026-07-23/24 activation totale Phase E)."""
    from core.v9.kill_switches import cross_pair_metrics_enabled
    assert cross_pair_metrics_enabled() is True


def test_cross_pair_metrics_module_exists():
    """v9_cross_pair_metrics contient cross_pair_dispersion + pair_force_ratio."""
    from core.v9 import v9_cross_pair_metrics
    assert hasattr(v9_cross_pair_metrics, "cross_pair_dispersion")
    assert hasattr(v9_cross_pair_metrics, "pair_force_ratio")
    assert hasattr(v9_cross_pair_metrics, "neutre_rate_24h")


def test_cross_pair_metrics_docstring():
    """Docstring kill switch R25'."""
    from core.v9.kill_switches import cross_pair_metrics_enabled
    assert "R25'" in cross_pair_metrics_enabled.__doc__


# ── Axe 5 — Audit ──────────────────────────────────────────────────

def test_audit_edgefund_module_exists():
    """EDGEFUND_AUDIT_FINAL_20260718.md existe (CLOS 19/07)."""
    audit_path = ROOT / "docs" / "audit" / "EDGEFUND_AUDIT_FINAL_20260718.md"
    assert audit_path.exists()
    content = audit_path.read_text(encoding="utf-8")
    assert "MARGINAL" in content
    assert "GO conditionnel" in content


def test_audit_resolution_drift_module_exists():
    """v9_audit_resolution_drift existe."""
    from scripts import v9_audit_resolution_drift
    assert hasattr(v9_audit_resolution_drift, "__file__")


def test_audit_cron_wiring_module_exists():
    """v9_audit_cron_wiring existe (axe 5.2 cohérence)."""
    from scripts import v9_audit_cron_wiring
    assert hasattr(v9_audit_cron_wiring, "__file__")


# ── Axe 6 — Hardening ───────────────────────────────────────────────

def test_push_canonique_done():
    """Motion #41 : merge resolve-drift → foundation-clean (déjà fait)."""
    # Vérification git : feat/v9-foundation-clean existe
    import subprocess
    result = subprocess.run(
        ["git", "branch", "-r"], cwd=str(ROOT), capture_output=True, text=True
    )
    assert "feat/v9-foundation-clean" in result.stdout


def test_tokens_rotation_pending():
    """Motion #40 : rotation tokens Telegram EN ATTENTE depuis 19/07 (action CEO)."""
    # Doc de la checklist security le mentionne
    checklist = ROOT / "docs" / "security" / "PRE_REOUVERTURE_CHECKLIST_20260719.md"
    if checklist.exists():
        content = checklist.read_text(encoding="utf-8")
        assert "BotFather" in content or "rotation" in content.lower()


def test_phase_10_gel():
    """Phase 10 GELÉE par R19 / décision Søn."""
    content = (ROOT / "AGENT.md").read_text(encoding="utf-8")
    assert "Phase 10" in content or "Fédération d'agents" in content
