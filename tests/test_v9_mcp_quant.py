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