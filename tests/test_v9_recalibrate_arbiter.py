#!/usr/bin/env python3
"""test_v9_recalibrate_arbiter.py — Tests recalibrage arbiter V9."""

from __future__ import annotations

import json
import sqlite3
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest

from scripts.v9_recalibrate_arbiter import (
    _aggregate,
    _propose_adjustment,
    _build_report,
    CURRENT_WEIGHTS,
)


# ── _propose_adjustment ───────────────────────────────────────────────
def test_propose_adjustment_below_significance() -> None:
    bucket = {"n": 10, "wins": 5, "losses": 5, "pips_total": 0.0}
    res = _propose_adjustment(bucket, 5, -3, min_decisions=50)
    assert res["proposed"] is False
    assert "significance" in res["reason"]


def test_propose_adjustment_hr_low_increase_weight() -> None:
    """HR 30% (< 60%) → boost insuffisant, on propose d'augmenter le poids.

    Logique : HR < target 75% → delta_hr négatif → proposed_delta = -delta_hr * 0.3 → positif.
    Cas d'usage : 'naissance' sous-performe → on suggère d'augmenter son boost.
    """
    bucket = {"n": 100, "wins": 30, "losses": 70, "pips_total": -200.0}
    res = _propose_adjustment(bucket, +5, None, min_decisions=50)
    assert res["proposed"] is True
    assert res["hr_pct"] == 30.0
    assert res["proposed_delta"] > 0  # HR < target → on remonte le poids


def test_propose_adjustment_hr_high_decrease_weight() -> None:
    """HR 95% (> 75%) → boost trop généreux, on propose de le réduire.

    Cas d'usage : 'zone neutre' HR 98% sans boost → inutile d'ajouter du poids.
    """
    bucket = {"n": 100, "wins": 95, "losses": 5, "pips_total": 500.0}
    res = _propose_adjustment(bucket, +5, None, min_decisions=50)
    assert res["proposed"] is True
    assert res["proposed_delta"] < 0  # HR > target → on baisse le poids


def test_propose_adjustment_bounds_clamped() -> None:
    """HR 100% → on pourrait proposer +25 mais clampé à +15."""
    bucket = {"n": 100, "wins": 100, "losses": 0, "pips_total": 1000.0}
    res = _propose_adjustment(bucket, 0, 0, min_decisions=50)
    assert res["proposed_delta"] <= 15
    assert res["proposed_delta"] >= -15


# ── _aggregate ────────────────────────────────────────────────────────
def test_aggregate_groups_by_zone_session() -> None:
    decisions = [
        {"zone_type": "neutre", "session": "asie", "is_win": True, "pips": 5.0},
        {"zone_type": "neutre", "session": "asie", "is_win": False, "pips": -2.0},
        {"zone_type": "naissance", "session": "london", "is_win": True, "pips": 8.0},
    ]
    agg = _aggregate(decisions)
    assert agg[("neutre", "asie")]["n"] == 2
    assert agg[("neutre", "asie")]["wins"] == 1
    assert agg[("naissance", "london")]["n"] == 1


def test_aggregate_handles_unknown_zone() -> None:
    decisions = [{"zone_type": None, "session": "asie", "is_win": True, "pips": 1.0}]
    agg = _aggregate(decisions)
    assert agg[("unknown", "asie")]["n"] == 1


# ── _build_report ─────────────────────────────────────────────────────
def test_build_report_wr_global() -> None:
    decisions = [
        {"zone_type": "neutre", "session": "asie", "is_win": True, "pips": 5.0},
        {"zone_type": "neutre", "session": "asie", "is_win": True, "pips": 3.0},
        {"zone_type": "neutre", "session": "asie", "is_win": False, "pips": -2.0},
    ]
    report = _build_report(decisions, min_decisions=2)
    assert report["n_total_decisions"] == 3
    assert report["n_won"] == 2
    assert abs(report["wr_global_pct"] - 66.67) < 0.1
    assert "buckets" in report
    assert CURRENT_WEIGHTS == report["current_weights_reference"]


def test_build_report_empty_input() -> None:
    report = _build_report([], min_decisions=50)
    assert report["n_total_decisions"] == 0
    assert report["wr_global_pct"] == 0.0
    assert report["buckets"] == []
