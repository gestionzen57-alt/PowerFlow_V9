"""tests/test_v9_boot_alerts.py — Phase 8 motion CEO « EDGE FUND MAX ».

BUG-P1/P2/P4 : alertes boot sur incoherence kill switches.
"""
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Reset tous les env vars pour isolation
    for k in (
        "V9_MEGA_EDGE_ENABLED", "V9_TIME_EXIT_ENABLED",
        "V9_DRM_HUMAN_PROFILE_ENABLED", "V9_HUMAN_MIRROR_ENABLED",
        "V9_HUMAN_MIRROR_BLOCKING", "PYTEST_CURRENT_TEST",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def test_no_warning_when_l3_compatible_with_human(monkeypatch, tmp_path):
    """Si L3 OFF ou HUMAN_SCALP OFF, BUG-P4 ne se déclenche pas → 0 warning."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE v9_human_trades "
            "(id INTEGER PRIMARY KEY, timestamp TEXT)"
        )
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO v9_human_trades (timestamp) VALUES (?)", (now,)
        )
        conn.commit()

    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "1")
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "0")  # L3 OFF
    monkeypatch.setenv("V9_DRM_HUMAN_PROFILE_ENABLED", "1")
    monkeypatch.setenv("V9_HUMAN_MIRROR_ENABLED", "1")
    monkeypatch.setattr("core.v9.config.DB_PATH", db)

    from core.v9.v9_boot_alerts import check_kill_switch_coherence
    warnings = check_kill_switch_coherence(db_path=db)
    # BUG-P4 ne doit PAS se déclencher si L3 OFF
    assert not any("BUG-P4" in w for w in warnings)


def test_bug_p1_mega_off_in_prod(monkeypatch, tmp_path):
    """BUG-P1 : MEGA OFF + V9_BOOT_CONTEXT=prod → warning."""
    db = tmp_path / "v9.db"
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "0")
    monkeypatch.setenv("V9_BOOT_CONTEXT", "prod")

    # Reload pour forcer re-lecture env au runtime du check
    from core.v9 import v9_boot_alerts
    import importlib
    importlib.reload(v9_boot_alerts)
    warnings = v9_boot_alerts.check_kill_switch_coherence(db_path=db)
    assert any("BUG-P1" in w for w in warnings)


def test_bug_p1_silent_in_pytest(monkeypatch, tmp_path):
    """BUG-P1 : MEGA OFF en pytest (sans V9_BOOT_CONTEXT=prod) → pas de warning."""
    db = tmp_path / "v9.db"
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "0")
    monkeypatch.delenv("V9_BOOT_CONTEXT", raising=False)

    from core.v9.v9_boot_alerts import check_kill_switch_coherence
    warnings = check_kill_switch_coherence(db_path=db)
    assert not any("BUG-P1" in w for w in warnings)


def test_bug_p4_l3_vs_human_scalp_alerts(monkeypatch, tmp_path):
    """BUG-P4 : L3 ON + HUMAN_SCALP ON → warning coherence TP=25 vs 5min."""
    db = tmp_path / "v9.db"
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "1")
    monkeypatch.setenv("V9_DRM_HUMAN_PROFILE_ENABLED", "1")

    from core.v9.v9_boot_alerts import check_kill_switch_coherence
    warnings = check_kill_switch_coherence(db_path=db)
    assert any("BUG-P4" in w for w in warnings)


def test_bug_p2_mirror_blocking_no_data_alerts(monkeypatch, tmp_path):
    """BUG-P2 : BLOCKING actif + table v9_human_trades vide → warning."""
    db = tmp_path / "v9.db"
    # DB sans table v9_human_trades
    with sqlite3.connect(str(db)) as conn:
        conn.commit()
    monkeypatch.setenv("V9_HUMAN_MIRROR_ENABLED", "1")
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")

    from core.v9.v9_boot_alerts import check_kill_switch_coherence
    warnings = check_kill_switch_coherence(db_path=db)
    assert any("BUG-P2" in w for w in warnings)


def test_bug_p2_mirror_blocking_stale_data_alerts(monkeypatch, tmp_path):
    """BUG-P2 : BLOCKING actif + dernier trade humain > 7j → warning."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE v9_human_trades "
            "(id INTEGER PRIMARY KEY, timestamp TEXT)"
        )
        old = (datetime.utcnow() - timedelta(days=14)).isoformat()
        conn.execute(
            "INSERT INTO v9_human_trades (timestamp) VALUES (?)", (old,)
        )
        conn.commit()
    monkeypatch.setenv("V9_HUMAN_MIRROR_ENABLED", "1")
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")

    from core.v9.v9_boot_alerts import check_kill_switch_coherence
    warnings = check_kill_switch_coherence(db_path=db)
    assert any("BUG-P2" in w and "obsolète" in w for w in warnings)


def test_mirror_data_age_returns_none_for_missing_db(tmp_path):
    """_mirror_data_age_days retourne None si DB absente."""
    from core.v9.v9_boot_alerts import _mirror_data_age_days
    res = _mirror_data_age_days(db_path=tmp_path / "absent.db")
    assert res is None


def test_run_boot_alerts_returns_count(monkeypatch, tmp_path):
    """run_boot_alerts retourne nombre de warnings."""
    db = tmp_path / "v9.db"
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "1")
    monkeypatch.setenv("V9_DRM_HUMAN_PROFILE_ENABLED", "1")

    from core.v9.v9_boot_alerts import run_boot_alerts
    n = run_boot_alerts(db_path=db)
    assert n >= 1  # BUG-P4 au minimum