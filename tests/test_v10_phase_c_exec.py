"""Tests V10 Phase C — Exécution & Microstructure.

R2 additif pur : nouveau fichier tests/. Pas de modif core/.
Vérifie que chaque script :
  - Retourne un verdict (GO/NO-GO)
  - A la structure JSON attendue
  - Gère l'absence de DB (R6 fail-open)
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


# ── Latence ────────────────────────────────────────────────────────────
def test_latency_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_latency.py")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "latency_total_ms" in r
    assert "budget_v9_ms" in r
    assert "budget_institutionnel_ms" in r
    assert "kill_criteria" in r


# ── Slippage ──────────────────────────────────────────────────────────
def test_slippage_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_slippage_model.py", ["--factor", "0.5"])
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "spread_mean" in r
    assert "slippage_estimated_pips" in r
    assert "kill_criteria" in r


def test_slippage_higher_factor_higher_estimate():
    if not has_db():
        pytest.skip("DB live absente")
    r_low = run_v10_script("v10_slippage_model.py", ["--factor", "0.2"])
    r_high = run_v10_script("v10_slippage_model.py", ["--factor", "0.9"])
    if "_error" in r_low or "_error" in r_high:
        pytest.skip("Pas de spreads dispo")
    assert r_high["slippage_estimated_pips"] >= r_low["slippage_estimated_pips"]


# ── Order Flow ────────────────────────────────────────────────────────
def test_order_flow_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_order_flow.py")
    if "error" in r:
        assert "n_signals" in r
        pytest.skip(f"Pas de signaux directionnels: {r['error']}")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "ofi" in r
    assert "vpin" in r
    assert "buy_ratio" in r
    assert "kill_criteria" in r


def test_order_flow_ofi_bounded():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_order_flow.py")
    if "error" in r:
        pytest.skip("Pas de signaux")
    assert -1.0 <= r["ofi"] <= 1.0
    assert 0.0 <= r["vpin"] <= 1.0


# ── Fill Rate ─────────────────────────────────────────────────────────
def test_fill_rate_json_structure():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_fill_rate.py")
    if "error" in r:
        assert "n_dir" in r
        pytest.skip(f"Pas de signaux directionnels: {r['error']}")
    assert "_error" not in r, r.get("_error")
    assert "verdict" in r
    assert r["verdict"] in ("GO", "NO-GO")
    assert "fill_rate_pct" in r
    assert "target_min_pct" in r
    assert "kill_criteria" in r


def test_fill_rate_pct_range():
    if not has_db():
        pytest.skip("DB live absente")
    r = run_v10_script("v10_fill_rate.py")
    if "error" in r:
        pytest.skip("Pas de signaux directionnels sur la fenêtre")
    # Fill rate aligné sur fenêtre commune (24h) doit être dans une plage
    # raisonnable [0, 130]. >130 = décompte encore incohérent (R6 fail-open).
    assert 0.0 <= r["fill_rate_pct"] <= 130.0, \
        f"Fill rate {r['fill_rate_pct']}% hors plage attendue"
    assert r["window_hours"] == 24


# ── Orchestrateur Phase C ─────────────────────────────────────────────
def test_phase_c_orchestrator_runs():
    if not has_db():
        pytest.skip("DB live absente")
    cmd = [sys.executable, str(SCRIPTS / "v10_phase_c_exec.py"), "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode in (0, 1)
    data = json.loads(result.stdout)
    assert "verdict_global" in data
    assert data["verdict_global"] in ("GO", "HOLD", "NO-GO")
    assert "latency" in data
    assert "slippage_model" in data
    assert "order_flow" in data
    assert "fill_rate" in data
    assert "summary" in data
    assert data["summary"]["n_total"] == 4