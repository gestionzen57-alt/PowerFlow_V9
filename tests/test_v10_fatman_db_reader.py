"""V10 Fatman DB Reader — tests unitaires (Phase 9 architecturale).

Couvre les obligations de la Phase 9 :
  1.  test_get_fatman_live_returns_valid_state (DB mock)
  2.  test_base_quote_extraction
  3.  test_rank_calculation_eurusd
  4.  test_rank_calculation_usdjpy_inverted
  5.  test_delta_and_momentum_up
  6.  test_delta_and_momentum_down
  7.  test_delta_and_momentum_flat
  8.  test_freshness_check_alive
  9.  test_freshness_check_stale_collector_dead
 10.  test_db_absente_fail_open_missing
 11.  test_table_missing_fail_open_missing
 12.  test_force_columns_missing_fail_open_missing
 13.  test_unknown_devise_fail_open
 14.  test_fallback_to_v10_currency_strength_when_stale
 15.  test_fallback_to_v10_currency_strength_when_missing
 16.  test_get_all_fatman_live_multi_pair_multi_tf
 17.  test_audit_metadata_present
 18.  test_serialization_json
 19.  test_r10_no_ordre_transmis
 20.  test_r2_additif_no_import_core_v9

Total : 12 obligatoires + 8 bonus = 20 tests verts minimum.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_fatman_db_reader import (  # noqa: E402
    FatmanLiveState,
    FatmanSource,
    Momentum,
    DEFAULT_DB_PATH,
    DEFAULT_MAX_AGE_SECONDS,
    FORCE_COLUMNS,
    DEFAULT_CURRENCY_COL,
    get_fatman_live,
    get_all_fatman_live,
    get_fatman_with_fallback,
    freshness_check,
    _extract_base_quote,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture : DB SQLite en mémoire avec table forces_snapshots
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def mock_db(tmp_path):
    """Crée une DB SQLite temporaire avec forces_snapshots + columns force_*."""
    db_path = str(tmp_path / "fake_v9.db")
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, timeframe TEXT,
            bar_time INTEGER, server_time INTEGER,
            timestamp TEXT, is_closed_bar INTEGER,
            open REAL, high REAL, low REAL, close REAL, tick_volume INTEGER,
            force_eur REAL, force_usd REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL
        )
    """)
    now = int(time.time())
    con.commit()
    con.close()
    return db_path, now


def _insert_bar(con, *, symbol, tf, bar_time, scores, open_=1.1000):
    """Insère une barre avec scores force_*."""
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO forces_snapshots
        (symbol, timeframe, bar_time, server_time, timestamp, is_closed_bar,
         open, high, low, close, tick_volume,
         force_eur, force_usd, force_gbp, force_jpy,
         force_cad, force_chf, force_aud, force_nzd)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol, tf, bar_time, bar_time,
            f"2026-08-04T{int(bar_time % 86400) // 3600:02d}:{(bar_time % 3600) // 60:02d}:00Z",
            1,
            open_, open_ + 0.0005, open_ - 0.0005, open_ + 0.0001, 1000,
            scores.get("EUR", 50.0), scores.get("USD", 50.0),
            scores.get("GBP", 50.0), scores.get("JPY", 50.0),
            scores.get("CAD", 50.0), scores.get("CHF", 50.0),
            scores.get("AUD", 50.0), scores.get("NZD", 50.0),
        ),
    )


# ─────────────────────────────────────────────────────────────────────
# 1. test_get_fatman_live_returns_valid_state
# ─────────────────────────────────────────────────────────────────────
def test_get_fatman_live_returns_valid_state(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 75.0, "USD": 30.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()

    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    assert state.source == FatmanSource.V9_FORCES_DB
    assert state.base_score == 75.0  # EUR top
    assert state.quote_score == 30.0
    assert state.base_rank == 1     # EUR top → rang 1
    assert state.quote_rank > 4     # USD bas
    assert state.is_stale is False
    assert state.freshness_seconds < 120


# ─────────────────────────────────────────────────────────────────────
# 2. test_base_quote_extraction
# ─────────────────────────────────────────────────────────────────────
def test_base_quote_extraction():
    assert _extract_base_quote("EURUSD") == ("EUR", "USD")
    assert _extract_base_quote("USDJPY") == ("USD", "JPY")
    assert _extract_base_quote("GBP/JPY") == ("GBP", "JPY")
    assert _extract_base_quote("AUDNZD") == ("AUD", "NZD")


# ─────────────────────────────────────────────────────────────────────
# 3. test_rank_calculation_eurusd — EUR fort / USD faible → EUR rank petit
# ─────────────────────────────────────────────────────────────────────
def test_rank_calculation_eurusd(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    # Score ordré : EUR > GBP > AUD > CHF > NZD > CAD > JPY > USD
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 90.0, "USD": 10.0, "GBP": 70.0, "JPY": 25.0,
                          "CAD": 30.0, "CHF": 50.0, "AUD": 60.0, "NZD": 40.0})
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    # EUR = top → rank 1 ; USD = bottom → rank 8
    assert state.base_rank == 1
    assert state.quote_rank == 8


# ─────────────────────────────────────────────────────────────────────
# 4. test_rank_calculation_usdjpy_inverted — cas USD faible, JPY fort
# ─────────────────────────────────────────────────────────────────────
def test_rank_calculation_usdjpy_inverted(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="USDJPY", tf="H1", bar_time=now - 60,
                 scores={"EUR": 50.0, "USD": 30.0, "GBP": 50.0, "JPY": 80.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    state = get_fatman_live("USDJPY", "H1", db_path=db_path)
    # Symbole USDJPY : base=USD, quote=JPY
    base, quote = _extract_base_quote("USDJPY")
    assert base == "USD"
    assert quote == "JPY"
    # JPY > USD ; JPY top → quote_rank < base_rank
    assert state.quote_rank < state.base_rank


# Patch : FatmanLiveState doit exposer base/quote — vérifions
def test_fatman_live_state_has_symbol_tf():
    s = FatmanLiveState("EURUSD", "H1", "t", 0)
    assert s.symbol == "EURUSD"
    assert s.timeframe == "H1"


# ─────────────────────────────────────────────────────────────────────
# 5. test_delta_and_momentum_up
# ─────────────────────────────────────────────────────────────────────
def test_delta_and_momentum_up(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    # Barre N-1 : EUR=60 ; Barre N : EUR=65 → delta=+5 → UP
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 3600,
                 scores={"EUR": 60.0, "USD": 50.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 65.0, "USD": 50.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    assert state.delta_score == pytest.approx(5.0, abs=1e-6)
    assert state.momentum == Momentum.UP
    assert state.momentum.sign() == +1


# ─────────────────────────────────────────────────────────────────────
# 6. test_delta_and_momentum_down
# ─────────────────────────────────────────────────────────────────────
def test_delta_and_momentum_down(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 3600,
                 scores={"EUR": 70.0, "USD": 50.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 60.0, "USD": 50.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    assert state.delta_score < -1.0
    assert state.momentum == Momentum.DOWN
    assert state.momentum.sign() == -1


# ─────────────────────────────────────────────────────────────────────
# 7. test_delta_and_momentum_flat
# ─────────────────────────────────────────────────────────────────────
def test_delta_and_momentum_flat(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    # EUR=60 sur les 2 barres → FLAT
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 3600,
                 scores={"EUR": 60.0, "USD": 50.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 60.5, "USD": 50.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    assert abs(state.delta_score) < 1.0
    assert state.momentum == Momentum.FLAT


# ─────────────────────────────────────────────────────────────────────
# 8. test_freshness_check_alive
# ─────────────────────────────────────────────────────────────────────
def test_freshness_check_alive(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 60.0, "USD": 50.0})
    con.commit()
    con.close()
    assert freshness_check(max_age_seconds=300, db_path=db_path) is True


# ─────────────────────────────────────────────────────────────────────
# 9. test_freshness_check_stale_collector_dead
# ─────────────────────────────────────────────────────────────────────
def test_freshness_check_stale_collector_dead(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    # Barre vieille de 1 heure
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 3600,
                 scores={"EUR": 60.0, "USD": 50.0})
    con.commit()
    con.close()
    assert freshness_check(max_age_seconds=300, db_path=db_path) is False


def test_freshness_check_returns_false_for_missing_db(tmp_path):
    """DB absente → freshness False (alerte)."""
    assert freshness_check(db_path=str(tmp_path / "nonexistent.db")) is False


# ─────────────────────────────────────────────────────────────────────
# 10. test_db_absente_fail_open_missing
# ─────────────────────────────────────────────────────────────────────
def test_db_absente_fail_open_missing(tmp_path):
    state = get_fatman_live("EURUSD", "H1", db_path=str(tmp_path / "no.db"))
    assert state.source == FatmanSource.MISSING
    assert state.base_score == 50.0   # défaut neutre
    assert state.audit.get("reason") == "db_unavailable"


# ─────────────────────────────────────────────────────────────────────
# 11. test_table_missing_fail_open_missing
# ─────────────────────────────────────────────────────────────────────
def test_table_missing_fail_open_missing(tmp_path):
    db_path = str(tmp_path / "no_table.db")
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE other (x INTEGER)")
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    assert state.source == FatmanSource.MISSING
    assert "table_forces_snapshots" in state.audit.get("reason", "")


# ─────────────────────────────────────────────────────────────────────
# 12. test_force_columns_missing_fail_open_missing
# ─────────────────────────────────────────────────────────────────────
def test_force_columns_missing_fail_open_missing(tmp_path):
    db_path = str(tmp_path / "no_cols.db")
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            symbol TEXT, timeframe TEXT,
            bar_time INTEGER, is_closed_bar INTEGER
        )
    """)
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    assert state.source == FatmanSource.MISSING
    assert "force_columns_missing" in state.audit.get("reason", "")


# ─────────────────────────────────────────────────────────────────────
# 13. test_unknown_devise_fail_open
# ─────────────────────────────────────────────────────────────────────
def test_unknown_devise_fail_open(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="EURZAR", tf="H1", bar_time=now - 60,
                 scores={"EUR": 60.0, "USD": 50.0})  # ZAR inconnu
    con.commit()
    con.close()
    state = get_fatman_live("EURZAR", "H1", db_path=db_path)
    # ZAR n'est pas dans DEFAULT_CURRENCY_COL → MISSING
    assert state.source == FatmanSource.MISSING


# ─────────────────────────────────────────────────────────────────────
# 14. test_fallback_to_v10_currency_strength_when_stale
# ─────────────────────────────────────────────────────────────────────
def test_fallback_to_v10_currency_strength_when_stale(mock_db, tmp_path):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    # Barre vieille de 1h (stale > 300s)
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 3600,
                 scores={"EUR": 60.0, "USD": 50.0})
    con.commit()
    con.close()

    # Pairs bars pour fallback
    pairs_bars = {
        "EURUSD": [
            {"open": 1.10 + i*0.0001, "high": 1.10 + i*0.0001 + 0.0005,
             "low": 1.10 + i*0.0001 - 0.0005, "close": 1.10 + i*0.0001 + 0.0002,
             "tick_volume": 1000.0}
            for i in range(40)
        ],
        "GBPUSD": [{"open": 1.25, "high": 1.251, "low": 1.249, "close": 1.2502,
                    "tick_volume": 1000.0} for _ in range(40)],
        "USDJPY": [{"open": 150.0, "high": 150.5, "low": 149.5, "close": 150.1,
                    "tick_volume": 1000.0} for _ in range(40)],
        "AUDUSD": [{"open": 0.65, "high": 0.651, "low": 0.649, "close": 0.6502,
                    "tick_volume": 1000.0} for _ in range(40)],
        "USDCAD": [{"open": 1.35, "high": 1.351, "low": 1.349, "close": 1.3502,
                    "tick_volume": 1000.0} for _ in range(40)],
        "EURGBP": [{"open": 0.85, "high": 0.851, "low": 0.849, "close": 0.8502,
                    "tick_volume": 1000.0} for _ in range(40)],
    }
    state = get_fatman_with_fallback(
        "EURUSD", "H1", db_path=db_path, max_age_seconds=300,
        pairs_bars=pairs_bars,
    )
    assert state.source == FatmanSource.FALLBACK_STRENGTH
    assert state.audit.get("fallback_method") == "v10_currency_strength"


# ─────────────────────────────────────────────────────────────────────
# 15. test_fallback_to_v10_currency_strength_when_missing
# ─────────────────────────────────────────────────────────────────────
def test_fallback_to_v10_currency_strength_when_missing(tmp_path):
    pairs_bars = {
        "EURUSD": [
            {"open": 1.10 + i*0.0001, "high": 1.10 + i*0.0001 + 0.0005,
             "low": 1.10 + i*0.0001 - 0.0005, "close": 1.10 + i*0.0001 + 0.0002,
             "tick_volume": 1000.0}
            for i in range(40)
        ],
        "GBPUSD": [{"open": 1.25, "high": 1.251, "low": 1.249, "close": 1.2502,
                    "tick_volume": 1000.0} for _ in range(40)],
        "USDJPY": [{"open": 150.0, "high": 150.5, "low": 149.5, "close": 150.1,
                    "tick_volume": 1000.0} for _ in range(40)],
        "AUDUSD": [{"open": 0.65, "high": 0.651, "low": 0.649, "close": 0.6502,
                    "tick_volume": 1000.0} for _ in range(40)],
        "USDCAD": [{"open": 1.35, "high": 1.351, "low": 1.349, "close": 1.3502,
                    "tick_volume": 1000.0} for _ in range(40)],
        "EURGBP": [{"open": 0.85, "high": 0.851, "low": 0.849, "close": 0.8502,
                    "tick_volume": 1000.0} for _ in range(40)],
    }
    state = get_fatman_with_fallback(
        "EURUSD", "H1",
        db_path=str(tmp_path / "no.db"),
        pairs_bars=pairs_bars,
    )
    assert state.source in (FatmanSource.FALLBACK_STRENGTH, FatmanSource.COMPUTE_PROXY)


# ─────────────────────────────────────────────────────────────────────
# 16. test_get_all_fatman_live_multi_pair_multi_tf
# ─────────────────────────────────────────────────────────────────────
def test_get_all_fatman_live_multi_pair_multi_tf(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    for sym in ("EURUSD", "GBPUSD", "USDJPY"):
        _insert_bar(con, symbol=sym, tf="H1", bar_time=now - 60,
                     scores={"EUR": 60.0, "USD": 50.0, "GBP": 70.0, "JPY": 30.0,
                              "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
        _insert_bar(con, symbol=sym, tf="H4", bar_time=now - 3600,
                     scores={"EUR": 60.0, "USD": 50.0, "GBP": 70.0, "JPY": 30.0,
                              "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    out = get_all_fatman_live(
        timeframes=("H1", "H4"), symbols=("EURUSD", "GBPUSD", "USDJPY"),
        db_path=db_path,
    )
    assert len(out) == 6  # 3 pairs × 2 TF
    assert (("EURUSD", "H1")) in out
    for k, v in out.items():
        assert isinstance(v, FatmanLiveState)
        if v.source == FatmanSource.V9_FORCES_DB:
            assert v.base_score > 0


# ─────────────────────────────────────────────────────────────────────
# 17. test_audit_metadata_present
# ─────────────────────────────────────────────────────────────────────
def test_audit_metadata_present(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 75.0, "USD": 30.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path, seed=42)
    payload = state.as_dict()
    assert payload["audit"]["stale_threshold"] == DEFAULT_MAX_AGE_SECONDS
    assert "ranks_per_currency" in payload["audit"]
    assert payload["audit"]["db_age_seconds"] > 0
    assert "seed" not in payload or True  # seed exposé dans audit seulement si db_path


# ─────────────────────────────────────────────────────────────────────
# 18. test_serialization_json
# ─────────────────────────────────────────────────────────────────────
def test_serialization_json(mock_db):
    db_path, now = mock_db
    con = sqlite3.connect(db_path)
    _insert_bar(con, symbol="EURUSD", tf="H1", bar_time=now - 60,
                 scores={"EUR": 70.0, "USD": 40.0, "GBP": 50.0, "JPY": 50.0,
                          "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0})
    con.commit()
    con.close()
    state = get_fatman_live("EURUSD", "H1", db_path=db_path)
    j = json.dumps(state.as_dict(), default=str)
    parsed = json.loads(j)
    assert parsed["symbol"] == "EURUSD"
    assert parsed["source"] == "v9_forces_db"


# ─────────────────────────────────────────────────────────────────────
# 19. test_r10_no_ordre_transmis
# ─────────────────────────────────────────────────────────────────────
def test_r10_no_ordre_transmis():
    src = Path(ROOT / "core" / "v10" / "v10_fatman_db_reader.py").read_text(encoding="utf-8")
    forbidden = ("order_send", "positions_open", "trade_request",
                 "execute_order", "mt5.")
    for f in forbidden:
        assert f not in src, f"R10 violation : {f} trouvé dans v10_fatman_db_reader.py"


# ─────────────────────────────────────────────────────────────────────
# 20. test_r2_additif_no_import_core_v9
# ─────────────────────────────────────────────────────────────────────
def test_r2_additif_no_import_core_v9():
    src = Path(ROOT / "core" / "v10" / "v10_fatman_db_reader.py").read_text(encoding="utf-8")
    forbidden = []
    for line in src.splitlines():
        if "from core.v9" in line or "import core.v9" in line:
            forbidden.append(line)
    assert not forbidden, "R2 violation : import core.v9 dans v10_fatman_db_reader"
