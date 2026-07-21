"""tests/test_v9_brier_dashboard.py — Tests du dashboard Brier live.

Doctrine : R7 (tests verts), R8 (traçabilité), R22 (CLI lecture seule).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_brier_dashboard import (  # noqa: E402
    base_rate,
    compute_brier,
    fetch_decisions,
    find_over_under_confident,
    main,
    reliability_table,
    render_text,
)


@pytest.fixture
def temp_db():
    """Crée une DB temporaire avec table decisions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            confiance INTEGER,
            is_win INTEGER,
            resolution_strategy TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


def _insert(conn, conf, win, strategy="DYNAMIC"):
    conn.execute(
        "INSERT INTO decisions (timestamp, confiance, is_win, resolution_strategy) "
        "VALUES (datetime('now', '-1 day'), ?, ?, ?)",
        (conf, win, strategy),
    )


def test_compute_brier_perfect():
    """Prédictions parfaites → Brier = 0."""
    decisions = [
        {"confiance": 100, "is_win": True},
        {"confiance": 0, "is_win": False},
        {"confiance": 100, "is_win": True},
    ]
    assert compute_brier(decisions) == 0.0


def test_compute_brier_random():
    """Prédictions à 0.5 sur résultats binaires → Brier = 0.25."""
    decisions = [
        {"confiance": 50, "is_win": True},
        {"confiance": 50, "is_win": False},
    ]
    assert abs(compute_brier(decisions) - 0.25) < 1e-9


def test_compute_brier_over_confident():
    """Conf 100 toujours win 0 → Brier = 1.0 (pire que l'aléatoire)."""
    decisions = [
        {"confiance": 100, "is_win": False},
        {"confiance": 100, "is_win": False},
    ]
    assert compute_brier(decisions) == 1.0


def test_compute_brier_empty():
    """Aucune décision → NaN."""
    import math
    assert math.isnan(compute_brier([]))


def test_base_rate():
    """WR observé = base_rate."""
    decisions = [
        {"confiance": 80, "is_win": True},
        {"confiance": 80, "is_win": False},
        {"confiance": 80, "is_win": True},
        {"confiance": 80, "is_win": True},
    ]
    assert base_rate(decisions) == 0.75


def test_reliability_table_10_bins():
    """100 décisions → 10 bins."""
    decisions = [{"confiance": i, "is_win": i % 2 == 0} for i in range(100)]
    table = reliability_table(decisions, n_bins=10)
    assert len(table) == 10
    # Tri par confiance croissante
    confs = [int(row["bin"].split("-")[0].strip("[")) for row in table]
    assert confs == sorted(confs)


def test_reliability_table_too_few():
    """Moins de 10 décisions → table vide."""
    decisions = [{"confiance": 80, "is_win": True}]
    table = reliability_table(decisions, n_bins=10)
    assert table == []


def test_find_over_under_confident():
    """Top buckets sur/sous-confiants correctement triés."""
    table = [
        {"bin": "[80-90]", "n": 10, "pred": 0.85, "obs_wr": 0.50, "gap": -0.35},
        {"bin": "[90-100]", "n": 10, "pred": 0.95, "obs_wr": 0.90, "gap": -0.05},
        {"bin": "[60-70]", "n": 10, "pred": 0.65, "obs_wr": 0.75, "gap": +0.10},
    ]
    over, under = find_over_under_confident(table)
    assert over[0]["bin"] == "[80-90]"  # gap le plus négatif
    assert under[0]["bin"] == "[60-70]"  # gap le plus positif


def test_render_text_includes_brier():
    """Le rendu texte contient les éléments clés."""
    report = {
        "window_days": 7,
        "n_decisions": 100,
        "brier_score": 0.35,
        "brier_qualitative": "🔴 MAUVAIS",
        "base_rate": 0.50,
        "reliability_table": [
            {"bin": "[80-90]", "n": 10, "pred": 0.85, "obs_wr": 0.50, "gap": -0.35},
        ],
        "over_confident": [],
        "under_confident": [],
        "recommendation": "Sizer=0",
    }
    text = render_text(report)
    assert "Brier score" in text
    assert "0.3500" in text
    assert "🔴" in text


def test_fetch_decisions_empty(temp_db):
    """DB vide → liste vide."""
    with pytest.MonkeyPatch.context() as mp:
        from scripts import v9_brier_dashboard as mod
        mp.setattr(mod, "DB_PATH", temp_db)
        assert fetch_decisions(7) == []


def test_fetch_decisions_filters_strategy(temp_db):
    """Filtre resolution_strategy = DYNAMIC uniquement (et min_n=5)."""
    from unittest.mock import patch
    conn = sqlite3.connect(str(temp_db))
    # 5 DYNAMIC (passé le filtre min_n) + 1 SKIPPED + 1 TP_SL
    for i in range(5):
        _insert(conn, 80, 1, "DYNAMIC")
    _insert(conn, 90, 0, "SKIPPED")  # Exclu
    _insert(conn, 70, 1, "TP_SL")    # Exclu
    conn.commit()
    conn.close()

    with patch("scripts.v9_brier_dashboard.DB_PATH", temp_db):
        decisions = fetch_decisions(7)
    assert len(decisions) == 5
    assert all(d["confiance"] == 80 for d in decisions)


def test_main_runs_without_error(temp_db, capsys):
    """CLI main() doit tourner sans crash même si DB est vide."""
    from unittest.mock import patch
    conn = sqlite3.connect(str(temp_db))
    conn.execute(
        "INSERT INTO decisions VALUES (1, datetime('now', '-1 day'), 80, 1, 'DYNAMIC')"
    )
    conn.commit()
    conn.close()

    with patch("scripts.v9_brier_dashboard.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog"]):
            rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Brier Dashboard" in captured.out


def test_main_json_output(temp_db, capsys):
    """CLI --json doit produire un JSON parsable."""
    from unittest.mock import patch
    conn = sqlite3.connect(str(temp_db))
    for i in range(20):
        _insert(conn, 70 + i, 1 if i % 2 == 0 else 0, "DYNAMIC")
    conn.commit()
    conn.close()

    test_argv = ["prog", "--json", "--window-days", "7"]
    with patch("scripts.v9_brier_dashboard.DB_PATH", temp_db):
        with patch.object(sys, "argv", test_argv):
            rc = main()

    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "brier_score" in data
    assert "n_decisions" in data
    assert data["n_decisions"] == 20
