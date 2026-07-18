"""Tests — validation walk-forward (core/v9/walk_forward.py).

Vérifie :
  - découpe en fenêtres contiguës + calibration in-sample / test out-of-sample
  - verdict EDGE_REEL quand l'edge tient hors-échantillon
  - verdict OVERFITTING quand l'edge s'effondre sur le futur
  - DONNEES_INSUFFISANTES sous le plancher de trades
  - le rendu Markdown contient le verdict et le caveat de provenance
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.walk_forward import (
    WalkForwardValidator,
    render_markdown,
    MIN_INSAMPLE_TRADES,
    MIN_OOS_TRADES,
)


def _seed_db(tmp_path: Path, rows: list[tuple[str, int, float, int]]) -> Path:
    """Crée une DB avec une table decisions minimale.

    rows : (timestamp, confiance, resolution_pips, is_win)
    """
    db = tmp_path / "wf_test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE decisions (
            decision_id TEXT, timestamp TEXT, snapshot_id TEXT, symbol TEXT,
            confiance INTEGER, resolution_pips REAL, is_win INTEGER
        )
    """)
    for i, (ts, conf, pips, win) in enumerate(rows):
        conn.execute(
            "INSERT INTO decisions (decision_id, timestamp, snapshot_id, symbol, "
            "confiance, resolution_pips, is_win) VALUES (?,?,?,?,?,?,?)",
            (f"d{i}", ts, f"snap{i}", "GBPUSD", conf, pips, win),
        )
    conn.commit()
    conn.close()
    return db


def _ts(i: int) -> str:
    """Timestamp STRICTEMENT croissant (ordre lexicographique == ordre i).

    Encode i dans le champ microsecondes (i < 1e6) : garantit que trier par
    la chaîne préserve exactement l'ordre temporel des trades — condition
    nécessaire pour que la structure passé/futur du test soit respectée.
    """
    return f"2026-07-06T00:00:00.{i:06d}+00:00"


def test_insufficient_data_verdict(tmp_path: Path):
    """Trop peu de trades → DONNEES_INSUFFISANTES."""
    rows = [(_ts(i), 80, 5.0, 1) for i in range(10)]
    db = _seed_db(tmp_path, rows)
    report = WalkForwardValidator(db_path=db).run(n_windows=5)
    assert report.verdict == "DONNEES_INSUFFISANTES"


def test_edge_reel_when_high_confidence_persists(tmp_path: Path):
    """Un edge stable (haute confiance = gain) sur tout l'historique → EDGE_REEL.

    On construit un signal séparable : confiance>=80 → +8 pips (gagnant),
    confiance<80 → -5 pips (perdant). Le seuil calibré in-sample (≥80) doit
    tenir out-of-sample.
    """
    rows = []
    n = 600
    for i in range(n):
        if i % 2 == 0:
            rows.append((_ts(i), 85, 8.0, 1))   # haute conf → gagnant
        else:
            rows.append((_ts(i), 60, -5.0, 0))  # basse conf → perdant
    # tri stable par index (timestamps déjà croissants par i)
    rows.sort(key=lambda r: r[0])
    db = _seed_db(tmp_path, rows)
    report = WalkForwardValidator(db_path=db).run(n_windows=5)
    assert report.n_trades == n
    assert report.mean_oos_expectancy > 0
    assert report.verdict in ("EDGE_REEL", "EDGE_REEL_DEGRADE")
    # le seuil calibré doit filtrer les perdants (≥ un seuil > 60)
    assert all(f.threshold >= 65 for f in report.folds)


def test_overfitting_when_edge_collapses(tmp_path: Path):
    """L'edge in-sample disparaît out-of-sample → OVERFITTING.

    Première moitié : haute confiance gagnante. Seconde moitié (le futur) :
    la même haute confiance devient perdante. Le seuil calibré sur le passé
    ne survit pas → expectancy OOS négative.
    """
    rows = []
    n = 600
    for i in range(n):
        first_half = i < n // 2
        conf = 85 if i % 2 == 0 else 60
        if conf == 85:
            pips = 8.0 if first_half else -8.0
            win = 1 if first_half else 0
        else:
            pips = -5.0
            win = 0
        rows.append((_ts(i), conf, pips, win))
    rows.sort(key=lambda r: r[0])
    db = _seed_db(tmp_path, rows)
    report = WalkForwardValidator(db_path=db).run(n_windows=5)
    assert report.mean_oos_expectancy < 0
    assert report.verdict == "OVERFITTING"


def test_render_markdown_contains_verdict_and_caveat(tmp_path: Path):
    rows = [(_ts(i), 85 if i % 2 == 0 else 60,
             8.0 if i % 2 == 0 else -5.0, 1 if i % 2 == 0 else 0)
            for i in range(600)]
    rows.sort(key=lambda r: r[0])
    db = _seed_db(tmp_path, rows)
    report = WalkForwardValidator(db_path=db).run(n_windows=5)
    md = render_markdown(report, generated_at="2026-07-18T00:00:00+00:00")
    assert "Walk-Forward Validation" in md
    assert report.verdict in md or "EDGE" in md
    # le caveat de provenance doit toujours être présent (honnêteté données)
    assert "Provenance des données" in md
    assert "resolution_pips" in md
