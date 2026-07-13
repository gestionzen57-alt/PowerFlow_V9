"""Tests — core/v9/order_queue_watcher.py (ORDER-BRIDGE, 2026-07-13).

Aucun accès DB, aucun réseau (R18) : uniquement filesystem via tmp_path.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.v9.order_queue_watcher import purge_queue, scan_queue


@pytest.fixture
def queue_dir(tmp_path: Path) -> Path:
    d = tmp_path / "order_queue"
    d.mkdir()
    return d


def _write_command(queue_dir: Path, command_id: str, *, hours_ago: float = 0.0) -> Path:
    path = queue_dir / f"{command_id}.json"
    path.write_text(json.dumps({"command_id": command_id}), encoding="utf-8")
    if hours_ago:
        import os
        mtime = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).timestamp()
        os.utime(path, (mtime, mtime))
    return path


def _write_result(queue_dir: Path, command_id: str, status: str = "filled") -> Path:
    path = queue_dir / f"{command_id}.result.json"
    path.write_text(json.dumps({"status": status}), encoding="utf-8")
    return path


# ── scan_queue ──────────────────────────────────────────────────────────


def test_scan_queue_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert scan_queue(tmp_path / "does_not_exist") == []


def test_scan_queue_empty_dir(queue_dir: Path) -> None:
    assert scan_queue(queue_dir) == []


def test_scan_queue_pending_no_result_recent(queue_dir: Path) -> None:
    _write_command(queue_dir, "cmd-1")
    entries = scan_queue(queue_dir, expiry_hours=24.0)
    assert len(entries) == 1
    assert entries[0].status == "pending"
    assert entries[0].command_id == "cmd-1"


def test_scan_queue_consumed_with_result(queue_dir: Path) -> None:
    _write_command(queue_dir, "cmd-2")
    _write_result(queue_dir, "cmd-2", status="filled")
    entries = scan_queue(queue_dir)
    assert len(entries) == 1
    assert entries[0].status == "consumed"
    assert entries[0].result == {"status": "filled"}


def test_scan_queue_expired_without_result(queue_dir: Path) -> None:
    _write_command(queue_dir, "cmd-3", hours_ago=48.0)
    entries = scan_queue(queue_dir, expiry_hours=24.0)
    assert len(entries) == 1
    assert entries[0].status == "expired"


def test_scan_queue_result_file_not_double_counted(queue_dir: Path) -> None:
    _write_command(queue_dir, "cmd-4")
    _write_result(queue_dir, "cmd-4")
    entries = scan_queue(queue_dir)
    assert len(entries) == 1


def test_scan_queue_ignores_orphan_result_file(queue_dir: Path) -> None:
    _write_result(queue_dir, "cmd-orphan")
    entries = scan_queue(queue_dir)
    assert entries == []


# ── purge_queue ─────────────────────────────────────────────────────────


def test_purge_queue_dry_run_moves_nothing(queue_dir: Path) -> None:
    _write_command(queue_dir, "cmd-1")
    consumed = _write_command(queue_dir, "cmd-2")
    _write_result(queue_dir, "cmd-2")

    report = purge_queue(queue_dir, apply=False)

    assert report["applied"] is False
    assert report["pending"] == 1
    assert report["consumed_archived"] == 1
    assert consumed.exists()  # rien déplacé


def test_purge_queue_apply_archives_consumed_and_expired(queue_dir: Path) -> None:
    pending = _write_command(queue_dir, "cmd-pending")
    consumed = _write_command(queue_dir, "cmd-consumed")
    result = _write_result(queue_dir, "cmd-consumed")
    expired = _write_command(queue_dir, "cmd-expired", hours_ago=48.0)

    report = purge_queue(queue_dir, apply=True, expiry_hours=24.0)

    assert report["applied"] is True
    assert report["pending"] == 1
    assert report["consumed_archived"] == 1
    assert report["expired_archived"] == 1

    assert pending.exists()
    assert not consumed.exists()
    assert not result.exists()
    assert not expired.exists()

    archive_dir = queue_dir / "archive"
    assert (archive_dir / "cmd-consumed.json").exists()
    assert (archive_dir / "cmd-consumed.result.json").exists()
    assert (archive_dir / "cmd-expired.json").exists()


def test_purge_queue_never_touches_pending(queue_dir: Path) -> None:
    pending = _write_command(queue_dir, "cmd-pending")
    purge_queue(queue_dir, apply=True)
    assert pending.exists()


def test_purge_queue_custom_archive_dir(queue_dir: Path, tmp_path: Path) -> None:
    _write_command(queue_dir, "cmd-consumed")
    _write_result(queue_dir, "cmd-consumed")
    custom_archive = tmp_path / "custom_archive"

    purge_queue(queue_dir, archive_dir=custom_archive, apply=True)

    assert (custom_archive / "cmd-consumed.json").exists()


def test_purge_queue_no_op_on_empty_queue(queue_dir: Path) -> None:
    report = purge_queue(queue_dir, apply=True)
    assert report["pending"] == 0
    assert report["consumed_archived"] == 0
    assert report["expired_archived"] == 0
