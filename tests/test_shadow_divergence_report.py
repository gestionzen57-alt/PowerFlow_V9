"""Tests — scripts/v9_shadow_divergence_report.py (P2 Shadow mode, alerte).

Aucun test n'appelle le réseau (R18 respecté même en test) : `--send` est
testé en monkeypatchant `send_telegram`, jamais en frappant l'API réelle.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.db_schema import init_db  # noqa: E402
from core.v9.decision_db import init_decision_db  # noqa: E402
from scripts.v9_shadow_divergence_report import (  # noqa: E402
    _connect,
    _format_report,
    find_divergences,
    main,
)


def _insert_decision(
    db_path: Path,
    *,
    snapshot_id: str,
    source_type: str,
    action: str,
    direction: str | None = "haussiere",
    confiance: int = 80,
    timestamp: str = "2026-07-13T10:00:00+00:00",
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO decisions (decision_id, snapshot_id, source_type, action, "
            "direction, confiance, symbol, timeframe, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"dec_{source_type}_{snapshot_id}", snapshot_id, source_type, action,
                direction, confiance, "GBPUSD", "M5", timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_forces.db"
    init_db(path)
    init_decision_db(path)
    return path


# ── find_divergences ────────────────────────────────────────────────────


def test_find_divergences_empty_db(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        result = find_divergences(conn, since=datetime.now(timezone.utc) - timedelta(hours=24))
    finally:
        conn.close()
    assert result == []


def test_find_divergences_same_action_not_reported(db_path: Path) -> None:
    _insert_decision(db_path, snapshot_id="snap-1", source_type="live", action="aucune_action")
    _insert_decision(db_path, snapshot_id="snap-1", source_type="shadow", action="aucune_action")

    conn = _connect(db_path)
    try:
        result = find_divergences(conn, since=datetime.now(timezone.utc) - timedelta(hours=24))
    finally:
        conn.close()
    assert result == []


def test_find_divergences_different_action_reported(db_path: Path) -> None:
    _insert_decision(db_path, snapshot_id="snap-2", source_type="live", action="preparer_entree")
    _insert_decision(db_path, snapshot_id="snap-2", source_type="shadow", action="aucune_action")

    conn = _connect(db_path)
    try:
        result = find_divergences(conn, since=datetime.now(timezone.utc) - timedelta(hours=24))
    finally:
        conn.close()
    assert len(result) == 1
    assert result[0]["snapshot_id"] == "snap-2"
    assert result[0]["live_action"] == "preparer_entree"
    assert result[0]["shadow_action"] == "aucune_action"


def test_find_divergences_missing_shadow_side_not_reported(db_path: Path) -> None:
    _insert_decision(db_path, snapshot_id="snap-3", source_type="live", action="preparer_entree")
    # Pas de pendant shadow (hook désactivé ou en échec) — jamais rapporté.

    conn = _connect(db_path)
    try:
        result = find_divergences(conn, since=datetime.now(timezone.utc) - timedelta(hours=24))
    finally:
        conn.close()
    assert result == []


def test_find_divergences_respects_lookback_window(db_path: Path) -> None:
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    _insert_decision(
        db_path, snapshot_id="snap-old", source_type="live", action="preparer_entree",
        timestamp=old_ts,
    )
    _insert_decision(
        db_path, snapshot_id="snap-old", source_type="shadow", action="aucune_action",
        timestamp=old_ts,
    )

    conn = _connect(db_path)
    try:
        result = find_divergences(conn, since=datetime.now(timezone.utc) - timedelta(hours=24))
    finally:
        conn.close()
    assert result == []


# ── _format_report ──────────────────────────────────────────────────────


def test_format_report_no_divergence() -> None:
    report = _format_report([], hours=24.0)
    assert "Aucune divergence" in report


def test_format_report_with_divergence() -> None:
    divergences = [{
        "snapshot_id": "snap-1", "symbol": "GBPUSD", "timeframe": "M5",
        "timestamp": "2026-07-13T10:00:00+00:00",
        "live_action": "preparer_entree", "live_direction": "haussiere", "live_confiance": 85,
        "shadow_action": "aucune_action", "shadow_direction": None, "shadow_confiance": 0,
    }]
    report = _format_report(divergences, hours=24.0)
    assert "1 divergence" in report
    assert "GBPUSD" in report
    assert "preparer_entree" in report
    assert "aucune_action" in report


# ── main() — jamais de vrai réseau ──────────────────────────────────────


def test_main_report_only_never_calls_telegram(db_path: Path, monkeypatch, capsys) -> None:
    _insert_decision(db_path, snapshot_id="snap-4", source_type="live", action="preparer_entree")
    _insert_decision(db_path, snapshot_id="snap-4", source_type="shadow", action="aucune_action")

    import scripts.v9_telegram_notifier as tg_notifier

    def _boom(*args, **kwargs):
        raise AssertionError("send_telegram ne doit jamais être appelé sans --send")

    monkeypatch.setattr(tg_notifier, "send_telegram", _boom)

    exit_code = main(["--db-path", str(db_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "1 divergence" in out


def test_main_send_without_config_skips_gracefully(db_path: Path, monkeypatch, capsys) -> None:
    _insert_decision(db_path, snapshot_id="snap-5", source_type="live", action="preparer_entree")
    _insert_decision(db_path, snapshot_id="snap-5", source_type="shadow", action="aucune_action")

    import scripts.v9_shadow_divergence_report as report_mod
    monkeypatch.setattr(report_mod, "_load_telegram_config_safe", lambda: None)

    exit_code = main(["--db-path", str(db_path), "--send"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "envoi ignoré" in out


def test_main_send_with_config_calls_send_telegram_mocked(db_path: Path, monkeypatch, capsys) -> None:
    _insert_decision(db_path, snapshot_id="snap-6", source_type="live", action="preparer_entree")
    _insert_decision(db_path, snapshot_id="snap-6", source_type="shadow", action="aucune_action")

    import scripts.v9_shadow_divergence_report as report_mod
    monkeypatch.setattr(
        report_mod, "_load_telegram_config_safe",
        lambda: {"token": "fake", "chat_id": "fake"},
    )

    calls = []

    def _fake_send(text, cfg, timeout=15):
        calls.append((text, cfg, timeout))
        return True

    import scripts.v9_telegram_notifier as tg_notifier
    monkeypatch.setattr(tg_notifier, "send_telegram", _fake_send)

    exit_code = main(["--db-path", str(db_path), "--send"])

    assert exit_code == 0
    assert len(calls) == 1
    out = capsys.readouterr().out
    assert "[SEND] OK" in out
