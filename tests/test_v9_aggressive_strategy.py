"""Tests Chantier 1 — v9_aggressive_strategy (TP/SL dynamique + garde-fou short).

Couche backtest lecture-seule (motion CEO 2026-07-18). Vérifie : bornes dures,
fallback conservateur (R6), garde-fou short régime-dépendant, reconstruction
OHLC de la magnitude réelle (MFE/MAE).
"""
from __future__ import annotations

import sqlite3

import pytest

from core.v9 import v9_aggressive_strategy as ags


# ------------------------------------------------------------------ utilitaires

def test_bucket_vol_atr_low():
    assert ags._bucket_vol_atr(1.0) == "LOW"
    assert ags._bucket_vol_atr(2.0) == "LOW"


def test_bucket_vol_atr_medium():
    assert ags._bucket_vol_atr(2.1) == "MEDIUM"
    assert ags._bucket_vol_atr(6.0) == "MEDIUM"


def test_bucket_vol_atr_high():
    assert ags._bucket_vol_atr(6.1) == "HIGH"
    assert ags._bucket_vol_atr(50.0) == "HIGH"


def test_bucket_vol_atr_unknown():
    assert ags._bucket_vol_atr(None) == "UNKNOWN"
    assert ags._bucket_vol_atr(-1.0) == "UNKNOWN"
    assert ags._bucket_vol_atr("bad") == "UNKNOWN"


def test_pip_size_jpy():
    assert ags._pip_size("USDJPY") == 0.01
    assert ags._pip_size("GBPJPY") == 0.01


def test_pip_size_non_jpy():
    assert ags._pip_size("GBPUSD") == 0.0001
    assert ags._pip_size("EURUSD") == 0.0001


def test_pip_size_empty():
    assert ags._pip_size("") == 0.0001


def test_magnitude_cell_key():
    assert ags.magnitude_cell_key("GBPUSD", "M15", 1.0) == "GBPUSD|M15|LOW"
    assert ags.magnitude_cell_key("GBPUSD", "M15", None) == "GBPUSD|M15|UNKNOWN"


def test_clamp():
    assert ags._clamp(5, 0, 10) == 5
    assert ags._clamp(-1, 0, 10) == 0
    assert ags._clamp(11, 0, 10) == 10


def test_percentile_empty():
    assert ags._percentile([], 0.5) == 0.0


def test_percentile_single():
    assert ags._percentile([7.0], 0.9) == 7.0


def test_percentile_median():
    assert ags._percentile([1.0, 2.0, 3.0], 0.5) == 2.0


def test_percentile_interpolation():
    # P75 de [0,10] = 7.5 (interpolation linéaire).
    assert ags._percentile([0.0, 10.0], 0.75) == 7.5


# ------------------------------------------------------------------ compute_dynamic_tp_sl

def test_tp_sl_within_bounds_no_stats():
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", None)
    assert ags.AGGR_TP_MIN <= tp <= ags.AGGR_TP_MAX
    assert ags.AGGR_SL_MIN <= sl <= ags.AGGR_SL_MAX
    assert n == 0


def test_tp_sl_floor_when_no_info():
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", None)
    assert tp == ags.AGGR_TP_MIN
    assert src == "floor_min"


def test_tp_scales_with_vol_atr():
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", 15.0)
    # k_vol · 15 = 22.5 > floor.
    assert tp == pytest.approx(22.5, abs=0.01)
    assert src == "vol_atr"


def test_tp_capped_at_max():
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", 100.0)
    assert tp == ags.AGGR_TP_MAX


def test_tp_uses_cell_percentile():
    stats = {"GBPUSD|M15|MEDIUM": {"p50": 12, "p75": 20, "p90": 25, "p95": 28, "n": 100}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", 4.0, stats)
    assert tp == pytest.approx(20.0, abs=0.01)
    assert src == "cell_p75"
    assert n == 100


def test_cell_ignored_when_n_below_min():
    stats = {"GBPUSD|M15|MEDIUM": {"p75": 25, "n": 5}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", 4.0, stats)
    # n < MIN_N_MAGNITUDE → cellule ignorée, retombe sur vol_atr (1.5·4=6 → floor 10).
    assert src != "cell_p75"


def test_sl_ratio_of_tp():
    # phase developpement → facteur 0.8 ; tp=20 → sl=0.8·20·0.8=12.8.
    stats = {"GBPUSD|M15|MEDIUM": {"p75": 20, "n": 100}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "developpement", 4.0, stats)
    assert sl == pytest.approx(12.8, abs=0.01)


def test_sl_phase_climax_wider_than_trend():
    stats = {"GBPUSD|M15|MEDIUM": {"p75": 25, "n": 100}}
    _, sl_climax, _, _ = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "culmination", 4.0, stats)
    _, sl_trend, _, _ = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", 4.0, stats)
    assert sl_climax >= sl_trend


def test_sl_never_below_min():
    stats = {"GBPUSD|M15|LOW": {"p75": 10, "n": 100}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", 1.0, stats)
    assert sl >= ags.AGGR_SL_MIN


def test_sl_never_above_max():
    stats = {"GBPUSD|M15|HIGH": {"p75": 30, "n": 100}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "culmination", 20.0, stats)
    assert sl <= ags.AGGR_SL_MAX


def test_unknown_phase_uses_default_factor():
    stats = {"GBPUSD|M15|MEDIUM": {"p75": 20, "n": 100}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "??", 4.0, stats)
    assert ags.AGGR_SL_MIN <= sl <= ags.AGGR_SL_MAX


def test_compute_tp_sl_bad_vol_type_fallback():
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "initiation", "oops")  # type: ignore[arg-type]
    assert tp == ags.AGGR_TP_MIN


def test_rr_ratio_at_least_1_typical():
    # Avec ratio SL/TP=0.8 et facteur phase ≤1, RR = tp/sl ≥ 1.
    stats = {"GBPUSD|M15|MEDIUM": {"p75": 20, "n": 100}}
    tp, sl, src, n = ags.compute_dynamic_tp_sl("GBPUSD", "M15", "NEUTRE", "developpement", 4.0, stats)
    assert tp / sl >= 1.0


# ------------------------------------------------------------------ short gate

def test_short_gated_neutre():
    assert ags.is_short_gated("baissiere", "NEUTRE") is True


def test_short_allowed_cassure():
    assert ags.is_short_gated("baissiere", "CASSURE") is False


def test_short_allowed_extension():
    assert ags.is_short_gated("baissiere", "EXTENSION") is False


def test_long_never_gated():
    assert ags.is_short_gated("haussiere", "NEUTRE") is False
    assert ags.is_short_gated("haussiere", "CASSURE") is False


def test_short_synonyms_gated():
    assert ags.is_short_gated("sell", "NEUTRE") is True
    assert ags.is_short_gated("short", "PALIER") is True


# ------------------------------------------------------------------ evaluate_aggressive

def test_evaluate_returns_dataclass():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert isinstance(d, ags.AggressiveDecision)


def test_evaluate_edge_positive_when_p_high():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.9,
    )
    assert d.edge > 0


def test_evaluate_edge_negative_when_p_low():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.1,
    )
    assert d.edge < 0


def test_evaluate_edge_formula():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=None, p_win=0.7,
    )
    expected = 0.7 * d.tp - 0.3 * d.sl
    assert d.edge == pytest.approx(round(expected, 3), abs=0.01)


def test_evaluate_rr_ratio():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="developpement",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert d.rr_ratio == pytest.approx(round(d.tp / d.sl, 3), abs=0.001)


def test_evaluate_short_gated_flag():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="baissiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert d.short_gated is True
    assert "short_gated" in d.rationale


def test_evaluate_short_not_gated_in_cassure():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="CASSURE", phase="initiation",
        direction="baissiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert d.short_gated is False


def test_evaluate_clamps_p_win():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=1.5,
    )
    assert d.p_win <= 1.0


def test_evaluate_bad_p_win_defaults_half():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win="bad",  # type: ignore[arg-type]
    )
    assert d.p_win == pytest.approx(0.5, abs=0.01)


def test_evaluate_invalid_regime_normalized():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="ZZZ", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert d.regime == "NEUTRE"


def test_evaluate_invalid_phase_normalized():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="zzz",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert d.phase == "initiation"


def test_evaluate_to_dict_roundtrip():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.8,
    )
    dd = d.to_dict()
    assert dd["symbol"] == "GBPUSD"
    assert dd["tp"] == d.tp
    assert set(["tp", "sl", "edge", "short_gated", "rr_ratio"]).issubset(dd.keys())


def test_evaluate_vol_atr_bucket_recorded():
    d = ags.evaluate_aggressive(
        symbol="GBPUSD", timeframe="M15", regime="NEUTRE", phase="initiation",
        direction="haussiere", vol_atr_pips=4.0, p_win=0.8,
    )
    assert d.vol_atr_bucket == "MEDIUM"


# ------------------------------------------------------------------ ATR & excursion

def test_compute_atr_pips_empty():
    assert ags.compute_atr_pips([], 0.0001) is None


def test_compute_atr_pips_basic():
    bars = [{"high": 1.1010, "low": 1.1000}, {"high": 1.1020, "low": 1.1005}]
    atr = ags.compute_atr_pips(bars, 0.0001)
    # ranges = 10 pips, 15 pips → moyenne 12.5.
    assert atr == pytest.approx(12.5, abs=0.1)


def test_compute_atr_pips_ignores_bad_bars():
    bars = [{"high": 1.1010, "low": 1.1000}, {"high": None, "low": 1.1005}]
    atr = ags.compute_atr_pips(bars, 0.0001)
    assert atr == pytest.approx(10.0, abs=0.1)


def test_forward_excursion_long():
    forward = [{"high": 1.1030, "low": 1.0995}, {"high": 1.1050, "low": 1.1010}]
    mfe, mae = ags._forward_excursion(1.1000, "haussiere", forward, 0.0001)
    assert mfe == pytest.approx(50.0, abs=0.1)   # 1.1050 - 1.1000
    assert mae == pytest.approx(5.0, abs=0.1)    # 1.1000 - 1.0995


def test_forward_excursion_short():
    forward = [{"high": 1.1010, "low": 1.0960}]
    mfe, mae = ags._forward_excursion(1.1000, "baissiere", forward, 0.0001)
    assert mfe == pytest.approx(40.0, abs=0.1)   # 1.1000 - 1.0960
    assert mae == pytest.approx(10.0, abs=0.1)   # 1.1010 - 1.1000


def test_forward_excursion_non_negative():
    forward = [{"high": 1.0990, "low": 1.0980}]  # prix baisse pour un long
    mfe, mae = ags._forward_excursion(1.1000, "haussiere", forward, 0.0001)
    assert mfe >= 0.0 and mae >= 0.0


# ------------------------------------------------------------------ reconstruction OHLC (sqlite in-memory)

def _build_mini_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE forces_snapshots(
            snapshot_id TEXT, symbol TEXT, timeframe TEXT, bar_time INTEGER,
            open REAL, high REAL, low REAL, close REAL, is_closed_bar INTEGER
        );
        CREATE TABLE decisions(
            snapshot_id TEXT, symbol TEXT, timeframe TEXT, direction TEXT,
            is_win INTEGER
        );
        """
    )
    # 6 barres M15 GBPUSD montantes.
    base = 1_700_000_000
    closes = [1.3000, 1.3010, 1.3025, 1.3040, 1.3060, 1.3085]
    for i, cl in enumerate(closes):
        bt = base + i * 900
        con.execute(
            "INSERT INTO forces_snapshots VALUES(?,?,?,?,?,?,?,?,1)",
            (f"s{i}", "GBPUSD", "M15", bt, cl - 0.0005, cl + 0.0008, cl - 0.0006, cl),
        )
    # décision d'entrée à la barre 0 (haussière, résolue).
    con.execute("INSERT INTO decisions VALUES('s0','GBPUSD','M15','haussiere',1)")
    con.commit()
    con.close()


def test_reconstruct_returns_dict(tmp_path):
    db = tmp_path / "mini.db"
    _build_mini_db(str(db))
    stats = ags.reconstruct_magnitude_stats(str(db), horizon_bars=5)
    assert isinstance(stats, dict)
    assert len(stats) >= 1


def test_reconstruct_magnitude_uncapped(tmp_path):
    # Le mouvement forward monte de ~85 pips → MFE bien au-dessus du cap 9.5.
    db = tmp_path / "mini.db"
    _build_mini_db(str(db))
    stats = ags.reconstruct_magnitude_stats(str(db), horizon_bars=5)
    cell = next(iter(stats.values()))
    assert cell["p50"] > 9.5   # dépasse le cap resolution_pips


def test_reconstruct_missing_db_returns_empty():
    assert ags.reconstruct_magnitude_stats("/nonexistent/path/xyz.db") == {}


def test_reconstruct_cell_has_percentile_keys(tmp_path):
    db = tmp_path / "mini.db"
    _build_mini_db(str(db))
    stats = ags.reconstruct_magnitude_stats(str(db), horizon_bars=5)
    cell = next(iter(stats.values()))
    for k in ("n", "p50", "p75", "p90", "p95", "mae_p75", "mae_p90"):
        assert k in cell


def test_magnitude_cell_summary_shapes():
    c = ags.MagnitudeCell(mfe_pips=[5.0, 10.0, 15.0, 20.0], mae_pips=[1.0, 2.0, 3.0, 4.0])
    s = c.summary()
    assert s["n"] == 4.0
    assert s["p50"] == pytest.approx(12.5, abs=0.1)
    assert s["p95"] >= s["p50"]


def test_version_constant():
    assert ags.AGGRESSIVE_STRATEGY_VERSION == "1.0"
