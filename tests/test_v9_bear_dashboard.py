"""Tests des calculs dashboard baissier (Tâche 3).

Mission baissier 2/2. On teste le module PUR `core.v9.v9_bear_dashboard`
(sqlite3, sans FastAPI) qui alimente les endpoints /api/bear-stats et
/api/currency-bias-matrix. La couche FastAPI n'étant que de fins wrappers,
ces tests couvrent toute la logique métier.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9.v9_bear_dashboard import bear_stats, currency_bias_matrix


def _build_db() -> Path:
    """DB temp avec decisions + paper_trades : GBPUSD baissier perdant,
    haussier gagnant, + une décision polluée sur devise tierce (EUR)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT, snapshot_id TEXT, symbol TEXT, currency TEXT,
            direction TEXT, timestamp TEXT
        );
        CREATE TABLE paper_trades (
            trade_id TEXT, snapshot_id TEXT, direction TEXT,
            pips_simulated REAL, is_win INTEGER, closed_at TEXT
        );
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, symbol TEXT,
            timeframe TEXT, bar_time INTEGER, close REAL, stale INTEGER DEFAULT 0
        );
        """
    )
    # 5 baissiers GBPUSD, tous perdants (-5 pips) → WR 0%.
    # 4 haussiers GBPUSD, tous gagnants (+8 pips) → WR 100%.
    for i in range(5):
        snap = f"v9-GBPUSD-M15-{1000 + i}-bd"
        conn.execute("INSERT INTO decisions VALUES (?, ?, 'GBPUSD', 'GBP', "
                     "'baissiere', '2026-07-18T00:00:00+00:00')",
                     (f"dec_b{i}", snap))
        conn.execute("INSERT INTO paper_trades VALUES (?, ?, 'baissiere', "
                     "-5.0, 0, '2026-07-18T01:00:00+00:00')",
                     (f"tb{i}", snap))
    for i in range(4):
        snap = f"v9-GBPUSD-M15-{2000 + i}-bd"
        conn.execute("INSERT INTO decisions VALUES (?, ?, 'GBPUSD', 'USD', "
                     "'haussiere', '2026-07-18T00:00:00+00:00')",
                     (f"dec_h{i}", snap))
        conn.execute("INSERT INTO paper_trades VALUES (?, ?, 'haussiere', "
                     "8.0, 1, '2026-07-18T01:00:00+00:00')",
                     (f"th{i}", snap))
    # Décision polluée : GBPUSD sur devise tierce EUR (non constitutive).
    conn.execute("INSERT INTO decisions VALUES ('dec_poll', 'v9-GBPUSD-M15-3000-bd', "
                 "'GBPUSD', 'EUR', 'baissiere', '2026-07-18T00:00:00+00:00')")
    # Quelques closes M5 pour le drift (hausse → drift positif).
    for i in range(10):
        conn.execute("INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, "
                     "bar_time, close, stale) VALUES (?, 'GBPUSD', 'M5', ?, ?, 0)",
                     (f"v9-GBPUSD-M5-{i}", 1784300000 + i * 300, 1.34000 + i * 0.0001))
    conn.commit()
    conn.close()
    return path


def test_dashboard_api_bear_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    """bear_stats calcule WR baissier/haussier, would_skip, drift, reco."""
    monkeypatch.delenv("V9_BEAR_PERCEPTION_ENABLED", raising=False)
    path = _build_db()
    try:
        stats = bear_stats(path, "GBPUSD")
        assert stats["symbol"] == "GBPUSD"
        assert stats["baissier_n"] == 5
        assert stats["haussier_n"] == 4
        assert stats["baissier_wr_pct"] == 0.0
        assert stats["haussier_wr_pct"] == 100.0
        # would_skip = tous les baissiers ; saved = pips nets baissiers (-25).
        assert stats["would_skip_count"] == 5
        assert stats["would_skip_saved_pips"] == -25.0
        # drift positif (closes M5 en hausse).
        assert stats["drift_pips_per_day"] is not None
        assert stats["drift_pips_per_day"] > 0
        assert stats["bear_perception_enabled"] is False
        # WR baissier 0% + haussier 100% → recommandation act_fix.
        assert stats["recommandation"] == "act_fix"
    finally:
        path.unlink(missing_ok=True)


def test_dashboard_bear_stats_enabled_reco(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si le kill switch est ON, la reco passe à monitor_fix (déjà en action)."""
    monkeypatch.setenv("V9_BEAR_PERCEPTION_ENABLED", "1")
    path = _build_db()
    try:
        stats = bear_stats(path, "GBPUSD")
        assert stats["bear_perception_enabled"] is True
        assert stats["recommandation"] == "monitor_fix"
    finally:
        path.unlink(missing_ok=True)


def test_dashboard_currency_bias_matrix() -> None:
    """La matrice expose le ratio constitutif et marque la devise tierce."""
    path = _build_db()
    try:
        result = currency_bias_matrix(path)
        entries = {e["symbol"]: e for e in result["matrix"]}
        assert "GBPUSD" in entries
        gbp = entries["GBPUSD"]
        # 5 GBP + 4 USD (constitutifs) + 1 EUR (tiers) = 10 décisions.
        assert gbp["total_decisions"] == 10
        # ratio constitutif = 9/10 = 90%.
        assert gbp["constitutive_ratio_pct"] == 90.0
        # EUR marquée non constitutive.
        eur = next(c for c in gbp["currencies"] if c["currency"] == "EUR")
        assert eur["constitutive"] is False
        gbp_c = next(c for c in gbp["currencies"] if c["currency"] == "GBP")
        assert gbp_c["constitutive"] is True
    finally:
        path.unlink(missing_ok=True)


def test_dashboard_bear_stats_empty_db_is_safe() -> None:
    """DB vide → aucune exception, recommandation insufficient_data (R6)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE decisions (snapshot_id TEXT, symbol TEXT, currency TEXT, direction TEXT);"
        "CREATE TABLE paper_trades (snapshot_id TEXT, direction TEXT, "
        "pips_simulated REAL, is_win INTEGER, closed_at TEXT);"
        "CREATE TABLE forces_snapshots (snapshot_id TEXT, symbol TEXT, "
        "timeframe TEXT, bar_time INTEGER, close REAL, stale INTEGER);"
    )
    conn.commit()
    conn.close()
    try:
        stats = bear_stats(path, "GBPUSD")
        assert stats["baissier_n"] == 0
        assert stats["recommandation"] == "insufficient_data"
        matrix = currency_bias_matrix(path)
        assert matrix["matrix"] == []
    finally:
        path.unlink(missing_ok=True)
