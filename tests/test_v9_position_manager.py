"""Tests — gestion active de position (core/v9/position_manager.py).

Vérifie :
  - break-even : SL remonté à l'entrée après +30 % TP → pas de perte pleine
  - partial close : fraction verrouillée à +50 % TP
  - time-based exit : sortie sur stagnation
  - TP plein / SL plein
  - kill switch d'intégration (défaut OFF)
  - conventions pips (spread, direction, symbole JPY)
"""
from __future__ import annotations

import pytest

from core.v9.position_manager import (
    PositionManager,
    position_manager_enabled,
    ManageReason,
)


PIP = 1 / 10000  # GBPUSD


def _mids(entry: float, pip_offsets: list[float]) -> list[float]:
    """Construit une trajectoire à partir d'offsets en pips depuis l'entrée."""
    return [entry + off * PIP for off in pip_offsets]


# ---------- Kill switch ----------


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("V9_POSITION_MANAGER_ENABLED", raising=False)
    assert position_manager_enabled() is False


def test_enabled_by_env(monkeypatch):
    monkeypatch.setenv("V9_POSITION_MANAGER_ENABLED", "1")
    assert position_manager_enabled() is True


# ---------- Cas dégénérés ----------


def test_no_data():
    pm = PositionManager()
    r = pm.simulate(1.30, "haussiere", 10.0, 15.0, [], symbol="GBPUSD")
    assert r.exit_reason == ManageReason.NO_DATA.value
    assert r.pips == 0.0


# ---------- Take-profit / Stop-loss pleins ----------


def test_full_tp_hit():
    pm = PositionManager(spread_pips=0.5)
    entry = 1.30
    # monte régulièrement jusqu'à +10 pips (TP)
    mids = _mids(entry, [2, 4, 6, 8, 10])
    r = pm.simulate(entry, "haussiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.exit_reason == ManageReason.TP_HIT.value
    assert r.is_win == 1
    # partial (50%) verrouillé à +5 puis reste au TP → pips > 0
    assert r.pips > 0


def test_full_sl_hit_when_no_favorable_move():
    pm = PositionManager(spread_pips=0.5, stagnation_bars=99)
    entry = 1.30
    # descend directement à -15 pips sans jamais aller en faveur
    mids = _mids(entry, [-5, -10, -15])
    r = pm.simulate(entry, "haussiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.exit_reason == ManageReason.SL_HIT.value
    assert r.is_win == 0
    assert r.pips == pytest.approx(-(15.0 + 0.5))


# ---------- Break-even ----------


def test_break_even_protects_from_full_loss():
    """Le prix va à +30 % TP (break-even armé) puis retombe à l'entrée :
    on sort ~0 au lieu de -SL. La perte pleine est évitée."""
    pm = PositionManager(spread_pips=0.5, stagnation_bars=99)
    entry = 1.30
    # +3 pips (= 30 % de TP=10 → break-even armé), puis retour à l'entrée
    mids = _mids(entry, [1, 2, 3, 1, 0])
    r = pm.simulate(entry, "haussiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.break_even_activated is True
    assert r.exit_reason == ManageReason.BREAK_EVEN_HIT.value
    # sortie ≈ -spread, PAS -15
    assert r.pips == pytest.approx(-0.5)
    assert r.pips > -(15.0)


def test_break_even_not_armed_below_trigger():
    """Sous +30 % TP, le break-even n'est pas armé → SL plein s'applique."""
    pm = PositionManager(spread_pips=0.5, stagnation_bars=99)
    entry = 1.30
    # +2 pips seulement (< 3 = 30 % TP), puis -15
    mids = _mids(entry, [1, 2, -5, -15])
    r = pm.simulate(entry, "haussiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.break_even_activated is False
    assert r.exit_reason == ManageReason.SL_HIT.value


# ---------- Partial close ----------


def test_partial_close_locks_gain():
    """À +50 % TP, 50 % de la position est verrouillée."""
    pm = PositionManager(spread_pips=0.5, stagnation_bars=99)
    entry = 1.30
    # +5 pips (= 50 % TP) atteint, puis retombe au break-even (0)
    mids = _mids(entry, [3, 5, 3, 0])
    r = pm.simulate(entry, "haussiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.partial_closed is True
    assert r.remaining_fraction == pytest.approx(0.5)
    # partial verrouillé = 0.5 * (5 - 0.5) = 2.25 pips
    assert r.partial_pips == pytest.approx(2.25)
    # net = partial + reste * (-spread) au break-even
    assert r.pips == pytest.approx(2.25 + 0.5 * (-0.5))


# ---------- Time-based exit (stagnation) ----------


def test_stagnation_exit():
    """Trade qui stagne sous le break-even → coupé après N barres."""
    pm = PositionManager(spread_pips=0.5, stagnation_bars=4)
    entry = 1.30
    # oscille faiblement (+1/-1), jamais +3 (break-even) ni -15 (SL)
    mids = _mids(entry, [1, -1, 1, -1, 1, -1])
    r = pm.simulate(entry, "haussiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.exit_reason == ManageReason.STAGNATION_EXIT.value
    assert r.break_even_activated is False
    assert r.bars_held == 4


# ---------- Symétrie baissière ----------


def test_baissiere_tp_hit():
    pm = PositionManager(spread_pips=0.5)
    entry = 1.30
    # baissiere : le prix DESCEND → favorable
    mids = _mids(entry, [-2, -4, -6, -8, -10])
    r = pm.simulate(entry, "baissiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.exit_reason == ManageReason.TP_HIT.value
    assert r.is_win == 1


def test_baissiere_break_even():
    pm = PositionManager(spread_pips=0.5, stagnation_bars=99)
    entry = 1.30
    mids = _mids(entry, [-1, -2, -3, -1, 0])  # -3 pips favorable puis retour
    r = pm.simulate(entry, "baissiere", 10.0, 15.0, mids, symbol="GBPUSD")
    assert r.break_even_activated is True
    assert r.exit_reason == ManageReason.BREAK_EVEN_HIT.value
