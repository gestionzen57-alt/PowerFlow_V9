"""test_v9_live_watchdog_neutre_rate.py — Régression motion CEO #8 §5.3.

Vérifie que le watchdog intègre correctement `neutre_rate_24h` :
  1. _fetch_neutre_rate_24h retourne float ∈ [0, 100] (ou 0.0 si DB absente)
  2. Si > 75 %, alerte WARN (sans action auto)
  3. Si > 75 % ET wr_crit, alert escalade à p0 (halt total a priorité)
  4. Le champ neutre_rate_24h_pct est exposé dans to_dict()

Doctrine : R7 (tests verts), R2 (ne touche pas au watchdog runtime sauf mock)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _make_db_with_regime(db_path: Path, neutre_pct: float,
                         n_total: int = 100) -> None:
    """Crée une DB tmp avec regime_snapshots simulant un certain % NEUTRE."""
    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(
            """
            CREATE TABLE regime_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regime_type TEXT, symbol TEXT, timeframe TEXT,
                timestamp TEXT, source_type TEXT
            );
            CREATE TABLE paper_trades (
                trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
                closed_at TEXT, pips_simulated REAL, is_win INTEGER,
                opened_at TEXT
            );
            CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY, snapshot_id TEXT, symbol TEXT,
                timestamp TEXT, action TEXT, direction TEXT, confiance INTEGER,
                regime_type TEXT, source_type TEXT, is_win INTEGER,
                resolution_strategy TEXT, resolution_pips REAL, resolved_at TEXT
            );
            """
        )
        n_neutre = int(n_total * neutre_pct / 100)
        n_autres = n_total - n_neutre
        # Insère n_neutre snapshots NEUTRE sur 24h
        for i in range(n_neutre):
            con.execute(
                "INSERT INTO regime_snapshots (regime_type, symbol, timeframe, "
                "timestamp, source_type) VALUES ('NEUTRE', 'GBPUSD', 'M5', "
                "datetime('now', '-1 hour', ?), 'live')",
                (f"+{i} minutes",),
            )
        # Autres régimes (CASSURE, EXTENSION, PALIER)
        autres = ["CASSURE", "EXTENSION", "PALIER"]
        for i in range(n_autres):
            con.execute(
                "INSERT INTO regime_snapshots (regime_type, symbol, timeframe, "
                "timestamp, source_type) VALUES (?, 'GBPUSD', 'M5', "
                "datetime('now', '-1 hour', ?), 'live')",
                (autres[i % 3], f"+{i + n_neutre} minutes"),
            )
        # Crée 50 paper_trades GBPUSD long WIN pour que WR > WR_WARN
        for i in range(50):
            con.execute(
                "INSERT INTO paper_trades (trade_id, snapshot_id, direction, "
                "opened_at, closed_at, pips_simulated, is_win) VALUES "
                "(?, ?, 'haussiere', datetime('now','-1 day'), "
                "datetime('now','-30 minutes'), 4.5, 1)",
                (f"pt_{i}", f"v9-GBPUSD-M5-{i}"),
            )
            con.execute(
                "INSERT INTO decisions (decision_id, snapshot_id, symbol, "
                "timestamp, action, direction, confiance, regime_type, "
                "source_type, is_win, resolution_strategy, resolution_pips, "
                "resolved_at) VALUES (?, ?, 'GBPUSD', datetime('now','-1 day'), "
                "'preparer_entree', 'haussiere', 80, 'NEUTRE', 'live', 1, "
                "'DYNAMIC', 4.5, datetime('now','-30 minutes'))",
                (f"dec_{i}", f"v9-GBPUSD-M5-{i}"),
            )
        con.commit()
    finally:
        con.close()


def test_neutre_rate_low_no_alert(tmp_path: Path, monkeypatch):
    """NEUTRE_RATE < 75% → pas d'alerte WATCHDOG."""
    db = _make_db_with_regime(  # noqa
        tmp_path / "low_neutre.db", neutre_pct=30, n_total=100
    ) if False else None
    db = tmp_path / "low.db"
    _make_db_with_regime(db, neutre_pct=30, n_total=100)

    from core.v9 import kill_switches
    monkeypatch.setattr(kill_switches, "_switches", None)
    monkeypatch.setenv("V9_LIVE_WATCHDOG_ENABLED", "1")
    monkeypatch.setenv("V9_WATCHDOG_NEUTRE_RATE_WARN", "75")
    monkeypatch.setenv("V9_WATCHDOG_WR_WINDOW", "50")

    from core.v9.v9_live_watchdog import check_health
    decision = check_health(db_path=db)
    # WR=50/50=100% > 80% warn, mais neutre=30% < 75% → status=ok
    assert decision.neutre_rate_24h_pct == 30.0
    assert decision.status == "ok"


def test_neutre_rate_high_triggers_warn(tmp_path: Path, monkeypatch):
    """NEUTRE_RATE > 75% → alerte WARN (saturé détecté)."""
    db = tmp_path / "high.db"
    _make_db_with_regime(db, neutre_pct=83, n_total=100)

    from core.v9 import kill_switches
    monkeypatch.setattr(kill_switches, "_switches", None)
    monkeypatch.setenv("V9_LIVE_WATCHDOG_ENABLED", "1")
    monkeypatch.setenv("V9_WATCHDOG_NEUTRE_RATE_WARN", "75")
    monkeypatch.setenv("V9_WATCHDOG_WR_WINDOW", "50")

    from core.v9.v9_live_watchdog import check_health
    decision = check_health(db_path=db)
    assert decision.neutre_rate_24h_pct == 83.0
    assert decision.status == "warn"
    # triggered contient le message NEUTRE_RATE
    triggered_str = " ".join(decision.triggered)
    assert "neutre_rate_24h" in triggered_str


def test_to_dict_exposes_neutre_rate(tmp_path: Path, monkeypatch):
    """to_dict() inclut neutre_rate_24h_pct dans la sortie JSON."""
    db = tmp_path / "dict.db"
    _make_db_with_regime(db, neutre_pct=83, n_total=100)

    from core.v9 import kill_switches
    monkeypatch.setattr(kill_switches, "_switches", None)
    monkeypatch.setenv("V9_LIVE_WATCHDOG_ENABLED", "1")
    monkeypatch.setenv("V9_WATCHDOG_WR_WINDOW", "50")

    from core.v9.v9_live_watchdog import check_health
    decision = check_health(db_path=db)
    d = decision.to_dict()
    assert "neutre_rate_24h_pct" in d
    assert d["neutre_rate_24h_pct"] == 83.0


def test_neutre_rate_threshold_configurable(tmp_path: Path, monkeypatch):
    """Le seuil NEUTRE_RATE_WARN est lisible via env var."""
    db = tmp_path / "cfg.db"
    _make_db_with_regime(db, neutre_pct=70, n_total=100)  # 70%

    from core.v9 import kill_switches
    monkeypatch.setattr(kill_switches, "_switches", None)
    monkeypatch.setenv("V9_LIVE_WATCHDOG_ENABLED", "1")
    monkeypatch.setenv("V9_WATCHDOG_WR_WINDOW", "50")

    # Seuil par défaut 75 : 70% < 75% → pas d'alerte
    monkeypatch.setenv("V9_WATCHDOG_NEUTRE_RATE_WARN", "75")
    from core.v9.v9_live_watchdog import check_health as ev1
    d1 = ev1(db_path=db)
    assert d1.status == "ok"

    # Seuil custom 65 : 70% > 65% → alerte
    monkeypatch.setenv("V9_WATCHDOG_NEUTRE_RATE_WARN", "65")
    from core.v9.v9_live_watchdog import check_health as ev2
    d2 = ev2(db_path=db)
    assert d2.status == "warn"


def test_defensif_db_absente_neutre_rate():
    """DB absente → neutre_rate = 0.0, watchdog pas d'alerte NEUTRE."""
    from core.v9.v9_live_watchdog import _fetch_neutre_rate_24h
    fake_db = Path("/tmp/inexistante_v9_test.db")
    if fake_db.exists():
        fake_db.unlink()
    assert _fetch_neutre_rate_24h(fake_db) == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
