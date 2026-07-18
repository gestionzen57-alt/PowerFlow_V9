"""Tests du câblage BearPerception SHADOW dans TradeEngine (Tâche 1).

Mission baissier 2/2 — Phase A du déploiement progressif R25'.

On teste directement `TradeEngine._attach_bear_perception_shadow`, l'unité
introduite par la Tâche 1, sur une DB temporaire minimale (forces_snapshots +
decisions). Cela évite de dérouler tout `process()` (arbiter + risk + logger)
et rend les assertions déterministes.

Invariants vérifiés :
  - Kill switch OFF par défaut → aucune évaluation (status 'disabled').
  - Kill switch ON → évaluation SHADOW, signal attaché, MAIS aucune mutation
    du flux (log only).
  - DB vide → no-op gracieux (signal neutre, would_exit None).
  - Ne casse jamais un result d'ouverture de trade (R6).
  - Exception interne → status 'error', aucune remontée (R6).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9.trade_engine import TradeEngine
from core.v9.v9_bear_perception import BEAR_PERCEPTION_ENV


# ── Helpers ───────────────────────────────────────────────────────────


def _build_db(with_m1_bearish: bool = False, with_decision: bool = True) -> Path:
    """Crée une DB temporaire (forces_snapshots + decisions).

    Si ``with_m1_bearish`` : insère 10 bougies M1 baissières rapides pour
    déclencher un fast_move. Retourne le chemin (à supprimer par l'appelant).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, symbol TEXT,
            timeframe TEXT, bar_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, mid REAL,
            tick_volume INTEGER, stale INTEGER DEFAULT 0
        );
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY, snapshot_id TEXT, symbol TEXT,
            timeframe TEXT, direction TEXT, confiance INTEGER, timestamp TEXT
        );
        """
    )
    base_time = 1784327100
    snap_id = f"v9-GBPUSD-M15-{base_time + 9 * 60}-000999"
    if with_m1_bearish:
        base = 1.34000
        for i in range(10):
            close = base - i * 0.00025  # -2.5 pips/bar → fast_move baissier
            conn.execute(
                "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, "
                "bar_time, open, high, low, close, mid, tick_volume, stale) "
                "VALUES (?, 'GBPUSD', 'M1', ?, ?, ?, ?, ?, ?, 100, 0)",
                (
                    f"v9-GBPUSD-M1-{base_time + i * 60}",
                    base_time + i * 60,
                    close + 0.0001, close + 0.00015, close - 0.0001, close, close,
                ),
            )
    if with_decision:
        conn.execute(
            "INSERT INTO decisions (decision_id, snapshot_id, symbol, timeframe, "
            "direction, confiance, timestamp) VALUES "
            "('dec_te_bear', ?, 'GBPUSD', 'M15', 'baissiere', 80, "
            "'2026-07-18T20:00:00+00:00')",
            (snap_id,),
        )
    conn.commit()
    conn.close()
    return path


def _base_result(snapshot_id: str) -> dict:
    """Result partiel tel qu'il existe au point d'injection (après risk gate)."""
    return {
        "snapshot_id": snapshot_id,
        "trade_id": None,
        "action": "open",
        "direction": "baissiere",
        "confiance": 80,
        "risk_go": True,
        "tp_pips": 10.0,
        "sl_pips": 15.0,
    }


def _arbiter_result() -> dict:
    return {"direction": "baissiere", "confiance_arbitree": 80, "symbol": "GBPUSD"}


# ── Tests ─────────────────────────────────────────────────────────────


def test_trade_engine_bear_perception_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kill switch absent (défaut OFF) → aucune évaluation, status 'disabled'."""
    monkeypatch.delenv(BEAR_PERCEPTION_ENV, raising=False)
    path = _build_db(with_m1_bearish=True)
    try:
        engine = TradeEngine(db_path=path)
        result = _base_result(f"v9-GBPUSD-M15-{1784327100 + 540}-000999")
        engine._attach_bear_perception_shadow(
            result, result["snapshot_id"], _arbiter_result(), {},
        )
        assert result["bear_perception_enabled"] is False
        assert result["bear_perception_status"] == "disabled"
        assert result["bear_perception_signal"] is None
        assert result["bear_perception_would_skip"] is False
        assert result["bear_perception_would_exit"] is None
        # Log only : le flux d'ouverture est intact.
        assert result["action"] == "open"
        assert result["direction"] == "baissiere"
    finally:
        path.unlink(missing_ok=True)


def test_trade_engine_bear_perception_enabled_shadow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kill switch ON → signal évalué et attaché, MAIS log only (flux intact)."""
    monkeypatch.setenv(BEAR_PERCEPTION_ENV, "1")
    path = _build_db(with_m1_bearish=True)
    try:
        engine = TradeEngine(db_path=path)
        snap = f"v9-GBPUSD-M15-{1784327100 + 540}-000999"
        result = _base_result(snap)
        tp_before, sl_before = result["tp_pips"], result["sl_pips"]
        engine._attach_bear_perception_shadow(
            result, snap, _arbiter_result(), {},
        )
        assert result["bear_perception_enabled"] is True
        assert result["bear_perception_status"] == "evaluated"
        assert result["bear_perception_signal"] is not None
        assert "speed_pips_per_min" in result["bear_perception_signal"]
        # SHADOW STRICT : le TP/SL/direction/action réels ne bougent PAS.
        assert result["tp_pips"] == tp_before
        assert result["sl_pips"] == sl_before
        assert result["direction"] == "baissiere"
        assert result["action"] == "open"
    finally:
        path.unlink(missing_ok=True)


def test_trade_engine_bear_perception_no_op_if_no_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB sans bougies M1 → signal neutre, would_exit None, pas de crash."""
    monkeypatch.setenv(BEAR_PERCEPTION_ENV, "1")
    path = _build_db(with_m1_bearish=False, with_decision=True)
    try:
        engine = TradeEngine(db_path=path)
        snap = f"v9-GBPUSD-M15-{1784327100 + 540}-000999"
        result = _base_result(snap)
        engine._attach_bear_perception_shadow(
            result, snap, _arbiter_result(), {},
        )
        assert result["bear_perception_status"] == "evaluated"
        assert result["bear_perception_signal"]["is_fast_move"] is False
        assert result["bear_perception_would_exit"] is None
    finally:
        path.unlink(missing_ok=True)


def test_trade_engine_bear_perception_does_not_break_open_trade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Même sans decision en DB (symbol résolu par parse), le result d'open
    reste cohérent et rien ne remonte (R6)."""
    monkeypatch.setenv(BEAR_PERCEPTION_ENV, "1")
    path = _build_db(with_m1_bearish=True, with_decision=False)
    try:
        engine = TradeEngine(db_path=path)
        snap = f"v9-GBPUSD-M15-{1784327100 + 540}-000999"
        result = _base_result(snap)
        result["trade_id"] = "trade_xyz"
        engine._attach_bear_perception_shadow(
            result, snap, _arbiter_result(), {},
        )
        # L'ouverture n'est pas cassée : action + trade_id préservés.
        assert result["action"] == "open"
        assert result["trade_id"] == "trade_xyz"
        # symbol résolu via parse snapshot_id → évaluation faite.
        assert result["bear_perception_status"] == "evaluated"
    finally:
        path.unlink(missing_ok=True)


def test_trade_engine_bear_perception_r6_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exception interne (detect_fast_movement) → status 'error', jamais de
    remontée, flux préservé (R6)."""
    monkeypatch.setenv(BEAR_PERCEPTION_ENV, "1")
    path = _build_db(with_m1_bearish=True)
    try:
        engine = TradeEngine(db_path=path)
        snap = f"v9-GBPUSD-M15-{1784327100 + 540}-000999"
        result = _base_result(snap)

        # Force une exception au coeur de l'évaluation shadow.
        import core.v9.v9_bear_perception as bp

        def _boom(*_a, **_k):
            raise RuntimeError("boom shadow")

        monkeypatch.setattr(
            bp.BearPerceptionCorrection, "detect_fast_movement", _boom,
        )
        # Ne doit PAS lever.
        engine._attach_bear_perception_shadow(
            result, snap, _arbiter_result(), {},
        )
        assert result["bear_perception_status"] == "error"
        assert "shadow_eval" in result.get("bear_perception_reason", "")
        assert result["action"] == "open"  # flux intact
    finally:
        path.unlink(missing_ok=True)
