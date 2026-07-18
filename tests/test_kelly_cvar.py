"""Tests — CVaR sizing institutionnel (Chantier B, 2026-07-18) PowerFlow V9.

Kelly n'est PAS retesté ici : il existe déjà (paper_risk_manager +
v9_sizing_confidence) et n'est pas dupliqué (décision CEO). Ce chantier
ajoute uniquement la brique CVaR 95% et son plafond, appliqués en réutilisant
le sizing Kelly existant. Couvre :
  - cvar_95()            : expected shortfall (perte positive)
  - cvar_position_cap()  : plafond de taille par budget CVaR
  - kill switch V9_KELLY_CVAR_ENABLED (défaut OFF = sizing inchangé)
  - intégration trade_engine : OFF -> inchangé, ON -> position plafonnée
"""

from __future__ import annotations

import pytest

from core.v9.risk_manager import RiskManager
from core.v9.trade_engine import TradeEngine, _kelly_cvar_enabled


# ── cvar_95() ──────────────────────────────────────────────────────

def test_cvar_95_normal_series_positive_loss() -> None:
    # 10 valeurs, queue 5% = la pire (-8) -> CVaR = 8.0 (perte positive).
    returns = [5, -3, 2, -8, 1, -2, 4, -1, 3, -5]
    assert RiskManager.cvar_95(returns, 0.95) == pytest.approx(8.0)


def test_cvar_95_fat_tail_higher_than_normal() -> None:
    # Même VaR ~ mais une queue plus lourde -> CVaR strictement plus élevé.
    normal = [-5, -5, -5, 1, 1, 1, 2, 2, 2, 3]
    fat_tail = [-50, -40, -30, 1, 1, 1, 2, 2, 2, 3]
    cvar_normal = RiskManager.cvar_95(normal, 0.80)
    cvar_fat = RiskManager.cvar_95(fat_tail, 0.80)
    assert cvar_fat > cvar_normal


def test_cvar_95_empty_series_zero() -> None:
    assert RiskManager.cvar_95([], 0.95) == 0.0


def test_cvar_95_all_gains_zero() -> None:
    # Aucune perte -> pas de risque de perte à plafonner.
    assert RiskManager.cvar_95([1, 2, 3, 4, 5], 0.95) == 0.0


def test_cvar_95_single_worst_value() -> None:
    # Queue 5% sur 10 valeurs = 1 valeur (la pire).
    assert RiskManager.cvar_95([-12, 1, 2, 3, 4, 5, 6, 7, 8, 9], 0.95) == pytest.approx(12.0)


def test_cvar_95_bad_input_returns_zero() -> None:
    assert RiskManager.cvar_95(["x", None, "y"], 0.95) == 0.0


# ── cvar_position_cap() ────────────────────────────────────────────

def test_cvar_cap_reduces_when_over_budget() -> None:
    # cvar=50, budget=12 -> cap=0.24 < taille 2.0 -> réduit.
    res = RiskManager.cvar_position_cap(2.0, [-50] * 10 + [5] * 10, 12.0, 0.95)
    assert res["capped"] is True
    assert res["size"] == pytest.approx(0.24)
    assert res["cvar"] == pytest.approx(50.0)


def test_cvar_cap_unchanged_when_under_budget() -> None:
    res = RiskManager.cvar_position_cap(1.0, [-2, 1, -1, 2, -1.5, 1, -1, 2, -1, 1], 12.0, 0.95)
    assert res["capped"] is False
    assert res["size"] == pytest.approx(1.0)


def test_cvar_cap_unchanged_when_no_loss() -> None:
    # cvar=0 (que des gains) -> jamais de plafond.
    res = RiskManager.cvar_position_cap(1.5, [1, 2, 3, 4, 5], 12.0, 0.95)
    assert res["capped"] is False
    assert res["size"] == pytest.approx(1.5)


# ── Kill switch ────────────────────────────────────────────────────

def test_kelly_cvar_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("V9_KELLY_CVAR_ENABLED", raising=False)
    assert _kelly_cvar_enabled() is False


def test_kelly_cvar_enabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("V9_KELLY_CVAR_ENABLED", "1")
    assert _kelly_cvar_enabled() is True


# ── Intégration trade_engine ───────────────────────────────────────

class _ArbiterStub:
    def consolidate(self, _sid):
        return {
            "direction": "haussiere", "confiance_arbitree": 80,
            "confiance_arbitree_boosted": 80, "principes_source": [],
            "regime_type": "NEUTRE",
        }


class _RiskStub:
    capital = 10000.0

    def __init__(self, position_size=2.0):
        self._position_size = position_size

    def evaluate(self, _arb, _ctx, _open):
        return {
            "go": True, "raison_blocage": None,
            "risk_amount": 100.0, "position_size": self._position_size,
        }


class _CascadesStub:
    def get_active_cascades(self): return []
    def get_cascade_for_snapshot(self, *_a, **_kw): return []
    def apply_cascade_confidence_boost(self, arb, _casc): return arb


class _LoggerStub:
    def log_open(self, *a, **k): return "trade-test-stub"
    def log_close(self, *a, **k): return None


def _make_engine(monkeypatch, returns):
    import core.v9.trade_engine as _te_mod
    monkeypatch.setattr(_te_mod, "infer_session_from_hour", lambda _h: "london")
    # Isole du PRM et du DRM pour ne tester que le bloc CVaR.
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "0")
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "0")

    eng = TradeEngine(db_path=":memory:")
    eng._arbiter = _ArbiterStub()
    eng._risk_mgr = _RiskStub()
    eng._cascade = _CascadesStub()
    eng._logger = _LoggerStub()
    eng._get_open_trades = lambda: []
    eng._build_context = lambda _sid, _sess: {"symbol": "GBPUSD"}
    eng._resolve_symbol_and_decision = lambda _sid: ("GBPUSD", None)
    eng._recent_returns_pips = lambda _sym, _n: returns
    eng._fetch_signal_recommendation = lambda _sid: {
        "tp_pips_recommended": None, "sl_pips_recommended": None,
        "exit_strategy_recommended": "DYNAMIC",
    }
    eng._load_full_context = lambda _sid: None
    eng._attach_bear_perception_shadow = lambda *a, **k: None
    eng._trade_already_open = lambda *_a, **_kw: False
    return eng


def test_engine_cvar_off_leaves_sizing_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("V9_KELLY_CVAR_ENABLED", "0")
    eng = _make_engine(monkeypatch, returns=[-50.0] * 30)
    result = eng.process("v9-GBPUSD-M15-test")
    assert result["cvar_ceiling"] is None


def test_engine_cvar_on_caps_sizing(monkeypatch) -> None:
    monkeypatch.setenv("V9_KELLY_CVAR_ENABLED", "1")
    # 30 pertes de -50 pips -> cvar=50, cap=12/50=0.24 < position 2.0 -> plafonné.
    eng = _make_engine(monkeypatch, returns=[-50.0] * 30)
    result = eng.process("v9-GBPUSD-M15-test")
    assert result["cvar_ceiling"] is not None
    assert result["cvar_ceiling"]["cvar"] == pytest.approx(50.0)
    assert result["cvar_ceiling"]["position_size_before"] == pytest.approx(2.0)


def test_engine_cvar_on_insufficient_history_no_cap(monkeypatch) -> None:
    monkeypatch.setenv("V9_KELLY_CVAR_ENABLED", "1")
    # < CVAR_MIN_TRADES (20) returns -> pas assez d'historique, pas de plafond.
    eng = _make_engine(monkeypatch, returns=[-50.0] * 5)
    result = eng.process("v9-GBPUSD-M15-test")
    assert result["cvar_ceiling"] is None
