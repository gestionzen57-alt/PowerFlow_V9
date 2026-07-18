"""Tests du kill switch long-only transitoire GBPUSD (Tâche 4).

Mission baissier 2/2. Le switch V9_GBPUSD_LONG_ONLY force les décisions
baissières GBPUSD en haussières (drift structurel +46 pips/j), sans jamais
toucher les autres paires. Défaut OFF.

On pilote `TradeEngine.process()` avec un Arbiter factice pour isoler la
section 1b (l'override intervient AVANT tout accès DB lourd). `open_trades`
est préchargé à [] pour éviter les requêtes vers des tables absentes.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9.trade_engine import GBPUSD_LONG_ONLY_ENV, TradeEngine


class _FakeArbiter:
    def __init__(self, direction: str) -> None:
        self._direction = direction

    def consolidate(self, snapshot_id: str) -> dict:
        return {
            "direction": self._direction,
            "confiance_arbitree": 70,
            "principes_source": [],
            "session_marche": "LONDON",
            "snapshot_id": snapshot_id,
        }


def _empty_db() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    # Tables minimales pour que les helpers défensifs ne cassent rien.
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE paper_trades (trade_id TEXT, snapshot_id TEXT, "
        "direction TEXT, closed_at TEXT, pips_simulated REAL);"
        "CREATE TABLE decisions (decision_id TEXT, snapshot_id TEXT, "
        "symbol TEXT, timestamp TEXT, regime_type TEXT, exploitability_id TEXT);"
    )
    conn.commit()
    conn.close()
    return path


def _make_engine(direction: str, symbol: str) -> tuple[TradeEngine, Path]:
    path = _empty_db()
    engine = TradeEngine(db_path=path)
    engine._arbiter = _FakeArbiter(direction)  # court-circuite le vrai arbiter
    engine._batch_open_trades = []  # évite _get_open_trades (table réelle)
    # Symbole résolu de façon déterministe.
    engine._resolve_symbol_and_decision = lambda _snap: (symbol, None)  # type: ignore
    return engine, path


def test_long_only_gbpusd_overrides_baissier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ON + GBPUSD + baissiere → direction forcée haussiere, override=True."""
    monkeypatch.setenv(GBPUSD_LONG_ONLY_ENV, "1")
    engine, path = _make_engine("baissiere", "GBPUSD")
    try:
        result = engine.process("v9-GBPUSD-M15-1784327640-000999")
        assert result["direction"] == "haussiere"
        assert result["long_only_override"] is True
    finally:
        path.unlink(missing_ok=True)


def test_long_only_other_pairs_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ON mais EURUSD → aucune modification (override réservé à GBPUSD)."""
    monkeypatch.setenv(GBPUSD_LONG_ONLY_ENV, "1")
    engine, path = _make_engine("baissiere", "EURUSD")
    try:
        result = engine.process("v9-EURUSD-M15-1784327640-000999")
        assert result["direction"] == "baissiere"
        assert result["long_only_override"] is False
    finally:
        path.unlink(missing_ok=True)


def test_long_only_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switch absent → GBPUSD baissiere reste baissiere, override=False."""
    monkeypatch.delenv(GBPUSD_LONG_ONLY_ENV, raising=False)
    engine, path = _make_engine("baissiere", "GBPUSD")
    try:
        result = engine.process("v9-GBPUSD-M15-1784327640-000999")
        assert result["direction"] == "baissiere"
        assert result["long_only_override"] is False
    finally:
        path.unlink(missing_ok=True)
