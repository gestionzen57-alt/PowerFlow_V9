"""test_v9_cross_pair_metrics.py — Régression module cross-pair (motion #8).

Tests :
  1. cross_pair_dispersion retourne float sur symboles valides, None sur invalides
  2. pair_force_ratio retourne float ∈ [-100, +100]
  3. neutre_rate_24h calcule correctement le taux NEUTRE
  4. R6 défensif : DB absente / symbole inconnu → None, pas d'exception

Doctrine :
- R7 : tests verts obligatoires
- R2 : module séparé, n'altère pas RegimeDetector
- R6 : défensif, ne lève jamais
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _make_minimal_db(tmp_path: Path) -> Path:
    """Crée une DB tmp avec 1 snapshot par symbole × TF."""
    db = tmp_path / "test_cross_pair.db"
    con = sqlite3.connect(db)
    try:
        con.executescript(
            """
            CREATE TABLE forces_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT,
                symbol TEXT,
                timeframe TEXT,
                timestamp TEXT,
                force_usd REAL, force_gbp REAL, force_eur REAL, force_jpy REAL,
                force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL
            );
            CREATE TABLE regime_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regime_type TEXT,
                symbol TEXT,
                timeframe TEXT,
                timestamp TEXT
            );
            """
        )
        # 1 snapshot GBPUSD M5 : USD=80, GBP=20, le reste=50
        con.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, timestamp, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, "
            "force_aud, force_nzd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("snap1", "GBPUSD", "M5", "2026-07-20T10:00:00+00:00",
             80.0, 20.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0),
        )
        # 2nd snapshot GBPUSD M5 5min plus tard
        con.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, timestamp, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, "
            "force_aud, force_nzd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("snap2", "GBPUSD", "M5", "2026-07-20T10:05:00+00:00",
             70.0, 30.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0),
        )
        # Regime snapshots : 10 NEUTRE + 2 EXTENSION
        for i in range(10):
            con.execute(
                "INSERT INTO regime_snapshots (regime_type, symbol, timeframe, timestamp) "
                "VALUES ('NEUTRE', 'GBPUSD', 'M5', ?)",
                (f"2026-07-20T10:0{i}:00+00:00",),
            )
        for i in range(2):
            con.execute(
                "INSERT INTO regime_snapshots (regime_type, symbol, timeframe, timestamp) "
                "VALUES ('EXTENSION', 'GBPUSD', 'M5', ?)",
                (f"2026-07-20T10:1{i}:00+00:00",),
            )
        con.commit()
    finally:
        con.close()
    return db


def test_cross_pair_dispersion_returns_float(tmp_path: Path):
    """Stddev des 8 forces sur le snapshot le plus récent."""
    db = _make_minimal_db(tmp_path)
    from core.v9.v9_cross_pair_metrics import cross_pair_dispersion
    disp = cross_pair_dispersion(db, ts_iso="2026-07-20T10:00:00+00:00", symbol="GBPUSD")
    assert disp is not None
    assert isinstance(disp, float)
    assert disp > 0, "stddev > 0 quand les forces varient"


def test_cross_pair_dispersion_unknown_symbol(tmp_path: Path):
    """Symbole absent → None (R6)."""
    db = _make_minimal_db(tmp_path)
    from core.v9.v9_cross_pair_metrics import cross_pair_dispersion
    disp = cross_pair_dispersion(db, ts_iso="2026-07-20T10:00:00+00:00", symbol="UNKNOWN")
    assert disp is None


def test_pair_force_ratio_gbpusd_bearish(tmp_path: Path):
    """GBPUSD : GBP=20, USD=80 → ratio = -60 (très baissier)."""
    db = _make_minimal_db(tmp_path)
    from core.v9.v9_cross_pair_metrics import pair_force_ratio
    ratio = pair_force_ratio(db, symbol="GBPUSD", ts_iso="2026-07-20T10:00:00+00:00")
    assert ratio == -60.0


def test_pair_force_ratio_unknown_symbol(tmp_path: Path):
    """Symbole non mappé → None (R6)."""
    db = _make_minimal_db(tmp_path)
    from core.v9.v9_cross_pair_metrics import pair_force_ratio
    assert pair_force_ratio(db, symbol="UNKNOWN") is None


def test_neutre_rate_24h_count(tmp_path: Path):
    """10 NEUTRE + 2 EXTENSION = 12 total, 83.3% NEUTRE."""
    db = _make_minimal_db(tmp_path)
    from core.v9.v9_cross_pair_metrics import neutre_rate_24h
    res = neutre_rate_24h(db, symbol="GBPUSD", timeframe="M5")
    assert res["total"] == 12
    assert res["neutre"] == 10
    assert res["pct"] == 83.33
    assert res["by_regime"]["NEUTRE"] == 10
    assert res["by_regime"]["EXTENSION"] == 2


def test_neutre_rate_24h_global_no_filter(tmp_path: Path):
    """Sans filtre symbol/tf, retourne l'agrégat global."""
    db = _make_minimal_db(tmp_path)
    from core.v9.v9_cross_pair_metrics import neutre_rate_24h
    res = neutre_rate_24h(db)
    assert res["total"] == 12
    assert res["pct"] == 83.33


def test_defensif_db_absente(tmp_path: Path):
    """DB inexistante → None / dict vide, pas d'exception."""
    from core.v9.v9_cross_pair_metrics import cross_pair_dispersion, pair_force_ratio, neutre_rate_24h
    fake_db = tmp_path / "inexistante.db"
    assert cross_pair_dispersion(fake_db) is None
    assert pair_force_ratio(fake_db, symbol="GBPUSD") is None
    res = neutre_rate_24h(fake_db)
    assert res == {"total": 0, "neutre": 0, "pct": 0.0, "by_regime": {}}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
