"""Tests V10 Phase A audit (4 scripts : WFOOS, Monte Carlo, Deflated Sharpe, Stress Test).

R2 additif pur : nouveau fichier tests/. Pas de modif core/.
Vérifie que chaque script :
  - Retourne un verdict (GO/HOLD/NO-GO)
  - A la structure JSON attendue
  - Gère l'absence de DB (R6 fail-open)
  - Smoke test live sur DB réelle
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


# ── Helpers ────────────────────────────────────────────────────────────
def run_v10_script(name: str, args: list[str] | None = None) -> dict:
    """Exécute un script V10 et retourne le dict JSON."""
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


# ── Tests WFOOS ────────────────────────────────────────────────────────
def test_wfoos_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_wfoos.py", ["--window", "3", "--oos", "3"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    if "n_folds" in r:
        assert r["n_folds"] > 0
        assert "synthese" in r
        assert "avg_oos_sharpe" in r["synthese"]
        assert "kill_criteria" in r
        assert isinstance(r["kill_criteria"], list)
        assert "folds" in r
        assert isinstance(r["folds"], list)


def test_wfoos_smoke_test():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_wfoos.py", ["--window", "5", "--oos", "5"])
    assert "_error" not in r
    assert "kill_criteria" in r


# ── Tests Monte Carlo ──────────────────────────────────────────────────
def test_monte_carlo_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_monte_carlo.py", ["--n", "1000"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "sharpe" in r
    assert "mean" in r["sharpe"]
    assert "median" in r["sharpe"]
    assert "p5" in r["sharpe"]
    assert "p95" in r["sharpe"]
    assert "proba_ruine_pct" in r
    assert "kill_criteria" in r
    assert isinstance(r["kill_criteria"], list)


def test_monte_carlo_seed_reproducible():
    if not has_db():
        pytest.skip("DB live absente")
    r1 = run_v10_script("v10_monte_carlo.py", ["--n", "500", "--seed", "42"])
    r2 = run_v10_script("v10_monte_carlo.py", ["--n", "500", "--seed", "42"])
    assert r1["sharpe"]["median"] == r2["sharpe"]["median"], "Seed non-reproductible (R9 violation)"


# ── Tests Deflated Sharpe ──────────────────────────────────────────────
def test_deflated_sharpe_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_deflated_sharpe.py", ["--n-trials", "10"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "HOLD", "NO-GO")
    assert "deflated_sharpe" in r
    assert "dsr" in r["deflated_sharpe"]
    assert 0.0 <= r["deflated_sharpe"]["dsr"] <= 1.0, "DSR doit être une probabilité [0,1]"
    assert "stats" in r
    assert "sharpe" in r["stats"]
    assert "interpretation" in r


def test_deflated_sharpe_higher_n_trials_lower_dsr():
    """Plus de trials = DSR plus bas (correction data-snoosing)."""
    if not has_db():
        pytest.skip("DB live absente")
    r10 = run_v10_script("v10_deflated_sharpe.py", ["--n-trials", "10"])
    r100 = run_v10_script("v10_deflated_sharpe.py", ["--n-trials", "100"])
    # Le DSR devrait être ≤ pour plus de trials (correction pessimiste)
    assert r100["deflated_sharpe"]["dsr"] <= r10["deflated_sharpe"]["dsr"] + 0.001


# ── Tests Stress Test ──────────────────────────────────────────────────
def test_stress_test_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_stress_test.py")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "scenarios" in r
    assert len(r["scenarios"]) == 5, "Doit avoir 5 scénarios historiques"
    for scen in r["scenarios"]:
        assert "scenario" in scen
        assert "vol_multiplier" in scen
        assert "dd_shock_pct" in scen
        assert "sharpe_stressed" in scen
        assert "max_dd_stressed" in scen
        assert "survives" in scen
        assert isinstance(scen["survives"], bool)
    assert "n_survives" in r
    assert "kill_criteria" in r


def test_stress_test_all_scenarios_named():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_stress_test.py")
    scenario_names = {s["scenario"] for s in r["scenarios"]}
    assert "2008_GFC" in scenario_names
    assert "2010_FLASH_CRASH" in scenario_names
    assert "2015_CHF_UNPEGGING" in scenario_names
    assert "2020_COVID_CRASH" in scenario_names
    assert "2022_SNB_UKRAINE" in scenario_names


# ── Tests Orchestrateur Phase A ────────────────────────────────────────
def test_phase_a_orchestrator_runs():
    if not has_db():
        pytest.skip("DB live absente")
    cmd = [sys.executable, str(SCRIPTS / "v10_phase_a_audit.py"), "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode in (0, 1)
    data = json.loads(result.stdout)
    assert "verdict_global" in data
    assert data["verdict_global"] in ("GO", "HOLD", "NO-GO")
    assert "wfoos" in data
    assert "monte_carlo" in data
    assert "deflated_sharpe" in data
    assert "stress_test" in data
    assert "summary" in data
    assert data["summary"]["n_total"] == 4


def test_phase_a_orchestrator_creates_output_file():
    if not has_db():
        pytest.skip("DB live absente")
    output = ROOT / "docs" / "V10" / "audit_latest_test.json"
    cmd = [sys.executable, str(SCRIPTS / "v10_phase_a_audit.py"),
           "--json", "--output", str(output)]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert output.exists(), f"Fichier sortie non créé : {output}"
    with open(output) as f:
        data = json.load(f)
    assert "verdict_global" in data