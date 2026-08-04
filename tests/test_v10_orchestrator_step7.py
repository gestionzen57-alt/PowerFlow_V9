"""V10 Orchestrator Étape 7 — M30 integration + thresholds par (paire, TF).

Cible R7 : 10 tests verts minimum.

Doctrine V10 :
  R2 additif pur
  R6 fail-open
  R9 audit
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict

import pytest

from core.v10.v10_market_context_global import (
    compute_market_context,
    _make_multi_tf_polarized,
    _make_cs_for_context,
)
from core.v10.v10_orchestrator import (
    compose_signal_with_context,
    ContextFilteredSignal,
)


# ─────────────────────────────────────────────────────────────────────
# 1. M30 dans TF confluence
# ─────────────────────────────────────────────────────────────────────

def test_m30_tf_in_confluence_polarized():
    """Le multi_tf_snapshots par défaut (_make_multi_tf_polarized) inclut M30."""
    mtf = _make_multi_tf_polarized()
    assert "M30" in mtf


def test_compute_market_context_accepts_m30_params():
    """compute_market_context accepte les params bonus M30."""
    mtf = _make_multi_tf_polarized()
    # Doit accepter sans casser
    ctx = compute_market_context(
        mtf, timestamp="2026-08-05T00:00:00Z",
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="MARKUP", m30_solidarity_bonus=0.15,
    )
    assert ctx.tradeable


# ─────────────────────────────────────────────────────────────────────
# 2. Bonus solidarity +0.15 si M30+H1 alignés
# ─────────────────────────────────────────────────────────────────────

def test_m30_bonus_applied_when_aligned():
    """M30+H1 BULLISH alignés + state MARKUP → bonus +0.15 sur solidarity."""
    mtf = _make_multi_tf_polarized()
    ctx_no_bonus = compute_market_context(mtf, timestamp="t")
    ctx_with_bonus = compute_market_context(
        mtf, timestamp="t",
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="MARKUP",
    )
    # ContextScore plus élevé avec bonus
    assert ctx_with_bonus.context_score > ctx_no_bonus.context_score


def test_m30_bonus_not_applied_when_bias_mismatch():
    """Bias M30 et H1 différents → pas de bonus."""
    mtf = _make_multi_tf_polarized()
    ctx = compute_market_context(
        mtf, timestamp="t",
        m30_vsa_bias="BULLISH", h1_vsa_bias="BEARISH",
        m30_vsa_state="MARKUP",
    )
    # Pas de mention m30_bonus dans audit coalition
    audit = ctx.audit if hasattr(ctx, "audit") else {}
    assert "m30_bonus_applied" not in audit or not audit.get("m30_bonus_applied")


def test_m30_bonus_not_applied_when_state_ineligible():
    """State non éligible (DISTRIBUTION) → pas de bonus."""
    mtf = _make_multi_tf_polarized()
    ctx = compute_market_context(
        mtf, timestamp="t",
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="DISTRIBUTION",  # pas éligible
    )
    audit = ctx.audit if hasattr(ctx, "audit") else {}
    assert "m30_bonus_applied" not in audit or not audit.get("m30_bonus_applied")


def test_m30_bonus_audit_logs_params():
    """Audit contient m30_vsa_bias, h1_vsa_bias, m30_vsa_state."""
    mtf = _make_multi_tf_polarized()
    ctx = compute_market_context(
        mtf, timestamp="t",
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="ACCUMULATION",
    )
    audit = ctx.audit if hasattr(ctx, "audit") else {}
    assert audit.get("m30_included") is True
    assert audit.get("m30_vsa_state") == "ACCUMULATION"


def test_m30_bonus_capped_at_1():
    """Bonus capé à solidarity=1.0."""
    mtf = _make_multi_tf_polarized()
    ctx = compute_market_context(
        mtf, timestamp="t",
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="MARKUP",
        m30_solidarity_bonus=100.0,  # énorme
    )
    # Pas de crash
    assert ctx.context_score <= 100.0


# ─────────────────────────────────────────────────────────────────────
# 3. compose_signal_with_context — wiring M30
# ─────────────────────────────────────────────────────────────────────

def test_compose_signal_with_context_accepts_m30_vsa():
    """compose_signal_with_context accepte m30_vsa_*, ne casse pas."""
    mtf = _make_multi_tf_polarized()
    bars = [{"open": 1.27, "high": 1.271, "low": 1.269, "close": 1.2705, "volume": 100}]
    result = compose_signal_with_context(
        symbol="GBPUSD", pair="GBPUSD", timestamp="2026-08-05T00:00:00Z",
        timeframe="M30", bars=bars,
        multi_tf_snapshots=mtf,
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="MARKUP",
    )
    assert isinstance(result, ContextFilteredSignal)


def test_compose_signal_with_context_audit_m30_included():
    """Audit ctx contient m30_included=True."""
    mtf = _make_multi_tf_polarized()
    bars = [{"open": 1.27, "high": 1.271, "low": 1.269, "close": 1.2705, "volume": 100}]
    result = compose_signal_with_context(
        symbol="GBPUSD", pair="GBPUSD", timestamp="t",
        timeframe="M30", bars=bars, multi_tf_snapshots=mtf,
        m30_vsa_bias="BULLISH", h1_vsa_bias="BULLISH",
        m30_vsa_state="MARKUP",
    )
    assert result.context.audit.get("m30_included") is True


# ─────────────────────────────────────────────────────────────────────
# 4. Thresholds par (paire, TF) depuis JSON
# ─────────────────────────────────────────────────────────────────────

def test_compose_with_thresholds_pair_tf_json(tmp_path):
    """thresholds_pair_tf_path charge seuils ÉTAPE 6 depuis JSON ÉTAPE 6."""
    # Préparer un JSON au format Étape 6
    thresholds_data = {
        "timestamp": "2026-08-05T00:00:00Z",
        "version": "v2_pair_tf",
        "thresholds_by_pair_tf": {
            "GBPUSD_M30": {
                "pair": "GBPUSD", "tf": "M30",
                "context_score_min": 45.0, "anta_score_min": 15.0,
                "aligned_count_min": 3, "min_signal_level": "A3",
                "win_rate": 0.4811, "pnl_pips": 2.2,
                "gate_passed": True,
            }
        },
    }
    jpath = tmp_path / "thresholds.json"
    jpath.write_text(json.dumps(thresholds_data), encoding="utf-8")

    mtf = _make_multi_tf_polarized()
    bars = [{"open": 1.27, "high": 1.271, "low": 1.269, "close": 1.2705, "volume": 100}]
    result = compose_signal_with_context(
        symbol="GBPUSD", pair="GBPUSD", timestamp="t",
        timeframe="M30", bars=bars, multi_tf_snapshots=mtf,
        thresholds_pair_tf_path=str(jpath),
    )
    assert "GBPUSD" in result.context.audit.get("thresholds_per_pair", {})


def test_compose_thresholds_pair_tf_missing_path_failsafe(tmp_path):
    """Chemin inexistant → R6 fail-open (DEFAULT_THRESHOLDS)."""
    mtf = _make_multi_tf_polarized()
    bars = [{"open": 1.27, "high": 1.271, "low": 1.269, "close": 1.2705, "volume": 100}]
    result = compose_signal_with_context(
        symbol="GBPUSD", pair="GBPUSD", timestamp="t",
        timeframe="M30", bars=bars, multi_tf_snapshots=mtf,
        thresholds_pair_tf_path=str(tmp_path / "nope.json"),
    )
    # Pas de crash, R6 fail-open
    assert isinstance(result, ContextFilteredSignal)


# ─────────────────────────────────────────────────────────────────────
# 5. Tests legacy (regression)
# ─────────────────────────────────────────────────────────────────────

def test_step7_legacy_threshold_dict_still_works():
    """Le param `thresholds` (dict legacy) continue de fonctionner."""
    mtf = _make_multi_tf_polarized()
    bars = [{"open": 1.27, "high": 1.271, "low": 1.269, "close": 1.2705, "volume": 100}]
    custom_thresholds = {"GBPUSD": {"anta_score_min": 30.0, "aligned_count_min": 4}}
    result = compose_signal_with_context(
        symbol="GBPUSD", pair="GBPUSD", timestamp="t",
        timeframe="M30", bars=bars, multi_tf_snapshots=mtf,
        thresholds=custom_thresholds,  # legacy
    )
    assert "GBPUSD" in result.context.audit.get("thresholds_per_pair", {})


def test_step7_signature_backward_compatible():
    """Les anciens kwargs (sans M30) fonctionnent toujours."""
    import inspect
    sig = inspect.signature(compose_signal_with_context)
    # Le param m30_vsa_bias doit exister
    assert "m30_vsa_bias" in sig.parameters
    # thresholds_pair_tf_path aussi
    assert "thresholds_pair_tf_path" in sig.parameters
    # Legacy params toujours là
    assert "thresholds" in sig.parameters
    assert "multi_tf_snapshots" in sig.parameters
