"""test_v9_dynamic_tp_sl.py — Tests pour core/v9/v9_dynamic_tp_sl.py (Fix C).

Vérifie :
T1. Kill switch (V9_DYNAMIC_TP_SL_ENABLED) — défaut OFF (R28 motion CEO)
T2. compute_dynamic_tp_sl() retourne DynamicTpSl même si OFF (fallback R30)
T3. Bornes R30 respectées (TP/SL ∈ [5, 20])
T4. Source "vol_atr" prioritaire si vol_atr_pips fourni
T5. Source "magnitude_history" si P50 > 0 (sans vol_atr)
T6. Source "default_fallback" si P50=0 et vol_atr=None
T7. Ratio RR ≥ RR_TARGET (0.7) par défaut
T8. R6 : DB absente → fallback DEFAULT_TP/SL
T9. R6 : DB corrompue → fallback
T10. Pip multiplier JPY vs non-JPY
T11. Cache magnitude (deuxième appel = cache hit)
T12. get_stats() diagnostic
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from core.v9.v9_dynamic_tp_sl import (
    DEFAULT_SL,
    DEFAULT_TP,
    DYNAMIC_TP_SL_ENABLED_ENV,
    DynamicTpSl,
    SL_MAX,
    SL_MIN,
    TP_MAX,
    TP_MIN,
    _MAGNITUDE_CACHE,
    _compute_magnitude_history,
    compute_dynamic_tp_sl,
    dynamic_tp_sl_enabled,
    get_stats,
)


@pytest.fixture
def tmp_db_with_ohlc(tmp_path: Path) -> Path:
    """DB v9_forces-like avec OHLC pour calculer magnitudes."""
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript("""
            CREATE TABLE forces_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bar_close_time INTEGER, symbol TEXT, timeframe TEXT,
                high REAL, low REAL, open REAL, close REAL
            );
        """)
        # 100 candles GBPUSD M15 : range entre 5 et 15 pips
        import random
        random.seed(42)
        for i in range(100):
            base = 1.3000
            high = base + random.uniform(0.0005, 0.0015)  # 5-15 pips
            low = base - random.uniform(0.0005, 0.0010)
            conn.execute(
                "INSERT INTO forces_snapshots(bar_close_time, symbol, timeframe, high, low, open, close) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (i * 900, "GBPUSD", "M15", high, low, base, base),
            )
        # 100 candles USDJPY M15 : range entre 0.5 et 2.5 (yen)
        for i in range(100):
            base = 150.00
            high = base + random.uniform(0.05, 0.25)
            low = base - random.uniform(0.05, 0.20)
            conn.execute(
                "INSERT INTO forces_snapshots(bar_close_time, symbol, timeframe, high, low, open, close) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (i * 900, "USDJPY", "M15", high, low, base, base),
            )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch: pytest.MonkeyPatch):
    if DYNAMIC_TP_SL_ENABLED_ENV in os.environ:
        monkeypatch.delenv(DYNAMIC_TP_SL_ENABLED_ENV)
    _MAGNITUDE_CACHE.clear()
    yield


# ============================================================== T1 kill switch

def test_kill_switch_default_off():
    """R28 : V9_DYNAMIC_TP_SL_ENABLED défaut OFF."""
    assert DYNAMIC_TP_SL_ENABLED_ENV not in os.environ
    assert dynamic_tp_sl_enabled() is False


def test_kill_switch_when_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    assert dynamic_tp_sl_enabled() is True


def test_kill_switch_other_values(monkeypatch: pytest.MonkeyPatch):
    for val in ("0", "false", ""):
        monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, val)
        assert dynamic_tp_sl_enabled() is False


# ============================================================== T2 fallback si OFF

def test_compute_returns_fallback_when_disabled(tmp_db_with_ohlc: Path):
    """OFF → fallback hardcoded (R6)."""
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=tmp_db_with_ohlc)
    assert result.source == "disabled_kill_switch"
    assert result.tp == DEFAULT_TP
    assert result.sl == DEFAULT_SL


# ============================================================== T3 bornes R30

def test_compute_respects_tp_sl_bornes(monkeypatch: pytest.MonkeyPatch,
                                          tmp_db_with_ohlc: Path):
    """TP/SL dans [TP_MIN, TP_MAX] = [5, 20]."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    for symbol in ["GBPUSD", "USDJPY"]:
        result = compute_dynamic_tp_sl(symbol, "M15", db_path=tmp_db_with_ohlc)
        assert TP_MIN <= result.tp <= TP_MAX, f"{symbol}: TP {result.tp} hors bornes"
        assert SL_MIN <= result.sl <= SL_MAX, f"{symbol}: SL {result.sl} hors bornes"


# ============================================================== T4 source vol_atr

def test_compute_with_vol_atr_uses_vol_atr_source(
    monkeypatch: pytest.MonkeyPatch, tmp_db_with_ohlc: Path
):
    """Si vol_atr fourni → source='vol_atr'."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl(
        "GBPUSD", "M15", vol_atr_pips=8.0, db_path=tmp_db_with_ohlc
    )
    assert result.source == "vol_atr"
    assert result.vol_atr_used == 8.0
    # TP = max(8 * 1.5, 7.3 * 1.2) = max(12.0, 8.76) = 12.0
    # SL = 12 / 0.7 = 17.14
    assert result.tp >= 10
    assert result.sl >= 10


# ============================================================== T5 source magnitude_history

def test_compute_uses_magnitude_history(monkeypatch: pytest.MonkeyPatch,
                                          tmp_db_with_ohlc: Path):
    """Si P50 > 0 et pas de vol_atr → magnitude_history."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=tmp_db_with_ohlc)
    assert result.source == "magnitude_history"
    assert result.p50_used > 0
    assert result.p75_used > 0
    assert result.tp >= TP_MIN
    assert result.sl >= SL_MIN


# ============================================================== T6 default_fallback

def test_compute_default_fallback_no_data(monkeypatch: pytest.MonkeyPatch,
                                            tmp_path: Path):
    """Si DB vide + pas de vol_atr → default_fallback."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    db = tmp_path / "empty.db"
    # Crée une DB vide (sans table forces_snapshots)
    sqlite3.connect(str(db)).close()
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=db)
    assert result.source == "default_fallback"
    assert result.tp == DEFAULT_TP
    assert result.sl == DEFAULT_SL


# ============================================================== T7 RR ratio

def test_compute_rr_ratio_at_least_target(monkeypatch: pytest.MonkeyPatch,
                                            tmp_db_with_ohlc: Path):
    """Ratio SL/TP ≥ 0.7 par défaut (RR_TARGET)."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=tmp_db_with_ohlc)
    assert result.rr_ratio >= 0.7, f"RR={result.rr_ratio} < 0.7"


# ============================================================== T8-T9 R6 DB errors

def test_compute_db_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """DB absente → fallback (R6)."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=tmp_path / "no.db")
    assert result.source == "default_fallback"
    assert result.tp == DEFAULT_TP


def test_compute_db_corrupt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """DB corrompue → fallback (R6)."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    db = tmp_path / "corrupt.db"
    db.write_text("not sqlite")
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=db)
    assert result.source == "default_fallback"


# ============================================================== T10 JPY vs non-JPY

def test_jpy_pair_uses_100_pip_multiplier(
    monkeypatch: pytest.MonkeyPatch, tmp_db_with_ohlc: Path
):
    """USDJPY : 1 pip = 0.01 → multiplier 100."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl("USDJPY", "M15", db_path=tmp_db_with_ohlc)
    # P50 USDJPY avec ranges 0.05-0.25 yen = 5-25 pips
    assert result.p50_used > 5
    assert result.p50_used < 30
    assert result.source == "magnitude_history"


def test_non_jpy_pair_uses_10000_pip_multiplier(
    monkeypatch: pytest.MonkeyPatch, tmp_db_with_ohlc: Path
):
    """GBPUSD : 1 pip = 0.0001 → multiplier 10000."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=tmp_db_with_ohlc)
    # P50 GBPUSD avec ranges 5-15 pips
    assert result.p50_used > 4
    assert result.p50_used < 20


# ============================================================== T11 cache

def test_cache_hit_on_second_call(monkeypatch: pytest.MonkeyPatch,
                                    tmp_db_with_ohlc: Path):
    """Deuxième appel = cache (même P50 même si DB modifiée)."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    _MAGNITUDE_CACHE.clear()
    # Premier appel : DB query
    p50_a, p75_a = _compute_magnitude_history(tmp_db_with_ohlc, "GBPUSD", "M15")
    # Cache doit contenir la clé
    assert len(_MAGNITUDE_CACHE) == 1, f"Cache devrait avoir 1 clé, a {len(_MAGNITUDE_CACHE)}"
    # Modifier la DB (le 2e appel ne doit pas voir la modif)
    conn = sqlite3.connect(str(tmp_db_with_ohlc))
    try:
        conn.execute("DELETE FROM forces_snapshots WHERE symbol = 'GBPUSD'")
        conn.commit()
    finally:
        conn.close()
    # Deuxième appel : cache hit → même P50
    p50_b, p75_b = _compute_magnitude_history(tmp_db_with_ohlc, "GBPUSD", "M15")
    assert p50_a == p50_b, f"Cache hit: P50 doit être identique {p50_a} == {p50_b}"
    assert p75_a == p75_b


def test_cache_clear_resets(monkeypatch: pytest.MonkeyPatch,
                              tmp_db_with_ohlc: Path):
    """Cache clear → refetch."""
    _MAGNITUDE_CACHE.clear()
    p50_a, _ = _compute_magnitude_history(tmp_db_with_ohlc, "GBPUSD", "M15")
    _MAGNITUDE_CACHE.clear()
    # Recharger après delete
    conn = sqlite3.connect(str(tmp_db_with_ohlc))
    try:
        conn.execute("DELETE FROM forces_snapshots WHERE symbol = 'GBPUSD'")
        conn.commit()
    finally:
        conn.close()
    p50_b, _ = _compute_magnitude_history(tmp_db_with_ohlc, "GBPUSD", "M15")
    assert p50_b == 0.0  # DB vide


# ============================================================== T12 get_stats

def test_get_stats_returns_dict(tmp_db_with_ohlc: Path):
    stats = get_stats(db_path=tmp_db_with_ohlc)
    assert isinstance(stats, dict)
    assert "enabled" in stats
    assert "GBPUSD_p50" in stats
    assert "GBPUSD_p75" in stats
    assert stats["GBPUSD_p50"] > 0


def test_get_stats_db_missing(tmp_path: Path):
    stats = get_stats(db_path=tmp_path / "no.db")
    assert "db_status" in stats


# ============================================================== T13 DynamicTpSl dataclass

def test_dynamic_tp_sl_to_dict(monkeypatch: pytest.MonkeyPatch,
                                 tmp_db_with_ohlc: Path):
    """DynamicTpSl.to_dict contient tous les champs."""
    monkeypatch.setenv(DYNAMIC_TP_SL_ENABLED_ENV, "1")
    result = compute_dynamic_tp_sl("GBPUSD", "M15", db_path=tmp_db_with_ohlc)
    d = result.to_dict()
    assert "tp" in d
    assert "sl" in d
    assert "p50_used" in d
    assert "p75_used" in d
    assert "rr_ratio" in d
    assert "source" in d
    assert "rationale" in d
