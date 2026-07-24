"""test_v9_cycle_memory.py — Tests pour core/v9/v9_cycle_memory.py (Système Prédictif R33).

Vérifie :
1. Kill switch (V9_CYCLE_MEMORY_ENABLED) — défaut OFF
2. Schema init_db idempotent
3. Bucketisation vol_atr_pips (LOW/MEDIUM/HIGH/UNKNOWN)
4. recall() retourne None pour contexte inconnu
5. recall() retourne None si n_observations < MIN_N_OBSERVATIONS
6. update() incrémente correctement
7. recall() après update retourne les bonnes stats
8. Confidence calculation
9. get_transition() distribution correcte
10. update_transition() incrémente
11. purge_stale() supprime les patterns > TTL
12. recompute_percentiles() aligne p50/p95
13. R6 défensif : erreurs DB ne crashent pas
14. CyclePattern.is_actionable() cohérent
15. get_stats() diagnostic
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

from core.v9.v9_cycle_memory import (
    CYCLE_MEMORY_ENABLED_ENV,
    CyclePattern,
    DEFAULT_DB_PATH,
    MIN_N_OBSERVATIONS,
    TTL_DAYS,
    VOL_ATR_LOW_MAX,
    VOL_ATR_MEDIUM_MAX,
    TransitionPattern,
    cycle_memory_enabled,
    get_stats,
    get_transition,
    init_db,
    purge_stale,
    recall,
    recompute_percentiles,
    update,
    update_transition,
)
from core.v9.v9_cycle_memory import _bucket_vol_atr, _compute_confidence, _percentile


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """DB cycle memory jetable pour les tests."""
    db = tmp_path / "test_cycle_memory.db"
    init_db(db)
    return db


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch: pytest.MonkeyPatch):
    """Isole les tests des variables d'environnement."""
    if CYCLE_MEMORY_ENABLED_ENV in os.environ:
        monkeypatch.delenv(CYCLE_MEMORY_ENABLED_ENV)
    yield


# --------------------------------------------------------------- T1 kill switch

def test_cycle_memory_enabled_default_off():
    """Kill switch V9_CYCLE_MEMORY_ENABLED default OFF (SHADOW).
    
    Note: Currently enabled via config/v9_kill_switches.env (CEO motion 2026-07-21).
    This test verifies the default behavior when neither env var nor file sets it.
    """
    # Test the default by directly calling the underlying logic with no config
    from core.v9.kill_switches import is_enabled
    # Mock the file read to return empty dict
    import core.v9.kill_switches as ks
    original_load = ks._load
    ks._load = lambda: {}
    try:
        assert is_enabled("V9_CYCLE_MEMORY_ENABLED") is False
    finally:
        ks._load = original_load


def test_cycle_memory_enabled_when_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(CYCLE_MEMORY_ENABLED_ENV, "1")
    assert cycle_memory_enabled() is True


def test_cycle_memory_enabled_other_values(monkeypatch: pytest.MonkeyPatch):
    """Toute valeur ≠ '1' est traitée comme OFF (R6 défensif)."""
    for val in ("0", "false", "no", "", "TRUE", "yes"):
        monkeypatch.setenv(CYCLE_MEMORY_ENABLED_ENV, val)
        if val == "TRUE":
            # 'TRUE' != '1' exact : on reste strict
            assert cycle_memory_enabled() is False
        else:
            assert cycle_memory_enabled() is False


# --------------------------------------------------------------- T2 schema

def test_init_db_creates_schema(tmp_db: Path):
    """init_db crée les 3 tables et le meta."""
    conn = sqlite3.connect(str(tmp_db))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "cycle_patterns" in tables
        assert "phase_transitions" in tables
        assert "cycle_memory_meta" in tables
        meta = dict(conn.execute(
            "SELECT key, value FROM cycle_memory_meta"
        ).fetchall())
        assert meta.get("schema_version") == "1"
        assert "last_init_ts" in meta
    finally:
        conn.close()


def test_init_db_idempotent(tmp_db: Path):
    """init_db peut être appelé 2x sans erreur."""
    init_db(tmp_db)
    init_db(tmp_db)  # ne doit pas crash
    # Vérifie que la table est toujours cohérente
    conn = sqlite3.connect(str(tmp_db))
    try:
        n = conn.execute("SELECT COUNT(*) FROM cycle_patterns").fetchone()[0]
        assert n == 0
    finally:
        conn.close()


# --------------------------------------------------------------- T3 bucketisation

def test_bucket_vol_atr_low():
    assert _bucket_vol_atr(0.5) == "LOW"
    assert _bucket_vol_atr(1.0) == "LOW"
    assert _bucket_vol_atr(2.0) == "LOW"  # borne inclusive


def test_bucket_vol_atr_medium():
    assert _bucket_vol_atr(2.1) == "MEDIUM"
    assert _bucket_vol_atr(4.0) == "MEDIUM"
    assert _bucket_vol_atr(6.0) == "MEDIUM"  # borne inclusive


def test_bucket_vol_atr_high():
    assert _bucket_vol_atr(6.1) == "HIGH"
    assert _bucket_vol_atr(20.0) == "HIGH"


def test_bucket_vol_atr_unknown():
    assert _bucket_vol_atr(None) == "UNKNOWN"
    assert _bucket_vol_atr(-1.0) == "UNKNOWN"


def test_bucket_vol_atr_invalid_types():
    """R6 défensif : types invalides → UNKNOWN, pas d'exception."""
    assert _bucket_vol_atr("abc") == "UNKNOWN"
    assert _bucket_vol_atr([1, 2]) == "UNKNOWN"


# --------------------------------------------------------------- T4 recall None

def test_recall_unknown_context_returns_none(tmp_db: Path):
    """Pas de pattern pour un quintuplet jamais observé."""
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is None


def test_recall_db_inexistant_returns_none(tmp_path: Path):
    """R6 : DB absente ne crash pas, retourne None."""
    db = tmp_path / "no_such.db"
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=db)
    assert result is None


# --------------------------------------------------------------- T5 recall < MIN_N

def test_recall_below_min_n_returns_none(tmp_db: Path):
    """n_observations < MIN_N_OBSERVATIONS → recall retourne None."""
    # 4 updates < MIN_N (5)
    for i in range(MIN_N_OBSERVATIONS - 1):
        update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
               is_win=True, db_path=tmp_db)
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is None  # filtré par is_actionable()


# --------------------------------------------------------------- T6 update incrémental

def test_update_increments(tmp_db: Path):
    """update() incrémente n_observations correctement."""
    for _ in range(3):
        ok = update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
                    is_win=True, db_path=tmp_db)
        assert ok is True
    conn = sqlite3.connect(str(tmp_db))
    try:
        row = conn.execute(
            "SELECT n_observations, n_wins, n_resolved FROM cycle_patterns "
            "WHERE symbol='GBPUSD'"
        ).fetchone()
        assert row == (3, 3, 3)
    finally:
        conn.close()


def test_update_mixed_wins_losses(tmp_db: Path):
    """n_wins comptabilise seulement les is_win=True."""
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=False, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=None, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True, db_path=tmp_db)
    conn = sqlite3.connect(str(tmp_db))
    try:
        row = conn.execute(
            "SELECT n_observations, n_wins, n_resolved, n_pending FROM cycle_patterns"
        ).fetchone()
        assert row == (4, 2, 3, 1)
    finally:
        conn.close()


def test_update_with_duration(tmp_db: Path):
    """duration_bars alimente sum_duration et max_duration."""
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=10.0, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=25.0, db_path=tmp_db)
    conn = sqlite3.connect(str(tmp_db))
    try:
        row = conn.execute(
            "SELECT sum_duration, max_duration FROM cycle_patterns"
        ).fetchone()
        sum_d, max_d = row
        assert sum_d == 35.0
        assert max_d == 25.0
    finally:
        conn.close()


def test_update_invalid_phase_returns_false(tmp_db: Path):
    """Phase hors vocabulaire → pas d'insertion (R6)."""
    ok = update("GBPUSD", "M15", "NEUTRE", "INVALID_PHASE", 3.5,
                is_win=True, db_path=tmp_db)
    assert ok is False


def test_update_invalid_regime_returns_false(tmp_db: Path):
    ok = update("GBPUSD", "M15", "INVALID_REGIME", "culmination", 3.5,
                is_win=True, db_path=tmp_db)
    assert ok is False


# --------------------------------------------------------------- T7 recall après update

def test_recall_returns_correct_stats(tmp_db: Path):
    """Après MIN_N updates, recall retourne les bonnes stats."""
    # 6 wins sur 7 observations
    for i in range(7):
        update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
               is_win=(i < 6), db_path=tmp_db)
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is not None
    assert result.symbol == "GBPUSD"
    assert result.timeframe == "M15"
    assert result.regime_type == "NEUTRE"
    assert result.phase == "culmination"
    assert result.vol_atr_bucket == "MEDIUM"
    assert result.n_observations == 7
    assert result.n_wins == 6
    assert result.n_resolved == 7
    assert result.win_rate == pytest.approx(6 / 7, abs=0.01)
    assert result.is_actionable() is True


def test_recall_different_buckets_isolated(tmp_db: Path):
    """LOW et MEDIUM sont des patterns séparés."""
    for _ in range(6):
        update("GBPUSD", "M15", "NEUTRE", "culmination", 1.0,
               is_win=True, db_path=tmp_db)
        update("GBPUSD", "M15", "NEUTRE", "culmination", 4.0,
               is_win=False, db_path=tmp_db)
    low_p = recall("GBPUSD", "M15", "NEUTRE", "culmination", 1.0, db_path=tmp_db)
    med_p = recall("GBPUSD", "M15", "NEUTRE", "culmination", 4.0, db_path=tmp_db)
    assert low_p is not None and med_p is not None
    assert low_p.vol_atr_bucket == "LOW"
    assert med_p.vol_atr_bucket == "MEDIUM"
    assert low_p.win_rate == 1.0
    assert med_p.win_rate == 0.0


# --------------------------------------------------------------- T8 confidence

def test_compute_confidence_zero_obs():
    assert _compute_confidence(0, 0, 0.0) == 0.0


def test_compute_confidence_full():
    """30 obs, 100% résolu, 0 jour → confidence = 1.0."""
    conf = _compute_confidence(30, 30, 0.0)
    assert conf == pytest.approx(1.0, abs=0.01)


def test_compute_confidence_decay_with_age():
    """Confidence décroît avec l'âge."""
    young = _compute_confidence(30, 30, 0.0)
    old = _compute_confidence(30, 30, TTL_DAYS * 86400.0)  # TTL atteint
    assert young > old


def test_compute_confidence_volume_dominant():
    """Volume d'observations a 50% de poids."""
    high_vol = _compute_confidence(60, 30, 0.0)
    low_vol = _compute_confidence(15, 8, 0.0)
    assert high_vol > low_vol


# --------------------------------------------------------------- T9 transitions

def test_update_transition_increments(tmp_db: Path):
    ok = update_transition("culmination", "initiation", "GBPUSD", "M15",
                           "NEUTRE", db_path=tmp_db)
    assert ok is True
    conn = sqlite3.connect(str(tmp_db))
    try:
        n = conn.execute(
            "SELECT n_transitions FROM phase_transitions "
            "WHERE from_phase='culmination' AND to_phase='initiation'"
        ).fetchone()[0]
        assert n == 1
    finally:
        conn.close()


def test_get_transition_returns_distribution(tmp_db: Path):
    """P(phase_T | phase_T-1) bien normalisée."""
    # 3 culminations, 2 initiations, 1 developpement depuis 'initiation'
    for _ in range(3):
        update_transition("initiation", "culmination", "GBPUSD", "M15",
                          "NEUTRE", db_path=tmp_db)
    for _ in range(2):
        update_transition("initiation", "initiation", "GBPUSD", "M15",
                          "NEUTRE", db_path=tmp_db)
    update_transition("initiation", "developpement", "GBPUSD", "M15",
                      "NEUTRE", db_path=tmp_db)
    t = get_transition("initiation", "GBPUSD", "M15", "NEUTRE", db_path=tmp_db)
    assert t is not None
    assert t.from_phase == "initiation"
    assert t.n_transitions == 6
    assert t.most_likely_next == "culmination"
    assert t.most_likely_proba == pytest.approx(0.5, abs=0.01)
    # Distribution normalisée
    total_proba = sum(t.distribution.values())
    assert total_proba == pytest.approx(1.0, abs=0.01)


def test_get_transition_below_min_n_returns_none(tmp_db: Path):
    """< MIN_N transitions → None."""
    for _ in range(MIN_N_OBSERVATIONS - 1):
        update_transition("culmination", "initiation", "GBPUSD", "M15",
                          "NEUTRE", db_path=tmp_db)
    t = get_transition("culmination", "GBPUSD", "M15", "NEUTRE", db_path=tmp_db)
    assert t is None


def test_get_transition_invalid_phase(tmp_db: Path):
    """Phase hors vocabulaire → None (R6)."""
    t = get_transition("INVALID", "GBPUSD", "M15", "NEUTRE", db_path=tmp_db)
    assert t is None


def test_update_transition_invalid_phases(tmp_db: Path):
    assert update_transition("INVALID", "culmination", "GBPUSD", "M15",
                             "NEUTRE", db_path=tmp_db) is False
    assert update_transition("culmination", "INVALID", "GBPUSD", "M15",
                             "NEUTRE", db_path=tmp_db) is False


# --------------------------------------------------------------- T10 update_transition

def test_update_transition_repeated(tmp_db: Path):
    for _ in range(10):
        update_transition("culmination", "initiation", "GBPUSD", "M15",
                          "NEUTRE", db_path=tmp_db)
    conn = sqlite3.connect(str(tmp_db))
    try:
        n = conn.execute(
            "SELECT n_transitions FROM phase_transitions "
            "WHERE from_phase='culmination' AND to_phase='initiation'"
        ).fetchone()[0]
        assert n == 10
    finally:
        conn.close()


# --------------------------------------------------------------- T11 purge_stale

def test_purge_stale_removes_old(tmp_db: Path):
    """Patterns dont last_updated_ts > TTL sont purgés."""
    # Insère 1 pattern très vieux (TTL + 1 jour)
    conn = sqlite3.connect(str(tmp_db))
    try:
        old_ts = time.time() - (TTL_DAYS + 1) * 86400.0
        conn.execute(
            "INSERT INTO cycle_patterns VALUES (?, ?, ?, ?, ?, 5, 5, 5, 0, 0, 0, 0, 0, 0, ?)",
            ("GBPUSD", "M15", "NEUTRE", "culmination", "MEDIUM", old_ts),
        )
        # Pattern récent (doit rester)
        new_ts = time.time()
        conn.execute(
            "INSERT INTO cycle_patterns VALUES (?, ?, ?, ?, ?, 5, 5, 5, 0, 0, 0, 0, 0, 0, ?)",
            ("EURUSD", "M15", "NEUTRE", "culmination", "MEDIUM", new_ts),
        )
        conn.commit()
    finally:
        conn.close()
    n = purge_stale(db_path=tmp_db)
    assert n >= 1  # au moins le vieux
    # Le récent doit toujours être là
    result = recall("EURUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is not None


def test_purge_stale_db_inexistant(tmp_path: Path):
    n = purge_stale(db_path=tmp_path / "no.db")
    assert n == 0


# --------------------------------------------------------------- T12 percentiles

def test_percentile_basic():
    assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == pytest.approx(3.0)
    assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == pytest.approx(4.8, abs=0.1)
    assert _percentile([], 0.5) == 0.0
    assert _percentile([5.0], 0.5) == 5.0


def test_recompute_percentiles(tmp_db: Path):
    """Recalcule p50/p95 depuis liste brute."""
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=5.0, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=15.0, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=25.0, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=35.0, db_path=tmp_db)
    update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, is_win=True,
           duration_bars=100.0, db_path=tmp_db)
    ok = recompute_percentiles("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
                               [5.0, 15.0, 25.0, 35.0, 100.0], db_path=tmp_db)
    assert ok is True
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is not None
    assert result.p50_duration_bars == 25.0
    # p95 sur [5, 15, 25, 35, 100] par interpolation linéaire (n=5, idx=3.8) :
    # idx=3.8 → entre sorted_d[3]=35 et sorted_d[4]=100 → 35 + (100-35)*0.8 = 87.0
    assert result.p95_duration_bars == pytest.approx(87.0, abs=2.0)


def test_recompute_percentiles_empty_list(tmp_db: Path):
    ok = recompute_percentiles("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
                               [], db_path=tmp_db)
    assert ok is False


# --------------------------------------------------------------- T13 R6 défensif

def test_recall_handles_db_error(tmp_path: Path, monkeypatch):
    """R6 : si DB corrompue, recall ne crash pas, retourne None."""
    db = tmp_path / "corrupt.db"
    db.write_text("not a sqlite db")
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=db)
    assert result is None


def test_update_handles_db_error(tmp_path: Path):
    db = tmp_path / "corrupt.db"
    db.write_text("not a sqlite db")
    ok = update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
                is_win=True, db_path=db)
    assert ok is False


# --------------------------------------------------------------- T14 is_actionable

def test_is_actionable_under_min_n(tmp_db: Path):
    """is_actionable False si n_observations < MIN_N."""
    for _ in range(MIN_N_OBSERVATIONS - 1):
        update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
               is_win=True, db_path=tmp_db)
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is None  # recall filtre déjà


def test_is_actionable_expired(tmp_db: Path):
    """is_actionable False si age > TTL."""
    conn = sqlite3.connect(str(tmp_db))
    try:
        old_ts = time.time() - (TTL_DAYS + 5) * 86400.0
        conn.execute(
            "INSERT INTO cycle_patterns VALUES (?, ?, ?, ?, ?, 10, 7, 10, 0, 0, 0, 0, 0, 0, ?)",
            ("GBPUSD", "M15", "NEUTRE", "culmination", "MEDIUM", old_ts),
        )
        conn.commit()
    finally:
        conn.close()
    # recall() retourne None car expired
    result = recall("GBPUSD", "M15", "NEUTRE", "culmination", 3.5, db_path=tmp_db)
    assert result is None


# --------------------------------------------------------------- T15 get_stats

def test_get_stats_empty_db(tmp_db: Path):
    stats = get_stats(tmp_db)
    assert stats["exists"] is True
    assert stats["n_patterns"] == 0
    assert stats["n_actionable_patterns"] == 0
    assert stats["n_transitions"] == 0


def test_get_stats_after_updates(tmp_db: Path):
    for _ in range(7):
        update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
               is_win=True, db_path=tmp_db)
    update_transition("culmination", "initiation", "GBPUSD", "M15",
                      "NEUTRE", db_path=tmp_db)
    stats = get_stats(tmp_db)
    assert stats["n_patterns"] == 1
    assert stats["n_actionable_patterns"] == 1  # n=7 >= MIN_N
    assert stats["n_transitions"] == 1


def test_get_stats_db_inexistant(tmp_path: Path):
    stats = get_stats(tmp_path / "no.db")
    assert stats["exists"] is False


# --------------------------------------------------------------- T16 dataclasses

def test_cycle_pattern_to_dict():
    p = CyclePattern(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_bucket="MEDIUM",
        n_observations=10, n_wins=8, win_rate=0.8,
        mean_duration_bars=15.0, p50_duration_bars=12.0, p95_duration_bars=25.0,
        n_resolved=10, n_pending=0, confidence=0.7,
        last_updated_ts=time.time(),
    )
    d = p.to_dict()
    assert d["symbol"] == "GBPUSD"
    assert d["win_rate"] == 0.8
    # Round-trip via dataclass constructor
    p2 = CyclePattern(**d)
    assert p2 == p


def test_transition_pattern_to_dict():
    t = TransitionPattern(
        from_phase="initiation", symbol="GBPUSD", timeframe="M15",
        regime_type="NEUTRE", n_transitions=10,
        distribution={"culmination": 0.6, "initiation": 0.4},
        most_likely_next="culmination", most_likely_proba=0.6,
        confidence=0.5,
    )
    d = t.to_dict()
    assert d["most_likely_next"] == "culmination"


# --------------------------------------------------------------- T17 default DB path

def test_default_db_path_exists_constant():
    """DEFAULT_DB_PATH pointe vers data/v9_cycle_memory.db (R8)."""
    assert str(DEFAULT_DB_PATH).endswith("v9_cycle_memory.db")


# --------------------------------------------------------------- T18 CLI

def test_main_init(tmp_path: Path, capsys):
    from core.v9.v9_cycle_memory import main
    db = tmp_path / "cli_test.db"
    rc = main(["--init", "--db", str(db)])
    assert rc == 0
    assert db.exists()
    captured = capsys.readouterr()
    assert "DB initialisée" in captured.out


def test_main_stats(tmp_db: Path, capsys):
    from core.v9.v9_cycle_memory import main
    rc = main(["--stats", "--db", str(tmp_db)])
    assert rc == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "n_patterns" in out
    assert "exists" in out


def test_main_no_args(capsys):
    from core.v9.v9_cycle_memory import main
    rc = main([])
    assert rc == 1
