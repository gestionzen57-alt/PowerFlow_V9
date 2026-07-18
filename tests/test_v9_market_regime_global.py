"""Tests — détecteur risk-on/off global (core/v9/market_regime_global.py).

Vérifie :
  - classify() : risk_on / risk_off / neutral + régime USD
  - modulation TP transmise (risk-off tempère, risk-on assume)
  - detect() lit la DB et retombe en fallback NEUTRE si vide (R6)
  - injection dans le DynamicRiskManager module bien le TP (rétro-compatible)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.market_regime_global import (
    MarketRegimeGlobal,
    GlobalRegime,
    classify,
    TP_MOD_RISK_OFF,
    TP_MOD_RISK_ON,
    TP_MOD_NEUTRAL,
)


# ---------- classify (pur) ----------


def test_classify_risk_off():
    """Refuges forts (JPY/CHF), risk-on faibles → risk_off + TP tempéré."""
    fm = {"usd": 60.0, "jpy": 75.0, "chf": 72.0, "aud": 30.0, "nzd": 28.0}
    reg = classify(fm, n_samples=30)
    assert reg.risk_sentiment == "risk_off"
    assert reg.tp_modulation == TP_MOD_RISK_OFF
    assert reg.usd_regime == "usd_strong"
    assert reg.risk_score < 0


def test_classify_risk_on():
    """Risk-on forts (AUD/NZD), refuges faibles → risk_on + TP assumé."""
    fm = {"usd": 42.0, "jpy": 30.0, "chf": 33.0, "aud": 72.0, "nzd": 70.0}
    reg = classify(fm, n_samples=30)
    assert reg.risk_sentiment == "risk_on"
    assert reg.tp_modulation == TP_MOD_RISK_ON
    assert reg.usd_regime == "usd_weak"
    assert reg.risk_score > 0


def test_classify_neutral():
    """Écart faible → neutral + TP inchangé."""
    fm = {"usd": 50.0, "jpy": 50.0, "chf": 51.0, "aud": 52.0, "nzd": 53.0}
    reg = classify(fm, n_samples=30)
    assert reg.risk_sentiment == "neutral"
    assert reg.tp_modulation == TP_MOD_NEUTRAL
    assert reg.usd_regime == "usd_neutral"


def test_to_dict_serializable():
    reg = classify({"usd": 60.0, "jpy": 75.0, "chf": 72.0, "aud": 30.0, "nzd": 28.0}, 30)
    import json
    d = reg.to_dict()
    json.dumps(d)  # ne doit pas lever
    assert d["risk_sentiment"] == "risk_off"
    assert "detail" in d


# ---------- detect (DB) ----------


def _seed_forces(tmp_path: Path, rows: list[dict]) -> Path:
    db = tmp_path / "mrg.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE forces_snapshots (
            bar_time INTEGER, force_usd REAL, force_jpy REAL, force_chf REAL,
            force_aud REAL, force_nzd REAL, force_gbp REAL, force_eur REAL,
            force_cad REAL
        )
    """)
    for r in rows:
        conn.execute(
            "INSERT INTO forces_snapshots (bar_time, force_usd, force_jpy, "
            "force_chf, force_aud, force_nzd, force_gbp, force_eur, force_cad) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (r["bar_time"], r["usd"], r["jpy"], r["chf"], r["aud"], r["nzd"],
             r.get("gbp", 50.0), r.get("eur", 50.0), r.get("cad", 50.0)),
        )
    conn.commit()
    conn.close()
    return db


def test_detect_empty_db_returns_fallback(tmp_path: Path):
    db = _seed_forces(tmp_path, [])
    reg = MarketRegimeGlobal(db_path=db).detect()
    assert reg.source == "fallback"
    assert reg.risk_sentiment == "neutral"


def test_detect_risk_off_from_db(tmp_path: Path):
    rows = [
        {"bar_time": 1000 + i, "usd": 60.0, "jpy": 76.0, "chf": 73.0,
         "aud": 30.0, "nzd": 29.0}
        for i in range(30)
    ]
    db = _seed_forces(tmp_path, rows)
    reg = MarketRegimeGlobal(db_path=db).detect()
    assert reg.source == "computed"
    assert reg.risk_sentiment == "risk_off"
    assert reg.n_samples == 30


# ---------- injection DRM (rétro-compatible) ----------


def test_drm_injection_modulates_tp():
    """Le régime global module le TP de la RiskDecision dynamique.

    On compare la même décision avec et sans régime : le risk_on doit
    augmenter le TP (avant clamp), le risk_off le réduire.
    """
    from core.v9.dynamic_risk_manager import DynamicRiskManager

    # Contexte NON saturant (coalition LTF faible) : le TP reste sous le
    # plafond de clamp (TP_MAX=40) pour que la modulation reste visible.
    ctx = {
        "scene": {
            "cinematique_json": {
                "velocite_moyenne": 0.01,
                "acceleration_deceleration": "acceleration",
                "compression_extension": {"etat": "neutre"},
            },
            "coalitions_json": [{
                "intensite_alignement": 20.0,   # < 30 → coalition faible ×0.7
                "intensite_trend": "montante",
                "age_bars": 2,
            }],
            "confluences_mtf_json": {
                "coalition_mtf_depth": "M5",     # LTF ×0.8
                "emboitement_detecte": False,
            },
        },
        "behavior": {"phase": "developpement"},
        "regime": [{"regime_type": "EXTENSION"}],
    }
    drm = DynamicRiskManager()
    base = drm.evaluate(ctx, decision={"session_marche": "london"})
    assert base.source == "dynamic"

    risk_on = GlobalRegime(risk_sentiment="risk_on", tp_modulation=1.10)
    risk_off = GlobalRegime(risk_sentiment="risk_off", tp_modulation=0.85)
    dec_on = drm.evaluate(ctx, decision={"session_marche": "london"},
                          global_regime=risk_on)
    dec_off = drm.evaluate(ctx, decision={"session_marche": "london"},
                           global_regime=risk_off)

    # Le TP risk_on > TP risk_off (modulation appliquée avant clamp).
    assert dec_on.tp_pips > dec_off.tp_pips
    # La base (sans régime) est encadrée par les deux modulations.
    assert dec_off.tp_pips < base.tp_pips < dec_on.tp_pips
    # La modulation est tracée.
    assert "global_regime_tp" in dec_off.modulation


def test_drm_injection_none_is_backward_compatible():
    """Sans global_regime, la décision est identique à l'ancien comportement."""
    from core.v9.dynamic_risk_manager import DynamicRiskManager
    ctx = {"behavior": {"phase": "developpement"}, "regime": [{"regime_type": "EXTENSION"}]}
    drm = DynamicRiskManager()
    d1 = drm.evaluate(ctx, decision={"session_marche": "london"})
    d2 = drm.evaluate(ctx, decision={"session_marche": "london"}, global_regime=None)
    assert d1.tp_pips == d2.tp_pips
    assert "global_regime_tp" not in d2.modulation
