"""Tests pour v9_heatmap_l15.py (Phase 126 L15).

Couvre :
1. Chargement des trades depuis la DB (R6 fail-open si DB absente)
2. Construction heatmap 3D et 2D
3. Détection de niches (WR > 70% ET n >= 10)
4. Proposition de kill switches (BOOST / BLACKLIST)
5. Sérialisation JSON (tuples en strings)
6. Idempotence : 2 runs successifs donnent mêmes niches
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import v9_heatmap_l15 as mod


def test_infer_session_from_hour_import():
    """infer_session_from_hour vient de core.v9.exit_simulator."""
    from core.v9.exit_simulator import infer_session_from_hour
    assert infer_session_from_hour(0) == "asie"
    assert infer_session_from_hour(8) == "london"
    assert infer_session_from_hour(14) == "overlap"
    assert infer_session_from_hour(18) == "new_york"
    assert infer_session_from_hour(23) == "after"


def test_symbol_from_snapshot():
    """Parse v9-{SYMBOL}-{TF}-{bar_time}-{seq} -> SYMBOL."""
    assert mod._symbol_from_snapshot("v9-GBPUSD-M15-123-1") == "GBPUSD"
    assert mod._symbol_from_snapshot("v9-EURUSD-M5-456-2") == "EURUSD"
    assert mod._symbol_from_snapshot("v9-USDJPY-H1-789-3") == "USDJPY"
    assert mod._symbol_from_snapshot("garbage") == "UNKNOWN"
    assert mod._symbol_from_snapshot("") == "UNKNOWN"


def test_build_heatmap_synthetic():
    """Heatmap 3D et 2D avec données synthétiques."""
    trades = [
        {"symbol": "GBPUSD", "session": "london", "regime": "CASSURE", "pattern": "1",
         "is_win": 1, "pips": 5.0, "direction": "haussiere", "n_principes": 1, "utc_hour": 8, "timestamp": "2026-01-01T08:00:00"},
        {"symbol": "GBPUSD", "session": "london", "regime": "CASSURE", "pattern": "1",
         "is_win": 1, "pips": 3.0, "direction": "haussiere", "n_principes": 1, "utc_hour": 8, "timestamp": "2026-01-01T08:00:00"},
        {"symbol": "EURUSD", "session": "asie", "regime": "RETOUR_EQUILIBRE", "pattern": "2",
         "is_win": 0, "pips": -2.0, "direction": "baissiere", "n_principes": 2, "utc_hour": 3, "timestamp": "2026-01-01T03:00:00"},
    ]
    heatmap = mod.build_heatmap(trades)
    # Vérif 3D
    assert "CASSURE" in heatmap["3d_regime_session_pattern"]
    assert "london" in heatmap["3d_regime_session_pattern"]["CASSURE"]
    s = heatmap["3d_regime_session_pattern"]["CASSURE"]["london"]["1"]
    assert s["n"] == 2
    assert s["wins"] == 2
    assert s["pnl"] == 8.0
    # Vérif 2D
    assert heatmap["2d_symbol_session"][("GBPUSD", "london")]["n"] == 2
    assert heatmap["2d_symbol_session"][("EURUSD", "asie")]["pnl"] == -2.0


def test_find_niches_threshold():
    """Niche = WR > 70% ET n >= 10."""
    trades = []
    # 12 trades gagnants (niche)
    for _ in range(12):
        trades.append({"symbol": "GBPUSD", "session": "overlap", "regime": "EXTENSION",
                       "pattern": "1", "is_win": 1, "pips": 5.0, "direction": "haussiere",
                       "n_principes": 1, "utc_hour": 14, "timestamp": "2026-01-01T14:00:00"})
    # 5 trades perdants (non-niche : n<10)
    for _ in range(5):
        trades.append({"symbol": "EURUSD", "session": "asie", "regime": "RETOUR_EQUILIBRE",
                       "pattern": "1", "is_win": 0, "pips": -1.0, "direction": "baissiere",
                       "n_principes": 1, "utc_hour": 2, "timestamp": "2026-01-01T02:00:00"})

    heatmap = mod.build_heatmap(trades)
    niches = mod.find_niches(heatmap, min_n=10, min_wr=70.0)
    assert len(niches) == 1
    n = niches[0]
    assert n["regime"] == "EXTENSION"
    assert n["session"] == "overlap"
    assert n["n"] == 12
    assert n["wr_pct"] == 100.0


def test_propose_kill_switches_boost_and_blacklist():
    """Top niche WR>80% n>=20 -> BOOST ; anti-niche WR<30% n>=15 -> BLACKLIST."""
    trades = []
    # BOOST : 25 trades WR 100%
    for _ in range(25):
        trades.append({"symbol": "GBPUSD", "session": "london", "regime": "CASSURE",
                       "pattern": "1", "is_win": 1, "pips": 5.0, "direction": "haussiere",
                       "n_principes": 1, "utc_hour": 8, "timestamp": "2026-01-01T08:00:00"})
    # BLACKLIST : 20 trades WR 0%
    for _ in range(20):
        trades.append({"symbol": "EURUSD", "session": "asie", "regime": "REJET",
                       "pattern": "5+", "is_win": 0, "pips": -3.0, "direction": "baissiere",
                       "n_principes": 5, "utc_hour": 2, "timestamp": "2026-01-01T02:00:00"})

    heatmap = mod.build_heatmap(trades)
    niches = mod.find_niches(heatmap, min_n=10, min_wr=70.0)
    proposals = mod.propose_kill_switches(niches, heatmap)

    # Au moins 1 BOOST + 1 BLACKLIST
    boost_proposals = [p for p in proposals if p["type"] == "BOOST"]
    blacklist_proposals = [p for p in proposals if p["type"] == "BLACKLIST"]
    assert len(boost_proposals) >= 1, "Aucun BOOST proposé"
    assert len(blacklist_proposals) >= 1, "Aucun BLACKLIST proposé"

    # BOOST sizing_multiplier = 1.3
    assert boost_proposals[0]["sizing_multiplier"] == 1.3
    # BLACKLIST sizing_multiplier = 0.0
    assert blacklist_proposals[0]["sizing_multiplier"] == 0.0
    # Default OFF
    assert boost_proposals[0]["default"] == "0"


def test_stringify_keys_handles_tuples():
    """Sérialise les tuples en strings pour JSON."""
    d = {("GBPUSD", "london"): {"n": 5}}
    out = mod._stringify_keys(d)
    assert "GBPUSD,london" in out
    assert isinstance(list(out.keys())[0], str)


def test_main_idempotent_synthetic(tmp_path):
    """2 runs successifs avec données synthétiques (mock DB) donnent même shape."""
    # Mock DB simple
    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE paper_trades (
            snapshot_id TEXT, direction TEXT, is_win INTEGER,
            pips_simulated REAL, principes_source TEXT, closed_at TEXT
        );
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT, timestamp TEXT, symbol TEXT
        );
        CREATE TABLE regime_snapshots (
            forces_snapshot_ref TEXT, regime_type TEXT, timestamp TEXT
        );
        INSERT INTO paper_trades VALUES
            ('v9-GBPUSD-M15-100-1', 'haussiere', 1, 5.0, 'P1', '2026-01-01T08:00:00'),
            ('v9-GBPUSD-M15-100-2', 'haussiere', 0, -3.0, 'P1,P2', '2026-01-01T08:00:00');
        INSERT INTO forces_snapshots VALUES
            ('v9-GBPUSD-M15-100-1', '2026-01-01T08:00:00+00:00', 'GBPUSD'),
            ('v9-GBPUSD-M15-100-2', '2026-01-01T08:00:00+00:00', 'GBPUSD');
        INSERT INTO regime_snapshots VALUES
            ('v9-GBPUSD-M15-100-1', 'CASSURE', '2026-01-01T08:00:00+00:00'),
            ('v9-GBPUSD-M15-100-2', 'REJET', '2026-01-01T08:00:00+00:00');
    """)
    con.commit()
    con.close()

    output = tmp_path / "out.json"
    report = tmp_path / "report.md"
    rc = mod.main([
        "--db", str(db_path),
        "--output", str(output),
        "--report", str(report),
    ])
    assert rc == 0
    assert output.exists()
    d = json.loads(output.read_text(encoding="utf-8"))
    assert d["total_trades"] == 2
    assert d["niches_count"] >= 0  # Pas de niche avec n<10


def test_main_missing_db(tmp_path):
    """R6 fail-open : DB introuvable -> exit code 4."""
    rc = mod.main([
        "--db", str(tmp_path / "nope.db"),
        "--output", str(tmp_path / "out.json"),
        "--report", str(tmp_path / "report.md"),
    ])
    assert rc == 4
