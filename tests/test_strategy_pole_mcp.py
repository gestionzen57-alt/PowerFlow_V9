"""Tests pour le MCP server du pôle stratégie V9.

2026-07-17 motion CEO « continue optimiser au max ».
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MCP_PATH = ROOT / "mcp_servers" / "strategy_pole_server.py"


def _call_mcp(tool: str, args: dict | None = None, timeout: int = 30) -> dict:
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
    # Première ligne = {"ready": True}, deuxième = réponse
    assert len(lines) >= 2, f"MCP a retourné <2 lignes: {proc.stdout}"
    return json.loads(lines[1])


def test_mcp_meta_returns_totals() -> None:
    """tool=meta → dict avec section totals."""
    resp = _call_mcp("meta")
    assert "totals" in resp
    totals = resp["totals"]
    assert "n_trades" in totals
    assert totals["n_trades"] > 0
    assert 0 <= totals["wr_pct"] <= 100


def test_mcp_catalogue_returns_segments() -> None:
    """tool=catalogue → liste de segments."""
    resp = _call_mcp("catalogue", {"min_n": 20})
    assert resp["count"] >= 1
    assert isinstance(resp["segments"], list)
    assert len(resp["segments"]) == resp["count"]


def test_mcp_top_returns_best_first() -> None:
    """tool=top → trié par métrique décroissante."""
    resp = _call_mcp("top", {"n": 3, "by": "avg_pips", "min_n": 20})
    assert resp["by"] == "avg_pips"
    assert resp["count"] >= 1
    segs = resp["segments"]
    for a, b in zip(segs, segs[1:]):
        assert a["avg_pips"] >= b["avg_pips"]


def test_mcp_recommend_valid_segment() -> None:
    """tool=recommend pour PRICE_LAG_AT_NODE_BIRTH new_york NEUTRE."""
    resp = _call_mcp("recommend", {
        "principle": "PRICE_LAG_AT_NODE_BIRTH",
        "session": "new_york",
        "regime": "NEUTRE",
    })
    assert resp["principle"] == "PRICE_LAG_AT_NODE_BIRTH"
    assert resp["recommended_tp"] > 0
    assert resp["recommended_sl"] > 0
    assert resp["recommended_strategy"] in ("TP_SL", "TRAILING")
    assert 0 <= resp["confidence"] <= 1


def test_mcp_recommend_fallback_unknown() -> None:
    """tool=recommend pour un segment inconnu → fallback."""
    resp = _call_mcp("recommend", {
        "principle": "UNKNOWN_PRINCIPE_XYZ",
        "session": "unknown_session",
        "regime": "UNKNOWN",
    })
    assert resp["source"] == "default"
    assert resp["recommended_tp"] == 10.0
    assert resp["recommended_sl"] == 15.0


def test_mcp_recommend_missing_args() -> None:
    """tool=recommend sans args → erreur explicite."""
    resp = _call_mcp("recommend", {"principle": "P"})
    assert "error" in resp


def test_mcp_unknown_tool() -> None:
    """tool=unknown → erreur avec liste des tools disponibles."""
    resp = _call_mcp("unknown_tool_xyz")
    assert "error" in resp
    assert "available" in resp
    assert "meta" in resp["available"]


def test_mcp_tune_no_apply() -> None:
    """tool=tune apply=False → grid search sans écrire config."""
    resp = _call_mcp("tune", {"min_n": 20, "apply": False})
    assert resp["count"] >= 1
    assert "overrides_path" not in resp  # pas d'écriture
    assert "best_tp" in resp["segments"][0]


def test_mcp_save_catalogue() -> None:
    """tool=save_catalogue → chemin du fichier sauvegardé."""
    resp = _call_mcp("save_catalogue", {"min_n": 20})
    assert "path" in resp
    assert Path(resp["path"]).exists()