"""P0 2026-07-19 — câblage effectif du kill switch V9_PAPER_TRADE_HALT.

Bug observé (P0 c) : `V9_PAPER_TRADE_HALT` est documenté comme « HALT
TOTAL du paper-trading » (fail-safe R6) et recommandé par le watchdog
lors d'une décision critique, mais aucun consommateur dans le code ne le
lit. TradeEngine.process() ouvre toujours un paper-trade si go=True,
même quand le halt est demandé.

Reproduction : `V9_PAPER_TRADE_HALT=1` doit bloquer `TradeEngine.process()`
AVANT l'ouverture du paper-trade (action=skip + raison=`paper_halt`).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.v9 import kill_switches
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.trade_engine import TradeEngine


HALT_ENV = "V9_PAPER_TRADE_HALT"


def test_paper_halt_kill_switch_defined() -> None:
    """Le kill switch doit avoir un helper nommé dans kill_switches.py."""
    assert hasattr(kill_switches, "paper_trade_halt_enabled")
    assert kill_switches.paper_trade_halt_enabled() is False
    os.environ[HALT_ENV] = "1"
    try:
        assert kill_switches.paper_trade_halt_enabled() is True
    finally:
        os.environ.pop(HALT_ENV, None)


def test_paper_halt_blocks_trade_engine_process(tmp_path: Path,
                                                 monkeypatch) -> None:
    """Si V9_PAPER_TRADE_HALT=1, TradeEngine.process() retourne
    action='skip' + raison_blocage='paper_halt' SANS appeler
    paper_trade_logger.log_open()."""
    monkeypatch.setenv(HALT_ENV, "1")

    # Stub le trade_logger AVANT l'init du singleton TradeEngine.
    engine = TradeEngine(db_path=tmp_path / "v9_forces.db")
    mock_logger = MagicMock()
    engine._logger = mock_logger  # court-circuite lazy property

    # On a besoin d'un snapshot_id réel : insérer une ligne forces_snapshots.
    db_path = tmp_path / "v9_forces.db"
    init_db(db_path)
    snapshot_id = "v9-halt-test-001"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": "2026-07-19T22:00:00.000Z",
        "source": "MT4_SDI",
        "symbol": "GBPUSD",
        "timeframe": "M5",
        "bar_time": 100,
        "is_closed_bar": True,
        "high": 1.29, "low": 1.28, "close": 1.285,
        "force_usd": 50.0, "force_gbp": 70.0, "force_eur": 45.0,
        "force_jpy": 50.0, "force_cad": 50.0, "force_chf": 50.0,
        "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "compression_extension_etat": "neutre",
        "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": "2026-07-19T22:00:00.100Z",
    })
    conn = get_connection(db_path)
    try:
        cols = ", ".join(FORCES_COLUMNS)
        ph = ", ".join("?" for _ in FORCES_COLUMNS)
        conn.execute(
            f"INSERT INTO forces_snapshots ({cols}) VALUES ({ph})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()

    # Stub tous les composants internes pour isoler le halt.
    mock_arbiter = MagicMock()
    mock_arbiter.consolidate.return_value = {
        "direction": "haussiere",
        "confiance_arbitree": 95,
        "principes_source": ["PRICE_LAG_AT_NODE_BIRTH"],
    }
    engine._arbiter = mock_arbiter
    engine._risk_mgr = MagicMock()
    engine._risk_mgr.evaluate.return_value = {
        "go": True, "position_size": 1.0, "reasons": [],
    }
    engine._pyramiding = MagicMock()
    engine._pyramiding.evaluate.return_value = {
        "pyramiding_allowed": False, "multiplier": 1.0,
    }
    engine._dynamic_risk = MagicMock()
    engine._portfolio_risk = MagicMock()
    engine._market_regime_global = MagicMock()
    engine._cascade = MagicMock()
    engine._active_cascades = []

    result = engine.process(snapshot_id)

    assert result["action"] == "skip"
    assert result.get("raison_blocage") == "paper_halt"
    assert result.get("trade_id") is None
    mock_logger.log_open.assert_not_called()
