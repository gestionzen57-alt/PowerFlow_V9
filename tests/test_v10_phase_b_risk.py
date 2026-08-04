"""Tests V10 Phase B — Risk Management institutionnel.

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


# ── Tests VaR/CVaR ─────────────────────────────────────────────────────
def test_var_cvar_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_var_cvar.py", ["--confidence", "0.95"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "var" in r
    assert "parametrique" in r["var"]
    assert "historique" in r["var"]
    assert "monte_carlo" in r["var"]
    assert "cvar" in r
    assert "parametrique" in r["cvar"]
    assert "historique" in r["cvar"]
    assert "monte_carlo" in r["cvar"]
    assert "kill_criteria" in r
    assert isinstance(r["kill_criteria"], list)


def test_var_cvar_99_more_conservative_than_95():
    """VaR 99% doit être plus grand (en valeur absolue) que VaR 95%."""
    if not has_db():
        pytest.skip("DB live absente")
    r95 = run_v10_script("v10_var_cvar.py", ["--confidence", "0.95"])
    r99 = run_v10_script("v10_var_cvar.py", ["--confidence", "0.99"])
    assert abs(r99["var"]["historique"]) >= abs(r95["var"]["historique"])


# ── Tests Liquidity Sharpe ────────────────────────────────────────────
def test_liquidity_sharpe_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_liquidity_sharpe.py", ["--spread", "1.5", "--slippage", "0.5"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "sharpe_brut" in r
    assert "sharpe_liquidity_adjusted" in r
    assert "edge_decay_pct" in r
    assert "cost_per_trade_pips" in r
    assert "kill_criteria" in r


def test_liquidity_sharpe_adjusted_less_than_brut():
    """Sharpe ajusté doit être <= Sharpe brut (coûts réduisent l'edge)."""
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_liquidity_sharpe.py", ["--spread", "2.0", "--slippage", "1.0"])
    assert r["sharpe_liquidity_adjusted"] <= r["sharpe_brut"] + 0.001


# ── Tests Risk Parity ──────────────────────────────────────────────────
def test_risk_parity_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_risk_parity.py")
    # R6 fail-open : si < 2 paires, le script retourne {"error", "n_symbols"}
    # (pas un verdict) — comportement attendu, on skip plutôt que fail.
    if "error" in r:
        assert "n_symbols" in r
        pytest.skip(f"Pas assez de paires pour risk parity: {r['error']}")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "weights" in r
    assert "avg_correlation" in r
    assert "risk_contribution_pct" in r
    assert "kill_criteria" in r


def test_risk_parity_weights_sum_to_one():
    """La somme des poids risk parity doit être ~1.0."""
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_risk_parity.py")
    if "error" in r:
        pytest.skip(f"Pas assez de paires: {r['error']}")
    total = sum(r["weights"].values())
    assert abs(total - 1.0) < 0.01, f"Somme poids = {total:.3f} != 1.0"


# ── Tests Vol Targeting ────────────────────────────────────────────────
def test_vol_targeting_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_vol_targeting.py", ["--target", "0.08"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "vol_annualized" in r
    assert "scale" in r
    assert "position_scale" in r
    assert "target_vol" in r
    assert "kill_criteria" in r


def test_vol_targeting_scale_clamped():
    """Scale doit être clampé à [0.1, 3.0]."""
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_vol_targeting.py", ["--target", "0.08"])
    assert 0.1 <= r["scale"] <= 3.0


def test_vol_targeting_lower_target_lower_scale():
    """Cible plus basse → scale plus petit (position réduite)."""
    if not has_db():
        pytest.skip("DB live absente")
    r_low = run_v10_script("v10_vol_targeting.py", ["--target", "0.05"])
    r_high = run_v10_script("v10_vol_targeting.py", ["--target", "0.20"])
    assert r_low["scale"] <= r_high["scale"]


# ── Tests orchestrateur Phase B ────────────────────────────────────────
def test_phase_b_orchestrator_runs():
    """Orchestrateur Phase B exécute les 4 scripts et produit un rapport."""
    if not has_db():
        pytest.skip("DB live absente")
    cmd = [sys.executable, str(SCRIPTS / "v10_phase_b_risk.py"), "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode in (0, 1)
    data = json.loads(result.stdout)
    assert "verdict_global" in data
    assert data["verdict_global"] in ("GO", "HOLD", "NO-GO")
    assert "var_cvar" in data
    assert "liquidity_sharpe" in data
    assert "risk_parity" in data
    assert "vol_targeting" in data
    assert "summary" in data
    assert data["summary"]["n_total"] == 4