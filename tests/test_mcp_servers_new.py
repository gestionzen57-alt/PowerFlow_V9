"""test_mcp_servers_new.py — Tests pour les 3 nouveaux MCP (paper_trade, meta_strategy_shadow, data_integrity).

Pattern : subprocess direct stdin/stdout sur chaque .py server, JSON-RPC simple.
DB live = data/v9_forces.db (read-only URI).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(r"C:\projet\V9")
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def _call(server: str, requests: list[dict], timeout: int = 30) -> list[str]:
    """Lance un MCP server avec stdin JSON-RPC, retourne stdout lines."""
    stdin_data = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        [str(PYTHON), str(REPO_ROOT / "mcp_servers" / server)],
        input=stdin_data, capture_output=True, text=True, timeout=timeout,
        cwd=str(REPO_ROOT),
    )
    return [l for l in proc.stdout.split("\n") if l.strip()]


# ------------------------------------------------------------------ paper_trade_server


PAPER_TRADE_TESTS = [
    ("tools/list", None),
    ("tools/call/paper_trades_idempotency_check", {}),
    ("tools/call/paper_trades_open", {}),
    ("tools/call/paper_trades_stats", {"since": "30d"}),
    ("tools/call/paper_trades_resolution_breakdown", {"since": "30d"}),
    ("tools/call/paper_trades_recent", {"since": "24h", "limit": 5}),
]


@pytest.mark.parametrize("method,args", PAPER_TRADE_TESTS)
def test_paper_trade_server(method, args):
    timeout = 60 if method in ("tools/call/paper_trades_stats", "tools/call/paper_trades_recent") else 30
    req = {"method": method, "args": args or {}}
    lines = _call("paper_trade_server.py", [req], timeout=timeout)
    assert len(lines) >= 1, f"no output for {method}"
    resp = json.loads(lines[0])
    assert "error" not in resp, f"{method} returned error: {resp.get('error')}"
    if method == "tools/list":
        assert len(resp["tools"]) == 5
    elif method == "tools/call/paper_trades_idempotency_check":
        # Live DB : peut avoir 0 ou N dup selon état
        assert "verdict" in resp
        assert resp["verdict"] in ("OK", "DUP_DETECTED")
        assert "n_total" in resp
        assert "n_unique" in resp
    elif method == "tools/call/paper_trades_open":
        assert "rows" in resp
        assert "count" in resp
    elif method == "tools/call/paper_trades_stats":
        assert "global" in resp
        g = resp["global"]
        assert "n_trades" in g
        assert "wr" in g
        assert "pf" in g
        assert "max_drawdown_pips" in g
        assert "by_segment" in resp
    elif method == "tools/call/paper_trades_resolution_breakdown":
        assert "by_strategy" in resp
        assert "n_total" in resp
    elif method == "tools/call/paper_trades_recent":
        assert "rows" in resp
        assert "count" in resp


# ------------------------------------------------------------------ meta_strategy_shadow_server


META_STRATEGY_SHADOW_TESTS = [
    ("tools/list", None),
    ("tools/call/shadow_kill_switch_status", {}),
    ("tools/call/shadow_log_summary", {"since": "7d"}),
    ("tools/call/shadow_log_recent", {"since": "7d", "limit": 5}),
    ("tools/call/shadow_aggregate_overall", {"since": "7d"}),
    ("tools/call/shadow_simulation_run", {"since": "7d", "limit": 100}),
]


@pytest.mark.parametrize("method,args", META_STRATEGY_SHADOW_TESTS)
def test_meta_strategy_shadow_server(method, args):
    timeout = 90 if method == "tools/call/shadow_aggregate_overall" else 30
    req = {"method": method, "args": args or {}}
    lines = _call("meta_strategy_shadow_server.py", [req], timeout=timeout)
    assert len(lines) >= 1, f"no output for {method}"
    resp = json.loads(lines[0])
    assert "error" not in resp, f"{method} returned error: {resp.get('error')}"
    if method == "tools/list":
        assert len(resp["tools"]) == 5
    elif method == "tools/call/shadow_kill_switch_status":
        assert "V9_META_STRATEGY_SHADOW_ENABLED" in resp
        assert "V9_META_STRATEGY_OPTIMIZER_ENABLED" in resp
    elif method == "tools/call/shadow_log_summary":
        assert "n_shadows" in resp
        assert "agreement_rate" in resp
        assert "by_meta_strategy" in resp
        assert "by_legacy_strategy" in resp
    elif method == "tools/call/shadow_log_recent":
        assert "rows" in resp
        assert "count" in resp
    elif method == "tools/call/shadow_aggregate_overall":
        assert "wr_legacy" in resp
        assert "wr_meta" in resp
        assert "delta_wr" in resp
        assert "verdict" in resp
        assert "limit" in resp  # LIMIT explicite depuis le fix timeout
    elif method == "tools/call/shadow_simulation_run":
        assert "verdict" in resp
        assert "n_decisions" in resp


# ------------------------------------------------------------------ data_integrity_server


DATA_INTEGRITY_TESTS = [
    ("tools/list", None),
    ("tools/call/streams_health_summary", {"max_stale_min": 10}),
    ("tools/call/duplicates_check", {"table": "forces_snapshots"}),
    ("tools/call/disk_size", {}),
    ("tools/call/stream_freshness", {"max_stale_min": 10}),
    ("tools/call/db_table_stats", {}),
]


@pytest.mark.parametrize("method,args", DATA_INTEGRITY_TESTS)
def test_data_integrity_server(method, args):
    # db_table_stats est lent sur 28 tables × 3 queries → timeout 60s
    timeout = 90 if method == "tools/call/db_table_stats" else 30
    req = {"method": method, "args": args or {}}
    lines = _call("data_integrity_server.py", [req], timeout=timeout)
    assert len(lines) >= 1, f"no output for {method}"
    resp = json.loads(lines[0])
    assert "error" not in resp, f"{method} returned error: {resp.get('error')}"
    if method == "tools/list":
        assert len(resp["tools"]) == 5
    elif method == "tools/call/streams_health_summary":
        assert "n_streams" in resp
        assert "by_status" in resp
        assert "pct_mort" in resp
        assert "verdict" in resp
        assert resp["verdict"] in ("HEALTHY", "DEGRADED", "CRITICAL")
    elif method == "tools/call/duplicates_check":
        assert "n_total" in resp
        assert "n_unique" in resp
        assert "ratio" in resp
        assert "verdict" in resp
    elif method == "tools/call/disk_size":
        assert "db_size_gb" in resp
        assert "tables_breakdown" in resp
        assert resp["db_size_gb"] > 0
    elif method == "tools/call/stream_freshness":
        assert "streams" in resp
        assert "count" in resp
    elif method == "tools/call/db_table_stats":
        assert "tables" in resp
        assert "count" in resp
        assert resp["count"] >= 20  # au moins 20 tables


# ------------------------------------------------------------------ all-servers smoke


def test_all_servers_have_5_tools():
    """Vérifie que chaque MCP expose exactement 5 tools (consistance UX)."""
    for server in ["paper_trade_server.py", "meta_strategy_shadow_server.py", "data_integrity_server.py"]:
        lines = _call(server, [{"method": "tools/list"}])
        resp = json.loads(lines[0])
        assert len(resp["tools"]) == 5, f"{server} exposes {len(resp['tools'])} tools"


def test_all_servers_handle_unknown_method_gracefully():
    """Tool inconnu → JSON error au lieu d'un crash Python."""
    for server in ["paper_trade_server.py", "meta_strategy_shadow_server.py", "data_integrity_server.py"]:
        lines = _call(server, [{"method": "tools/call/nonexistent_tool", "args": {}}])
        resp = json.loads(lines[0])
        assert "error" in resp
        assert "nonexistent_tool" in resp["error"]


def test_all_servers_handle_invalid_json():
    """JSON malformé → JSON error au lieu d'un crash."""
    for server in ["paper_trade_server.py", "meta_strategy_shadow_server.py", "data_integrity_server.py"]:
        proc = subprocess.run(
            [str(PYTHON), str(REPO_ROOT / "mcp_servers" / server)],
            input="not a json\n", capture_output=True, text=True, timeout=10,
            cwd=str(REPO_ROOT),
        )
        lines = [l for l in proc.stdout.split("\n") if l.strip()]
        assert len(lines) >= 1
        resp = json.loads(lines[0])
        assert "error" in resp
        assert "invalid json" in resp["error"].lower()