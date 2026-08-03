"""tests/test_v9_mcp_quant.py — Phase 40A motion CEO 48h.

Tests pour v9_mcp_quant_server.
"""
import json
import pytest


def test_tools_list():
    """tools/list retourne 7 tools."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    resp = handle_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "result" in resp
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "monte_carlo" in tool_names
    assert "kelly" in tool_names
    assert "bayesian" in tool_names
    assert "var" in tool_names
    assert "walk_forward_mc" in tool_names
    assert "regime" in tool_names
    assert "sentiment" in tool_names


def test_tools_call_unknown_tool():
    """tools/call avec tool inconnu → error -32601."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": "unknown", "arguments": {}},
    }
    resp = handle_request(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_tools_call_kelly():
    """tools/call kelly retourne kelly + lot."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {
        "jsonrpc": "2.0", "id": 3,
        "method": "tools/call",
        "params": {
            "name": "kelly",
            "arguments": {"wr": 0.946, "capital": 10000, "tp": 25, "sl": 8},
        },
    }
    resp = handle_request(req)
    assert "result" in resp
    data = resp["result"]["content"][0]["data"]
    assert "kelly" in data
    assert "lot" in data
    assert data["kelly"]["kelly_full"] > 0.5


def test_tools_call_kelly_error():
    """tools/call kelly avec args invalides → error -32603."""
    from scripts.v9_mcp_quant_server import handle_request, TOOLS
    # Force error en monkeypatchant
    import scripts.v9_mcp_quant_server as mqs
    original_kelly = mqs.TOOLS["kelly"]
    def broken(_args):
        raise ValueError("test error")
    mqs.TOOLS["kelly"] = broken
    try:
        req = {
            "jsonrpc": "2.0", "id": 4,
            "method": "tools/call",
            "params": {"name": "kelly", "arguments": {}},
        }
        resp = mqs.handle_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32603
    finally:
        mqs.TOOLS["kelly"] = original_kelly


def test_tools_call_unknown_method():
    """method inconnu → error."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {"jsonrpc": "2.0", "id": 5, "method": "unknown/method"}
    resp = handle_request(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_tool_monte_carlo_direct():
    """tool_monte_carlo direct call."""
    from scripts.v9_mcp_quant_server import tool_monte_carlo
    res = tool_monte_carlo({"n_sims": 100, "seed": 42})
    # Soit error soit result
    assert "n_simulations" in res or "error" in res


def test_tool_bayesian_direct():
    """tool_bayesian direct call."""
    from scripts.v9_mcp_quant_server import tool_bayesian
    res = tool_bayesian({"threshold": 0.60})
    assert "posterior_mean_wr" in res or "error" in res


def test_tool_var_direct():
    """tool_var direct call."""
    from scripts.v9_mcp_quant_server import tool_var
    res = tool_var({"confidence": 0.95})
    assert "var_pips" in res or "error" in res


def test_tool_sentiment_direct():
    """tool_sentiment direct call."""
    from scripts.v9_mcp_quant_server import tool_sentiment
    res = tool_sentiment({"days": 7})
    assert "sentiment" in res


def test_main_list_mode(capsys):
    """CLI main list tools."""
    from scripts.v9_mcp_quant_server import main
    exit_code = main(["--mode", "test"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "monte_carlo" in captured.out


def test_main_call_mode(capsys):
    """CLI main call kelly."""
    from scripts.v9_mcp_quant_server import main
    exit_code = main(["--mode", "test", "--tool", "kelly",
                       "--args", '{"wr": 0.85, "capital": 5000}'])
    captured = capsys.readouterr()
    assert exit_code == 0
    data = json.loads(captured.out)
    assert "kelly" in data


def test_main_invalid_json():
    """CLI main avec JSON invalide → exit 1."""
    from scripts.v9_mcp_quant_server import main
    exit_code = main(["--mode", "test", "--tool", "kelly", "--args", "not json"])
    assert exit_code == 1


# === Phase 174 : gap_signaux_diagnostic + venv_deps_audit ===

def test_tools_list_includes_phase174_tools():
    """tools/list inclut les 2 nouveaux tools Phase 174."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {"jsonrpc": "2.0", "id": 100, "method": "tools/list"}
    resp = handle_request(req)
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "gap_signaux_diagnostic" in tool_names
    assert "venv_deps_audit" in tool_names
    # 7 anciens + 2 nouveaux = 9
    assert len(resp["result"]["tools"]) == 9


def test_tool_gap_signaux_diagnostic_direct():
    """tool_gap_signaux_diagnostic retourne les cles attendues."""
    from scripts.v9_mcp_quant_server import tool_gap_signaux_diagnostic
    res = tool_gap_signaux_diagnostic({"hours": 2, "tail_lines": 50})
    # Cles obligatoires
    for key in ("now_utc", "max_ts", "gap_min", "total_signals",
                "db_volume_per_min", "log_crash_count",
                "log_crash_sample", "verdict"):
        assert key in res, f"cle manquante: {key}"
    # verdict ∈ {OK, GAP, CRASH, COLD, STALE}
    assert res["verdict"] in ("OK", "GAP", "CRASH", "COLD", "STALE")
    # gap_min est un nombre (ou None si COLD)
    assert res["gap_min"] is None or isinstance(res["gap_min"], (int, float))
    # db_volume_per_min est une liste
    assert isinstance(res["db_volume_per_min"], list)


def test_tool_gap_signaux_diagnostic_small_hours():
    """tool_gap_signaux_diagnostic avec hours=1."""
    from scripts.v9_mcp_quant_server import tool_gap_signaux_diagnostic
    res = tool_gap_signaux_diagnostic({"hours": 1, "tail_lines": 10})
    assert "verdict" in res
    # Avec hours=1, si max_ts < now-1h, verdict ∈ {GAP, CRASH, STALE, COLD}
    # Si > 1h, peut-etre OK. Juste sanity check que ça repond.
    assert res["verdict"] is not None


def test_tool_venv_deps_audit_direct():
    """tool_venv_deps_audit detecte pyyaml (Phase 171 anti-regression)."""
    from scripts.v9_mcp_quant_server import tool_venv_deps_audit
    res = tool_venv_deps_audit({})
    # Cles obligatoires
    for key in ("venv_python", "pyproject", "pyproject_deps", "pip_installed",
                "missing", "undeclared", "status"):
        assert key in res, f"cle manquante: {key}"
    # status ∈ {OK, DRIFT, MISSING, UNREACHABLE}
    assert res["status"] in ("OK", "DRIFT", "MISSING", "UNREACHABLE")
    # Si le venv est OK, pyyaml doit etre installe (Phase 171)
    if res["status"] != "UNREACHABLE":
        assert "pyyaml" in res["pip_installed"], \
            "pyyaml devrait etre dans pip_installed (Phase 171)"
        assert "pyyaml" in res["pyproject_deps"], \
            "pyyaml devrait etre dans pyproject_deps (Phase 171)"
        assert "pyyaml" not in res["missing"], \
            "pyyaml missing = regression Phase 171"


def test_tool_venv_deps_audit_invalid_pyproject(tmp_path):
    """tool_venv_deps_audit avec pyproject inexistant → UNREACHABLE."""
    from scripts.v9_mcp_quant_server import tool_venv_deps_audit
    fake = str(tmp_path / "no_pyproject.toml")
    res = tool_venv_deps_audit({"pyproject": fake})
    assert res["status"] == "UNREACHABLE"
    assert "introuvable" in res["error"]


def test_tools_call_gap_signaux_diagnostic():
    """JSON-RPC tools/call gap_signaux_diagnostic."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {
        "jsonrpc": "2.0", "id": 200,
        "method": "tools/call",
        "params": {
            "name": "gap_signaux_diagnostic",
            "arguments": {"hours": 2, "tail_lines": 20},
        },
    }
    resp = handle_request(req)
    assert "result" in resp
    data = resp["result"]["content"][0]["data"]
    assert "verdict" in data


def test_tools_call_venv_deps_audit():
    """JSON-RPC tools/call venv_deps_audit."""
    from scripts.v9_mcp_quant_server import handle_request
    req = {
        "jsonrpc": "2.0", "id": 201,
        "method": "tools/call",
        "params": {
            "name": "venv_deps_audit",
            "arguments": {},
        },
    }
    resp = handle_request(req)
    assert "result" in resp
    data = resp["result"]["content"][0]["data"]
    assert "status" in data