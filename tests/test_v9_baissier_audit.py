"""Tests pour v9_strategy_compare et v9_sl_tp_grid_search.

2026-07-17 motion CEO « test different strategie de gestion ».

Ces tests valident que les scripts d'audit tournent et retournent des
résultats cohérents (sans valider les chiffres exacts qui dépendent de la DB).

NOTE : ces tests invoquent des scripts qui prennent 30-60s chacun
(mark `slow` pour les skipper en CI rapide).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_GRID = ROOT / "scripts" / "v9_sl_tp_grid_search.py"
SCRIPT_COMPARE = ROOT / "scripts" / "v9_strategy_compare.py"
SCRIPT_V3 = ROOT / "scripts" / "v9_strategy_v3.py"

slow = pytest.mark.slow


def _run_script(script: Path, timeout: int = 180) -> dict:
    """Invoque le mode machine-readable d'un script et retourne son JSON."""
    p = subprocess.run(
        [sys.executable, str(script), "--json"],
        capture_output=True, text=True, timeout=timeout, cwd=str(ROOT),
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"{script.name} exited {p.returncode}: {p.stderr[-500:]}"
        )
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"invalid JSON in {script.name}: {p.stdout[-500:]}"
        ) from exc


@slow
def test_sl_tp_grid_search_returns_results() -> None:
    """Grid search doit retourner au moins 100 combinaisons."""
    r = _run_script(SCRIPT_GRID)
    assert "results" in r
    assert "n_combos" in r
    assert r["n_combos"] >= 100
    # Toutes les combinaisons ont les bons champs
    for res in r["results"][:5]:
        assert "tp" in res
        assert "sl" in res
        assert "strategy" in res
        assert "wr_pct" in res
        assert "total_pips" in res


@slow
def test_sl_tp_grid_search_baseline_exists() -> None:
    """Le baseline (TP=8, SL=15, TP_SL) doit être dans les résultats."""
    r = _run_script(SCRIPT_GRID)
    baseline = next(
        (res for res in r["results"]
         if res["tp"] == 8 and res["sl"] == 15 and res["strategy"] == "TP_SL"),
        None,
    )
    assert baseline is not None
    # WR doit être faible (baissier perd)
    assert baseline["wr_pct"] < 5.0
    assert baseline["total_pips"] < 0  # négatif


@slow
def test_sl_tp_grid_search_export_file_exists() -> None:
    """Le grid search doit exporter un fichier JSON."""
    out = ROOT / "data" / "strategy_pole" / "sl_tp_grid_search.json"
    assert out.exists(), f"Fichier manquant : {out}"


@slow
def test_strategy_compare_returns_all_strategies() -> None:
    """strategy_compare doit retourner 6 stratégies."""
    r = _run_script(SCRIPT_COMPARE)
    assert "results" in r
    assert len(r["results"]) >= 5
    # Vérifie que les 4 stratégies principales sont présentes
    names = [res["strategy"] for res in r["results"]]
    assert any("BASELINE" in n for n in names)
    assert any("ASYMMETRIC" in n for n in names)
    assert any("TIME_EXIT" in n for n in names)
    assert any("TRAILING" in n for n in names)


@slow
def test_strategy_compare_baseline_worst() -> None:
    """Le baseline doit être le plus perdant (ou proche)."""
    r = _run_script(SCRIPT_COMPARE)
    sorted_by_total = sorted(r["results"], key=lambda x: -x["total_pips"])
    best = sorted_by_total[0]
    worst = sorted_by_total[-1]
    # Le baseline (TP=8/SL=15) doit être au moins proche du pire
    baseline = next((x for x in r["results"] if "BASELINE" in x["strategy"]), None)
    assert baseline is not None
    # Le baseline doit être dans le bottom 50% (puisqu'on a vu qu'il perd)
    n = len(r["results"])
    baseline_rank = sorted_by_total.index(baseline)
    assert baseline_rank >= n // 2, (
        f"Baseline rank={baseline_rank}/{n} devrait être dans le bottom 50% "
        f"(pire que la médiane). Total={baseline['total_pips']}, "
        f"best={best['total_pips']}, worst={worst['total_pips']}"
    )


@slow
def test_strategy_v3_finds_best_short_strategy() -> None:
    """v3 doit trouver au moins 1 stratégie avec avg_pips > -5 (amélioration)."""
    r = _run_script(SCRIPT_V3, timeout=240)
    assert "results" in r
    assert len(r["results"]) >= 30
    # Au moins une stratégie doit avoir avg_pips > -5 (vs baseline -15.40)
    improved = [res for res in r["results"] if res["avg_pips"] > -5.0]
    assert len(improved) >= 1, (
        "Aucune stratégie n'améliore le baseline (avg_pips > -5). "
        "Le grid search n'a rien trouvé d'utile."
    )
    # Le top doit avoir total_pips > baseline (-56680)
    top = sorted(r["results"], key=lambda x: -x["total_pips"])[0]
    assert top["total_pips"] > -56680, (
        f"Meilleure stratégie {top['total_pips']} doit être > baseline -56680"
    )


def test_baissier_audit_final_json_exists() -> None:
    """Le rapport final d'audit baissier doit exister."""
    out = ROOT / "data" / "strategy_pole" / "baissier_audit_final.json"
    assert out.exists(), f"Rapport manquant : {out}"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "decouverte_principale" in data
    assert "recommandations" in data