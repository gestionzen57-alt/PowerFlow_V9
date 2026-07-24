"""tests/test_v9_axes_3_4_smoke.py — Tests du smoke global axes 3+4.

Doctrine : R7 (tests verts), R22 (CLI lecture seule).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_axes_3_4_smoke import main, render_text, smoke_all  # noqa: E402


def test_smoke_all_returns_dict():
    """smoke_all() retourne un dict structuré."""
    report = smoke_all()
    assert isinstance(report, dict)
    assert "generated_at" in report
    assert "axe_3" in report
    assert "axe_4" in report
    assert "kill_switches" in report
    assert "all_ok" in report
    assert "verdict" in report


def test_smoke_all_modules_ok():
    """Tous les modules axes 3+4 s'instancient correctement."""
    report = smoke_all()
    assert report["all_ok"] is True
    assert report["verdict"] == "✅ TOUS OK"
    for axe in ("axe_3", "axe_4"):
        for module_name, m in report[axe].items():
            assert m.get("ok") is True, f"{axe}.{module_name} KO : {m.get('error')}"


def test_smoke_kill_switches_present():
    """Les 5 kill switches axes 3+4 sont présents dans le rapport."""
    report = smoke_all()
    expected = [
        "V9_DRAWDOWN_PROTECTOR_ENABLED",
        "V9_RISK_PARITY_ENABLED",
        "V9_CYCLE_MEMORY_ENABLED",
        "V9_META_STRATEGY_OPTIMIZER_ENABLED",
        "V9_KELLY_CVAR_ENABLED",
    ]
    for k in expected:
        assert k in report["kill_switches"]


def test_render_text_includes_axes():
    """Le rendu texte inclut les sections axe 3 + axe 4."""
    report = smoke_all()
    text = render_text(report)
    assert "AXE 3" in text
    assert "AXE 4" in text
    assert "Kill switches" in text
    assert "TOUS OK" in text or "CERTAINS MODULES KO" in text


def test_main_runs(capsys):
    """CLI main() tourne sans crash."""
    import sys as _sys
    _sys.argv = ["prog"]
    rc = main()
    assert rc in (0, 1)  # 0 = tous OK, 1 = certains KO
    captured = capsys.readouterr()
    assert "Smoke global Axes 3+4" in captured.out


def test_main_json_output(capsys):
    """CLI --json produit JSON parsable."""
    import sys as _sys
    _sys.argv = ["prog", "--json"]
    rc = main()
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "axe_3" in data
    assert "axe_4" in data
    assert "all_ok" in data


def test_smoke_meta_strategy_optimizer_actually_on():
    """Le Meta Strategy Optimizer est activé (motion CEO 04h58)."""
    report = smoke_all()
    assert report["kill_switches"]["V9_META_STRATEGY_OPTIMIZER_ENABLED"] is True


def test_smoke_dd_rp_cycle_off():
    """DD protector est OFF par défaut (R25'), Risk Parity et Cycle Memory sont ON (CEO motion 2026-07-23)."""
    report = smoke_all()
    assert report["kill_switches"]["V9_DRAWDOWN_PROTECTOR_ENABLED"] is False
    assert report["kill_switches"]["V9_RISK_PARITY_ENABLED"] is True
    assert report["kill_switches"]["V9_CYCLE_MEMORY_ENABLED"] is True
