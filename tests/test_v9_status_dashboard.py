"""tests/test_v9_status_dashboard.py — Phase 20 motion CEO « EDGE FUND MAX »."""
import json
from pathlib import Path

import pytest


def test_render_dashboard_full(monkeypatch):
    """render_dashboard retourne string complet en mode full."""
    from scripts.v9_status_dashboard import (
        build_dashboard, render_dashboard, _git_head, _git_n_commits,
    )
    # Mock les fonctions lentes
    monkeypatch.setattr("scripts.v9_status_dashboard._git_head",
                        lambda: "abc1234 test commit")
    monkeypatch.setattr("scripts.v9_status_dashboard._git_n_commits", lambda: 33)
    monkeypatch.setattr("scripts.v9_status_dashboard._test_count", lambda: (264, 3001))
    monkeypatch.setattr("scripts.v9_status_dashboard._live_status", lambda: {
        "bridge_ready": True, "heartbeat_ok": True,
        "mirror_n_human_trades": 0, "mirror_blocking_enabled": False,
        "tokens_n_total": 0, "tokens_n_expired": 0,
    })
    monkeypatch.setattr("scripts.v9_status_dashboard._paper_status",
                        lambda: {"n_open": 20, "n_closed": 0, "n_total": 20,
                                 "wr_pct": 0.0})
    monkeypatch.setattr("scripts.v9_status_dashboard._rollback_status",
                        lambda: {"exit_code": 0, "recommendation": "OK"})

    d = build_dashboard()
    out = render_dashboard(d, mode="full")
    assert "POWERFLOW V9" in out
    assert "DASHBOARD LIVE" in out
    assert "EDGE METRICS" in out
    assert "LIVE STATUS" in out
    assert "PAPER TRADING" in out
    assert "AUTO-ROLLBACK" in out
    assert "ACTIONS HUMAINES" in out


def test_render_dashboard_json(monkeypatch):
    """render_dashboard retourne JSON valide en mode json."""
    from scripts.v9_status_dashboard import (
        build_dashboard, render_dashboard,
    )
    monkeypatch.setattr("scripts.v9_status_dashboard._git_head",
                        lambda: "abc1234")
    monkeypatch.setattr("scripts.v9_status_dashboard._git_n_commits", lambda: 33)
    monkeypatch.setattr("scripts.v9_status_dashboard._test_count", lambda: (264, 3001))
    monkeypatch.setattr("scripts.v9_status_dashboard._live_status", lambda: {})
    monkeypatch.setattr("scripts.v9_status_dashboard._paper_status",
                        lambda: {"n_open": 0, "n_closed": 0, "n_total": 0,
                                 "wr_pct": 0.0})
    monkeypatch.setattr("scripts.v9_status_dashboard._rollback_status",
                        lambda: {"exit_code": 0, "recommendation": "OK"})

    d = build_dashboard()
    out = render_dashboard(d, mode="json")
    parsed = json.loads(out)
    assert "system" in parsed
    assert "tests" in parsed
    assert "edge_metrics" in parsed
    assert "live_status" in parsed
    assert "paper_status" in parsed
    assert "rollback_status" in parsed
    assert "actions_humaines_restantes" in parsed


def test_render_dashboard_compact(monkeypatch):
    """render_dashboard retourne 4 lignes compactes."""
    from scripts.v9_status_dashboard import (
        build_dashboard, render_dashboard,
    )
    monkeypatch.setattr("scripts.v9_status_dashboard._git_head",
                        lambda: "abc1234 test")
    monkeypatch.setattr("scripts.v9_status_dashboard._git_n_commits", lambda: 33)
    monkeypatch.setattr("scripts.v9_status_dashboard._test_count", lambda: (264, 3001))
    monkeypatch.setattr("scripts.v9_status_dashboard._live_status", lambda: {
        "bridge_ready": True, "heartbeat_ok": True,
        "mirror_n_human_trades": 0, "mirror_blocking_enabled": False,
        "tokens_n_total": 0, "tokens_n_expired": 0,
    })
    monkeypatch.setattr("scripts.v9_status_dashboard._paper_status",
                        lambda: {"n_open": 20, "n_closed": 0, "n_total": 20,
                                 "wr_pct": 0.0})
    monkeypatch.setattr("scripts.v9_status_dashboard._rollback_status",
                        lambda: {"exit_code": 0, "recommendation": "OK"})

    d = build_dashboard()
    out = render_dashboard(d, mode="compact")
    lines = out.strip().split("\n")
    assert len(lines) == 4
    assert "HEAD=" in lines[0]
    assert "edge WR=" in lines[1]
    assert "bridge=" in lines[2]
    assert "rollback=" in lines[3]


def test_build_dashboard_has_actions(monkeypatch):
    """build_dashboard retourne 2 actions humaines restantes."""
    from scripts.v9_status_dashboard import build_dashboard
    monkeypatch.setattr("scripts.v9_status_dashboard._git_head", lambda: "abc")
    monkeypatch.setattr("scripts.v9_status_dashboard._git_n_commits", lambda: 1)
    monkeypatch.setattr("scripts.v9_status_dashboard._test_count", lambda: (1, 1))
    monkeypatch.setattr("scripts.v9_status_dashboard._live_status", lambda: {})
    monkeypatch.setattr("scripts.v9_status_dashboard._paper_status",
                        lambda: {"n_open": 0, "n_closed": 0, "n_total": 0,
                                 "wr_pct": 0.0})
    monkeypatch.setattr("scripts.v9_status_dashboard._rollback_status",
                        lambda: {"exit_code": 0, "recommendation": "OK"})
    d = build_dashboard()
    actions = d["actions_humaines_restantes"]
    assert len(actions) == 2
    ids = [a["id"] for a in actions]
    assert "R2" in ids
    assert "WALK_FORWARD_7J" in ids


def test_build_dashboard_edge_metrics_complete(monkeypatch):
    """edge_metrics contient tous les champs obligatoires."""
    from scripts.v9_status_dashboard import build_dashboard
    monkeypatch.setattr("scripts.v9_status_dashboard._git_head", lambda: "abc")
    monkeypatch.setattr("scripts.v9_status_dashboard._git_n_commits", lambda: 1)
    monkeypatch.setattr("scripts.v9_status_dashboard._test_count", lambda: (1, 1))
    monkeypatch.setattr("scripts.v9_status_dashboard._live_status", lambda: {})
    monkeypatch.setattr("scripts.v9_status_dashboard._paper_status",
                        lambda: {"n_open": 0, "n_closed": 0, "n_total": 0,
                                 "wr_pct": 0.0})
    monkeypatch.setattr("scripts.v9_status_dashboard._rollback_status",
                        lambda: {"exit_code": 0, "recommendation": "OK"})
    d = build_dashboard()
    e = d["edge_metrics"]
    assert e["wr_pct"] > 0
    assert e["expectancy_brut"] > 0
    assert e["expectancy_net_R6"] > 0
    assert e["max_dd_pips"] > 0
    assert e["recovery_factor"] > 0
    assert "GBPUSD" in e["window"]


def test_safe_run_basic():
    """_safe_run execute une commande simple."""
    from scripts.v9_status_dashboard import _safe_run
    rc, out = _safe_run(["python", "--version"])
    assert rc == 0
    assert "Python" in out


def test_safe_run_timeout_short():
    """_safe_run timeout sur commande trop longue."""
    from scripts.v9_status_dashboard import _safe_run
    rc, out = _safe_run(["python", "-c", "import time; time.sleep(5)"], timeout=1)
    assert rc != 0  # timeout


def test_git_head_returns_string():
    """_git_head retourne un string non-vide."""
    from scripts.v9_status_dashboard import _git_head
    h = _git_head()
    assert isinstance(h, str)
    assert len(h) > 0


def test_git_n_commits_positive():
    """_git_n_commits retourne un entier positif (session a 33+ commits)."""
    from scripts.v9_status_dashboard import _git_n_commits
    n = _git_n_commits()
    assert n > 0


def test_render_dashboard_lines_complete(monkeypatch):
    """render_dashboard full contient toutes les sections attendues."""
    from scripts.v9_status_dashboard import (
        build_dashboard, render_dashboard,
    )
    monkeypatch.setattr("scripts.v9_status_dashboard._git_head",
                        lambda: "abc1234")
    monkeypatch.setattr("scripts.v9_status_dashboard._git_n_commits", lambda: 33)
    monkeypatch.setattr("scripts.v9_status_dashboard._test_count", lambda: (264, 3001))
    monkeypatch.setattr("scripts.v9_status_dashboard._live_status", lambda: {
        "bridge_ready": True, "heartbeat_ok": True,
        "mirror_n_human_trades": 0, "mirror_blocking_enabled": False,
        "tokens_n_total": 0, "tokens_n_expired": 0,
    })
    monkeypatch.setattr("scripts.v9_status_dashboard._paper_status",
                        lambda: {"n_open": 20, "n_closed": 0, "n_total": 20,
                                 "wr_pct": 0.0})
    monkeypatch.setattr("scripts.v9_status_dashboard._rollback_status",
                        lambda: {"exit_code": 0, "recommendation": "OK"})

    d = build_dashboard()
    out = render_dashboard(d, mode="full")
    # Sections obligatoires
    assert "SYSTEM" in out
    assert "EDGE METRICS" in out
    assert "LIVE STATUS" in out
    assert "PAPER TRADING" in out
    assert "AUTO-ROLLBACK" in out
    assert "ACTIONS HUMAINES" in out
    # Métriques clés
    assert "94.6" in out  # WR
    assert "3.05" in out  # exp net
    assert "34.5" in out  # max DD