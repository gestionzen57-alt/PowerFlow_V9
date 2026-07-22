"""tests/test_v9_time_windows.py — Tests du module _time_windows + livrables refonte.

Couvre :
- core/v9/_time_windows.py (sessions, split today/yesterday/24h, intraday)
- scripts/v9_health_one_liner.py (refonte multi-lignes)
- scripts/v9_market_brief.py (sections jour/hier/24h)
- scripts/v9_dashboard_today.py (dashboard quotidien)

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R8 (traçabilité), R6 (défensif).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9._time_windows import (  # noqa: E402
    get_session_now,
    get_session_full_label,
    get_today_yesterday_split,
    get_24h_rolling,
    get_intraday_by_session,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def temp_db():
    """Crée une DB temporaire avec le schéma decisions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            regime_type TEXT,
            confiance INTEGER,
            is_win INTEGER,
            resolution_pips REAL,
            resolution_strategy TEXT,
            principes_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            cvd_delta INTEGER,
            cvd_cumul INTEGER,
            direction TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            opened_at TEXT,
            is_win INTEGER,
            pips_simulated REAL
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


def _insert_decision(conn, ts, symbol="EURUSD", is_win=1, pips=5.0,
                     strategy="DYNAMIC", confiance=80):
    conn.execute(
        "INSERT INTO decisions (timestamp, symbol, is_win, resolution_pips, "
        "resolution_strategy, confiance) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, symbol, is_win, pips, strategy, confiance),
    )


# ── Tests get_session_now ──────────────────────────────────────────────────

class TestGetSessionNow:
    def test_asie(self):
        dt = datetime(2026, 7, 22, 3, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "ASIE"

    def test_londres(self):
        dt = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "LONDRES"

    def test_overlap(self):
        dt = datetime(2026, 7, 22, 14, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "OVERLAP"

    def test_new_york(self):
        dt = datetime(2026, 7, 22, 18, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "NEW_YORK"

    def test_after_hours(self):
        dt = datetime(2026, 7, 22, 23, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "AFTER_HOURS"

    def test_boundary_asie_londres(self):
        """07:00 UTC = frontière → LONDRES."""
        dt = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "LONDRES"

    def test_boundary_londres_overlap(self):
        """12:00 UTC = frontière → OVERLAP."""
        dt = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        assert get_session_now(dt) == "OVERLAP"

    def test_default_now(self):
        """Sans argument → utilise maintenant (pas d'exception)."""
        result = get_session_now()
        assert result in ("ASIE", "LONDRES", "OVERLAP", "NEW_YORK", "AFTER_HOURS")


# ── Tests get_session_full_label ───────────────────────────────────────────

class TestGetSessionFullLabel:
    def test_asie_label(self):
        label = get_session_full_label("ASIE")
        assert "ASIE" in label
        assert "00-07" in label

    def test_londres_label(self):
        label = get_session_full_label("LONDRES")
        assert "LONDRES" in label
        assert "07-12" in label

    def test_unknown_session(self):
        label = get_session_full_label("UNKNOWN")
        assert label == "UNKNOWN"


# ── Tests get_today_yesterday_split ─────────────────────────────────────────

class TestGetTodayYesterdaySplit:
    def test_db_absente(self):
        """DB inexistante → error + structure vide."""
        result = get_today_yesterday_split(Path("/nonexistent.db"))
        assert "error" in result
        assert result["today"]["n"] == 0
        assert result["yesterday"]["n"] == 0

    def test_split_today_yesterday(self, temp_db):
        """Insère decisions today + yesterday → split correct."""
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(str(temp_db))
        # Today: 3 trades (2 win, 1 loss), +10 pips
        for i, (iw, p) in enumerate([(1, 5.0), (1, 3.0), (0, -2.0)]):
            ts = (now - timedelta(minutes=10 * (i + 1))).isoformat()
            _insert_decision(conn, ts, is_win=iw, pips=p)
        # Yesterday: 2 trades (1 win, 1 loss), -5 pips
        yesterday = now - timedelta(days=1, hours=2)
        _insert_decision(conn, yesterday.isoformat(), is_win=1, pips=10.0)
        _insert_decision(conn, (yesterday + timedelta(hours=1)).isoformat(),
                         is_win=0, pips=-15.0)
        conn.commit()
        conn.close()

        result = get_today_yesterday_split(temp_db)
        assert "error" not in result
        assert result["today"]["n"] == 3
        assert result["today"]["wr_pct"] == pytest.approx(66.7, abs=0.1)
        assert result["today"]["pips"] == pytest.approx(6.0, abs=0.1)
        assert result["today"]["date"] is not None
        assert result["today"]["session_now"] in (
            "ASIE", "LONDRES", "OVERLAP", "NEW_YORK", "AFTER_HOURS"
        )
        assert result["yesterday"]["n"] == 2
        assert result["yesterday"]["wr_pct"] == pytest.approx(50.0, abs=0.1)
        assert result["yesterday"]["pips"] == pytest.approx(-5.0, abs=0.1)

    def test_today_zero_trades(self, temp_db):
        """Aucun trade aujourd'hui → n=0."""
        conn = sqlite3.connect(str(temp_db))
        # Only yesterday
        yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
        _insert_decision(conn, yesterday.isoformat(), is_win=1, pips=5.0)
        conn.commit()
        conn.close()

        result = get_today_yesterday_split(temp_db)
        assert result["today"]["n"] == 0
        assert result["today"]["wr_pct"] == 0.0
        assert result["yesterday"]["n"] == 1

    def test_filters_skipped(self, temp_db):
        """resolution_strategy='SKIPPED' est exclu."""
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(str(temp_db))
        _insert_decision(conn, (now - timedelta(minutes=5)).isoformat(),
                         is_win=0, pips=0.0, strategy="SKIPPED")
        _insert_decision(conn, (now - timedelta(minutes=10)).isoformat(),
                         is_win=1, pips=5.0, strategy="DYNAMIC")
        conn.commit()
        conn.close()

        result = get_today_yesterday_split(temp_db)
        assert result["today"]["n"] == 1  # Only DYNAMIC counted


# ── Tests get_24h_rolling ───────────────────────────────────────────────────

class TestGet24hRolling:
    def test_db_absente(self):
        result = get_24h_rolling(Path("/nonexistent.db"))
        assert "error" in result
        assert result["n"] == 0

    def test_rolling_window(self, temp_db):
        """Trades dans les 24h sont comptés, > 48h exclus."""
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(str(temp_db))
        # Within 24h
        _insert_decision(conn, (now - timedelta(hours=2)).isoformat(),
                         is_win=1, pips=10.0)
        _insert_decision(conn, (now - timedelta(hours=12)).isoformat(),
                         is_win=0, pips=-5.0)
        # Outside 24h (48h ago — different date, excluded by SQLite text comparison)
        _insert_decision(conn, (now - timedelta(hours=48)).isoformat(),
                         is_win=1, pips=100.0)
        conn.commit()
        conn.close()

        result = get_24h_rolling(temp_db)
        assert "error" not in result
        # 48h ago has a different date prefix → excluded by text comparison
        assert result["n"] == 2
        assert result["pips"] == pytest.approx(5.0, abs=0.1)


# ── Tests get_intraday_by_session ───────────────────────────────────────────

class TestGetIntradayBySession:
    def test_empty_db(self, temp_db):
        result = get_intraday_by_session(temp_db)
        assert result == []

    def test_sessions_traversed(self, temp_db):
        """Trades dans ASIE + LONDRES → 2 sessions triées chronologiquement."""
        now = datetime.now(timezone.utc)
        conn = sqlite3.connect(str(temp_db))
        # ASIE (03:00 UTC)
        ts_asie = now.replace(hour=3, minute=0, second=0, microsecond=0)
        _insert_decision(conn, ts_asie.isoformat(), is_win=1, pips=5.0)
        # LONDRES (09:00 UTC) — only insert if today is valid
        ts_london = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if ts_london <= now:
            _insert_decision(conn, ts_london.isoformat(), is_win=0, pips=-3.0)
        conn.commit()
        conn.close()

        result = get_intraday_by_session(temp_db)
        assert len(result) >= 1
        # Sessions triées chronologiquement
        sessions = [r["session"] for r in result]
        order = {"ASIE": 0, "LONDRES": 1, "OVERLAP": 2, "NEW_YORK": 3, "AFTER_HOURS": 4}
        for i in range(1, len(sessions)):
            assert order[sessions[i]] > order[sessions[i - 1]]


# ── Tests v9_health_one_liner (refonte) ─────────────────────────────────────

class TestHealthOneLiner:
    def test_render_multi_has_today_yesterday_24h(self):
        """La sortie multi-lignes contient les 3 sections."""
        from scripts.v9_health_one_liner import render_health_multi
        health = {
            "all_ok": False,
            "local_time": "09:00",
            "utc_time": "07:00",
            "utc_date": "22/07",
            "pipeline": {"port": 31685, "active": True},
            "snapshot": {"age_sec": 3, "exists": True},
            "snapshot_fresh": True,
            "cvd": {"n_alive": 6, "n_total": 6},
            "cvd_full": True,
            "crons": {"ready": 32},
            "git": {"local": "abc12345", "aligned": True},
            "paper_trades_wr": {"wr": 41.7},
            "brier_7j": {"brier": 0.4648},
            "brier_ok": False,
            "kill_switches": {"bayesian_on": 3, "bayesian_total": 3,
                              "dd_protector": False, "risk_parity": False,
                              "cycle_memory": False},
            "walk_forward": {"verdict": "EDGE_REEL", "oos_expectancy": 6.7,
                             "ratio": 1.06},
            "today": {"date": "2026-07-22", "n": 12, "wr_pct": 41.7,
                      "pips": -34.2, "session_now": "LONDRES"},
            "yesterday": {"date": "2026-07-21", "n": 243, "wr_pct": 43.2,
                          "pips": -357.0},
            "24h_rolling": {"n": 453, "wr_pct": 43.0, "pips": -836.8},
        }
        text = render_health_multi(health)
        assert "Aujourd'hui" in text
        assert "Hier" in text
        assert "24h" in text
        assert "DEGRADED" in text
        assert "LONDRES" in text
        assert "bayésiens" in text

    def test_render_multi_today_zero_trades(self):
        """0 trade aujourd'hui → message marché pas encore actif."""
        from scripts.v9_health_one_liner import render_health_multi
        health = {
            "all_ok": True,
            "local_time": "09:00",
            "utc_time": "07:00",
            "utc_date": "22/07",
            "pipeline": {"port": 31685, "active": True},
            "snapshot": {"age_sec": 3, "exists": True},
            "snapshot_fresh": True,
            "cvd": {"n_alive": 6, "n_total": 6},
            "cvd_full": True,
            "crons": {"ready": 32},
            "git": {"local": "abc", "aligned": True},
            "paper_trades_wr": {"wr": None},
            "brier_7j": {"brier": None},
            "brier_ok": True,
            "kill_switches": {"bayesian_on": 3, "bayesian_total": 3,
                              "dd_protector": False, "risk_parity": False,
                              "cycle_memory": False},
            "walk_forward": None,
            "today": {"date": "2026-07-22", "n": 0, "wr_pct": 0.0,
                      "pips": 0.0, "session_now": "ASIE"},
            "yesterday": {"date": "2026-07-21", "n": 0, "wr_pct": 0.0,
                          "pips": 0.0},
            "24h_rolling": {"n": 0, "wr_pct": 0.0, "pips": 0.0},
        }
        text = render_health_multi(health)
        assert "pas encore actif" in text or "pas de d" in text

    def test_render_oneliner_legacy(self):
        """Le format --oneliner fonctionne encore."""
        from scripts.v9_health_one_liner import render_one_liner
        health = {
            "all_ok": True,
            "pipeline": {"active": True},
            "snapshot": {"age_sec": 3},
            "snapshot_fresh": True,
            "cvd": {"n_alive": 6, "n_total": 6},
            "cvd_full": True,
            "crons": {"ready": 32},
            "git": {"local": "abc", "aligned": True},
            "paper_trades_wr": {"wr": 50.0},
            "brier_7j": {"brier": 0.15},
        }
        text = render_one_liner(health)
        assert "V9" in text
        assert "OK" in text


# ── Tests v9_market_brief (refonte) ─────────────────────────────────────────

class TestMarketBrief:
    def test_render_brief_has_sections(self):
        """Le brief contient les sections AUJOURD'HUI, HIER, 24H."""
        from scripts.v9_market_brief import render_brief
        stats = {
            "today": {"date": "2026-07-22", "n": 12, "wr_pct": 41.7,
                      "pips": -34.2, "session_now": "LONDRES"},
            "yesterday": {"date": "2026-07-21", "n": 243, "wr_pct": 43.2,
                          "pips": -357.0},
            "24h_rolling": {"n": 453, "wr_pct": 43.0, "pips": -836.8},
            "by_symbol": {
                "EURUSD": {"n": 33, "wr_pct": 33.3, "avg_pips": -1.12, "total_pips": -37.0},
            },
            "cvd_alive": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"],
            "cvd_total_pairs": 6,
            "brier_7j": 0.4648,
            "brier_n": 100,
        }
        text = render_brief(stats, 4)
        assert "AUJOURD'HUI" in text
        assert "HIER" in text
        assert "24H GLISSANTES" in text
        assert "BRIEF MARCHÉ" in text
        assert "Session" in text

    def test_render_brief_error(self):
        """DB error → message d'erreur."""
        from scripts.v9_market_brief import render_brief
        stats = {"error": "DB absente"}
        text = render_brief(stats, 4)
        assert "DB absente" in text

    def test_render_brief_today_zero(self):
        """0 trade aujourd'hui → message marché pas encore actif."""
        from scripts.v9_market_brief import render_brief
        stats = {
            "today": {"date": "2026-07-22", "n": 0, "wr_pct": 0.0,
                      "pips": 0.0, "session_now": "ASIE"},
            "yesterday": {"date": "2026-07-21", "n": 100, "wr_pct": 50.0,
                          "pips": 10.0},
            "24h_rolling": {"n": 50, "wr_pct": 40.0, "pips": -20.0},
            "by_symbol": {},
            "cvd_alive": [],
            "cvd_total_pairs": 6,
            "brier_7j": None,
            "brier_n": 0,
        }
        text = render_brief(stats, 4)
        assert "pas encore actif" in text or "pas de d" in text

    def test_detect_alerts_brier_critical(self):
        """Brier > 0.40 → alerte critique."""
        from scripts.v9_market_brief import detect_alerts
        stats = {
            "by_symbol": {},
            "cvd_alive": ["EURUSD"] * 6,
            "cvd_total_pairs": 6,
            "brier_7j": 0.45,
            "brier_n": 100,
            "24h_rolling": {"n": 10, "pips": 0.0},
        }
        alerts = detect_alerts(stats, 4)
        assert any("Brier" in a for a in alerts)

    def test_detect_alerts_24h_negative(self):
        """24h < -100 pips → alerte perte."""
        from scripts.v9_market_brief import detect_alerts
        stats = {
            "by_symbol": {},
            "cvd_alive": ["EURUSD"] * 6,
            "cvd_total_pairs": 6,
            "brier_7j": 0.15,
            "brier_n": 100,
            "24h_rolling": {"n": 50, "pips": -200.0},
        }
        alerts = detect_alerts(stats, 4)
        assert any("Pertes 24h" in a for a in alerts)


# ── Tests v9_dashboard_today ────────────────────────────────────────────────

class TestDashboardToday:
    def test_render_dashboard_has_sections(self):
        """Le dashboard contient les sections attendues."""
        from scripts.v9_dashboard_today import render_dashboard
        dash = {
            "paris_time": "09:00",
            "utc_time": "07:00",
            "utc_date": "22/07/2026",
            "session": "LONDRES",
            "today": {"n": 12, "wr_pct": 41.7, "pips": -34.2,
                      "date": "2026-07-22", "session_now": "LONDRES"},
            "yesterday": {"n": 243, "wr_pct": 43.2, "pips": -357.0,
                          "date": "2026-07-21"},
            "24h_rolling": {"n": 453, "wr_pct": 43.0, "pips": -836.8},
            "intraday": [
                {"session": "ASIE", "n": 4, "wr_pct": 50.0, "pips": 12.5},
                {"session": "LONDRES", "n": 8, "wr_pct": 37.5, "pips": -46.7},
            ],
            "cvd": {"alive": 6, "total": 6, "missing": []},
            "crons_ready": 32,
            "brier_7j": {"n": 100, "brier": 0.4648},
            "wr_live": {"n": 200, "wr": 31.9},
            "walk_forward": {"verdict": "EDGE_REEL", "oos_expectancy": 6.7,
                             "ratio": 1.06},
            "positions": [{"symbol": "EURUSD", "direction": "haussiere", "timeframe": "M15"}],
            "pipeline": {"port": 31685, "active": True},
            "kill_switches": {"bayesian_on": 3, "bayesian_total": 3,
                              "dd_protector": False, "risk_parity": False,
                              "cycle_memory": False},
            "recommendation": "Test recommendation",
        }
        text = render_dashboard(dash)
        assert "DASHBOARD AUJOURD'HUI" in text
        assert "SNAPSHOT DU JOUR" in text
        assert "PERFORMANCE INTRADAY" in text
        assert "POSITIONS ACTIVES" in text
        assert "ÉTAT SYSTÈME" in text
        assert "INDICATEURS DE QUALITÉ" in text
        assert "RECOMMANDATION" in text
        assert "LONDRES" in text

    def test_render_dashboard_today_zero(self):
        """0 trade aujourd'hui → message approprié."""
        from scripts.v9_dashboard_today import render_dashboard
        dash = {
            "paris_time": "09:00",
            "utc_time": "07:00",
            "utc_date": "22/07/2026",
            "session": "ASIE",
            "today": {"n": 0, "wr_pct": 0.0, "pips": 0.0,
                      "date": "2026-07-22", "session_now": "ASIE"},
            "yesterday": {"n": 0, "wr_pct": 0.0, "pips": 0.0, "date": "2026-07-21"},
            "24h_rolling": {"n": 0, "wr_pct": 0.0, "pips": 0.0},
            "intraday": [],
            "cvd": {"alive": 0, "total": 6, "missing": ["EURUSD"]},
            "crons_ready": 32,
            "brier_7j": {"n": 0, "brier": None},
            "wr_live": {"n": 0, "wr": None},
            "walk_forward": None,
            "positions": [],
            "pipeline": {"port": 31685, "active": False},
            "kill_switches": {"bayesian_on": 0, "bayesian_total": 3,
                              "dd_protector": False, "risk_parity": False,
                              "cycle_memory": False},
            "recommendation": "Système en observation.",
        }
        text = render_dashboard(dash)
        assert "pas encore actif" in text or "pas de d" in text

    def test_recommendation_brier_high(self):
        """Brier > 0.40 → recommandation mentionne anti-calibré."""
        from scripts.v9_dashboard_today import _generate_recommendation
        health = {
            "today": {"pips": -10.0},
            "brier_7j": {"brier": 0.48},
            "kill_switches": {"bayesian_on": 3},
        }
        rec = _generate_recommendation(health)
        assert "anti-calibr" in rec.lower() or "brier" in rec.lower()

    def test_recommendation_today_positive(self):
        """P&L positif → recommandation positive."""
        from scripts.v9_dashboard_today import _generate_recommendation
        health = {
            "today": {"pips": 50.0},
            "brier_7j": {"brier": 0.15},
            "kill_switches": {"bayesian_on": 3},
        }
        rec = _generate_recommendation(health)
        assert "positive" in rec.lower() or "stable" in rec.lower()