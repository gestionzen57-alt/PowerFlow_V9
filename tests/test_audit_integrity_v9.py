"""Tests Phase 180 — audit_integrity_check.py.

R2 additif pur : nouveau fichier tests/. Pas de modif core/.
Vérifie que le script d'audit :
  - Calcule correctement les métriques (mock DB sqlite)
  - Détecte les KILL criteria
  - Formate console + JSON
  - Détecte les doublons cachés
  - Gère l'absence de DB (R6 fail-open)
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "audit_integrity_check.py"


# ── Helpers ────────────────────────────────────────────────────────────
@pytest.fixture
def mock_db(tmp_path):
    """Crée une DB sqlite avec table paper_trades."""
    db = tmp_path / "test_v9.db"
    con = sqlite3.connect(str(db), timeout=5)
    con.executescript("""
        CREATE TABLE paper_trades (
            trade_id TEXT,
            snapshot_id TEXT,
            direction TEXT,
            confiance INTEGER,
            opened_at TEXT,
            closed_at TEXT,
            pips_simulated REAL,
            is_win INTEGER,
            spread_pips REAL,
            pips_net_of_spread REAL
        );
    """)
    con.close()
    return db


# ── Tests compute_metrics (mock DB) ────────────────────────────────────
def test_compute_metrics_empty_db(tmp_path, monkeypatch):
    """DB vide → retourne error (R6 fail-open)."""
    import importlib
    monkeypatch.setenv("V9_DB_PATH", str(tmp_path / "empty.db"))
    # Le script lit DB_PATH hardcoded, donc on test directement compute_metrics
    # en mockant DB_PATH via monkeypatch sur le module
    sys.path.insert(0, str(ROOT))
    if "scripts.audit_integrity_check" in sys.modules:
        del sys.modules["scripts.audit_integrity_check"]
    mod = importlib.import_module("scripts.audit_integrity_check")
    monkeypatch.setattr(mod, "DB_PATH", tmp_path / "nonexistent.db")
    result = mod.compute_metrics()
    assert "error" in result
    assert "introuvable" in result["error"]


def test_compute_metrics_all_wins(mock_db, monkeypatch):
    """Tous les trades gagnent → WR=100, PF=inf, Sharpe=0 (std=0)."""
    import importlib
    sys.path.insert(0, str(ROOT))
    if "scripts.audit_integrity_check" in sys.modules:
        del sys.modules["scripts.audit_integrity_check"]
    mod = importlib.import_module("scripts.audit_integrity_check")
    monkeypatch.setattr(mod, "DB_PATH", mock_db)

    # Insère 10 trades tous gagnants
    con = sqlite3.connect(str(mock_db), timeout=5)
    for i in range(10):
        con.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"t{i}", f"s{i}", "haussiere", 80, "2026-08-01T00:00:00+00:00",
             "2026-08-01T00:05:00+00:00", 5.0, 1, 1.5, 4.5),
        )
    con.commit()
    con.close()

    m = mod.compute_metrics()
    assert m["v1_total"] == 10
    assert m["v2_wr_pct"] == 100.0
    assert m["v4_profit_factor"] == float("inf")
    assert m["v3_pnl_net"] == 45.0  # 10 * 4.5
    assert "alerts" not in m  # pas d'alertes car PF=inf > 1, WR=100 > 50


def test_compute_metrics_all_losses(mock_db, monkeypatch):
    """Tous les trades perdent → KILL criteria WR, PF, Avg PnL, Sharpe."""
    import importlib
    sys.path.insert(0, str(ROOT))
    if "scripts.audit_integrity_check" in sys.modules:
        del sys.modules["scripts.audit_integrity_check"]
    mod = importlib.import_module("scripts.audit_integrity_check")
    monkeypatch.setattr(mod, "DB_PATH", mock_db)

    con = sqlite3.connect(str(mock_db), timeout=5)
    for i in range(10):
        con.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"t{i}", f"s{i}", "haussiere", 80, "2026-08-01T00:00:00+00:00",
             "2026-08-01T00:05:00+00:00", -3.0, 0, 1.5, -4.5),
        )
    con.commit()
    con.close()

    m = mod.compute_metrics()
    assert m["v1_total"] == 10
    assert m["v2_wr_pct"] == 0.0
    assert m["v4_profit_factor"] == 0.0  # 0 / 45
    assert m["v3_avg_pnl"] == -4.5
    alerts = mod.check_kill_criteria(m)
    # Au moins 4 KILL: WR<50, PF<1, Sharpe<0, avg_pnl<0
    assert len(alerts) >= 4


def test_compute_metrics_dup_hidden(mock_db, monkeypatch):
    """Doublons cachés (même closed_at + pnl + direction) sont détectés."""
    import importlib
    sys.path.insert(0, str(ROOT))
    if "scripts.audit_integrity_check" in sys.modules:
        del sys.modules["scripts.audit_integrity_check"]
    mod = importlib.import_module("scripts.audit_integrity_check")
    monkeypatch.setattr(mod, "DB_PATH", mock_db)

    con = sqlite3.connect(str(mock_db), timeout=5)
    # 3 lignes identiques (closed_at + pnl + direction) avec trade_id différents
    for i in range(3):
        con.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"t{i}", f"s{i}", "haussiere", 80, "2026-08-01T00:00:00+00:00",
             "2026-08-01T00:05:00+00:00", 5.0, 1, 1.5, 4.5),
        )
    con.commit()
    con.close()

    m = mod.compute_metrics()
    assert m["v7bis_dup_hidden"] >= 1  # au moins 1 groupe de doublons
    alerts = mod.check_kill_criteria(m)
    assert any("doublons" in a for a in alerts)


def test_compute_metrics_since_filter(mock_db, monkeypatch):
    """Filtre --since fonctionne correctement."""
    import importlib
    sys.path.insert(0, str(ROOT))
    if "scripts.audit_integrity_check" in sys.modules:
        del sys.modules["scripts.audit_integrity_check"]
    mod = importlib.import_module("scripts.audit_integrity_check")
    monkeypatch.setattr(mod, "DB_PATH", mock_db)

    con = sqlite3.connect(str(mock_db), timeout=5)
    # 5 trades avant 2026-08-01, 5 après
    for i in range(5):
        con.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"old_{i}", "s", "haussiere", 80, "2026-07-15T00:00:00+00:00",
             "2026-07-15T00:05:00+00:00", 5.0, 1, 1.5, 4.5),
        )
    for i in range(5):
        con.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"new_{i}", "s", "haussiere", 80, "2026-08-02T00:00:00+00:00",
             "2026-08-02T00:05:00+00:00", 5.0, 1, 1.5, 4.5),
        )
    con.commit()
    con.close()

    m_all = mod.compute_metrics()
    assert m_all["v1_total"] == 10

    m_since = mod.compute_metrics(since="2026-08-01")
    assert m_since["v1_total"] == 5  # seulement les 5 après 2026-08-01


def test_check_kill_criteria_returns_list(mock_db, monkeypatch):
    """check_kill_criteria retourne une liste (vide si tout OK)."""
    import importlib
    sys.path.insert(0, str(ROOT))
    if "scripts.audit_integrity_check" in sys.modules:
        del sys.modules["scripts.audit_integrity_check"]
    mod = importlib.import_module("scripts.audit_integrity_check")
    monkeypatch.setattr(mod, "DB_PATH", mock_db)

    # Métriques saines
    healthy = {
        "v2_wr_pct": 70.0,
        "v4_profit_factor": 2.5,
        "v5_max_dd": 100.0,
        "v9_sharpe_like_ann": 1.5,
        "v3_avg_pnl": 3.0,
        "v7bis_dup_hidden": 0,
    }
    alerts = mod.check_kill_criteria(healthy)
    assert alerts == []


# ── Tests CLI ───────────────────────────────────────────────────────────
def test_script_runs_with_json_output():
    """Le script --json produit un JSON valide sur la DB live."""
    if not (ROOT / "data" / "v9_forces.db").exists():
        pytest.skip("DB live absente (test env)")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode in (0, 1), f"Unexpected exit: {result.returncode}"
    data = json.loads(result.stdout)
    assert "v1_total" in data
    assert "v2_wr_pct" in data
    assert "v4_profit_factor" in data
    assert "v5_max_dd" in data
    assert "v9_sharpe_like_ann" in data


def test_script_runs_with_console_output():
    """Le script sans --json produit du texte console lisible."""
    if not (ROOT / "data" / "v9_forces.db").exists():
        pytest.skip("DB live absente (test env)")

    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )
    assert "AUDIT" in result.stdout or "ERREUR" in result.stdout
    # Exit non-zero si KILL criteria (DB live est en perte)
    assert result.returncode in (0, 1)
