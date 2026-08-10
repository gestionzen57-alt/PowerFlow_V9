"""V10 Force Native — tests unitaires (Phase 20++ CEO étape 9.1).

Cible R7 : 20 tests verts minimum.

Doctrine V10 :
  R2 additif pur (0 import core/v9/)
  R6 fail-open (forces absentes → neutre, intensité inconnue → MOYEN)
  R7 tests verts cumulés (cible 565+ après Phase 20+)
  R9 audit metadata honnête (JSON sérialisable)
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_force_native import (
    COMP_EXT_STATES,
    CROISEMENT_DIRECTION_TO_PIPS,
    INTENSITY_TO_PIPS,
    NativeForceFeatures,
    NativeForceReport,
    RECROISEMENT_BONUS_PIPS,
    REJET_PENALTY_PIPS,
    _intensity_to_pips,
    _pair_to_base_quote,
    _safe_float,
    apply_calibrated_params,
    compute_force_native_features,
    compute_force_native_pnl,
    compute_native_force_report,
    demo_run,
    get_runtime_state,
    load_snapshots_from_db,
    reset_runtime_params,
)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _make_snapshot(
    bar_time: int,
    force_usd: float = 50.0,
    force_eur: float = 50.0,
    force_gbp: float = 50.0,
    force_jpy: float = 50.0,
    force_chf: float = 50.0,
    force_aud: float = 50.0,
    force_cad: float = 50.0,
    force_nzd: float = 50.0,
    close: float = 1.1000,
    compression_extension_etat: str = "NEUTRE",
    compression_extension_intensite: str = "MOYEN",
    croisement_detecte: int = 0,
    croisement_direction: str = "NEUTRE",
    recroisement_detecte: int = 0,
    rejet_repulsion_detecte: int = 0,
    rejet_intensite: float = 0.0,
    timestamp: str = "",
) -> dict:
    """Helper : crée 1 snapshot minimaliste pour tests."""
    return {
        "bar_time": bar_time,
        "timestamp": timestamp or f"2026-08-05T{bar_time % 24:02d}:00:00Z",
        "is_closed_bar": 1,
        "close": close,
        "force_usd": force_usd,
        "force_eur": force_eur,
        "force_gbp": force_gbp,
        "force_jpy": force_jpy,
        "force_chf": force_chf,
        "force_aud": force_aud,
        "force_cad": force_cad,
        "force_nzd": force_nzd,
        "compression_extension_etat": compression_extension_etat,
        "compression_extension_intensite": compression_extension_intensite,
        "croisement_detecte": croisement_detecte,
        "croisement_direction": croisement_direction,
        "recroisement_detecte": recroisement_detecte,
        "rejet_repulsion_detecte": rejet_repulsion_detecte,
        "rejet_intensite": rejet_intensite,
    }


def _make_snapshots_polarized(n: int, trending: bool = True) -> list:
    """Génère n snapshots avec compression + croisement progressif."""
    snaps = []
    base_force = 70.0 if trending else 30.0
    quote_force = 30.0 if trending else 70.0
    close = 1.1000
    for i in range(n):
        close += 0.0010 if trending else -0.0010
        snaps.append(_make_snapshot(
            bar_time=1783111080 + i * 1800,
            force_eur=base_force,
            force_usd=quote_force,
            close=close,
            compression_extension_etat="COMPRESSION" if i % 3 == 0 else "EXTENSION",
            compression_extension_intensite="MOYEN",
            croisement_detecte=1 if i % 5 == 0 else 0,
            croisement_direction="HAUSSIERE" if trending else "BAISSIERE",
        ))
    return snaps


# ─────────────────────────────────────────────────────────────────────
# TESTS CONSTANTS (5)
# ─────────────────────────────────────────────────────────────────────

def test_constants_comp_ext_states():
    assert COMP_EXT_STATES == ("COMPRESSION", "EXTENSION", "NEUTRE")


def test_constants_intensity_to_pips_keys():
    """INTENSITY_TO_PIPS doit contenir FAIBLE/MOYEN/FORT/EXTREME."""
    assert set(INTENSITY_TO_PIPS.keys()) == {"FAIBLE", "MOYEN", "FORT", "EXTREME"}


def test_constants_croisement_direction_signs():
    """HAUSSIERE=+1, BAISSIERE=-1, NEUTRE=0."""
    assert CROISEMENT_DIRECTION_TO_PIPS["HAUSSIERE"] == 1.0
    assert CROISEMENT_DIRECTION_TO_PIPS["BAISSIERE"] == -1.0
    assert CROISEMENT_DIRECTION_TO_PIPS["NEUTRE"] == 0.0


def test_constants_recroisement_bonus_positive():
    """RECROISEMENT_BONUS_PIPS doit être > 0."""
    assert RECROISEMENT_BONUS_PIPS > 0


def test_constants_rejet_penalty_negative():
    """REJET_PENALTY_PIPS doit être < 0."""
    assert REJET_PENALTY_PIPS < 0


# ─────────────────────────────────────────────────────────────────────
# TESTS HELPERS (4)
# ─────────────────────────────────────────────────────────────────────

def test_helper_pair_to_base_quote_eurusd():
    assert _pair_to_base_quote("EURUSD") == ("EUR", "USD")


def test_helper_pair_to_base_quote_gbpusd():
    assert _pair_to_base_quote("GBPUSD") == ("GBP", "USD")


def test_helper_safe_float_none():
    assert _safe_float(None) == 0.0
    assert _safe_float(None, default=42.0) == 42.0


def test_helper_intensity_to_pips_unknown_returns_moyen():
    """R6 fail-open : intensité inconnue → MOYEN."""
    assert _intensity_to_pips("INCONNUE") == INTENSITY_TO_PIPS["MOYEN"]
    assert _intensity_to_pips("") == INTENSITY_TO_PIPS["MOYEN"]


# ─────────────────────────────────────────────────────────────────────
# TESTS FEATURES (4)
# ─────────────────────────────────────────────────────────────────────

def test_features_eurusd_basic():
    snap = _make_snapshot(bar_time=1000, force_eur=80.0, force_usd=20.0)
    feat = compute_force_native_features(snap, "EURUSD")
    assert feat.force_base == 80.0
    assert feat.force_quote == 20.0
    assert feat.force_delta == 60.0
    assert feat.force_base_rank == 1  # EUR top
    assert feat.force_quote_rank == 8  # USD bottom


def test_features_gbpusd_force_delta():
    snap = _make_snapshot(bar_time=1000, force_gbp=70.0, force_usd=30.0)
    feat = compute_force_native_features(snap, "GBPUSD")
    assert feat.force_delta == 40.0


def test_features_compression_extension_passed():
    snap = _make_snapshot(
        bar_time=1000,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="FORT",
    )
    feat = compute_force_native_features(snap, "EURUSD")
    assert feat.compression_extension_etat == "COMPRESSION"
    assert feat.compression_extension_intensite == "FORT"


def test_features_serializable_json():
    snap = _make_snapshot(bar_time=1000)
    feat = compute_force_native_features(snap, "EURUSD")
    j = json.dumps(feat.as_dict())
    assert "force_base" in j


# ─────────────────────────────────────────────────────────────────────
# TESTS PNL NATIF (4)
# ─────────────────────────────────────────────────────────────────────

def test_pnl_native_compression_bullish_positive():
    """COMPRESSION + force_delta positive → pnl > 0."""
    snap = _make_snapshot(
        bar_time=1000,
        force_eur=80.0, force_usd=20.0,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="FORT",
    )
    feat = compute_force_native_features(snap, "EURUSD")
    pnl = compute_force_native_pnl([feat], pair="EURUSD", direction="BULLISH")
    assert pnl > 0


def test_pnl_native_compression_bearish_negative():
    """COMPRESSION + BEARISH → pnl < 0."""
    snap = _make_snapshot(
        bar_time=1000,
        force_eur=20.0, force_usd=80.0,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="FORT",
    )
    feat = compute_force_native_features(snap, "EURUSD")
    pnl = compute_force_native_pnl([feat], pair="EURUSD", direction="BEARISH")
    assert pnl < 0


def test_pnl_native_neutre_state_lower_than_compression():
    """NEUTRE → pnl plus faible que COMPRESSION (même intensité)."""
    snap_neutre = _make_snapshot(
        bar_time=1000,
        force_eur=70.0, force_usd=30.0,
        compression_extension_etat="NEUTRE",
        compression_extension_intensite="MOYEN",
    )
    snap_compression = _make_snapshot(
        bar_time=1000,
        force_eur=70.0, force_usd=30.0,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="MOYEN",
    )
    f_n = compute_force_native_features(snap_neutre, "EURUSD")
    f_c = compute_force_native_features(snap_compression, "EURUSD")
    pnl_neutre = compute_force_native_pnl([f_n], direction="BULLISH")
    pnl_comp = compute_force_native_pnl([f_c], direction="BULLISH")
    assert abs(pnl_comp) > abs(pnl_neutre)


def test_pnl_native_rejet_penalty_applied():
    """Rejet répulsion détecté → pnl plus faible."""
    snap_no_rejet = _make_snapshot(
        bar_time=1000,
        force_eur=70.0, force_usd=30.0,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="MOYEN",
        rejet_repulsion_detecte=0,
    )
    snap_rejet = _make_snapshot(
        bar_time=1000,
        force_eur=70.0, force_usd=30.0,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="MOYEN",
        rejet_repulsion_detecte=1,
        rejet_intensite=1.0,
    )
    f_no = compute_force_native_features(snap_no_rejet, "EURUSD")
    f_re = compute_force_native_features(snap_rejet, "EURUSD")
    pnl_no = compute_force_native_pnl([f_no], direction="BULLISH")
    pnl_re = compute_force_native_pnl([f_re], direction="BULLISH")
    assert pnl_re < pnl_no


# ─────────────────────────────────────────────────────────────────────
# TESTS REPORT (3)
# ─────────────────────────────────────────────────────────────────────

def test_report_insufficient_snapshots():
    """len(snapshots) < horizon+1 → report vide avec error."""
    rep = compute_native_force_report([], "EURUSD", "M30", horizon=3)
    assert rep.n_snapshots_used == 0
    assert rep.audit.get("error") == "insufficient_snapshots"


def test_report_polarized_trending_bullish():
    """Snapshots trending bullish → pnl natif > proxy (compression)."""
    snaps = _make_snapshots_polarized(30, trending=True)
    rep = compute_native_force_report(snaps, "EURUSD", "M30", horizon=3)
    assert rep.n_snapshots_used > 0
    assert "wr_native" in rep.audit
    assert "wr_proxy" in rep.audit
    assert "delta_wr" in rep.audit
    # trending bullish → WR native devrait être > 50%
    assert rep.audit["wr_native"] > 0.50


def test_report_serializable():
    """Report doit être JSON-sérialisable."""
    snaps = _make_snapshots_polarized(10, trending=True)
    rep = compute_native_force_report(snaps, "EURUSD", "M30", horizon=3)
    j = json.dumps(rep.as_dict())
    assert "pair" in j
    assert "pnl_pips_native" in j


# ─────────────────────────────────────────────────────────────────────
# TESTS DB (3)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """DB temporaire avec table forces_snapshots."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, timeframe TEXT, bar_time INTEGER,
            close REAL, is_closed_bar INTEGER,
            force_usd REAL, force_gbp REAL, force_eur REAL,
            force_jpy REAL, force_cad REAL, force_chf REAL,
            force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT,
            compression_extension_intensite TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_snapshots(db_path: str, snapshots: list) -> None:
    con = sqlite3.connect(db_path)
    for s in snapshots:
        con.execute("""
            INSERT INTO forces_snapshots (
                symbol, timeframe, bar_time, close, is_closed_bar,
                force_usd, force_gbp, force_eur, force_jpy, force_cad,
                force_chf, force_aud, force_nzd,
                compression_extension_etat, compression_extension_intensite
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "EURUSD", "M30", s["bar_time"], s["close"],
            s["force_usd"], s["force_gbp"], s["force_eur"],
            s["force_jpy"], s["force_cad"], s["force_chf"],
            s["force_aud"], s["force_nzd"],
            s["compression_extension_etat"],
            s["compression_extension_intensite"],
        ))
    con.commit()
    con.close()


def test_load_snapshots_from_db_basic(tmp_db):
    """Charge 10 snapshots depuis DB → retourne 10."""
    snaps = _make_snapshots_polarized(10)
    _populate_snapshots(tmp_db, snaps)
    loaded = load_snapshots_from_db(tmp_db, "EURUSD", "M30")
    assert len(loaded) == 10


def test_load_snapshots_from_db_empty():
    """DB inexistante → [] (R6 fail-open)."""
    loaded = load_snapshots_from_db("/nonexistent_xyz.db", "EURUSD", "M30")
    assert loaded == []


def test_load_snapshots_from_db_limit(tmp_db):
    """limit=5 → retourne 5 snapshots max."""
    snaps = _make_snapshots_polarized(20)
    _populate_snapshots(tmp_db, snaps)
    loaded = load_snapshots_from_db(tmp_db, "EURUSD", "M30", limit=5)
    assert len(loaded) == 5


# ─────────────────────────────────────────────────────────────────────
# TESTS DEMO (2)
# ─────────────────────────────────────────────────────────────────────

def test_demo_run_returns_list():
    """demo_run retourne une liste de NativeForceReport."""
    reps = demo_run("data/v9_forces.db")
    assert isinstance(reps, list)
    # Au moins quelques reports si DB existe
    # (peut être [] si DB absente, mais sur ce projet elle existe)


def test_demo_run_reports_have_audit():
    """Chaque report a un audit avec wr_native/wr_proxy."""
    reps = demo_run("data/v9_forces.db")
    if reps:
        for r in reps:
            assert "wr_native" in r.audit
            assert "wr_proxy" in r.audit
            assert "delta_wr" in r.audit
            assert isinstance(r.pnl_pips_native, float)


# ─────────────────────────────────────────────────────────────────────
# TESTS R9 AUDIT (2)
# ─────────────────────────────────────────────────────────────────────

def test_audit_audit_metadata_honnete():
    """Audit metadata : source loggée + JSON sérialisable."""
    snaps = _make_snapshots_polarized(5)
    rep = compute_native_force_report(snaps, "EURUSD", "M30", horizon=3)
    assert rep.audit["method"] == "V10 native (compression/extension + croisement + force_delta)"
    assert "intensity_to_pips" in rep.audit
    assert "recroisement_bonus" in rep.audit
    assert "rejet_penalty" in rep.audit


def test_audit_n_trades_audit_correct():
    """n_snapshots_used == n_trades (audit R9 honest)."""
    snaps = _make_snapshots_polarized(20)
    rep = compute_native_force_report(snaps, "EURUSD", "M30", horizon=3)
    # 20 snapshots - 3 horizon = 17 trades
    assert rep.n_snapshots_used == 17


# ─────────────────────────────────────────────────────────────────────
# TESTS PHASE 28b ÉTAPE 1 — apply_calibrated_params (R2 additif)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def _phase28b_reset_runtime():
    """Garantit runtime reset avant ET après chaque test."""
    reset_runtime_params()
    yield
    reset_runtime_params()


def test_apply_calibrated_params_changes_intensity_to_pips(_phase28b_reset_runtime):
    """apply_calibrated_params modifie _intensity_to_pips effectivement."""
    snaps = _make_snapshots_polarized(5)
    rep_default = compute_native_force_report(snaps, "EURUSD", "M30", horizon=3)
    aud_default = rep_default.audit["intensity_to_pips"].copy()

    apply_calibrated_params({
        "intensity_to_pips": {"FAIBLE": 0.5, "MOYEN": 1.5, "FORT": 3.0, "EXTREME": 5.0},
        "recroisement_bonus_pips": 1.5,
        "rejet_penalty_pips": -2.0,
        "method": "phase28b_test",
        "n_pairs_tf_evaluated": 18,
    })
    rep_after = compute_native_force_report(snaps, "EURUSD", "M30", horizon=3)
    aud_after = rep_after.audit["intensity_to_pips"]

    # Constantes module intactes (R2 additif pur)
    assert INTENSITY_TO_PIPS == {"FAIBLE": 1.5, "MOYEN": 3.0, "FORT": 5.0, "EXTREME": 8.0}
    # Audit report reflète l'override
    assert aud_after != aud_default
    assert aud_after == {"FAIBLE": 0.5, "MOYEN": 1.5, "FORT": 3.0, "EXTREME": 5.0}
    assert rep_after.audit["runtime_override_active"] is True


def test_apply_calibrated_params_is_idempotent(_phase28b_reset_runtime):
    """2 appels avec mêmes valeurs → idempotent=True au 2e, audit inchangé."""
    p = {
        "intensity_to_pips": {"FAIBLE": 0.5, "MOYEN": 1.5, "FORT": 3.0, "EXTREME": 5.0},
        "recroisement_bonus_pips": 1.5,
        "rejet_penalty_pips": -2.0,
        "method": "phase28b_idem",
        "n_pairs_tf_evaluated": 18,
    }
    a1 = apply_calibrated_params(p)
    a2 = apply_calibrated_params(p)
    assert a1["applied"] is True
    assert a2["applied"] is True
    assert a1["idempotent"] is False
    assert a2["idempotent"] is True
    # Compteur global : a1 et a2 incrémentent, mais peut être partagé avec d'autres tests
    assert a2["n_applies_total"] >= 2


def test_apply_calibrated_params_invalid_order_falls_back(_phase28b_reset_runtime):
    """Ordre FAIBLE>MOYEN invalide → defaults, applied=True mais i2p reste default."""
    res = apply_calibrated_params({
        "intensity_to_pips": {"FAIBLE": 5.0, "MOYEN": 1.0, "FORT": 3.0, "EXTREME": 8.0},  # ordre cassé
        "recroisement_bonus_pips": 1.0,
        "rejet_penalty_pips": -1.0,
    })
    state = get_runtime_state()
    # L'ordre n'étant pas monotone croissant, fallback INTENSITY_TO_PIPS default
    assert state["intensity_to_pips"] == {"FAIBLE": 1.5, "MOYEN": 3.0, "FORT": 5.0, "EXTREME": 8.0}
    assert res["applied"] is True


def test_apply_calibrated_params_accepts_calibratedparams_dataclass(_phase28b_reset_runtime):
    """Accepte un CalibratedParams dataclass du calibrator (R6 input tolérant)."""
    from core.v10.v10_force_native_calibrator import CalibratedParams
    cp = CalibratedParams(
        intensity_to_pips={"FAIBLE": 0.5, "MOYEN": 2.5, "FORT": 4.0, "EXTREME": 6.5},
        recroisement_bonus_pips=1.5,
        rejet_penalty_pips=-1.5,
        method="phase27_grid_search",
        n_pairs_tf_evaluated=18,
        target_metric="delta_wr",
        target_metric_value=0.05,
    )
    res = apply_calibrated_params(cp)
    assert res["applied"] is True
    state = get_runtime_state()
    assert state["intensity_to_pips"] == {"FAIBLE": 0.5, "MOYEN": 2.5, "FORT": 4.0, "EXTREME": 6.5}
    assert state["audit"]["method"] == "phase27_grid_search"


def test_apply_calibrated_params_rejects_invalid_type(_phase28b_reset_runtime):
    """Type non-dataclass non-dict → applied=False, error explicite."""
    res = apply_calibrated_params("FAIBLE=1,MOYEN=2,...")
    assert res["applied"] is False
    assert "error" in res


def test_reset_runtime_params_restores_defaults(_phase28b_reset_runtime):
    """reset_runtime_params() restaure les constantes module après override."""
    apply_calibrated_params({
        "intensity_to_pips": {"FAIBLE": 0.1, "MOYEN": 0.2, "FORT": 0.3, "EXTREME": 0.4},
        "recroisement_bonus_pips": 0.5,
        "rejet_penalty_pips": -0.5,
    })
    s_before = get_runtime_state()
    assert s_before["has_runtime_override"] is True
    reset_info = reset_runtime_params()
    assert reset_info["reset"] is True
    s_after = get_runtime_state()
    assert s_after["has_runtime_override"] is False
    assert s_after["intensity_to_pips"] == INTENSITY_TO_PIPS  # revient aux constantes
    assert s_after["recroisement_bonus_pips"] == RECROISEMENT_BONUS_PIPS


def test_get_runtime_state_json_serializable(_phase28b_reset_runtime):
    """get_runtime_state est R9 — JSON sérialisable sans erreur."""
    apply_calibrated_params({
        "intensity_to_pips": {"FAIBLE": 1.0, "MOYEN": 2.0, "FORT": 3.0, "EXTREME": 4.0},
        "recroisement_bonus_pips": 1.5,
        "rejet_penalty_pips": -1.0,
    })
    state = get_runtime_state()
    s = json.dumps(state)  # doit passer sans TypeError
    assert "intensity_to_pips" in s
    assert "has_runtime_override" in s
    parsed = json.loads(s)
    assert parsed["has_runtime_override"] is True
    assert parsed["n_applies_total"] >= 1


def test_apply_calibrated_params_propagates_to_pnl_computation(_phase28b_reset_runtime):
    """compute_force_native_pnl change effectivement quand params overridés (vraie observabilité)."""
    feat_obj = NativeForceFeatures(
        timestamp="2026-08-05T00:00:00+00:00",
        bar_time=1,
        force_base=50.0,
        force_quote=10.0,
        force_delta=40.0,
        force_base_rank=10,
        force_quote_rank=80,
        compression_extension_etat="COMPRESSION",
        compression_extension_intensite="FORT",
        croisement_detecte=1,
        croisement_direction="HAUSSIERE",
        recroisement_detecte=1,
        rejet_repulsion_detecte=1,
        rejet_intensite=0.5,
    )
    pnl_default = compute_force_native_pnl([feat_obj])
    # Override : FORT passe 5.0 → 10.0 (x2)
    apply_calibrated_params({
        "intensity_to_pips": {"FAIBLE": 1.5, "MOYEN": 3.0, "FORT": 10.0, "EXTREME": 16.0},
        "recroisement_bonus_pips": 4.0,
        "rejet_penalty_pips": -2.0,
    })
    pnl_x2 = compute_force_native_pnl([feat_obj])
    # pnl doit augmenter (intensité x2, recroisement 2.0→4.0)
    assert pnl_x2 > pnl_default, f"override should increase pnl: default={pnl_default}, x2={pnl_x2}"


# ─────────────────────────────────────────────────────────────────────
# Z1 — compute_force_native (API SGL, R2 additif ZCode 10/08)
# ─────────────────────────────────────────────────────────────────────

def test_compute_force_native_returns_devise_forces():
    """Retourne le dict {DEVISE: force} de la dernière barre."""
    from core.v10.v10_force_native import compute_force_native
    bars = [
        {"force_usd": 40.0, "force_gbp": 55.0, "force_eur": 50.0, "force_jpy": 45.0,
         "force_cad": 48.0, "force_chf": 35.0, "force_aud": 52.0, "force_nzd": 30.0},
        {"force_usd": 45.0, "force_gbp": 60.0, "force_eur": 55.0, "force_jpy": 40.0,
         "force_cad": 48.0, "force_chf": 35.0, "force_aud": 50.0, "force_nzd": 30.0},
    ]
    r = compute_force_native(pair="GBPUSD", timeframe="M30", bars=bars)
    assert r is not None
    assert r["GBP"] == 60.0   # dernière barre
    assert r["USD"] == 45.0
    assert len(r) == 8          # 8 devises


def test_compute_force_native_fail_open():
    """R6 : bars vide/None → None (jamais de mock silencieux)."""
    from core.v10.v10_force_native import compute_force_native
    assert compute_force_native(pair="EURUSD", bars=[]) is None
    assert compute_force_native(pair="EURUSD", bars=None) is None
    assert compute_force_native(pair="EURUSD", bars=["not-a-dict"]) is None


def test_compute_force_native_default_50_when_missing():
    """Colonne force_<devise> absente → 50.0 (R6 fail-open)."""
    from core.v10.v10_force_native import compute_force_native
    r = compute_force_native(pair="EURUSD", bars=[{"force_eur": 70.0}])
    assert r["EUR"] == 70.0
    assert r["USD"] == 50.0  # absent → défaut
