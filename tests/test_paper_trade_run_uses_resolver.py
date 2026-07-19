"""Tests d'intégration : wire shadow PaperTradeResolver dans v9_paper_trade_run.

Le resolver tourne en SHADOW (R25') : il logge une résolution alternative sans
écraser `paper_trades`. R6 : toute défaillance retombe sur [] sans crash.
"""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest

import scripts.v9_paper_trade_run as ptr


def _seed_db(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE paper_trades (
            trade_id TEXT, snapshot_id TEXT, direction TEXT, confiance INTEGER,
            principes_source TEXT, opened_at TEXT, closed_at TEXT,
            pips_simulated REAL, is_win INTEGER, risk_go_context TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE decisions (
            snapshot_id TEXT, symbol TEXT, timeframe TEXT, regime_type TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO decisions (snapshot_id, symbol, timeframe, regime_type) "
        "VALUES ('snap1', 'GBPUSD', 'M1', 'range_calme')"
    )
    conn.execute(
        "INSERT INTO paper_trades (trade_id, snapshot_id, direction, confiance, "
        "opened_at, closed_at, pips_simulated, is_win) "
        "VALUES ('t1', 'snap1', 'haussiere', 80, "
        "'2026-07-20T03:00:00+00:00', '2026-07-20T04:00:00+00:00', 14.0, 1)"
    )
    conn.commit()
    conn.close()


def test_paper_trade_run_imports_resolver():
    """v9_paper_trade_run importe bien PaperTradeResolver."""
    mod = importlib.import_module("scripts.v9_paper_trade_run")
    assert hasattr(mod, "PaperTradeResolver")
    assert hasattr(mod, "shadow_resolve_recent")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "PaperTradeResolver" in src


def test_paper_trade_run_logs_shadow_resolution(tmp_path, capsys):
    """Un trade clôturé génère une comparaison shadow (log [SHADOW])."""
    db = tmp_path / "f.db"
    _seed_db(db)
    comps = ptr.shadow_resolve_recent(db_path=db, limit=10)
    assert len(comps) == 1
    c = comps[0]
    assert c["trade_id"] == "t1"
    assert c["effective_is_win"] == 1
    assert c["shadow_is_win"] == 1          # +14 pips ≥ TP(8) en LOW/M1
    assert c["exit_reason"] == "tp"
    out = capsys.readouterr().out
    assert "[SHADOW]" in out


def test_resolver_shadow_does_not_overwrite(tmp_path):
    """La table paper_trades n'est PAS modifiée par le shadow resolver."""
    db = tmp_path / "f.db"
    _seed_db(db)
    ptr.shadow_resolve_recent(db_path=db, limit=10)
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT pips_simulated, is_win FROM paper_trades WHERE trade_id='t1'"
    ).fetchone()
    conn.close()
    assert row == (14.0, 1)  # inchangé


def test_resolver_failure_triggers_fallback(tmp_path, capsys):
    """Si le resolver lève, shadow_resolve_recent retourne [] sans crash (R6)."""
    db = tmp_path / "f.db"
    _seed_db(db)

    class _Boom:
        def resolve(self, *a, **k):
            raise RuntimeError("boom")

        _regime_bucket = staticmethod(lambda r: "LOW")

    # Un resolver qui explose à chaque trade → aucune comparaison, pas de crash.
    comps = ptr.shadow_resolve_recent(db_path=db, limit=10, resolver=_Boom())
    assert comps == []
    out = capsys.readouterr().out
    assert "SHADOW WARN" in out


def test_shadow_handles_missing_db(tmp_path):
    """DB absente → [] sans crash."""
    comps = ptr.shadow_resolve_recent(db_path=tmp_path / "nope.db", limit=10)
    assert comps == []
