"""Test du backtest BearPerception (Tâche 5).

Mission baissier 2/2. Vérifie que scripts/v9_resolve_with_bear_perception.py
s'exécute sans erreur sur une DB minimale et produit des métriques cohérentes.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.v9_resolve_with_bear_perception import run_backtest


def _build_db() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT, snapshot_id TEXT, symbol TEXT, timeframe TEXT,
            direction TEXT, confiance INTEGER, timestamp TEXT
        );
        CREATE TABLE paper_trades (
            trade_id TEXT, snapshot_id TEXT, direction TEXT, opened_at TEXT,
            pips_simulated REAL, is_win INTEGER, closed_at TEXT
        );
        CREATE TABLE signals (
            snapshot_id TEXT, tp_pips_recommended REAL, sl_pips_recommended REAL,
            exit_strategy_recommended TEXT
        );
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, symbol TEXT, timeframe TEXT,
            bar_time INTEGER, open REAL, high REAL, low REAL, close REAL, mid REAL,
            tick_volume INTEGER, stale INTEGER DEFAULT 0
        );
        """
    )
    base_epoch = 1784300000
    # 3 baissiers GBPUSD clôturés.
    for i in range(3):
        snap = f"v9-GBPUSD-M15-{base_epoch + i}-r{i}"
        conn.execute(
            "INSERT INTO decisions VALUES (?, ?, 'GBPUSD', 'M15', 'baissiere', 70, "
            "'2026-07-18T00:00:00+00:00')",
            (f"dec_r{i}", snap),
        )
        conn.execute(
            "INSERT INTO paper_trades VALUES (?, ?, 'baissiere', "
            "'2026-07-18T00:00:00+00:00', ?, ?, '2026-07-18T02:00:00+00:00')",
            (f"tr{i}", snap, -5.0 if i % 2 == 0 else 6.0, 0 if i % 2 == 0 else 1),
        )
        conn.execute(
            "INSERT INTO signals VALUES (?, 8.0, 15.0, 'TP_SL')", (snap,),
        )
    # Prix futurs M5 (après opened_at) — tendance haussière → baissier perd.
    for i in range(30):
        conn.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, bar_time, "
            "open, high, low, close, mid, tick_volume, stale) "
            "VALUES (?, 'GBPUSD', 'M5', ?, ?, ?, ?, ?, ?, 100, 0)",
            (
                f"v9-GBPUSD-M5-{i}",
                # opened_at 2026-07-18T00:00 → epoch ~1784332800 ; on met après.
                1784332800 + (i + 1) * 300,
                1.34 + i * 0.0002, 1.34 + i * 0.0002 + 0.0001,
                1.34 + i * 0.0002 - 0.0001, 1.34 + i * 0.0002, 1.34 + i * 0.0002,
            ),
        )
    # Quelques M1 pour detect_fast_movement.
    for i in range(10):
        conn.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, bar_time, "
            "open, high, low, close, mid, tick_volume, stale) "
            "VALUES (?, 'GBPUSD', 'M1', ?, ?, ?, ?, ?, ?, 100, 0)",
            (
                f"v9-GBPUSD-M1-{i}", 1784332800 + i * 60,
                1.34, 1.3401, 1.3399, 1.34 - i * 0.00025, 1.34 - i * 0.00025,
            ),
        )
    conn.commit()
    conn.close()
    return path


def test_resolve_with_bear_perception_runs_without_error() -> None:
    """run_backtest ne lève pas et retourne des métriques cohérentes."""
    path = _build_db()
    try:
        metrics = run_backtest(db_path=path, write=False)
        assert isinstance(metrics, dict)
        # Clés attendues présentes.
        for key in (
            "win_rate_original", "win_rate_corrected",
            "avg_pips_original", "avg_pips_corrected",
            "would_skip_count", "estimated_savings_pips", "n_baissier_seen",
        ):
            assert key in metrics
        # 3 baissiers vus.
        assert metrics["n_baissier_seen"] == 3
        # Taux bornés [0, 100].
        assert 0.0 <= metrics["win_rate_original"] <= 100.0
        assert 0.0 <= metrics["win_rate_corrected"] <= 100.0
        # would_skip_count borné par le nombre de trades.
        assert 0 <= metrics["would_skip_count"] <= 3
    finally:
        path.unlink(missing_ok=True)


def test_resolve_writes_json_output(monkeypatch) -> None:
    """Avec write=True, le JSON de rapport est produit (chemin retourné).

    OUTPUT_PATH est redirigé vers un fichier temporaire pour NE PAS écraser
    l'artefact réel data/strategy_pole/bear_perception_backtest.json.
    """
    import scripts.v9_resolve_with_bear_perception as mod

    out_tmp = Path(tempfile.mkdtemp()) / "bt_out.json"
    monkeypatch.setattr(mod, "OUTPUT_PATH", out_tmp)
    path = _build_db()
    try:
        metrics = run_backtest(db_path=path, write=True)
        assert metrics.get("output_path") == str(out_tmp)
        assert out_tmp.exists()
    finally:
        path.unlink(missing_ok=True)
        out_tmp.unlink(missing_ok=True)
