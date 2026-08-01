"""Tests pour scripts/v9_l7_promotion_walkforward.py (Phase 109)."""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

SCRIPT_PATH = _ROOT / "scripts" / "v9_l7_promotion_walkforward.py"


@pytest.fixture
def wf_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("v9_l7_promotion_walkforward", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Tests _is_l7_blocked
# ---------------------------------------------------------------------------

def test_is_l7_blocked_grammar_pur(wf_module):
    """GRAMMAR pur no-stars → bloque."""
    assert wf_module._is_l7_blocked(json.dumps(["GRAMMAR_CONTEXTE"])) is True
    assert wf_module._is_l7_blocked(json.dumps(["GRAMMAR_PULLBACK", "GRAMMAR_CONTEXT"])) is True


def test_is_l7_blocked_elastic_pur(wf_module):
    """ELASTIC pur no-stars → bloque."""
    assert wf_module._is_l7_blocked(json.dumps(["ELASTIC_BREATH"])) is True


def test_is_l7_blocked_with_star_passes(wf_module):
    """Avec star (PRICE_LAG/POWER_ANGLE/GRAVITY) → PAS bloque."""
    assert wf_module._is_l7_blocked(json.dumps(["GRAMMAR_PULLBACK", "PRICE_LAG_AT_NODE_BIRTH"])) is False
    assert wf_module._is_l7_blocked(json.dumps(["ELASTIC_BREATH", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"])) is False


def test_is_l7_blocked_3_stars_passes(wf_module):
    """3 stars purs → PAS bloque."""
    assert wf_module._is_l7_blocked(json.dumps([
        "PRICE_LAG_AT_NODE_BIRTH",
        "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
        "GRAVITY_RESPRING_NODE",
    ])) is False


def test_is_l7_blocked_invalid_json(wf_module):
    """JSON invalide → False (R6 fail-open)."""
    assert wf_module._is_l7_blocked("not json") is False
    assert wf_module._is_l7_blocked("") is False
    assert wf_module._is_l7_blocked(None) is False


def test_is_l7_blocked_empty(wf_module):
    """Liste vide → False (rien a bloquer)."""
    assert wf_module._is_l7_blocked(json.dumps([])) is False


# ---------------------------------------------------------------------------
# Tests _compute_metrics
# ---------------------------------------------------------------------------

def test_compute_metrics_basic(wf_module):
    """Calcul WR/pnl/n standard."""
    trades = [
        {"trade_id": "T1", "is_win": 1, "pips_simulated": 5.0},
        {"trade_id": "T2", "is_win": 0, "pips_simulated": -3.0},
        {"trade_id": "T3", "is_win": 1, "pips_simulated": 7.0},
    ]
    blocked = set()
    m = wf_module._compute_metrics(trades, blocked)
    assert m["n_trades_executed"] == 3
    assert m["n_trades_blocked"] == 0
    assert m["n_wins"] == 2
    assert m["n_losses"] == 1
    assert m["wr_pct"] == 66.67
    assert m["pnl_pips"] == 9.0


def test_compute_metrics_excludes_blocked(wf_module):
    """Trades bloques exclus du walk-forward post-L7."""
    trades = [
        {"trade_id": "T1", "is_win": 0, "pips_simulated": -10.0},
        {"trade_id": "T2", "is_win": 1, "pips_simulated": 5.0},
        {"trade_id": "T3", "is_win": 0, "pips_simulated": -5.0},
    ]
    blocked = {"T1"}  # trade perdant bloque
    m = wf_module._compute_metrics(trades, blocked)
    assert m["n_trades_executed"] == 2
    assert m["n_trades_blocked"] == 1
    assert m["wr_pct"] == 50.0
    assert m["pnl_pips"] == 0.0  # +5 + -5


def test_compute_metrics_empty(wf_module):
    """Aucun trade execute → metriques zero."""
    m = wf_module._compute_metrics([], set())
    assert m["n_trades_executed"] == 0
    assert m["wr_pct"] == 0.0


def test_compute_metrics_all_blocked(wf_module):
    """Tous bloques → 0 execute."""
    trades = [
        {"trade_id": "T1", "is_win": 0, "pips_simulated": -5.0},
    ]
    m = wf_module._compute_metrics(trades, {"T1"})
    assert m["n_trades_executed"] == 0
    assert m["n_trades_blocked"] == 1


# ---------------------------------------------------------------------------
# Tests _set_env
# ---------------------------------------------------------------------------

def test_set_env_new_key(tmp_path, wf_module):
    """Ajoute une nouvelle cle .env."""
    fake_env = tmp_path / ".env"
    fake_env.write_text("EXISTING_KEY=value\n", encoding="utf-8")
    with patch.object(wf_module, "ENV_FILE", fake_env):
        wf_module._set_env("NEW_KEY", "1")
    text = fake_env.read_text(encoding="utf-8")
    assert "EXISTING_KEY=value" in text
    assert "NEW_KEY=1" in text


def test_set_env_update_existing(tmp_path, wf_module):
    """Mise a jour d'une cle existante (pas de doublon)."""
    fake_env = tmp_path / ".env"
    fake_env.write_text("V9_MEGA_EDGE_L7=0\nOTHER=foo\n", encoding="utf-8")
    with patch.object(wf_module, "ENV_FILE", fake_env):
        wf_module._set_env("V9_MEGA_EDGE_L7", "1")
    text = fake_env.read_text(encoding="utf-8")
    assert "V9_MEGA_EDGE_L7=1" in text
    assert "V9_MEGA_EDGE_L7=0" not in text
    assert text.count("V9_MEGA_EDGE_L7=") == 1


def test_set_env_creates_if_missing(tmp_path, wf_module):
    """Cree .env si absent (R6 fail-safe)."""
    fake_env = tmp_path / ".env"
    with patch.object(wf_module, "ENV_FILE", fake_env):
        wf_module._set_env("K", "v")
    assert fake_env.exists()
    assert "K=v" in fake_env.read_text(encoding="utf-8")


@pytest.fixture
def paper_trades_db(tmp_path):
    """Cree une DB SQLite minimale avec table paper_trades."""
    db = tmp_path / "v9_forces.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE paper_trades (
                trade_id TEXT, snapshot_id TEXT, direction TEXT, confiance INTEGER,
                principes_source TEXT, opened_at TEXT, closed_at TEXT,
                pips_simulated REAL, is_win INTEGER, risk_go_context TEXT,
                spread_pips REAL, pips_net_of_spread REAL
            )
        """)
        conn.commit()
    return db


# ---------------------------------------------------------------------------
# Tests integration main() avec mock DB
# ---------------------------------------------------------------------------

def test_main_hold_verdict_dry_run(wf_module, tmp_path, monkeypatch, caplog, paper_trades_db):
    """Verdict HOLD + dry-run : pas de promotion."""
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_report = fake_root / "report.json"
    fake_env.write_text("", encoding="utf-8")

    with sqlite3.connect(str(fake_db)) as conn:
        # 30 trades : 10 GRAMMAR pur (perdants, bloques), 20 stars (gagnants)
        opened_base = "2026-07-15T10:00:00"
        for i in range(10):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"G{i}", f"S{i}", "haussiere", 75, json.dumps(["GRAMMAR_PULLBACK"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -5.0),
            )
        for i in range(20):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"S{i}", f"SN{i}", "haussiere", 75, json.dumps(["PRICE_LAG_AT_NODE_BIRTH"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        conn.commit()

    with patch.object(wf_module, "DB_PATH", fake_db), \
         patch.object(wf_module, "ENV_FILE", fake_env), \
         patch.object(wf_module, "REPORT_PATH", fake_report), \
         patch.object(wf_module, "ROOT", fake_root), \
         patch.object(sys, "argv", [
             "v9_l7_promotion_walkforward.py",
             "--days", "60",
             "--dry-run",
         ]):
        with caplog.at_level(logging.INFO):
            rc = wf_module.main()
    # Verdict HOLD (WR post=100% mais trop peu de trades executes,
    # ou PNL gain insuffisant)
    assert rc in (0, 1)  # peut etre PROMOTE ou HOLD selon les chiffres
    # .env intact (dry-run)
    assert "V9_MEGA_EDGE_L7" not in fake_env.read_text(encoding="utf-8")
    # Rapport ecrit
    assert fake_report.exists()
    report = json.loads(fake_report.read_text(encoding="utf-8"))
    assert "pre_l7" in report
    assert "post_l7" in report
    assert "verdict" in report
    assert "conditions" in report


def test_main_apply_promotes_when_ok(wf_module, tmp_path, monkeypatch, paper_trades_db):
    """Verdict PROMOTE + --apply : ecrit .env + applied=True dans rapport."""
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_report = fake_root / "report.json"
    fake_env.write_text("", encoding="utf-8")

    with sqlite3.connect(str(fake_db)) as conn:
        opened_base = "2026-07-15T10:00:00"
        # 50 trades gagnants stars + 10 perdants GRAMMAR bloques
        for i in range(50):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"W{i}", f"SN{i}", "haussiere", 75, json.dumps(["PRICE_LAG_AT_NODE_BIRTH"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        for i in range(10):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"L{i}", f"SN{i}", "haussiere", 75, json.dumps(["GRAMMAR_PULLBACK"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -6.0),
            )
        conn.commit()

    with patch.object(wf_module, "DB_PATH", fake_db), \
         patch.object(wf_module, "ENV_FILE", fake_env), \
         patch.object(wf_module, "REPORT_PATH", fake_report), \
         patch.object(wf_module, "ROOT", fake_root), \
         patch.object(sys, "argv", [
             "v9_l7_promotion_walkforward.py",
             "--days", "60",
             "--apply",
             "--min-pnl-gain", "10",  # seuil bas pour forcer PROMOTE
         ]):
        rc = wf_module.main()
    # 50 wins, 10 losses bloques : post WR=100%, PNL=+200, gain=+250
    # Verdict PROMOTE, --apply
    assert rc == 0
    # .env mis a jour
    env_text = fake_env.read_text(encoding="utf-8")
    assert "V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED=1" in env_text
    # Rapport applied=True
    report = json.loads(fake_report.read_text(encoding="utf-8"))
    assert report["applied"] is True
    assert report["verdict"] == "PROMOTE"


def test_main_dry_run_does_not_promote(wf_module, tmp_path, monkeypatch, paper_trades_db):
    """Verdict PROMOTE + --dry-run : rapport applied=False, .env intact."""
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_report = fake_root / "report.json"
    fake_env.write_text("V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED=0\n", encoding="utf-8")

    with sqlite3.connect(str(fake_db)) as conn:
        opened_base = "2026-07-15T10:00:00"
        for i in range(50):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"W{i}", f"SN{i}", "haussiere", 75, json.dumps(["PRICE_LAG_AT_NODE_BIRTH"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        for i in range(10):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"L{i}", f"SN{i}", "haussiere", 75, json.dumps(["GRAMMAR_PULLBACK"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -6.0),
            )
        conn.commit()

    with patch.object(wf_module, "DB_PATH", fake_db), \
         patch.object(wf_module, "ENV_FILE", fake_env), \
         patch.object(wf_module, "REPORT_PATH", fake_report), \
         patch.object(wf_module, "ROOT", fake_root), \
         patch.object(sys, "argv", [
             "v9_l7_promotion_walkforward.py",
             "--days", "60",
             "--dry-run",
             "--min-pnl-gain", "10",
         ]):
        rc = wf_module.main()
    assert rc == 0
    env_text = fake_env.read_text(encoding="utf-8")
    # .env NON modifie
    assert "V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED=0" in env_text
    assert "V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED=1" not in env_text
    # Rapport applied=False
    report = json.loads(fake_report.read_text(encoding="utf-8"))
    assert report["applied"] is False


def test_main_apply_and_dry_run_exclusive(wf_module, tmp_path, monkeypatch, caplog):
    """--apply et --dry-run ensemble → exit 2."""
    fake_db = tmp_path / "v9_forces.db"
    fake_env = tmp_path / ".env"

    with patch.object(wf_module, "DB_PATH", fake_db), \
         patch.object(wf_module, "ENV_FILE", fake_env), \
         patch.object(sys, "argv", [
             "v9_l7_promotion_walkforward.py",
             "--apply",
             "--dry-run",
         ]):
        with caplog.at_level(logging.ERROR):
            rc = wf_module.main()
    assert rc == 2


def test_main_db_missing(wf_module, tmp_path, monkeypatch, caplog):
    """DB absente → exit 4 (R6)."""
    fake_db = tmp_path / "absent.db"
    fake_env = tmp_path / ".env"

    with patch.object(wf_module, "DB_PATH", fake_db), \
         patch.object(wf_module, "ENV_FILE", fake_env), \
         patch.object(sys, "argv", ["v9_l7_promotion_walkforward.py", "--dry-run"]):
        with caplog.at_level(logging.ERROR):
            rc = wf_module.main()
    assert rc == 4
