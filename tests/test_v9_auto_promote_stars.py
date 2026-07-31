"""tests/test_v9_auto_promote_stars.py — Phase 3 motion CEO « EDGE FUND MAX »."""
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setenv("V9_AUTO_PROMOTE_STARS_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_AUTO_PROMOTE_STARS_ENABLED", raising=False)


def test_kill_switch_default():
    """V9_AUTO_PROMOTE_STARS_ENABLED defaut ON."""
    from scripts.v9_auto_promote_stars import auto_promote_stars_enabled
    assert auto_promote_stars_enabled() is True


def test_force_promote_creates_override(tmp_path):
    """Override absent → cree avec les 3 stars."""
    from scripts.v9_auto_promote_stars import force_promote_stars
    p = tmp_path / "calibration_overrides.json"
    res = force_promote_stars(path=p)
    assert len(res["promotions"]) == 3
    assert res["written"] is True
    assert p.exists()
    data = json.loads(p.read_text())
    assert "PRICE_LAG_AT_NODE_BIRTH" in data["principle_active_ids_override"]
    assert "POWER_ANGLE_BREAK_TO_PRICE_IMPACT" in data["principle_active_ids_override"]
    assert "GRAVITY_RESPRING_NODE" in data["principle_active_ids_override"]


def test_force_promote_idempotent(tmp_path):
    """2 appels successifs → 2e ne fait rien."""
    from scripts.v9_auto_promote_stars import force_promote_stars
    p = tmp_path / "calibration_overrides.json"
    force_promote_stars(path=p)
    res = force_promote_stars(path=p)
    assert res["promotions"] == []
    assert len(res["already_present"]) == 3
    assert res["written"] is False


def test_force_promote_keeps_existing(tmp_path):
    """Override existant avec 2 stars → ajoute le 3eme."""
    from scripts.v9_auto_promote_stars import force_promote_stars
    p = tmp_path / "calibration_overrides.json"
    p.write_text(json.dumps({
        "principle_active_ids_override": [
            "PRICE_LAG_AT_NODE_BIRTH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        ]
    }))
    res = force_promote_stars(path=p)
    assert len(res["promotions"]) == 1
    assert "GRAVITY_RESPRING_NODE" in res["promotions"]
    assert len(res["already_present"]) == 2


def test_kill_switch_off_no_op(tmp_path, monkeypatch):
    """V9_AUTO_PROMOTE_STARS_ENABLED=0 → no-op."""
    from scripts.v9_auto_promote_stars import (
        auto_promote_stars_enabled, force_promote_stars,
    )
    monkeypatch.setenv("V9_AUTO_PROMOTE_STARS_ENABLED", "0")
    assert auto_promote_stars_enabled() is False
    p = tmp_path / "calibration_overrides.json"
    res = force_promote_stars(path=p)
    assert res == {"promotions": [], "already_present": [], "written": False}
    assert not p.exists()


def test_mega_edge_stars_constant():
    """Les 3 stars sont celles de l'audit SQL 90j."""
    from scripts.v9_auto_promote_stars import MEGA_EDGE_STARS
    assert len(MEGA_EDGE_STARS) == 3
    assert "PRICE_LAG_AT_NODE_BIRTH" in MEGA_EDGE_STARS
    assert "POWER_ANGLE_BREAK_TO_PRICE_IMPACT" in MEGA_EDGE_STARS
    assert "GRAVITY_RESPRING_NODE" in MEGA_EDGE_STARS