"""tests/test_v9_auto_rollback.py — Phase 18 motion CEO « EDGE FUND MAX »."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def workspace_rollback(tmp_path, monkeypatch):
    """Setup workspace avec DB, env file, motion log."""
    env_file = tmp_path / "v9_kill_switches.env"
    env_file.write_text("""# V9 env test
V9_MT4_BRIDGE_ENABLED=1
V9_PAPER_TRADE_HALT=0
V9_OTHER_FLAG=1
""", encoding="utf-8")

    motion_log = tmp_path / "v9_motion_log.json"
    motion_log.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("scripts.v9_auto_rollback.ENV_FILE", env_file)
    monkeypatch.setattr("scripts.v9_auto_rollback.MOTION_LOG", motion_log)
    return tmp_path, env_file, motion_log


def test_should_rollback_no_alert(monkeypatch):
    """Aucun rollback si drift/audit OK."""
    from scripts.v9_auto_rollback import should_rollback
    drift = {"alert": False, "drift_pts": -1.0}
    audit = {"n_closed": 25, "wr_pct": 80.0, "expectancy_net": 5.0}
    should, reasons = should_rollback(drift, audit)
    assert should is False
    assert reasons == []


def test_should_rollback_drift_alert():
    """L12 drift <= -5pts → rollback."""
    from scripts.v9_auto_rollback import should_rollback
    drift = {"alert": True, "drift_pts": -7.0}
    audit = {"n_closed": 25, "wr_pct": 80.0, "expectancy_net": 5.0}
    should, reasons = should_rollback(drift, audit)
    assert should is True
    assert any("L12" in r for r in reasons)


def test_should_rollback_low_wr():
    """WR < 50% (n>=10) → rollback."""
    from scripts.v9_auto_rollback import should_rollback
    drift = {"alert": False, "drift_pts": 0}
    audit = {"n_closed": 25, "wr_pct": 40.0, "expectancy_net": 5.0}
    should, reasons = should_rollback(drift, audit)
    assert should is True
    assert any("WR global" in r for r in reasons)


def test_should_rollback_negative_exp_net():
    """Expectancy net <= 0 → rollback."""
    from scripts.v9_auto_rollback import should_rollback
    drift = {"alert": False, "drift_pts": 0}
    audit = {"n_closed": 25, "wr_pct": 60.0, "expectancy_net": -2.0}
    should, reasons = should_rollback(drift, audit)
    assert should is True
    assert any("Expectancy" in r for r in reasons)


def test_should_rollback_low_wr_below_threshold_n():
    """WR < 50% mais n<10 → pas de rollback (sample insuffisant)."""
    from scripts.v9_auto_rollback import should_rollback
    drift = {"alert": False, "drift_pts": 0}
    audit = {"n_closed": 5, "wr_pct": 30.0, "expectancy_net": 0.0}
    should, reasons = should_rollback(drift, audit)
    assert should is False


def test_apply_rollback_disables_mt4_bridge(workspace_rollback):
    """apply_rollback desactive V9_MT4_BRIDGE_ENABLED."""
    tmp_path, env_file, motion_log = workspace_rollback
    from scripts.v9_auto_rollback import apply_rollback, ROLLBACK_DRIFT_THRESHOLD
    ok = apply_rollback("rb_test_001", ["test reason"])
    assert ok is True
    content = env_file.read_text(encoding="utf-8")
    assert "V9_MT4_BRIDGE_ENABLED=0" in content
    assert "V9_PAPER_TRADE_HALT=1" in content
    # V9_OTHER_FLAG preserve
    assert "V9_OTHER_FLAG=1" in content


def test_apply_rollback_logs_motion(workspace_rollback):
    """apply_rollback log dans v9_motion_log.json."""
    tmp_path, env_file, motion_log = workspace_rollback
    from scripts.v9_auto_rollback import apply_rollback
    apply_rollback("rb_test_002", ["test reason A", "test reason B"])
    assert motion_log.exists()
    motions = json.loads(motion_log.read_text(encoding="utf-8"))
    assert len(motions) == 1
    assert motions[0]["id"] == "rb_test_002"
    assert motions[0]["type"] == "ROLLBACK"
    assert "test reason A" in motions[0]["reasons"]


def test_apply_rollback_appends_existing_motion_log(workspace_rollback):
    """apply_rollback append au lieu d'overwrite si log existe deja."""
    tmp_path, env_file, motion_log = workspace_rollback
    # Pre-existing motion
    motion_log.write_text(json.dumps([
        {"id": "rb_prev", "type": "ROLLBACK", "ts": "2026-07-30T12:00:00"}
    ]), encoding="utf-8")

    from scripts.v9_auto_rollback import apply_rollback
    apply_rollback("rb_test_003", ["new reason"])

    motions = json.loads(motion_log.read_text(encoding="utf-8"))
    assert len(motions) == 2
    assert motions[0]["id"] == "rb_prev"
    assert motions[1]["id"] == "rb_test_003"


def test_apply_rollback_handles_corrupted_log(workspace_rollback):
    """apply_rollback gere motion_log corrompu."""
    tmp_path, env_file, motion_log = workspace_rollback
    motion_log.write_text("{ not json", encoding="utf-8")

    from scripts.v9_auto_rollback import apply_rollback
    ok = apply_rollback("rb_test_004", ["corrupted"])
    assert ok is True
    motions = json.loads(motion_log.read_text(encoding="utf-8"))
    assert len(motions) == 1  # reset, pas crash


def test_main_check_no_alert(workspace_rollback, monkeypatch, capsys):
    """CLI --check sans alerte → exit 0."""
    from scripts.v9_auto_rollback import main
    tmp_path, env_file, motion_log = workspace_rollback

    # Mock detect_drift + detect_paper_audit
    monkeypatch.setattr("scripts.v9_auto_rollback.detect_drift",
                        lambda db: {"alert": False, "drift_pts": 0,
                                    "reason": "stable"})
    monkeypatch.setattr("scripts.v9_auto_rollback.detect_paper_audit",
                        lambda db, **kw: {
                            "n_closed": 25, "wr_pct": 80.0,
                            "expectancy_net": 5.0, "max_dd_net": 50.0,
                            "recommendation": "GO_PHASE12_LIVE",
                        })

    exit_code = main(["--check"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Aucun rollback necessaire" in captured.out


def test_main_check_alert_no_force(workspace_rollback, monkeypatch, capsys):
    """CLI --check avec alerte → exit 2 (alerte detectee)."""
    from scripts.v9_auto_rollback import main
    tmp_path, env_file, motion_log = workspace_rollback

    monkeypatch.setattr("scripts.v9_auto_rollback.detect_drift",
                        lambda db: {"alert": True, "drift_pts": -7.0,
                                    "reason": "wr_declining_3d"})
    monkeypatch.setattr("scripts.v9_auto_rollback.detect_paper_audit",
                        lambda db, **kw: {
                            "n_closed": 25, "wr_pct": 80.0,
                            "expectancy_net": 5.0, "max_dd_net": 50.0,
                            "recommendation": "GO_PHASE12_LIVE",
                        })

    exit_code = main(["--check"])
    assert exit_code == 2  # alerte mais non appliquee


def test_main_force_applies_rollback(workspace_rollback, monkeypatch, capsys):
    """CLI --force applique rollback immediatement."""
    from scripts.v9_auto_rollback import main
    tmp_path, env_file, motion_log = workspace_rollback

    monkeypatch.setattr("scripts.v9_auto_rollback.detect_drift",
                        lambda db: {"alert": False})
    monkeypatch.setattr("scripts.v9_auto_rollback.detect_paper_audit",
                        lambda db, **kw: {"n_closed": 0})

    exit_code = main(["--force"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "force" in captured.out.lower() or "Rollback applique" in captured.out
    assert "V9_MT4_BRIDGE_ENABLED=0" in env_file.read_text(encoding="utf-8")


def test_apply_rollback_env_file_missing(tmp_path, monkeypatch):
    """apply_rollback sur env_file absent → False sans crash."""
    from scripts.v9_auto_rollback import apply_rollback
    missing = tmp_path / "absent.env"
    monkeypatch.setattr("scripts.v9_auto_rollback.ENV_FILE", missing)
    ok = apply_rollback("rb_001", ["test"])
    assert ok is False