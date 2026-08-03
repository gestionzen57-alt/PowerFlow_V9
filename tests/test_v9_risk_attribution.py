"""Tests pour v9_risk_attribution.py (Phase 132).

Couvre les cas critiques :
1. Trades vides -> all dicts empty, concentration = 0
2. Trades synthetiques -> aggregation correcte par cross/principe/regime/session
3. Concentration : top-5 negatif concentre
4. top_risk_concentrations : trie par PNL croissant
5. Render markdown : contient sections attendues
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9.v9_risk_attribution import (
    compute_risk_attribution,
    top_risk_concentrations,
    render_report,
    main,
)


def test_trades_vides():
    """Aucun trade -> agregations vides, concentration = 0."""
    a = compute_risk_attribution(trades=[])
    assert a["total_n"] == 0
    assert a["total_pnl"] == 0.0
    assert a["concentration"] == 0.0
    assert a["by_cross"] == {}
    assert a["by_principe"] == {}
    assert a["by_regime"] == {}
    assert a["by_session"] == {}


def test_aggregation_simple():
    """3 trades : agregation correcte."""
    trades = [
        {"principe_set": ("A", "B"), "regime": "CASSURE", "session": "london",
         "direction": "haussiere", "is_win": 1, "pips": 10.0},
        {"principe_set": ("A", "B"), "regime": "CASSURE", "session": "london",
         "direction": "haussiere", "is_win": 0, "pips": -5.0},
        {"principe_set": ("C",), "regime": "EXTENSION", "session": "new_york",
         "direction": "baissiere", "is_win": 1, "pips": 8.0},
    ]
    a = compute_risk_attribution(trades=trades)
    assert a["total_n"] == 3
    assert a["total_pnl"] == 13.0  # 10 - 5 + 8
    # by_cross
    assert len(a["by_cross"]) == 2
    # by_principe : A=2, B=2, C=1
    assert a["by_principe"]["A"]["n"] == 2
    assert a["by_principe"]["B"]["n"] == 2
    assert a["by_principe"]["C"]["n"] == 1
    # by_regime
    assert a["by_regime"]["CASSURE"]["n"] == 2
    assert a["by_regime"]["EXTENSION"]["n"] == 1
    # by_session
    assert a["by_session"]["london"]["n"] == 2
    assert a["by_session"]["new_york"]["n"] == 1


def test_concentration_top5():
    """Concentration : 5 croisements distincts avec PNL negatif massif.

    Note : la concentration est calculee par croisement unique (par tuple
    (principe_set, regime, session)), pas par trade. Donc 5 croisements
    uniques avec PNL = -100 = -500 total concentre sur ces 5.
    """
    trades = []
    # 5 croisements distincts, 5 trades chacun = 25 trades a -100p chacun
    for i in range(5):
        for _ in range(5):
            trades.append({
                "principe_set": (f"P{i}",), "regime": "REJET", "session": "asie",
                "direction": "baissiere", "is_win": 0, "pips": -100.0,
            })
    # 100 croisements distincts chacun avec PNL = -2p
    for i in range(100):
        trades.append({
            "principe_set": (f"Q{i}",), "regime": "RETOUR_EQUILIBRE", "session": "asie",
            "direction": "baissiere", "is_win": 0, "pips": -2.0,
        })
    a = compute_risk_attribution(trades=trades)
    # Top 5 = 5 croisements * -500 = -2500
    # Total negatif = -2500 + 100*-2 = -2700
    # Concentration = 2500/2700 = 92.6%
    assert 92.0 <= a["concentration"] <= 93.0


def test_top_risk_concentrations_ordre():
    """top_risk_concentrations trie par PNL croissant (plus negatif en premier)."""
    trades = [
        {"principe_set": ("A",), "regime": "R1", "session": "asie",
         "direction": "h", "is_win": 0, "pips": -10.0},
        {"principe_set": ("B",), "regime": "R1", "session": "asie",
         "direction": "h", "is_win": 0, "pips": -100.0},
        {"principe_set": ("C",), "regime": "R1", "session": "asie",
         "direction": "h", "is_win": 0, "pips": -50.0},
    ]
    a = compute_risk_attribution(trades=trades)
    top = top_risk_concentrations(a, top_n=3)
    assert len(top) == 3
    # Premier = plus negatif = B (-100)
    assert top[0]["pnl"] == -100.0
    assert top[1]["pnl"] == -50.0
    assert top[2]["pnl"] == -10.0


def test_top_risk_exclude_positive_pnl():
    """top_risk_concentrations exclut les croisements avec PNL >= 0."""
    trades = [
        {"principe_set": ("A",), "regime": "R1", "session": "asie",
         "direction": "h", "is_win": 1, "pips": 50.0},
        {"principe_set": ("B",), "regime": "R1", "session": "asie",
         "direction": "h", "is_win": 0, "pips": -10.0},
    ]
    a = compute_risk_attribution(trades=trades)
    top = top_risk_concentrations(a, top_n=5)
    # Seul B est negatif
    assert len(top) == 1
    assert "B" in top[0]["cross"]


def test_render_report_contient_sections():
    """render_report contient les sections attendues."""
    trades = [
        {"principe_set": ("A",), "regime": "CASSURE", "session": "london",
         "direction": "h", "is_win": 0, "pips": -10.0},
    ]
    a = compute_risk_attribution(trades=trades)
    top = top_risk_concentrations(a, top_n=5)
    md = render_report(a, top)
    assert "Phase 132" in md
    assert "Total trades" in md
    assert "Concentration" in md
    assert "Top 5 croisements" in md
    assert "PNL par regime" in md
    assert "PNL par session" in md
    assert "PNL par principe" in md


def test_main_with_db_synthetique(tmp_path):
    """main() avec DB synthetique ecrit JSON + Markdown."""
    db_path = tmp_path / "test_risk.db"
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
            ('v9-GBPUSD-M15-100-1', 'haussiere', 1, 10.0, 'A,B', '2026-01-07T10:00:00'),
            ('v9-GBPUSD-M15-100-2', 'haussiere', 0, -5.0, 'A,B', '2026-01-07T10:00:00');
        INSERT INTO forces_snapshots VALUES
            ('v9-GBPUSD-M15-100-1', '2026-01-07T10:00:00+00:00', 'GBPUSD'),
            ('v9-GBPUSD-M15-100-2', '2026-01-07T10:00:00+00:00', 'GBPUSD');
        INSERT INTO regime_snapshots VALUES
            ('v9-GBPUSD-M15-100-1', 'CASSURE', '2026-01-07T10:00:00+00:00'),
            ('v9-GBPUSD-M15-100-2', 'CASSURE', '2026-01-07T10:00:00+00:00');
    """)
    con.commit()
    con.close()

    output = tmp_path / "out.json"
    report = tmp_path / "report.md"
    rc = main(db_path=db_path, output=output, report=report)
    assert rc == 0
    assert output.exists()
    assert report.exists()
    # JSON contient total_n=2
    import json
    d = json.loads(output.read_text(encoding="utf-8"))
    assert d["total_n"] == 2
    assert d["total_pnl"] == 5.0