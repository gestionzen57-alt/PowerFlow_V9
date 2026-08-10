"""Tests CEO-OPT1/OPT2/OPT3 — Kelly adaptatif + Circuit-breaker + Edge scorer."""
import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from ceo_kelly_optimizer import compute_adaptive_kelly, MIN_KELLY, MAX_KELLY
from ceo_circuit_breaker import check_circuit_breaker, STREAK_SOFT, STREAK_HARD
from ceo_quant_edge_scorer import compute_edge_score


# ── CEO-OPT1 : Kelly ─────────────────────────────────────────────

class TestKellyOptimizer:
    def test_insufficient_trades_returns_floor(self):
        result = compute_adaptive_kelly([])
        assert result.method == "floor"
        assert result.fraction == MIN_KELLY

    def test_negative_edge_returns_floor(self):
        # WR 30% avec RR 1.5 → Kelly négatif
        trades = [{"result": "LOSS", "pnl_pips": -10}] * 14 + [{"result": "WIN", "pnl_pips": 15}] * 6
        result = compute_adaptive_kelly(trades, rr_target=1.5)
        assert result.method == "floor"
        assert result.fraction == MIN_KELLY

    def test_strong_edge_returns_adaptive(self):
        # WR 65% avec RR 1.5 → Kelly positif
        trades = [{"result": "WIN", "pnl_pips": 15}] * 13 + [{"result": "LOSS", "pnl_pips": -10}] * 7
        result = compute_adaptive_kelly(trades, rr_target=1.5)
        assert result.method == "adaptive"
        assert MIN_KELLY <= result.fraction <= MAX_KELLY
        assert result.kelly_raw > 0

    def test_atr_scale_reduces_on_high_volatility(self):
        trades = [{"result": "WIN", "pnl_pips": 15}] * 13 + [{"result": "LOSS", "pnl_pips": -10}] * 7
        low_vol  = compute_adaptive_kelly(trades, atr_current=10.0)
        high_vol = compute_adaptive_kelly(trades, atr_current=30.0)
        # Volatilité haute → fraction plus petite
        assert high_vol.fraction <= low_vol.fraction

    def test_fraction_always_in_bounds(self):
        trades = [{"result": "WIN", "pnl_pips": 20}] * 20
        result = compute_adaptive_kelly(trades, atr_current=5.0)
        assert MIN_KELLY <= result.fraction <= MAX_KELLY

    def test_as_dict_serializable(self):
        trades = [{"result": "WIN", "pnl_pips": 15}] * 12 + [{"result": "LOSS", "pnl_pips": -10}] * 8
        result = compute_adaptive_kelly(trades)
        d = result.as_dict()
        assert "fraction" in d
        assert "method" in d


# ── CEO-OPT2 : Circuit-breaker ───────────────────────────────────

class TestCircuitBreaker:
    def test_no_db_returns_clear(self, tmp_path):
        state = check_circuit_breaker(db_path=tmp_path / "nodb.db")
        assert state.level == "CLEAR"
        assert not state.is_open

    def test_no_streak_returns_clear(self, tmp_path):
        db = tmp_path / "trades.db"
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE shadow_trades (result TEXT, resolved_at TEXT, pair TEXT, timeframe TEXT, pnl_pips REAL)")
            conn.execute("INSERT INTO shadow_trades VALUES ('WIN', '2026-08-10T20:00:00', 'EURUSD', 'M15', 15)")
            conn.execute("INSERT INTO shadow_trades VALUES ('LOSS', '2026-08-10T20:15:00', 'EURUSD', 'M15', -10)")
            conn.execute("INSERT INTO shadow_trades VALUES ('WIN', '2026-08-10T20:30:00', 'EURUSD', 'M15', 15)")
        state = check_circuit_breaker(db_path=db)
        assert state.level == "CLEAR"
        assert not state.is_open

    def test_soft_streak_opens_circuit(self, tmp_path):
        db = tmp_path / "trades.db"
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE shadow_trades (result TEXT, resolved_at TEXT, pair TEXT, timeframe TEXT, pnl_pips REAL)")
            for i in range(STREAK_SOFT):
                conn.execute(f"INSERT INTO shadow_trades VALUES ('SL', '2026-08-10T20:{i:02d}:00', 'EURUSD', 'M15', -10)")
        state = check_circuit_breaker(db_path=db)
        assert state.level == "SOFT"
        assert state.is_open
        assert state.streak_count == STREAK_SOFT

    def test_hard_streak_opens_circuit(self, tmp_path):
        db = tmp_path / "trades.db"
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE shadow_trades (result TEXT, resolved_at TEXT, pair TEXT, timeframe TEXT, pnl_pips REAL)")
            for i in range(STREAK_HARD):
                conn.execute(f"INSERT INTO shadow_trades VALUES ('SL', '2026-08-10T20:{i:02d}:00', 'EURUSD', 'M15', -10)")
        state = check_circuit_breaker(db_path=db)
        assert state.level == "HARD"
        assert state.is_open

    def test_win_breaks_streak(self, tmp_path):
        db = tmp_path / "trades.db"
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE shadow_trades (result TEXT, resolved_at TEXT, pair TEXT, timeframe TEXT, pnl_pips REAL)")
            conn.execute("INSERT INTO shadow_trades VALUES ('WIN', '2026-08-10T20:00:00', 'EURUSD', 'M15', 15)")
            for i in range(2):
                conn.execute(f"INSERT INTO shadow_trades VALUES ('SL', '2026-08-10T19:{i:02d}:00', 'EURUSD', 'M15', -10)")
        state = check_circuit_breaker(db_path=db)
        assert state.level == "CLEAR"

    def test_as_dict_serializable(self, tmp_path):
        state = check_circuit_breaker(db_path=tmp_path / "nodb.db")
        d = state.as_dict()
        assert "is_open" in d
        assert "level" in d


# ── CEO-OPT3 : Edge Scorer ───────────────────────────────────────

class TestEdgeScorer:
    def test_strong_setup_scores_high(self):
        edge = compute_edge_score(
            force_delta=25.0,
            force_history=[10, 12, 15, 18, 20, 22, 25],
            pre_wave_phase="COMPRESSION",
            regime="TRENDING_UP",
            signal_level="A1",
        )
        assert edge.score >= 0.70
        assert edge.grade == "STRONG"
        assert edge.go is True

    def test_weak_setup_scores_low(self):
        edge = compute_edge_score(
            force_delta=2.0,
            pre_wave_phase="DIVERGENCE",
            regime="RANGING",
            signal_level="A3",
        )
        assert edge.score < 0.55
        assert not edge.go

    def test_divergence_watch_only_penalizes(self):
        div  = compute_edge_score(force_delta=20.0, pre_wave_phase="DIVERGENCE", regime="TRENDING_UP", signal_level="A1")
        comp = compute_edge_score(force_delta=20.0, pre_wave_phase="COMPRESSION", regime="TRENDING_UP", signal_level="A1")
        assert comp.score > div.score

    def test_score_in_bounds(self):
        for phase in ["COMPRESSION", "NEUTRAL", "DIVERGENCE"]:
            for regime in ["TRENDING_UP", "RANGING", "UNKNOWN"]:
                edge = compute_edge_score(force_delta=15.0, pre_wave_phase=phase, regime=regime)
                assert 0.0 <= edge.score <= 1.0

    def test_fail_open_bad_history(self):
        # force_history vide → fail-open, score doit être calculé quand même
        edge = compute_edge_score(force_delta=15.0, force_history=[], pre_wave_phase="COMPRESSION")
        assert 0.0 <= edge.score <= 1.0

    def test_as_dict_serializable(self):
        edge = compute_edge_score(force_delta=10.0)
        d = edge.as_dict()
        assert "score" in d
        assert "grade" in d
        assert "go" in d
        assert "components" in d
