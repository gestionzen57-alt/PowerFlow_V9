"""Tests E2E pour les 4 nouveaux tools du MCP strategy_pole.

Tools couverts (cf. mcp_servers/strategy_pole_server.py) :
- live_snapshot
- pair_breakdown
- principle_leaderboard
- dashboard_summary

Pattern identique à tests/test_strategy_pole_mcp.py : subprocess stdio + JSON-lines.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MCP_PATH = ROOT / "mcp_servers" / "strategy_pole_server.py"


def _call_mcp(tool: str, args: dict | None = None, timeout: int = 60) -> dict:
    """Invoque le MCP server via stdio et retourne la 2ème ligne (réponse)."""
    args = args or {}
    req = json.dumps({"tool": tool, "args": args})
    proc = subprocess.run(
        [sys.executable, str(MCP_PATH)],
        input=req + "\n",
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert len(lines) >= 2, (
        f"MCP a retourné <2 lignes pour {tool!r}: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    return json.loads(lines[1])


# ── live_snapshot ───────────────────────────────────────────────────


def test_live_snapshot_eurusd_structure() -> None:
    """live_snapshot EURUSD : 3 TF + last_decision, tous présents (peuvent être None)."""
    resp = _call_mcp("live_snapshot", {"symbol": "EURUSD"})
    assert resp["symbol"] == "EURUSD"
    for tf in ("h1", "m15", "m5"):
        assert tf in resp, f"timeframe {tf!r} manquant"
        # Chaque TF est soit None, soit un dict avec au moins un timestamp.
        snap = resp[tf]
        assert snap is None or isinstance(snap, dict)
    assert "last_decision" in resp
    assert "open_trade" in resp
    # Décision présente attendue sur EURUSD (les forces y sont).
    if resp["last_decision"] is not None:
        assert "decision_id" in resp["last_decision"]


def test_live_snapshot_missing_symbol_error() -> None:
    """live_snapshot sans symbol → erreur explicite, pas de crash."""
    resp = _call_mcp("live_snapshot", {})
    assert "error" in resp
    assert "symbol" in resp["error"].lower()


def test_live_snapshot_unknown_symbol_returns_nulls() -> None:
    """live_snapshot pour symbole inconnu → champs null, pas de crash."""
    resp = _call_mcp("live_snapshot", {"symbol": "ZZZUNKNOWN"})
    assert resp["symbol"] == "ZZZUNKNOWN"
    assert resp["h1"] is None
    assert resp["m15"] is None
    assert resp["m5"] is None
    assert resp["last_decision"] is None
    assert resp["open_trade"] is None


# ── pair_breakdown ──────────────────────────────────────────────────


def test_pair_breakdown_gbpusd_totals_consistent() -> None:
    """pair_breakdown GBPUSD : baissiere + haussiere ≈ total (vérif sommation)."""
    resp = _call_mcp("pair_breakdown", {"symbol": "GBPUSD"})
    assert resp["symbol"] == "GBPUSD"
    b = resp["baissiere"]
    h = resp["haussiere"]
    t = resp["total"]
    # n cohérent
    assert t["n"] == b["n"] + h["n"]
    # pips cohérents
    assert abs(t["pips"] - round(b["pips"] + h["pips"], 2)) < 0.01
    # WR global dans [0, 100]
    assert 0 <= t["wr"] <= 100
    # WR par direction aussi
    assert 0 <= b["wr"] <= 100
    assert 0 <= h["wr"] <= 100


def test_pair_breakdown_unknown_symbol_empty() -> None:
    """pair_breakdown pour symbole sans trades → directions à zéro."""
    resp = _call_mcp("pair_breakdown", {"symbol": "ZZZUNKNOWN"})
    assert resp["baissiere"] == {"n": 0, "wr": 0.0, "pips": 0.0}
    assert resp["haussiere"] == {"n": 0, "wr": 0.0, "pips": 0.0}
    assert resp["total"]["n"] == 0


# ── principle_leaderboard ──────────────────────────────────────────


def test_principle_leaderboard_default_metric_sorted() -> None:
    """principle_leaderboard metric=avg_pips → trié par avg_pips décroissant."""
    resp = _call_mcp("principle_leaderboard", {"metric": "avg_pips", "limit": 5})
    assert resp["metric"] == "avg_pips"
    assert resp["limit"] == 5
    assert resp["min_n"] == 20
    assert resp["count"] >= 1
    rows = resp["principles"]
    for a, b in zip(rows, rows[1:]):
        assert a["avg_pips"] >= b["avg_pips"]
    # Chaque ligne respecte min_n
    for r in rows:
        assert r["n"] >= 20
        assert r["principle"]


def test_principle_leaderboard_metric_wr_pct() -> None:
    """principle_leaderboard metric=wr_pct → trié par wr_pct décroissant."""
    resp = _call_mcp("principle_leaderboard", {"metric": "wr_pct", "limit": 3})
    assert resp["metric"] == "wr_pct"
    rows = resp["principles"]
    assert resp["count"] >= 1
    for a, b in zip(rows, rows[1:]):
        assert a["wr_pct"] >= b["wr_pct"]


def test_principle_leaderboard_unknown_metric_error() -> None:
    """principle_leaderboard avec metric inconnue → erreur + liste available."""
    resp = _call_mcp("principle_leaderboard", {"metric": "no_such_metric"})
    assert "error" in resp
    assert "available" in resp
    assert "avg_pips" in resp["available"]
    assert "profit_factor" in resp["available"]


# ── dashboard_summary ───────────────────────────────────────────────


def test_dashboard_summary_shape() -> None:
    """dashboard_summary : structure complète attendue pour le dashboard web."""
    resp = _call_mcp("dashboard_summary")
    # Totaux méta
    assert "totals" in resp
    totals = resp["totals"]
    assert "wr_pct" in totals
    assert "profit_factor" in totals
    assert "total_pips" in totals
    assert totals["n_trades"] > 0
    # Compteurs ouverts/fermés
    assert "open_trades" in resp
    assert "closed_trades" in resp
    assert resp["open_trades"] >= 0
    assert resp["closed_trades"] > 0
    # Last snapshot timestamp
    assert "last_snapshot" in resp
    assert resp["last_snapshot"] is not None
    # Top 3 stratégies
    assert "top_3" in resp
    assert len(resp["top_3"]) <= 3
    for seg in resp["top_3"]:
        assert "principle" in seg
        assert "avg_pips" in seg
    # Kill switches
    assert "kill_switches" in resp
    ks = resp["kill_switches"]
    assert "trader_mini" in ks
    assert "shadow_mode" in ks
    assert "execution" in ks
    assert isinstance(ks["trader_mini"], bool)


# ── routing ─────────────────────────────────────────────────────────


def test_extended_tools_listed_in_available() -> None:
    """Les 4 nouveaux tools sont bien enregistrés dans HANDLERS (via unknown_tool)."""
    resp = _call_mcp("unknown_tool_zzz")
    assert "error" in resp
    available = resp["available"]
    for tool in (
        "live_snapshot",
        "pair_breakdown",
        "principle_leaderboard",
        "dashboard_summary",
    ):
        assert tool in available, f"tool {tool!r} manquant dans available"


def test_mcp_hedge_fund_summary() -> None:
    """tool=hedge_fund_summary → dict avec drawdown + risk_parity + meta_metrics."""
    resp = _call_mcp("hedge_fund_summary", {"capital": 10000, "target_vol": 0.15})
    assert "drawdown_protection" in resp
    assert "risk_parity" in resp
    assert "meta_metrics" in resp
    # DD decision
    dd = resp["drawdown_protection"]
    assert dd["decision"]["action"] in ("normal", "reduce_50", "halt_24h", "halt_forever", "pause_5_losses")
    assert 0.0 <= dd["decision"]["position_multiplier"] <= 1.0
    # Risk parity
    rp = resp["risk_parity"]
    assert isinstance(rp["budgets"], list)
    if rp["budgets"]:
        assert all("symbol" in b for b in rp["budgets"])
    # Meta metrics
    meta = resp["meta_metrics"]["totals"]
    assert meta["n_trades"] > 0
    assert 0 <= meta["wr_pct"] <= 100

