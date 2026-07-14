"""Tests — core/v9/trader_mini_weigher.py (Brief Q1, 2026-07-12).

Même garde-fous que le PrincipleScorer/O2 : kill switch OFF par défaut,
neutre en cas de modèle absent/contexte indisponible, bornes dures jamais
dépassées, ne lève jamais.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.v9.trader_mini_weigher import (
    PROBA_LOSS_THRESHOLD,
    PROBA_WIN_THRESHOLD,
    TRADER_MINI_ENABLED_ENV,
    TRADER_MINI_MULT_BOUNDS,
    TRADER_MINI_MULT_LOSS,
    TRADER_MINI_MULT_NEUTRAL,
    TRADER_MINI_MULT_WIN,
    TraderMiniWeigher,
    trader_mini_enabled,
)


def _fake_model_path(tmp_path: Path, weights: list[float], bias: float, schema: dict) -> Path:
    p = tmp_path / "fake_model.json"
    p.write_text(json.dumps({
        "version": "test", "weights": weights, "bias": bias, "schema": schema,
    }), encoding="utf-8")
    return p


def test_trader_mini_enabled_by_default():
    """V9_TRADER_MINI_ENABLED=1 (activé 2026-07-14)."""
    assert trader_mini_enabled() is True


def test_trader_mini_enabled_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    assert trader_mini_enabled() is True


def test_weigher_kill_switch_off_returns_neutral_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "0")
    schema = {"heure_utc": {"type": "numeric"}}
    model_path = _fake_model_path(tmp_path, [1.0], 0.0, schema)
    weigher = TraderMiniWeigher(model_path=model_path)
    conn = sqlite3.connect(":memory:")
    mult, basis = weigher.compute_multiplier("snap1", conn)
    assert mult == TRADER_MINI_MULT_NEUTRAL
    assert basis == "disabled"


def test_weigher_enabled_but_model_missing_returns_no_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    weigher = TraderMiniWeigher(model_path=tmp_path / "does_not_exist.json")
    conn = sqlite3.connect(":memory:")
    mult, basis = weigher.compute_multiplier("snap1", conn)
    assert mult == TRADER_MINI_MULT_NEUTRAL
    assert basis == "no_model"


def test_weigher_corrupt_model_file_returns_no_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    p = tmp_path / "corrupt.json"
    p.write_text("{not valid json", encoding="utf-8")
    weigher = TraderMiniWeigher(model_path=p)
    conn = sqlite3.connect(":memory:")
    mult, basis = weigher.compute_multiplier("snap1", conn)
    assert mult == TRADER_MINI_MULT_NEUTRAL
    assert basis == "no_model"


class _FakeEngine:
    """Simule PrincipleEngine._load_shared_context sans DB réelle."""
    def __init__(self, context: dict) -> None:
        self._context = context

    def _load_shared_context(self, conn, snapshot_id):
        return {"context": dict(self._context)}


def test_weigher_predicted_loss_below_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    schema = {"x": {"type": "numeric"}}
    # bias très négatif -> sigmoid proche de 0 -> proba(win) sous le seuil LOSS.
    model_path = _fake_model_path(tmp_path, [0.0], -10.0, schema)
    weigher = TraderMiniWeigher(model_path=model_path)
    conn = sqlite3.connect(":memory:")
    engine = _FakeEngine({"x": 1.0})
    mult, basis = weigher.compute_multiplier("snap1", conn, principle_engine=engine)
    assert basis == "predicted_loss"
    assert mult == TRADER_MINI_MULT_LOSS


def test_weigher_predicted_win_above_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    schema = {"x": {"type": "numeric"}}
    # bias très positif -> sigmoid proche de 1 -> proba(win) au-dessus du seuil WIN.
    model_path = _fake_model_path(tmp_path, [0.0], 10.0, schema)
    weigher = TraderMiniWeigher(model_path=model_path)
    conn = sqlite3.connect(":memory:")
    engine = _FakeEngine({"x": 1.0})
    mult, basis = weigher.compute_multiplier("snap1", conn, principle_engine=engine)
    assert basis == "predicted_win"
    assert mult == TRADER_MINI_MULT_WIN


def test_weigher_neutral_zone_between_thresholds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    schema = {"x": {"type": "numeric"}}
    # bias=0 -> sigmoid(0)=0.5, strictement entre PROBA_LOSS_THRESHOLD et
    # PROBA_WIN_THRESHOLD -> neutre.
    assert PROBA_LOSS_THRESHOLD < 0.5 < PROBA_WIN_THRESHOLD
    model_path = _fake_model_path(tmp_path, [0.0], 0.0, schema)
    weigher = TraderMiniWeigher(model_path=model_path)
    conn = sqlite3.connect(":memory:")
    engine = _FakeEngine({"x": 1.0})
    mult, basis = weigher.compute_multiplier("snap1", conn, principle_engine=engine)
    assert basis == "neutral"
    assert mult == TRADER_MINI_MULT_NEUTRAL


def test_weigher_context_unavailable_never_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(TRADER_MINI_ENABLED_ENV, "1")
    schema = {"x": {"type": "numeric"}}
    model_path = _fake_model_path(tmp_path, [0.0], 0.0, schema)
    weigher = TraderMiniWeigher(model_path=model_path)
    conn = sqlite3.connect(":memory:")

    class _RaisingEngine:
        def _load_shared_context(self, conn, snapshot_id):
            raise RuntimeError("boom")

    mult, basis = weigher.compute_multiplier("snap1", conn, principle_engine=_RaisingEngine())
    assert mult == TRADER_MINI_MULT_NEUTRAL
    assert basis == "context_unavailable"


def test_weigher_multiplier_bounds_never_exceeded():
    lo, hi = TRADER_MINI_MULT_BOUNDS
    assert lo <= TRADER_MINI_MULT_LOSS <= hi
    assert lo <= TRADER_MINI_MULT_WIN <= hi
    assert lo <= TRADER_MINI_MULT_NEUTRAL <= hi
    assert lo < hi
