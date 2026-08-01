"""Tests unitaires pour les sous-méthodes Phase 106 de TradeEngine.

Couvre :
- _check_paper_halt : halt ON/OFF, fail-open sur exception
- _check_mega_edge_filter : ON bloque, OFF laisse passer, mega_edge metadata
- _check_j2_kill_switch_gates : anti-série 3 losses, kill_dd_wr thresholds
- _consolidate_arbiter_with_overrides : arbiter success/error, overrides GBPUSD/no_baissiere

Ces tests sont des tests UNITAIRES isoles : ils n'appellent pas process()
dans son integralite, ils testent la sous-methode directement avec des
mocks leger de l'instance TradeEngine.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

logging.getLogger("v9.trade_engine").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_db(tmp_path: Path) -> Path:
    """Cree une mini-DB avec paper_trades pour les tests J2."""
    db = tmp_path / "v9_forces.db"
    with sqlite3.connect(str(db)) as c:
        c.executescript("""
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            pips_simulated REAL NOT NULL,
            is_win INTEGER NOT NULL
        );
        """)
    return db


class _StubEngine:
    """Stub minimaliste : on injecte directement les attributs necessaires
    sans heriter de TradeEngine (les proprietes @property bloquent l'assignation).

    On ne peut pas utiliser TradeEngine.__new__ directement car les @property
    definies dans la classe (arbiter, risk_manager, etc.) n'ont pas de setter.
    """


def _build_engine(tmp_path: Path, **overrides):
    """Construit un stub TradeEngine-like pour les tests unitaires.

    Bypasse l'init de TradeEngine (qui ouvre la DB) en utilisant object.__new__.
    Le @property `arbiter` lit self._arbiter, donc on doit mocker _arbiter
    ET on peut shunter le getter en injectant directement dans __dict__.
    """
    from core.v9 import trade_engine as te_mod

    eng = object.__new__(te_mod.TradeEngine)
    eng.db_path = overrides.get("db_path", tmp_path / "v9_forces.db")
    eng._resolve_symbol_and_decision = overrides.get(
        "resolve_symbol", lambda sid: ("GBPUSD", "haussiere")
    )
    # @property arbiter lit self._arbiter
    arbiter_mock = MagicMock()
    arbiter_mock.consolidate = MagicMock(return_value={
        "direction": "haussiere",
        "confiance_arbitree": 75,
        "principes_source": ["PRICE_LAG"],
    })
    eng._arbiter = arbiter_mock
    return eng


# ---------------------------------------------------------------------------
# Tests _check_paper_halt
# ---------------------------------------------------------------------------

def test_check_paper_halt_disabled(monkeypatch, tmp_path):
    """Halt OFF → retourne None (autorisation de trader)."""
    eng = _build_engine(tmp_path)
    # Patcher la fonction top-level _paper_trade_halt_enabled
    monkeypatch.setattr(
        "core.v9.trade_engine._paper_trade_halt_enabled",
        lambda: False,
    )
    assert eng._check_paper_halt("SNAP-001") is None


def test_check_paper_halt_enabled(monkeypatch, tmp_path):
    """Halt ON → retourne dict avec raison_blocage."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._paper_trade_halt_enabled",
        lambda: True,
    )
    res = eng._check_paper_halt("SNAP-001")
    assert res is not None
    assert res["raison_blocage"] == "paper_halt"


def test_check_paper_halt_failopen(monkeypatch, tmp_path):
    """Si la lecture du kill switch leve, on autorise (fail-open)."""
    eng = _build_engine(tmp_path)
    def boom():
        raise RuntimeError("KS read failed")
    monkeypatch.setattr(
        "core.v9.trade_engine._paper_trade_halt_enabled", boom,
    )
    assert eng._check_paper_halt("SNAP-001") is None  # fail-open


# ---------------------------------------------------------------------------
# Tests _check_mega_edge_filter
# ---------------------------------------------------------------------------

def test_mega_edge_disabled(monkeypatch, tmp_path):
    """MEGA_EDGE OFF → retourne None."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.kill_switches.mega_edge_enabled", lambda: False,
    )
    assert eng._check_mega_edge_filter("SNAP-001", {}) is None


def test_mega_edge_enabled_blocked(monkeypatch, tmp_path):
    """MEGA_EDGE ON + go=False → dict action=skip."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.kill_switches.mega_edge_enabled", lambda: True,
    )
    fake_module = MagicMock()
    fake_module.mega_edge_evaluation = MagicMock(return_value={
        "go": False, "reason": "L2_blackout", "leviers": ["L2"],
    })
    monkeypatch.setitem(sys.modules, "core.v9.v9_mega_edge_filter", fake_module)
    res = eng._check_mega_edge_filter("SNAP-001", {})
    assert res is not None
    assert res["action"] == "skip"
    assert "mega_edge_L2_blackout" in res["raison_blocage"]


def test_mega_edge_enabled_pass(monkeypatch, tmp_path):
    """MEGA_EDGE ON + go=True → metadata uniquement (pas de skip)."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.kill_switches.mega_edge_enabled", lambda: True,
    )
    fake_module = MagicMock()
    fake_module.mega_edge_evaluation = MagicMock(return_value={
        "go": True, "reason": "ok", "leviers": [],
    })
    monkeypatch.setitem(sys.modules, "core.v9.v9_mega_edge_filter", fake_module)
    res = eng._check_mega_edge_filter("SNAP-001", {})
    assert res is not None
    assert "action" not in res
    assert res["mega_edge"]["go"] is True


def test_mega_edge_filter_exception_returns_none(monkeypatch, tmp_path):
    """Exception dans mega_edge → retourne None (R6 jamais bloquant)."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.kill_switches.mega_edge_enabled", lambda: True,
    )

    def boom(*a, **kw):
        raise RuntimeError("mega edge crash")
    fake_module = MagicMock()
    fake_module.mega_edge_evaluation = boom
    monkeypatch.setitem(sys.modules, "core.v9.v9_mega_edge_filter", fake_module)
    assert eng._check_mega_edge_filter("SNAP-001", {}) is None


# ---------------------------------------------------------------------------
# Tests _check_j2_kill_switch_gates
# ---------------------------------------------------------------------------

def test_j2_disabled(monkeypatch, tmp_path):
    """J2 desactive → retourne None immediatement."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.kill_switches.anti_serie_perdante_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_dd_wr_enabled", lambda: False,
    )
    assert eng._check_j2_kill_switch_gates("SNAP-001", {}) is None


def test_j2_anti_serie_3_losses(monkeypatch, tmp_path):
    """3 losses consecutives (symbol, direction) → skip anti_serie."""
    db = _make_temp_db(tmp_path)
    eng = _build_engine(tmp_path, db_path=db, resolve_symbol=lambda sid: ("GBPUSD", "haussiere"))
    eng.db_path = db
    monkeypatch.setattr(
        "core.v9.kill_switches.anti_serie_perdante_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_dd_wr_enabled", lambda: False,
    )
    # Inserer 3 losses GBPUSD haussiere
    with sqlite3.connect(str(db)) as c:
        now = datetime.now(timezone.utc)
        for i in range(3):
            c.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?)",
                (f"T{i}", f"v9-GBPUSD-{i}", "haussiere",
                 (now - timedelta(hours=i)).isoformat(), -10.0, 0),
            )
        c.commit()
    res = eng._check_j2_kill_switch_gates("SNAP-001", {"direction": "haussiere"})
    assert res is not None
    assert res["action"] == "skip"
    assert res["raison_blocage"] == "anti_serie_3_losses"


def test_j2_kill_dd_wr_triggered(monkeypatch, tmp_path):
    """DD 24h sous seuil → skip kill_dd_wr."""
    db = _make_temp_db(tmp_path)
    eng = _build_engine(tmp_path, db_path=db, resolve_symbol=lambda sid: ("GBPUSD", "haussiere"))
    eng.db_path = db
    monkeypatch.setattr(
        "core.v9.kill_switches.anti_serie_perdante_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_dd_wr_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_dd_pips", lambda: -100.0,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_wr_floor", lambda: 0.40,
    )
    # Inserer des trades -150 pips sur 24h (sous -100)
    with sqlite3.connect(str(db)) as c:
        now = datetime.now(timezone.utc)
        for i in range(10):
            c.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?)",
                (f"T{i}", f"v9-GBPUSD-{i}", "haussiere",
                 (now - timedelta(hours=i)).isoformat(), -15.0, 0),
            )
        c.commit()
    res = eng._check_j2_kill_switch_gates("SNAP-001", {"direction": "haussiere"})
    assert res is not None
    assert res["action"] == "skip"
    assert "kill_dd_wr" in res["raison_blocage"]


def test_j2_passes_when_healthy(monkeypatch, tmp_path):
    """20 trades gagnants consecutifs + DD=0 → passe les gates."""
    db = _make_temp_db(tmp_path)
    eng = _build_engine(tmp_path, db_path=db, resolve_symbol=lambda sid: ("GBPUSD", "haussiere"))
    eng.db_path = db
    monkeypatch.setattr(
        "core.v9.kill_switches.anti_serie_perdante_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_dd_wr_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_dd_pips", lambda: -100.0,
    )
    monkeypatch.setattr(
        "core.v9.kill_switches.kill_wr_floor", lambda: 0.40,
    )
    # Inserer 20 trades gagnants GBPUSD haussiere
    with sqlite3.connect(str(db)) as c:
        now = datetime.now(timezone.utc)
        for i in range(20):
            c.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?)",
                (f"T{i}", f"v9-GBPUSD-{i}", "haussiere",
                 (now - timedelta(hours=i)).isoformat(), 10.0, 1),
            )
        c.commit()
    res = eng._check_j2_kill_switch_gates("SNAP-001", {"direction": "haussiere"})
    assert res is None


# ---------------------------------------------------------------------------
# Tests _consolidate_arbiter_with_overrides
# ---------------------------------------------------------------------------

def test_arbiter_success(monkeypatch, tmp_path):
    """Arbiter reussit → retourne (arbiter_result, context)."""
    eng = _build_engine(tmp_path)
    eng._build_context = MagicMock(return_value={"symbol": "GBPUSD", "session": "london"})
    res = eng._consolidate_arbiter_with_overrides("SNAP-001", {"direction": None})
    assert res is not None
    arbiter_result, context = res
    assert arbiter_result["direction"] == "haussiere"
    assert arbiter_result["confiance_arbitree"] == 75
    assert context["symbol"] == "GBPUSD"


def test_arbiter_failure(monkeypatch, tmp_path):
    """Arbiter leve → retourne None + result.error renseigne."""
    eng = _build_engine(tmp_path)
    eng.arbiter.consolidate.side_effect = RuntimeError("arbiter down")
    result = {"direction": None}
    res = eng._consolidate_arbiter_with_overrides("SNAP-001", result)
    assert res is None
    assert "arbiter:" in result["error"]


def test_arbiter_gbpusd_long_only(monkeypatch, tmp_path):
    """V9_GBPUSD_LONG_ONLY=1 + GBPUSD baissier → force haussiere."""
    eng = _build_engine(tmp_path, resolve_symbol=lambda sid: ("GBPUSD", "baissiere"))
    eng._build_context = MagicMock(return_value={"symbol": "GBPUSD"})
    eng.arbiter.consolidate.return_value = {
        "direction": "baissiere", "confiance_arbitree": 75, "principes_source": [],
    }
    monkeypatch.setattr(
        "core.v9.trade_engine._gbpusd_long_only_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._no_baissiere_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine.loop_breaker_enabled", lambda: False,
    )
    result = {"direction": None}
    res = eng._consolidate_arbiter_with_overrides("SNAP-001", result)
    assert res is not None
    arbiter_result, _ = res
    assert arbiter_result["direction"] == "haussiere"  # force
    assert result["long_only_override"] is True


def test_arbiter_no_baissiere_global(monkeypatch, tmp_path):
    """V9_NO_BAISSIERE=1 + EURUSD baissier → force haussiere (global)."""
    eng = _build_engine(tmp_path, resolve_symbol=lambda sid: ("EURUSD", "baissiere"))
    eng._build_context = MagicMock(return_value={"symbol": "EURUSD"})
    eng.arbiter.consolidate.return_value = {
        "direction": "baissiere", "confiance_arbitree": 75, "principes_source": [],
    }
    monkeypatch.setattr(
        "core.v9.trade_engine._gbpusd_long_only_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._no_baissiere_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine.loop_breaker_enabled", lambda: False,
    )
    result = {"direction": None}
    res = eng._consolidate_arbiter_with_overrides("SNAP-001", result)
    assert res is not None
    arbiter_result, _ = res
    assert arbiter_result["direction"] == "haussiere"
    assert result["no_baissiere_override"] is True


def test_arbiter_no_override_when_haussiere(monkeypatch, tmp_path):
    """Decision deja haussiere + GBPUSD long-only → pas d'override."""
    eng = _build_engine(tmp_path)
    eng._build_context = MagicMock(return_value={"symbol": "GBPUSD"})
    eng.arbiter.consolidate.return_value = {
        "direction": "haussiere", "confiance_arbitree": 75, "principes_source": [],
    }
    monkeypatch.setattr(
        "core.v9.trade_engine._gbpusd_long_only_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._no_baissiere_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine.loop_breaker_enabled", lambda: False,
    )
    result = {"direction": "haussiere"}
    res = eng._consolidate_arbiter_with_overrides("SNAP-001", result)
    assert res is not None
    assert result["long_only_override"] is False  # pas declenche
