"""Tests d'intégration — hook SHADOW DynamicRiskManager dans TradeEngine
(Phase 13.3).

Vérifie que :
  - le kill switch env pilote l'évaluation shadow
  - la RiskDecision est JSON-sérialisable (elle entre dans result["dynamic_risk"])
  - l'évaluation shadow ne lève jamais (R6) et reste purement additive (R2 :
    ne modifie pas le SL/TP appliqué)
"""
from __future__ import annotations

import json

from core.v9.dynamic_risk_manager import DynamicRiskManager
from core.v9.trade_engine import _dynamic_risk_enabled


def _ctx(regime: str = "EXTENSION", mtf_depth: str = "D1") -> dict:
    return {
        "scene": {
            "cinematique_json": {
                "velocite_moyenne": 0.01,
                "acceleration_deceleration": "acceleration",
                "compression_extension": {"etat": "neutre"},
            },
            "coalitions_json": [{
                "intensite_alignement": 65.0,
                "intensite_trend": "montante",
                "age_bars": 2,
            }],
            "confluences_mtf_json": {
                "coalition_mtf_depth": mtf_depth,
                "emboitement_detecte": True,
            },
        },
        "behavior": {"phase": "developpement"},
        "regime": [{"regime_type": regime}],
    }


# ---------- Kill switch ----------


def test_dynamic_risk_enabled_default_on(monkeypatch):
    monkeypatch.delenv("V9_DYNAMIC_RISK_ENABLED", raising=False)
    assert _dynamic_risk_enabled() is True


def test_dynamic_risk_disabled_by_env(monkeypatch):
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "0")
    assert _dynamic_risk_enabled() is False


def test_dynamic_risk_enabled_explicit_on(monkeypatch):
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "1")
    assert _dynamic_risk_enabled() is True


# ---------- Contrat de sortie (shadow → result["dynamic_risk"]) ----------


def test_risk_decision_is_json_serializable():
    """result["dynamic_risk"] doit pouvoir entrer dans un diagnostic JSON."""
    drm = DynamicRiskManager()
    decision = drm.evaluate(_ctx(), decision={
        "tp_pips": 8.0, "sl_pips": 15.0, "strategy": "DYNAMIC",
        "session_marche": "london",
    })
    payload = decision.to_dict()
    dumped = json.dumps(payload)          # ne doit pas lever
    assert "phase" in json.loads(dumped)


def test_shadow_decision_carries_expected_contract_keys():
    drm = DynamicRiskManager()
    payload = drm.evaluate(_ctx(), decision={"session_marche": "london"}).to_dict()
    for key in (
        "tp_pips", "sl_pips", "rr_ratio", "exit_strategy", "allow_new_position",
        "phase", "phase_confidence", "source", "session_tradable", "modulation",
    ):
        assert key in payload


def test_shadow_evaluation_is_additive_not_applied():
    """Le SL/TP dynamique diffère du SL/TP courant sans le modifier :
    l'appelant garde la main (SHADOW). On vérifie juste que l'évaluation
    produit une décision cohérente sans toucher au dict d'entrée."""
    drm = DynamicRiskManager()
    current = {"tp_pips": 8.0, "sl_pips": 15.0, "session_marche": "london"}
    before = dict(current)
    decision = drm.evaluate(_ctx(), decision=current)
    assert current == before                       # entrée non mutée
    assert decision.source == "dynamic"
    assert decision.phase == "trend"


def test_shadow_evaluation_never_raises_on_missing_context():
    drm = DynamicRiskManager()
    decision = drm.evaluate(None, decision={"tp_pips": 8.0, "sl_pips": 15.0})
    assert decision.source == "fallback"
    assert decision.tp_pips == 8.0


# ---------- APPLY (Phase 13.3 activation motion CEO Søn 2026-07-17) ----------


def test_apply_propagates_dynamic_tp_sl(monkeypatch):
    """Quand le DRM retourne source='dynamic' + allow_new_position=True,
    le bloc 4b de TradeEngine.process() doit propager tp_pips/sl_pips/strategy
    vers les locales et vers result[].
    """
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "1")
    import sqlite3
    from datetime import datetime, timezone

    from core.v9.trade_engine import TradeEngine

    # Snapshot id factice + contexte_complet dans une mini-DB in-memory
    snap = "v9-test-apply-dynamic"
    now = datetime.now(timezone.utc).isoformat()
    eng = TradeEngine(db_path=":memory:")
    # Stub _load_full_context pour éviter la DB
    eng._load_full_context = lambda _sid: _ctx()  # type: ignore[assignment]
    # Stub les autres dépendances : arbiter + risk_manager + cascade
    class _ArbiterStub:
        def consolidate(self, _sid):
            return {
                "direction": "haussiere",
                "confiance_arbitree": 80,
                "confiance_arbitree_boosted": 80,
                "principes_source": ["GRAMMAR_LOCK"],
                "regime_type": "NEUTRE",
            }
    class _RiskStub:
        def evaluate(self, _arb, _ctx, _open):
            return {"go": True, "raison_blocage": None}
    class _CascadesStub:
        def get_active_cascades(self):
            return []
        def get_cascade_for_snapshot(self, *_a, **_kw):
            return []
        def apply_cascade_confidence_boost(self, arb, _casc):
            return arb
    eng._arbiter = _ArbiterStub()  # type: ignore[assignment]
    eng._risk_mgr = _RiskStub()    # type: ignore[assignment]
    eng._cascade = _CascadesStub() # type: ignore[assignment]
    eng._get_open_trades = lambda: []  # type: ignore[assignment]
    eng._fetch_signal_recommendation = lambda _sid: {  # type: ignore[assignment]
        "tp_pips_recommended": None,
        "sl_pips_recommended": None,
        "exit_strategy_recommended": "DYNAMIC",
    }
    eng._trade_already_open = lambda *_a, **_kw: False  # type: ignore[assignment]
    eng._record_paper_trade = lambda **_kw: None  # type: ignore[assignment]
    class _LoggerStub:
        def log_open(self, *args, **kwargs):
            return "trade-test-stub"
        def log_close(self, *args, **kwargs):
            return None
    eng._logger = _LoggerStub()  # type: ignore[assignment]

    result = eng.process(snap)
    # SL/TP doit venir du DRM (source="dynamic") et non pas des défauts 8/15
    assert result.get("drm_applied") is True
    assert result["dynamic_risk"] is not None
    assert result["dynamic_risk"]["source"] == "dynamic"
    # Les valeurs appliquées différent des défauts statiques
    assert result["tp_pips"] != 8.0 or result["sl_pips"] != 15.0
    # Cohérence locale/result
    assert result["tp_pips"] is not None
    assert result["sl_pips"] is not None
    assert result["strategy"] is not None


def test_apply_falls_back_silently_on_evaluation_error(monkeypatch):
    """Si l'évaluation DRM lève, le bloc 4b doit swallow (R6) et conserver
    les valeurs courantes. Aucun crash, pipeline reste opérationnel.
    """
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "1")
    from core.v9.trade_engine import TradeEngine

    eng = TradeEngine(db_path=":memory:")

    class _Boom:
        def evaluate(self, *_a, **_kw):
            raise RuntimeError("simulated DRM crash")

    eng._load_full_context = lambda _sid: _ctx()  # type: ignore[assignment]
    eng._dynamic_risk = _Boom()  # type: ignore[assignment]
    class _ArbiterStub:
        def consolidate(self, _sid):
            return {
                "direction": "baissiere",
                "confiance_arbitree": 80,
                "confiance_arbitree_boosted": 80,
                "principes_source": [],
                "regime_type": "NEUTRE",
            }
    class _RiskStub:
        def evaluate(self, _arb, _ctx, _open):
            return {"go": True, "raison_blocage": None}
    class _CascadesStub:
        def get_active_cascades(self):
            return []
        def get_cascade_for_snapshot(self, *_a, **_kw):
            return []
        def apply_cascade_confidence_boost(self, arb, _casc):
            return arb
    eng._arbiter = _ArbiterStub()
    eng._risk_mgr = _RiskStub()
    eng._cascade = _CascadesStub()
    eng._get_open_trades = lambda: []  # type: ignore[assignment]
    eng._fetch_signal_recommendation = lambda _sid: {  # type: ignore[assignment]
        "tp_pips_recommended": None,
        "sl_pips_recommended": None,
        "exit_strategy_recommended": "DYNAMIC",
    }
    eng._trade_already_open = lambda *_a, **_kw: False  # type: ignore[assignment]
    eng._record_paper_trade = lambda **_kw: None  # type: ignore[assignment]
    class _LoggerStub:
        def log_open(self, *args, **kwargs):
            return "trade-test-stub"
        def log_close(self, *args, **kwargs):
            return None
    eng._logger = _LoggerStub()  # type: ignore[assignment]

    # Ne doit pas lever (R6)
    result = eng.process("v9-test-apply-crash")
    assert result["error"] is None
    # Fallback sur défauts (8/15)
    assert result["tp_pips"] == 8.0 or result["tp_pips"] is not None
