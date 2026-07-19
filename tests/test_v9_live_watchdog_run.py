"""test_v9_live_watchdog_run.py — Tests du runner CLI (Axe 6, pré-réouverture 07-19).

Vérifie :
T1. status_to_exit_code : disabled=4, ok=0, warn=1, critical=2, db_error=3, no_data=0
T2. build_report contient les champs requis (dont timestamp)
T3. --apply-recommendations : append au .env + backup créé
T4. blacklist : V9_GBPUSD_LONG_ONLY=0 n'est jamais écrit
T5. pas d'alerte Telegram si watchdog disabled
T6. le log JSONL est bien append (2 runs → 2 lignes)
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import scripts.v9_live_watchdog_run as runner
from core.v9.v9_live_watchdog import (
    LIVE_WATCHDOG_ENABLED_ENV,
    WatchdogDecision,
)


def _make_db(tmp_path: Path, n_win: int, n_loss: int) -> Path:
    """DB minimale GBPUSD haussiere clôturés récents."""
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE decisions (snapshot_id TEXT, symbol TEXT, direction TEXT)")
        conn.execute(
            """CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, direction TEXT, opened_at TEXT, closed_at TEXT,
                pips_simulated REAL, is_win INTEGER)"""
        )
        now = datetime.now(timezone.utc)
        closed = (now - timedelta(hours=1)).isoformat()
        idx = 0
        for pips, is_win, count in ((8.0, 1, n_win), (-3.0, 0, n_loss)):
            for _ in range(count):
                sid = f"s{idx}"
                idx += 1
                conn.execute(
                    "INSERT INTO decisions (snapshot_id, symbol, direction) VALUES (?, ?, ?)",
                    (sid, "GBPUSD", "haussiere"),
                )
                conn.execute(
                    "INSERT INTO paper_trades "
                    "(snapshot_id, direction, opened_at, closed_at, pips_simulated, is_win) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sid, "haussiere", closed, closed, pips, is_win),
                )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.get(LIVE_WATCHDOG_ENABLED_ENV)
    yield
    if saved is None:
        os.environ.pop(LIVE_WATCHDOG_ENABLED_ENV, None)
    else:
        os.environ[LIVE_WATCHDOG_ENABLED_ENV] = saved


# ── T1 : exit code mapping ─────────────────────────────────────────

def test_exit_code_mapping():
    assert runner.status_to_exit_code("disabled") == 4
    assert runner.status_to_exit_code("ok") == 0
    assert runner.status_to_exit_code("no_data") == 0
    assert runner.status_to_exit_code("warn") == 1
    assert runner.status_to_exit_code("critical") == 2
    assert runner.status_to_exit_code("db_error") == 3


# ── T2 : build_report champs requis ────────────────────────────────

def test_json_output():
    d = WatchdogDecision(
        status="ok", net_pnl_24h_pips=12.0, wr_long_only_gbpusd=0.9, n_recent=20,
    )
    report = runner.build_report(d)
    for key in ("timestamp", "status", "net_pnl_24h_pips",
                "wr_long_only_gbpusd", "n_recent", "triggered",
                "recommended_actions", "alert_level"):
        assert key in report
    # JSON-serializable
    json.dumps(report)


# ── T3 : apply-recommendations écrit le .env + backup ──────────────

def test_apply_recommendations_writes_env(tmp_path):
    env = tmp_path / "v9_kill_switches.env"
    env.write_text("V9_EXISTING=1\n", encoding="utf-8")
    applied = runner.apply_recommendations(
        ["V9_PAPER_TRADE_HALT=1", "V9_NO_BAISSIERE=1"], env,
    )
    assert applied == ["V9_PAPER_TRADE_HALT=1", "V9_NO_BAISSIERE=1"]
    content = env.read_text(encoding="utf-8")
    assert "V9_PAPER_TRADE_HALT=1" in content
    assert "V9_EXISTING=1" in content  # append, pas d'écrasement
    backups = list(tmp_path.glob("v9_kill_switches.env.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "V9_EXISTING=1\n"


# ── T4 : blacklist long-only ───────────────────────────────────────

def test_apply_recommendations_blacklists_long_only(tmp_path):
    env = tmp_path / "v9_kill_switches.env"
    env.write_text("V9_EXISTING=1\n", encoding="utf-8")
    applied = runner.apply_recommendations(
        ["V9_GBPUSD_LONG_ONLY=0", "V9_PAPER_TRADE_HALT=1"], env,
    )
    assert "V9_GBPUSD_LONG_ONLY=0" not in applied
    assert "V9_PAPER_TRADE_HALT=1" in applied
    assert "V9_GBPUSD_LONG_ONLY=0" not in env.read_text(encoding="utf-8")


def test_apply_only_blacklisted_writes_nothing(tmp_path):
    env = tmp_path / "v9_kill_switches.env"
    env.write_text("V9_EXISTING=1\n", encoding="utf-8")
    applied = runner.apply_recommendations(["V9_GBPUSD_LONG_ONLY=0"], env)
    assert applied == []
    # aucun backup si rien à appliquer
    assert list(tmp_path.glob("v9_kill_switches.env.bak.*")) == []


# ── T5 : pas d'alerte si disabled ──────────────────────────────────

def test_no_alert_when_disabled(tmp_path, monkeypatch):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "0"
    db = _make_db(tmp_path, 12, 0)
    log = tmp_path / "wd.log"
    calls: list[str] = []
    monkeypatch.setattr(runner, "send_telegram_alert", lambda text: calls.append(text) or True)
    code = runner.main([
        "--db-path", str(db), "--alert-telegram", "--log-file", str(log),
    ])
    assert code == 4  # disabled
    assert calls == []


# ── T6 : log JSONL append ──────────────────────────────────────────

def test_log_file_appended(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    db = _make_db(tmp_path, 12, 0)
    log = tmp_path / "wd.log"
    runner.main(["--db-path", str(db), "--log-file", str(log)])
    runner.main(["--db-path", str(db), "--log-file", str(log)])
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln)  # chaque ligne = JSON valide
