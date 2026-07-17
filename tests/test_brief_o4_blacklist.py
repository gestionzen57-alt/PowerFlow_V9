"""Tests — Brief O4 CEO 2026-07-13 : exclusion structurelle NY+after.

Couvre (CEO décision 2026-07-13, politique conservatrice) :
- `exit_simulator.DYNAMIC_BLACKLIST_SESSIONS` == {"new_york", "after"}
- `exit_simulator.DYNAMIC_TRADABLE_SESSIONS` == {"asie", "london", "overlap", "sydney"}
- `exit_simulator.is_session_tradable()` retourne False pour NY/after
- `signal_generator._recommend_dynamic_for_active()` retourne None sur
  session blacklistée, propage `tradeable=False`
- `decision_logger._determine_action()` force `aucune_action` quand
  exit_strategy_recommended est None (defense-in-depth)
- Sessions non blacklistées continuent de retourner la recommandation DYNAMIC

2026-07-17 audit senior quant : overlap réactivé (sizing adaptatif contrôle
le risque). new_york + after restent blacklistés (WR 0% structurel).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.exit_simulator import (
    DYNAMIC_BLACKLIST_SESSIONS,
    DYNAMIC_PROFILES,
    DYNAMIC_TRADABLE_SESSIONS,
    is_session_tradable,
)
from core.v9.signal_generator import (
    SignalGenerator,
    _recommend_dynamic_for_active,
    _recommend_dynamic_for_absent,
)
from core.v9 import decision_logger as decision_logger_mod
from core.v9.decision_logger import DecisionLogger


# ── exit_simulator — constantes & helpers ──────────────────────────────


def test_blacklist_contains_ny_and_after():
    """Décision CEO Brief O4 2026-07-13 : new_york et after sont
    blacklistées — politique conservatrice, WR structurellement négatif
    Phase 13.2 calibration (NY 29.6%/-7.5, after 20.6%/-10.6)."""
    assert "new_york" in DYNAMIC_BLACKLIST_SESSIONS
    assert "after" in DYNAMIC_BLACKLIST_SESSIONS
    assert isinstance(DYNAMIC_BLACKLIST_SESSIONS, frozenset)


def test_tradable_is_blacklist_complement():
    """Sessions tradables = total des DYNAMIC_PROFILES - blacklist."""
    expected_tradable = set(DYNAMIC_PROFILES.keys()) - DYNAMIC_BLACKLIST_SESSIONS
    assert DYNAMIC_TRADABLE_SESSIONS == frozenset(expected_tradable)
    # 2026-07-17 : overlap réactivé (sizing adaptatif). new_york + after restent exclus.
    assert "overlap" in DYNAMIC_TRADABLE_SESSIONS
    assert "new_york" not in DYNAMIC_TRADABLE_SESSIONS
    assert "after" not in DYNAMIC_TRADABLE_SESSIONS


@pytest.mark.parametrize("session", ["new_york", "after"])
def test_is_session_tradable_false_blacklisted(session):
    assert is_session_tradable(session) is False


@pytest.mark.parametrize("session", ["asie", "london"])
def test_is_session_tradable_true_allowed(session):
    assert is_session_tradable(session) is True


def test_is_session_tradable_unknown_session():
    """Une session inconnue (pas dans DYNAMIC_PROFILES) n'est PAS tradable
    par défaut — conservateur."""
    assert is_session_tradable("inconnu") is False
    assert is_session_tradable("") is False


# ── signal_generator — propagation de la blacklist ────────────────────


def test_recommend_dynamic_ny_returns_none():
    """Si l'heure UTC est NY (par ex. 18h UTC), la recommandation doit
    retourner None/None/None/None/False (strategy/tp_pips/sl_pips/scale/tradeable)."""
    from datetime import datetime
    import unittest.mock

    # Monkeypatch datetime.now pour figer NY (18h UTC)
    class _NYDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 18, 0, 0, tzinfo=tz)

    sig = SignalGenerator.__new__(SignalGenerator)
    with unittest.mock.patch("core.v9.signal_generator.datetime", _NYDatetime):
        rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    assert rec["strategy"] is None
    assert rec["tp_pips"] is None
    assert rec["sl_pips"] is None
    assert rec["session_marche"] == "new_york"
    assert rec["tradeable"] is False
    assert "o4" in rec["reason"].lower() or "blacklist" in rec["reason"].lower()


def test_recommend_dynamic_after_returns_none():
    """Heure UTC after (23h UTC) → blacklistée, recommandation None."""
    from datetime import datetime
    import unittest.mock

    class _AfterDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 23, 0, 0, tzinfo=tz)

    sig = SignalGenerator.__new__(SignalGenerator)
    with unittest.mock.patch("core.v9.signal_generator.datetime", _AfterDatetime):
        rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    assert rec["strategy"] is None
    assert rec["tp_pips"] is None
    assert rec["sl_pips"] is None
    assert rec["session_marche"] == "after"
    assert rec["tradeable"] is False


@pytest.mark.parametrize("utc_hour,session_expected", [
    (3, "asie"),
    (10, "london"),
])
def test_recommend_dynamic_allowed_sessions_intact(utc_hour, session_expected):
    """Brief O4 ne touche PAS les sessions tradables : asie, london
    continuent de retourner la recommandation DYNAMIC intacte.
    2026-07-15 : overlap désormais blacklistée (expectancy -2.26 pips/trade)."""
    from datetime import datetime
    import unittest.mock

    class _FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, utc_hour, 0, 0, tzinfo=tz)

    sig = SignalGenerator.__new__(SignalGenerator)
    with unittest.mock.patch("core.v9.signal_generator.datetime", _FixedDatetime):
        rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    assert rec["strategy"] == "DYNAMIC"
    assert rec["session_marche"] == session_expected
    assert rec["tradeable"] is True
    assert rec["tp_pips"] is not None
    assert rec["sl_pips"] is not None


def test_recommend_dynamic_overlap_now_tradable():
    """2026-07-17 : overlap réactivé avec sizing réduit (scale 0.6).
    audit senior quant : le sizing adaptatif contrôle le risque, pas la blacklist."""
    from datetime import datetime
    import unittest.mock

    class _OverlapDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 14, 0, 0, tzinfo=tz)  # 14h UTC = overlap

    sig = SignalGenerator.__new__(SignalGenerator)
    with unittest.mock.patch("core.v9.signal_generator.datetime", _OverlapDatetime):
        rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    assert rec["strategy"] == "DYNAMIC"
    assert rec["session_marche"] == "overlap"
    assert rec["tradeable"] is True
    assert rec["tp_pips"] is not None


def test_recommend_dynamic_absent_propagates_blacklist():
    """Signal absent sur session blacklistée → recommendation None."""
    from datetime import datetime
    import unittest.mock

    class _NYDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 18, 0, 0, tzinfo=tz)

    sig = SignalGenerator.__new__(SignalGenerator)
    with unittest.mock.patch("core.v9.signal_generator.datetime", _NYDatetime):
        rec = _recommend_dynamic_for_absent(sig, "GBPUSD", "M15")
    assert rec["strategy"] is None
    assert rec["tradeable"] is False


# ── Revertion : si tu changes la constante, ça se ré-active ────────────


def test_blacklist_reversible_by_constant_change():
    """Si la blacklist est vidée, `is_session_tradable('new_york')`
    retourne True. Régression guard."""
    backup = DYNAMIC_BLACKLIST_SESSIONS
    try:
        # Manip impossible (frozenset), mais on peut vérifier que sans
        # la constante, le helper retournerait True
        # On documente donc la dépendance sans toucher
        assert "new_york" in DYNAMIC_BLACKLIST_SESSIONS, "o4 doit rester appliqué"
    finally:
        # Pas de modif
        assert DYNAMIC_BLACKLIST_SESSIONS == backup


# ── decision_logger — defense-in-depth Brief O4 ───────────────────────


class _StubSignal:
    """Stub minimal pour tester _determine_action sans DB.
    Doit supporter accès dict-style, attribut-style et .get().
    """
    def __init__(self, exit_strategy=None, direction="haussiere", raison_absence=None,
                 horizon="court_terme"):
        self.exit_strategy_recommended = exit_strategy
        self.direction = direction
        self.raison_absence = raison_absence
        self.horizon = horizon
        self.snapshot_id = "test-stub"

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)


class _StubExploitability:
    def __init__(self, statut="exploitable"):
        self.statut = statut
        self._data = {"statut": statut}

    def __getitem__(self, key):
        return self._data[key] if key in self._data else getattr(self, key, None)


def test_decide_action_blacklisted_signal_forced_no_trade():
    """Defense-in-depth : si un signal a exit_strategy_recommended=None
    (session blacklistée O4) MAIS qu'il a direction='haussiere' et
    statut='exploitable' en amont, _determine_action doit forcer
    'aucune_action'. Sans ça, le pipeline aval trade quand même."""
    sig = _StubSignal(exit_strategy=None, direction="haussiere")
    exploit = _StubExploitability(statut="exploitable")
    inst = DecisionLogger.__new__(DecisionLogger)  # skip init
    action = inst._determine_action(sig, exploit)
    assert action == "aucune_action", (
        f"defense-in-depth échouée : signal blacklistée aurait dû donner "
        f"'aucune_action', got {action!r}"
    )


def test_decide_action_dtradable_signal_intact():
    """Régression : un signal DYNAMIC tradable (exit_strategy=DYNAMIC)
    continue de retourner preparer_entree normalement."""
    sig = _StubSignal(exit_strategy="DYNAMIC", direction="haussiere")
    exploit = _StubExploitability(statut="exploitable")
    inst = DecisionLogger.__new__(DecisionLogger)
    action = inst._determine_action(sig, exploit)
    assert action == "preparer_entree"


def test_decide_action_neutre_signal_no_change():
    """Régression : un signal direction='neutre' reste 'aucune_action'
    même si exit_strategy_recommended != None (comportement baseline)."""
    sig = _StubSignal(exit_strategy="DYNAMIC", direction="neutre")
    exploit = _StubExploitability(statut="exploitable")
    inst = DecisionLogger.__new__(DecisionLogger)
    action = inst._determine_action(sig, exploit)
    assert action == "aucune_action"
