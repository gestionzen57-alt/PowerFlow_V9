"""Tests — kill switch walk_forward + smoke CLI (Axe 1.3 J3).

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R25' (kill switch OFF).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_kill_switch_default_off(monkeypatch):
    """V9_WALK_FORWARD_ENABLED=1 par motion CEO 2026-07-23 (Phase E)."""
    from core.v9.kill_switches import walk_forward_enabled
    monkeypatch.delenv("V9_WALK_FORWARD_ENABLED", raising=False)
    # is_enabled lit _load() qui lit os.environ au démarrage
    # Motion CEO 2026-07-23 l'a activé → défaut maintenant ON
    assert walk_forward_enabled() is True


def test_kill_switch_function_exists():
    """walk_forward_enabled() existe dans kill_switches."""
    from core.v9 import kill_switches
    assert hasattr(kill_switches, "walk_forward_enabled")
    assert callable(kill_switches.walk_forward_enabled)
    # Comportement par défaut (env actuel = 1 suite motion CEO)
    assert kill_switches.walk_forward_enabled() is True


def test_module_imports():
    """Le module walk_forward est importable."""
    from core.v9 import walk_forward
    assert hasattr(walk_forward, "WalkForwardValidator")
    assert hasattr(walk_forward, "WalkForwardReport")
    assert hasattr(walk_forward, "render_markdown")
    assert hasattr(walk_forward, "DEFAULT_N_WINDOWS")
    assert walk_forward.DEFAULT_N_WINDOWS >= 3


def test_smoke_cli_runs():
    """CLI smoke s'exécute sans crash sur la DB live (verdict retourné)."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "v9_walk_forward.py"), "--windows", "5"],
        capture_output=True, text=True, timeout=60,
    )
    # Le script doit sortir 0 (succès) ou 1 (verdict négatif), pas crash
    assert result.returncode in (0, 1)
    # Sortie doit contenir soit verdict string legacy, soit champs JSON
    # (refacto CLI 03/08 : sortie JSON au lieu de verdict textuel)
    output = result.stdout + result.stderr
    legacy_verdict = any(
        v in output
        for v in ["EDGE_REEL", "OVERFITTING", "NON_CONCLUANT", "DONNEES_INSUFFISANTES"]
    )
    json_fields = any(
        f in output
        for f in ['"wr_avg"', '"n_windows_passed"', '"summary"']
    )
    assert legacy_verdict or json_fields, (
        f"Output ne contient ni verdict legacy ni champs JSON :\n{output[:500]}"
    )
