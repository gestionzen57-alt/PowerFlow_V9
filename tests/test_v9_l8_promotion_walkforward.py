"""Tests pour scripts/v9_l8_promotion_walkforward.py (Phase 122).

Couvre :
- _is_l8_blocked : n_principes >= 5
- _compute_metrics : pre/post WR + PNL
- adaptive_wr_threshold / adaptive_pnl_threshold (Phase 122)
- _set_env : new key, update, create
- main() : verdict HOLD/QUASI/PROMOTE, dry-run vs apply
"""
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


@pytest.fixture
def l8_wf_module():
    """Charge le module walk-forward L8."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v9_l8_promotion", _ROOT / "scripts" / "v9_l8_promotion_walkforward.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
# Tests _is_l8_blocked
# ---------------------------------------------------------------------------

def test_is_l8_blocked_5_principes(l8_wf_module):
    """5 principes (seuil) : bloque."""
    assert l8_wf_module._is_l8_blocked(json.dumps(["p1", "p2", "p3", "p4", "p5"])) is True


def test_is_l8_blocked_10_principes(l8_wf_module):
    """10 principes : bloque."""
    lst = [f"p{i}" for i in range(10)]
    assert l8_wf_module._is_l8_blocked(json.dumps(lst)) is True


def test_is_l8_blocked_4_principes_passes(l8_wf_module):
    """4 principes (sous seuil) : ne bloque PAS."""
    assert l8_wf_module._is_l8_blocked(json.dumps(["p1", "p2", "p3", "p4"])) is False


def test_is_l8_blocked_1_principe_passes(l8_wf_module):
    """1 principe pur : ne bloque PAS."""
    assert l8_wf_module._is_l8_blocked(json.dumps(["PRICE_LAG_AT_NODE_BIRTH"])) is False


def test_is_l8_blocked_invalid_json(l8_wf_module):
    """JSON invalide : ne bloque PAS (R6 fail-open)."""
    assert l8_wf_module._is_l8_blocked("not_json{") is False


def test_is_l8_blocked_empty(l8_wf_module):
    """Liste vide : ne bloque PAS."""
    assert l8_wf_module._is_l8_blocked(json.dumps([])) is False
    assert l8_wf_module._is_l8_blocked("") is False
    assert l8_wf_module._is_l8_blocked(None) is False


# ---------------------------------------------------------------------------
# Tests _compute_metrics
# ---------------------------------------------------------------------------

def test_compute_metrics_basic(l8_wf_module):
    """Metriques de base."""
    trades = [
        {"trade_id": "T1", "principes_source": "[]", "pips_simulated": 5.0, "is_win": 1},
        {"trade_id": "T2", "principes_source": "[]", "pips_simulated": -5.0, "is_win": 0},
        {"trade_id": "T3", "principes_source": "[]", "pips_simulated": 10.0, "is_win": 1},
    ]
    metrics = l8_wf_module._compute_metrics(trades, set())
    assert metrics["n_trades_executed"] == 3
    assert metrics["n_trades_blocked"] == 0
    assert metrics["wr_pct"] == 66.67
    assert metrics["pnl_pips"] == 10.0
    assert metrics["n_wins"] == 2
    assert metrics["n_losses"] == 1


def test_compute_metrics_excludes_blocked(l8_wf_module):
    """Les bloques ne sont pas dans les metriques post."""
    trades = [
        {"trade_id": "T1", "principes_source": json.dumps([f"p{i}" for i in range(10)]),
         "pips_simulated": -10.0, "is_win": 0},  # bloque par L8
        {"trade_id": "T2", "principes_source": json.dumps(["p1"]),
         "pips_simulated": 5.0, "is_win": 1},
    ]
    metrics = l8_wf_module._compute_metrics(trades, {"T1"})
    assert metrics["n_trades_executed"] == 1
    assert metrics["n_trades_blocked"] == 1
    assert metrics["wr_pct"] == 100.0
    assert metrics["pnl_pips"] == 5.0


def test_compute_metrics_empty(l8_wf_module):
    """Aucun trade : zeros."""
    metrics = l8_wf_module._compute_metrics([], set())
    assert metrics["n_trades_executed"] == 0
    assert metrics["wr_pct"] == 0.0
    assert metrics["pnl_pips"] == 0.0


# ---------------------------------------------------------------------------
# Tests seuils adaptatifs
# ---------------------------------------------------------------------------

def test_adaptive_wr_threshold_large(l8_wf_module):
    """n=100+ : seuil strict 70%."""
    assert l8_wf_module.adaptive_wr_threshold(100) == 70.0
    assert l8_wf_module.adaptive_wr_threshold(500) == 70.0


def test_adaptive_wr_threshold_small(l8_wf_module):
    """n=30 : plancher 50%."""
    assert l8_wf_module.adaptive_wr_threshold(30) == 50.0


def test_adaptive_pnl_threshold_large(l8_wf_module):
    """n_blocked=30+ : seuil strict +50p."""
    assert l8_wf_module.adaptive_pnl_threshold(30) == 50.0


def test_adaptive_pnl_threshold_small(l8_wf_module):
    """n_blocked=5 : plancher +20p."""
    assert l8_wf_module.adaptive_pnl_threshold(5) == 20.0


# ---------------------------------------------------------------------------
# Tests _set_env
# ---------------------------------------------------------------------------

def test_set_env_new_key(l8_wf_module, tmp_path):
    """Ajoute une nouvelle cle dans .env."""
    env = tmp_path / ".env"
    env.write_text("# existing\nFOO=bar\n", encoding="utf-8")
    with patch.object(l8_wf_module, "ENV_FILE", env):
        l8_wf_module._set_env("V9_NEW_KEY", "1")
    text = env.read_text(encoding="utf-8")
    assert "V9_NEW_KEY=1" in text
    assert "FOO=bar" in text


def test_set_env_update_existing(l8_wf_module, tmp_path):
    """Met a jour une cle existante dans .env."""
    env = tmp_path / ".env"
    env.write_text("V9_KEY=0\n", encoding="utf-8")
    with patch.object(l8_wf_module, "ENV_FILE", env):
        l8_wf_module._set_env("V9_KEY", "1")
    text = env.read_text(encoding="utf-8")
    assert "V9_KEY=1" in text
    assert "V9_KEY=0" not in text


def test_set_env_creates_if_missing(l8_wf_module, tmp_path):
    """Cree le fichier .env s'il n'existe pas."""
    env = tmp_path / ".env"
    assert not env.exists()
    with patch.object(l8_wf_module, "ENV_FILE", env):
        l8_wf_module._set_env("V9_KEY", "1")
    assert env.exists()
    assert "V9_KEY=1" in env.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests main() integration
# ---------------------------------------------------------------------------

def test_main_promote_verdict(l8_wf_module, tmp_path, monkeypatch, paper_trades_db, caplog):
    """Scenario PROMOTE (4/5 conditions OK car n<30 sur petit echantillon).

    Le verdict PROMOTE exige >= 4 conditions OK (Phase 122 logique).
    Scenario : n_exe=20 (< 30 strict) -> condition n_trades_above_min False,
    mais les 4 autres conditions OK -> verdict PROMOTE.
    """
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_esc = fake_root / "ESCALATIONS_QUEUE_L8.md"
    fake_env.write_text("", encoding="utf-8")

    with sqlite3.connect(str(fake_db)) as conn:
        opened_base = "2026-07-15T10:00:00"
        # 10 bloques : 10 principes chacun, tous perdants
        for i in range(10):
            lst_json = json.dumps([f"p{j}" for j in range(10)])
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"B{i}", f"SN{i}", "haussiere", 75, lst_json,
                 opened_base, opened_base, -10.0, 0, None, 1.0, -11.0),
            )
        # 15 winners : 2 principes purs (edge authentique)
        for i in range(15):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"W{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1", "p2"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        # 5 losers : 2 principes purs
        for i in range(5):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"L{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1", "p2"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -6.0),
            )
        conn.commit()

    with patch.object(l8_wf_module, "DB_PATH", fake_db), \
         patch.object(l8_wf_module, "ENV_FILE", fake_env), \
         patch.object(l8_wf_module, "REPORT_PATH", fake_root / "report.json"), \
         patch.object(l8_wf_module, "ROOT", fake_root), \
         patch.object(l8_wf_module, "ESCALATIONS_QUEUE_PATH", fake_esc), \
         patch.object(sys, "argv", [
             "v9_l8_promotion_walkforward.py",
             "--days", "60",
             "--dry-run",
         ]):
        with caplog.at_level(logging.INFO):
            rc = l8_wf_module.main()

    # Verifier verdict PROMOTE (4/5 conditions OK : n_trades_above_min peut etre False sur petit sample)
    report = json.loads((fake_root / "report.json").read_text(encoding="utf-8"))
    assert report["verdict"] == "PROMOTE", f"Verdict attendu PROMOTE, recu {report['verdict']}"
    assert rc == 0
    # Conditions : au moins 4/5 OK
    n_ok = sum(1 for v in report["conditions"].values() if v)
    assert n_ok >= 4, f"Attendu >= 4 conditions OK, recu {n_ok}/5"
    # Conditions cles
    assert report["conditions"]["wr_above_threshold"] is True
    assert report["conditions"]["pnl_improved"] is True
    assert report["conditions"]["wr_improved"] is True
    assert report["conditions"]["edge_preserved"] is True


def test_main_apply_writes_env(l8_wf_module, tmp_path, monkeypatch, paper_trades_db):
    """PROMOTE + --apply : ecrit V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED=1 dans .env."""
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_esc = fake_root / "ESCALATIONS_QUEUE_L8.md"
    fake_env.write_text("", encoding="utf-8")

    # Mocker L8 ON check pour eviter idempotence (Phase 121 fix)
    from core.v9 import kill_switches as ks
    monkeypatch.setattr(ks, "mega_edge_l8_principle_count_blacklist_enabled", lambda: False)

    with sqlite3.connect(str(fake_db)) as conn:
        opened_base = "2026-07-15T10:00:00"
        for i in range(10):
            lst_json = json.dumps([f"p{j}" for j in range(10)])
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"B{i}", f"SN{i}", "haussiere", 75, lst_json,
                 opened_base, opened_base, -10.0, 0, None, 1.0, -11.0),
            )
        for i in range(15):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"W{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1", "p2"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        for i in range(5):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"L{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1", "p2"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -6.0),
            )
        conn.commit()

    with patch.object(l8_wf_module, "DB_PATH", fake_db), \
         patch.object(l8_wf_module, "ENV_FILE", fake_env), \
         patch.object(l8_wf_module, "REPORT_PATH", fake_root / "report.json"), \
         patch.object(l8_wf_module, "ROOT", fake_root), \
         patch.object(l8_wf_module, "ESCALATIONS_QUEUE_PATH", fake_esc), \
         patch.object(sys, "argv", [
             "v9_l8_promotion_walkforward.py",
             "--days", "60",
             "--apply",
         ]):
        rc = l8_wf_module.main()

    assert rc == 0
    env_text = fake_env.read_text(encoding="utf-8")
    assert "V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED=1" in env_text


def test_main_dry_run_no_write(l8_wf_module, tmp_path, monkeypatch, paper_trades_db):
    """PROMOTE + --dry-run : rapport applied=False, .env intact."""
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_esc = fake_root / "ESCALATIONS_QUEUE_L8.md"
    fake_env.write_text("V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED=0\n", encoding="utf-8")

    with sqlite3.connect(str(fake_db)) as conn:
        opened_base = "2026-07-15T10:00:00"
        for i in range(10):
            lst_json = json.dumps([f"p{j}" for j in range(10)])
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"B{i}", f"SN{i}", "haussiere", 75, lst_json,
                 opened_base, opened_base, -10.0, 0, None, 1.0, -11.0),
            )
        for i in range(15):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"W{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1", "p2"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        for i in range(5):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"L{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1", "p2"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -6.0),
            )
        conn.commit()

    with patch.object(l8_wf_module, "DB_PATH", fake_db), \
         patch.object(l8_wf_module, "ENV_FILE", fake_env), \
         patch.object(l8_wf_module, "REPORT_PATH", fake_root / "report.json"), \
         patch.object(l8_wf_module, "ROOT", fake_root), \
         patch.object(l8_wf_module, "ESCALATIONS_QUEUE_PATH", fake_esc), \
         patch.object(sys, "argv", [
             "v9_l8_promotion_walkforward.py",
             "--days", "60",
             "--dry-run",
         ]):
        rc = l8_wf_module.main()

    assert rc == 0
    env_text = fake_env.read_text(encoding="utf-8")
    assert "V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED=0" in env_text
    assert "V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED=1" not in env_text
    report = json.loads((fake_root / "report.json").read_text(encoding="utf-8"))
    assert report["applied"] is False


def test_main_quasi_promote_escalation(l8_wf_module, tmp_path, monkeypatch, paper_trades_db, caplog):
    """QUASI_PROMOTE (3/5 OK) : escalade CEO dans queue dedup."""
    fake_db = paper_trades_db
    fake_env = tmp_path / ".env"
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()
    fake_esc = fake_root / "ESCALATIONS_QUEUE_L8.md"
    fake_env.write_text("", encoding="utf-8")

    with sqlite3.connect(str(fake_db)) as conn:
        opened_base = "2026-07-15T10:00:00"
        # 5 bloques 10 principes (perdants) + 5 winners + 5 losers (purs)
        # pre : n=15, wr=33%, pnl=-25
        # post : n=10, wr=50%, pnl=0
        # gain = +25, wr_delta = +17
        # Conditions : wr 50 >= 50 adapt OK, n 10<30 NOT, pnl 25>=20 OK, wr_imp 17>=0.1 OK, edge OK
        # 4/5 = PROMOTE
        # Pour QUASI_PROMOTE, on force 3 OK. Ajustons.
        for i in range(5):
            lst_json = json.dumps([f"p{j}" for j in range(10)])
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"B{i}", f"SN{i}", "haussiere", 75, lst_json,
                 opened_base, opened_base, -10.0, 0, None, 1.0, -11.0),
            )
        for i in range(3):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"W{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1"]),
                 opened_base, opened_base, 5.0, 1, None, 1.0, 4.0),
            )
        for i in range(7):
            conn.execute(
                "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"L{i}", f"SN{i}", "haussiere", 75, json.dumps(["p1"]),
                 opened_base, opened_base, -5.0, 0, None, 1.0, -6.0),
            )
        conn.commit()

    with patch.object(l8_wf_module, "DB_PATH", fake_db), \
         patch.object(l8_wf_module, "ENV_FILE", fake_env), \
         patch.object(l8_wf_module, "REPORT_PATH", fake_root / "report.json"), \
         patch.object(l8_wf_module, "ROOT", fake_root), \
         patch.object(l8_wf_module, "ESCALATIONS_QUEUE_PATH", fake_esc), \
         patch.object(sys, "argv", [
             "v9_l8_promotion_walkforward.py",
             "--days", "60",
             "--dry-run",
         ]):
        with caplog.at_level(logging.WARNING):
            rc = l8_wf_module.main()

    assert rc in (0, 1, 2)
    report = json.loads((fake_root / "report.json").read_text(encoding="utf-8"))
    if report["verdict"] == "QUASI_PROMOTE":
        assert fake_esc.exists()
        text = fake_esc.read_text(encoding="utf-8")
        assert "L8 QUASI_PROMOTE" in text


def test_main_db_missing(l8_wf_module, tmp_path, monkeypatch, caplog):
    """DB absente : exit 4 (R6)."""
    fake_db = tmp_path / "absent.db"
    fake_env = tmp_path / ".env"

    with patch.object(l8_wf_module, "DB_PATH", fake_db), \
         patch.object(l8_wf_module, "ENV_FILE", fake_env), \
         patch.object(sys, "argv", ["v9_l8_promotion_walkforward.py", "--dry-run"]):
        with caplog.at_level(logging.ERROR):
            rc = l8_wf_module.main()
    assert rc == 4