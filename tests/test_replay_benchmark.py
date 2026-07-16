"""Tests — scripts/v9_replay_benchmark.py (DIVERSIFY Chantier C).

Tests des fonctions pures de reporting (sans fixture DB lourde). Le chemin
run_benchmark est validé manuellement sur la base réelle (lecture seule).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_replay_benchmark as bench  # noqa: E402


def test_pct_basic():
    assert bench._pct(1, 2) == "50.0%"
    assert bench._pct(0, 0) == "n/a"
    assert bench._pct(87, 100) == "87.0%"


def _fake_result():
    return {
        "sample_size": 600,
        "baseline": {
            "n": 8593,
            "with_price_lag": 8225,
            "top": [("PRICE_LAG_AT_NODE_BIRTH", 8225), ("ZONE_RETEST", 299)],
        },
        "after": {
            "n_signals": 600,
            "n_directional": 234,
            "n_with_price_lag": 204,
            "n_fusion_applied": 201,
            "fusion_rules": {"boost_high_plus_partner": 201},
            "contributors": [("PRICE_LAG_AT_NODE_BIRTH", 204)] + [(f"P{i}", 120) for i in range(12)],
        },
    }


def test_render_report_contains_kpi_and_shares():
    report = bench.render_report(_fake_result())
    assert "Benchmark diversification" in report
    assert "95.7%" in report          # part PRICE_LAG avant
    assert "87.2%" in report          # part PRICE_LAG après
    assert "KPI mission" in report
    # 13 contributeurs > 100 dans le fake (PRICE_LAG + 12 P{i})
    assert "**13**" in report


def test_render_report_handles_empty_after():
    result = _fake_result()
    result["after"]["n_directional"] = 0
    result["after"]["contributors"] = []
    report = bench.render_report(result)
    assert "n/a" in report  # part après = n/a quand 0 signal directionnel
