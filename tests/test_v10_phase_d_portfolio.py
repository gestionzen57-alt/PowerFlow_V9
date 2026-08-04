"""Tests V10 Phase D — Multi-stratégie & Portfolio.

R2 additif pur : nouveau fichier tests/. Pas de modif core/.
Vérifie que chaque script retourne un verdict + structure JSON + R6.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run_v10_script(name: str, args: list[str] | None = None) -> dict:
    cmd = [sys.executable, str(SCRIPTS / name)]
    if args:
        cmd.extend(args)
    cmd.append("--json")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if not result.stdout.strip():
        return {"_error": f"empty stdout, stderr={result.stderr[-500:]}"}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"_error": f"JSON decode: {e}", "stdout_tail": result.stdout[-300:]}


def has_db() -> bool:
    return (ROOT / "data" / "v9_forces.db").exists()


# ── Kelly ──────────────────────────────────────────────────────────────
def test_kelly_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_kelly.py", ["--fraction", "0.5"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "win_rate" in r
    assert "payoff_ratio" in r
    assert "kelly_clamped" in r
    assert "kelly_recommended_pct" in r
    assert "kill_criteria" in r


def test_kelly_clamped_range():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_kelly.py", ["--fraction", "0.5"])
    assert 0.0 <= r["kelly_clamped"] <= 1.0


# ── Black-Litterman ───────────────────────────────────────────────────
def test_black_litterman_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_black_litterman.py")
    if "error" in r:
        pytest.skip(f"Pas de perf par principe: {r['error']}")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "combined_weights" in r
    assert "prior_weights" in r
    assert "view_weights" in r
    assert "hhi_concentration" in r
    assert "kill_criteria" in r


def test_black_litterman_weights_sum_to_one():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_black_litterman.py")
    if "error" in r:
        pytest.skip("Pas de perf")
    total = sum(r["combined_weights"].values())
    assert abs(total - 1.0) < 0.01


# ── Corrélation ───────────────────────────────────────────────────────
def test_correlation_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_correlation.py")
    if "error" in r:
        pytest.skip(f"Pas assez de stratégies: {r['error']}")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "avg_correlation" in r
    assert "min_correlation" in r
    assert "max_correlation" in r
    assert "kill_criteria" in r


def test_correlation_avg_bounded():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_correlation.py")
    if "error" in r:
        pytest.skip("Pas de corrélation")
    assert -1.0 <= r["avg_correlation"] <= 1.0


# ── Risk Budget ───────────────────────────────────────────────────────
def test_risk_budget_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_risk_budget.py", ["--target-vol", "0.08", "--max-dd", "0.05"])
    if "error" in r:
        pytest.skip(f"Pas de stratégie: {r['error']}")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "vol_by_strategy" in r
    assert "risk_budget" in r
    assert "total_risk_budget" in r
    assert "kill_criteria" in r


def test_risk_budget_positive():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_risk_budget.py", ["--target-vol", "0.08"])
    if "error" in r:
        pytest.skip("Pas de stratégie")
    assert all(v >= 0 for v in r["risk_budget"].values())


# ── Orchestrateur Phase D ─────────────────────────────────────────────
def test_phase_d_orchestrator_runs():
    if not has_db():
        pytest.skip("DB live absente")
    cmd = [sys.executable, str(SCRIPTS / "v10_phase_d_portfolio.py"), "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode in (0, 1)
    data = json.loads(result.stdout)
    assert "verdict_global" in data
    assert data["verdict_global"] in ("GO", "HOLD", "NO-GO")
    assert "kelly" in data
    assert "black_litterman" in data
    assert "correlation" in data
    assert "risk_budget" in data
    assert "summary" in data
    assert data["summary"]["n_total"] == 4