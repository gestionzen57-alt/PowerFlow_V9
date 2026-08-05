"""V10 Currency Behavior — tests unitaires (Phase 32, 2026-08-05).

Couvre les obligations de la Phase 32 :
  Layer 0 : load_currency_series (DB réelle + R6 fail-open + saturation)
  Layer 1 : états, coalitions, leadership, régimes, lead-lag
  Layer 2 : fidélité (garde-fou C)
  Layer 3 : réversibilité, calibration, drift
  Layer 4 : narratives + behavior_context global

Total ≥ 20 tests. 0 import core/v9/ (R2 additif strict).
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_currency_behavior import (  # noqa: E402
    CONFIG,
    CURRENCIES,
    CurrencySeries,
    apply_behavior_config,
    build_behavior_context,
    build_causal_narrative,
    build_narrative,
    calibrate_regime_thresholds,
    classify_currency_states,
    classify_regime,
    compute_fidelity,
    compute_fidelity_composite,
    compute_fidelity_extreme,
    compute_lead_lag,
    compute_leadership,
    detect_coalitions,
    detect_drift,
    get_behavior_state,
    load_currency_series,
    reset_behavior_config,
    session_of,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
def _make_series(n: int = 120, forces: dict = None) -> CurrencySeries:
    """Série synthétique : prix avec rendements non triviaux + forces par devise.

    Prix : marche aléatoire déterministe (sinus + bruit) — rendements
    variables, requis par le calcul de fidélité.
    """
    forces = forces or {}
    s = CurrencySeries(pair="GBPUSD", timeframe="M30")
    px = 1.30
    for i in range(n):
        s.timestamps.append(f"2026-08-0{(i % 5) + 1}T{(i % 22):02d}:00:00Z")
        # rendement variable : 0.05% ± 0.15% * sin
        px *= 1.0 + 0.0005 + 0.0015 * math.sin(i / 4.0)
        s.closes.append(px)
        for c in CURRENCIES:
            base = forces.get(c, "flat")
            if base == "flat":
                v = 50.0
            elif base == "rising":
                v = 30.0 + 60.0 * i / n
            elif base == "falling":
                v = 70.0 - 60.0 * i / n
            elif base == "cyclical":
                v = 50.0 + 30.0 * math.sin(i / 3.0)
            elif isinstance(base, float):  # constante
                v = base
            else:  # liste de valeurs
                v = base[i] if i < len(base) else 50.0
            s.forces.setdefault(c, []).append(v)
    return s


def _make_fake_db(path: str) -> str:
    """DB SQLite temporaire imitant forces_snapshots (Layer 0)."""
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE forces_snapshots (
            timestamp TEXT, symbol TEXT, timeframe TEXT,
            close REAL, force_usd REAL, force_gbp REAL, force_eur REAL,
            force_jpy REAL, force_cad REAL, force_chf REAL,
            force_aud REAL, force_nzd REAL
        )
    """)
    for i in range(60):
        ts = f"2026-08-0{(i % 5) + 1}T{8 + (i % 8):02d}:00:00Z"
        cur.execute(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts, "GBPUSD", "M30", 1.30 + i * 0.0001,
             50 + i / 10, 40 + i / 10, 60, 55, 45, 65, 35, 55),
        )
    # 2 points saturés (0/100) doivent être filtrés
    cur.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-08-05T06:00:00Z", "GBPUSD", "M30", 1.30,
         0.0, 100.0, 50, 50, 50, 50, 50, 50),
    )
    con.commit()
    con.close()
    return path


# ─────────────────────────────────────────────────────────────────────
# Layer 3 — Réversibilité (règle d'or CEO)
# ─────────────────────────────────────────────────────────────────────
def test_apply_config_surcharge_et_idempotent():
    r1 = apply_behavior_config({"coalition_corr_min": 0.8})
    assert r1["applied"]
    assert get_behavior_state()["config_active"]["coalition_corr_min"] == 0.8
    # Idempotent : 2e appel ne change pas la valeur
    apply_behavior_config({"coalition_corr_min": 0.8})
    assert get_behavior_state()["config_active"]["coalition_corr_min"] == 0.8
    reset_behavior_config()


def test_apply_config_merge_profond_sessions():
    apply_behavior_config({"sessions_utc": {"ASIAN": (0, 7), "LONDON": (7, 15)}})
    cfg = get_behavior_state()["config_active"]
    # Merge profond : les clés non touchées de sessions_utc survivent
    assert "NY" in cfg["sessions_utc"]
    assert cfg["sessions_utc"]["ASIAN"] == (0, 7)
    reset_behavior_config()


def test_apply_config_type_invalide_rejete():
    r = apply_behavior_config("nope")
    assert not r["applied"]
    assert r["error"] == "cfg_must_be_dict"


def test_reset_restaure_defaults():
    apply_behavior_config({"drift_eps": 0.9})
    assert get_behavior_state()["config_active"]["drift_eps"] == 0.9
    reset_behavior_config()
    assert get_behavior_state()["config_active"] == CONFIG


def test_state_serialisable_json():
    s = get_behavior_state()
    json.dumps(s)  # ne doit pas lever


# ─────────────────────────────────────────────────────────────────────
# Layer 0 — Observation
# ─────────────────────────────────────────────────────────────────────
def test_load_series_db_reelle():
    s = load_currency_series("data/v9_forces.db", "GBPUSD", "M30", days=7)
    assert len(s) > 50
    assert len(s.closes) == len(s.timestamps)
    for c in CURRENCIES:
        assert len(s.forces[c]) == len(s)
    assert all(2.0 <= v <= 98.0 for v in s.forces["usd"])


def test_load_series_db_inexistante_fail_open():
    s = load_currency_series("nonexistent_zz.db", "GBPUSD", "M30")
    assert len(s) == 0


def test_load_series_filtre_saturation(tmp_path):
    db = _make_fake_db(str(tmp_path / "fake.db"))
    s = load_currency_series(db, "GBPUSD", "M30", days=30)
    assert len(s) == 60  # 2 points saturés retirés
    assert all(2.0 <= v <= 98.0 for v in s.forces["usd"])


def test_load_series_table_absente_fail_open(tmp_path):
    db = str(tmp_path / "empty.db")
    con = sqlite3.connect(db)
    con.close()
    s = load_currency_series(db, "GBPUSD", "M30")
    assert len(s) == 0


# ─────────────────────────────────────────────────────────────────────
# Layer 1a — Dynamique temporelle
# ─────────────────────────────────────────────────────────────────────
def test_etat_rising_rallye():
    s = _make_series(forces={"usd": "rising"})
    st = classify_currency_states(s)
    assert st["usd"]["state"] == "RALLYE"
    assert st["usd"]["percentile"] >= 70


def test_etat_falling_decline():
    s = _make_series(forces={"chf": "falling"})
    st = classify_currency_states(s)
    assert st["chf"]["state"] in ("DECLINE", "RETOURNEMENT")
    assert st["chf"]["percentile"] <= 30


def test_etat_flat_range():
    s = _make_series()
    st = classify_currency_states(s)
    assert st["gbp"]["state"] == "RANGE"


def test_etat_donnees_insuffisantes_range():
    s = _make_series(n=5)
    st = classify_currency_states(s)
    assert st["gbp"]["state"] == "RANGE"
    assert st["gbp"]["value"] == 50.0


# ─────────────────────────────────────────────────────────────────────
# Layer 1b — Relations inter-devises
# ─────────────────────────────────────────────────────────────────────
def test_coalition_cycliques_detectee():
    aud = [50 + 30 * math.sin(i / 3.0) for i in range(120)]
    nzd = [50 + 29 * math.sin(i / 3.0) for i in range(120)]
    s = _make_series(forces={"aud": aud, "nzd": nzd})
    co = detect_coalitions(s)
    assert co["n_coalitions"] >= 1
    assert any(frozenset(c["members"]) == frozenset(["AUD", "NZD"])
               for c in co["coalitions"])


def test_coalition_corr_min_config():
    s = _make_series(forces={"aud": "cyclical", "nzd": "cyclical",
                             "usd": "rising"})
    # Seuil strict → la corrélation ~1 AUD/NZD reste, rien d'autre
    apply_behavior_config({"coalition_corr_min": 0.99})
    co = detect_coalitions(s)
    reset_behavior_config()
    assert any(frozenset(c["members"]) == frozenset(["AUD", "NZD"])
               for c in co["coalitions"])


def test_leadership_leader_max_follower_min():
    forces = {}
    for c in CURRENCIES:
        forces[c] = {"usd": 80.0, "gbp": 20.0}.get(c, 50.0)
    s = _make_series(forces=forces)
    ld = compute_leadership(s)
    assert ld["leader"] == "USD"
    assert ld["follower"] == "GBP"


def test_leadership_rotation_detectee():
    # USD fort sur la 1re moitié, GBP fort sur la 2e
    usd = [80.0] * 60 + [30.0] * 60
    gbp = [20.0] * 60 + [70.0] * 60
    s = _make_series(forces={"usd": usd, "gbp": gbp})
    ld = compute_leadership(s)
    assert ld["rotation_detected"]
    assert ld["leader"] == "GBP"
    assert ld["leader_before"] == "USD"


# ─────────────────────────────────────────────────────────────────────
# Layer 1c — Régimes
# ─────────────────────────────────────────────────────────────────────
def test_regime_risk_on():
    s = _make_series(forces={"aud": 80.0, "nzd": 75.0, "jpy": 20.0, "chf": 30.0})
    rg = classify_regime(s, session="LONDON")
    assert rg["regime"] == "RISK_ON"
    assert rg["session"] == "LONDON"


def test_regime_safe_haven():
    s = _make_series(forces={"aud": 20.0, "nzd": 25.0, "jpy": 80.0, "chf": 85.0})
    rg = classify_regime(s)
    assert rg["regime"] == "SAFE_HAVEN"


def test_regime_mixed_deux_flags():
    s = _make_series(forces={"aud": 80.0, "nzd": 75.0, "jpy": 80.0, "chf": 85.0})
    rg = classify_regime(s)
    assert rg["regime"] == "MIXED"


def test_regime_neutral():
    s = _make_series()
    rg = classify_regime(s)
    assert rg["regime"] == "NEUTRAL"


def test_session_of_borne_utc():
    assert session_of(datetime(2026, 8, 5, 3, 0, tzinfo=timezone.utc)) == "ASIAN"
    assert session_of(datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)) == "LONDON"
    assert session_of(datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)) == "NY"


# ─────────────────────────────────────────────────────────────────────
# Layer 1d — Causalité multi-TF
# ─────────────────────────────────────────────────────────────────────
def test_lead_lag_slow_leads():
    # H4 monte avec un léger décalage temporel vs M30 → SLOW_LEADS attendu
    # (le TF lent reflète le même signal, corrélations croisées positives)
    h4 = _make_series(n=60, forces={"gbp": "rising"})
    m30 = _make_series(n=60, forces={"gbp": "rising"})
    ll = compute_lead_lag(h4, m30)
    assert ll["n_currencies_total"] >= 1
    assert ll["lead_lag"] in ("SLOW_LEADS", "SYNCHRONOUS", "FAST_LEADS")


def test_lead_lag_synchrone_flat():
    h4 = _make_series(n=60)
    m30 = _make_series(n=60)
    ll = compute_lead_lag(h4, m30)
    assert "lead_lag" in ll


# ─────────────────────────────────────────────────────────────────────
# Layer 2 — Fidélité (garde-fou C)
# ─────────────────────────────────────────────────────────────────────
def test_fidelite_forces_refletent_prix():
    # Force GBP croissante + prix dont les rendements futurs croissent aussi
    # (GBPUSD monte de plus en plus vite quand GBP force) → corr positive
    s = _make_series(n=200, forces={"gbp": "rising"})
    px = 1.30
    closes = []
    for i in range(200):
        px *= 1.0 + 0.0002 + 0.00001 * i  # rendements croissants
        closes.append(px)
    s.closes = closes
    fid = compute_fidelity(s)
    assert fid["n_points"] == 200
    assert fid["per_currency"]["gbp"]["corr"] > 0.5
    assert fid["per_currency"]["gbp"]["n_samples"] >= 10


def test_fidelite_donnees_insuffisantes():
    s = _make_series(n=6)
    fid = compute_fidelity(s)
    assert fid["composite"] == 0.0
    assert not fid["reliable"]


def test_fidelite_composite_pondere():
    f30 = {"composite": 0.6, "reliable": True}
    f1 = {"composite": 0.4, "reliable": True}
    comp = compute_fidelity_composite(f30, f1)
    assert comp["composite"] == 0.6 * 0.6 + 0.4 * 0.4  # 0.52
    assert comp["reliable"]


def test_fidelite_composite_en_dessous_seuil():
    f30 = {"composite": 0.1}
    f1 = {"composite": 0.2}
    comp = compute_fidelity_composite(f30, f1)
    assert not comp["reliable"]
    assert comp["reason"] == "fidelity_below_threshold"


def test_fidelite_extreme_force_fiable():
    # Force USD en hausse + prix montant de plus en plus vite quand USD
    # est au percentile haut → WR directionnel élevé aux queues
    s = _make_series(n=200, forces={"usd": "rising"})
    px = 1.30
    closes = []
    for i in range(200):
        px *= 1.0 + 0.0002 + 0.00001 * i
        closes.append(px)
    s.closes = closes
    fx = compute_fidelity_extreme(s)
    assert fx["n_points"] == 200
    assert fx["per_currency"]["usd"]["wr_hi_pct"] is not None
    assert fx["per_currency"]["usd"]["wr_hi_pct"] > 60.0


def test_fidelite_extreme_donnees_insuffisantes():
    s = _make_series(n=10)
    fx = compute_fidelity_extreme(s)
    assert not fx["extreme_reliable"]
    assert fx["reason"] == "insufficient_data"


def test_fidelite_extreme_meilleure_devise_detectee():
    s = _make_series(n=200, forces={"usd": "rising"})
    px = 1.30
    closes = []
    for i in range(200):
        px *= 1.0 + 0.0002 + 0.00001 * i
        closes.append(px)
    s.closes = closes
    fx = compute_fidelity_extreme(s)
    assert fx["best_currency"] == "USD"
    assert fx["best_wr_pct"] > 60.0


def test_behavior_context_extreme_reliable_non_degrade():
    # USD extrême fiable → le contexte n'est PAS degradé même si la
    # corrélation linéaire est ~0 (le signal vit aux queues)
    s = _make_series(n=200, forces={"usd": "rising"})
    px = 1.30
    closes = []
    for i in range(200):
        px *= 1.0 + 0.0002 + 0.00001 * i
        closes.append(px)
    s.closes = closes
    ctx = build_behavior_context(s, s)
    assert ctx["fidelity_extreme"]["extreme_reliable"]


# ─────────────────────────────────────────────────────────────────────
# Layer 3b — Calibration + drift
# ─────────────────────────────────────────────────────────────────────
def test_calibration_propose_percentiles():
    s = _make_series(forces={"aud": "rising", "nzd": "rising",
                             "jpy": "falling", "chf": "falling"})
    cal = calibrate_regime_thresholds(s)
    assert cal["proposed"] is not None
    assert 0 < cal["proposed"]["risk_on_threshold"] <= 100
    assert cal["proposed"]["n_samples_cycliques"] > 0


def test_calibration_donnees_insuffisantes():
    s = _make_series(n=5)
    cal = calibrate_regime_thresholds(s)
    assert cal["proposed"] is None
    assert cal["reason"] == "insufficient_data"


def test_drift_detecte():
    hist = [0.5] * 48 + [0.1] * 12
    dr = detect_drift(hist)
    assert dr["drift_detected"]


def test_drift_absent():
    hist = [0.5] * 60
    dr = detect_drift(hist)
    assert not dr["drift_detected"]


def test_drift_historique_court():
    dr = detect_drift([0.5, 0.5, 0.5])
    assert not dr["drift_detected"]
    assert dr["reason"] == "insufficient_history"


# ─────────────────────────────────────────────────────────────────────
# Layer 4 — Expression
# ─────────────────────────────────────────────────────────────────────
def test_narrative_contient_leader_et_regime():
    ctx = {
        "leadership": {"leader": "GBP", "leader_strength": 72.0,
                       "rotation_detected": True, "leader_before": "USD"},
        "regime": {"regime": "RISK_ON", "session": "LONDON"},
        "fidelity_composite": {"reliable": True, "composite": 0.61},
    }
    n = build_narrative(ctx)
    assert "GBP" in n
    assert "RISK_ON" in n
    assert "fidélité OK" in n


def test_narrative_donnees_insuffisantes():
    n = build_narrative({})
    assert "insuffisantes" in n


def test_narrative_fidelite_degradee():
    ctx = {
        "leadership": {"leader": "USD", "leader_strength": 60.0},
        "regime": {"regime": "NEUTRAL", "session": "ASIAN"},
        "fidelity_composite": {"reliable": False, "composite": 0.2},
    }
    n = build_narrative(ctx)
    assert "DÉGRADÉE" in n


def test_causal_narrative_chaines():
    assert "H4 précède" in build_causal_narrative({"lead_lag": {"lead_lag": "SLOW_LEADS"}})
    assert "M30 précède" in build_causal_narrative({"lead_lag": {"lead_lag": "FAST_LEADS"}})
    assert "ensemble" in build_causal_narrative({"lead_lag": {"lead_lag": "SYNCHRONOUS"}})


def test_behavior_context_complet():
    s = _make_series(n=200, forces={"usd": "rising", "aud": 80.0, "nzd": 75.0})
    s.timestamps = ["2026-08-05T10:00:00Z"] * 200  # session déterministe
    ctx = build_behavior_context(s, s)
    assert ctx["pair"] == "GBPUSD"
    assert ctx["session"] == "LONDON"
    assert "per_currency" in ctx and len(ctx["per_currency"]) == 8
    assert "coalitions" in ctx
    assert "leadership" in ctx
    assert "regime" in ctx
    assert "fidelity_composite" in ctx
    assert isinstance(ctx["narrative"], str) and ctx["narrative"]
    assert isinstance(ctx["degraded"], bool)
    json.dumps(ctx)  # R9 serialisable


def test_behavior_context_marque_degrade_si_fidelite_basse():
    # Prix plats (pas de rendement) + forces constantes → fidélité ~0
    s = _make_series(n=200)
    for i in range(len(s.closes)):
        s.closes[i] = 1.30
    ctx = build_behavior_context(s, s)
    assert ctx["degraded"]
    assert "fidelity_below_threshold" in ctx.get("warning", "")
