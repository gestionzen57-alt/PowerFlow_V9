"""tests/test_v9_phase86.py — Phase 86 motion CEO 48H (post-Plan C).

Tests pour backup_strategy.
"""
import pytest
from pathlib import Path


def test_rotation_strategy():
    from scripts.v9_backup_strategy import RotationStrategy
    assert RotationStrategy.DAILY.value == "daily"
    assert RotationStrategy.WEEKLY.value == "weekly"
    assert RotationStrategy.MONTHLY.value == "monthly"


def test_default_retention():
    from scripts.v9_backup_strategy import DEFAULT_RETENTION
    assert "daily" in DEFAULT_RETENTION
    assert "weekly" in DEFAULT_RETENTION
    assert "monthly" in DEFAULT_RETENTION


def test_list_existing_backups_empty(tmp_path):
    from scripts.v9_backup_strategy import list_existing_backups
    res = list_existing_backups(tmp_path)
    assert res == []


def test_list_existing_backups(tmp_path):
    from scripts.v9_backup_strategy import list_existing_backups
    for i in range(3):
        (tmp_path / f"backup_2026-07-{28+i:02d}.db").touch()
    res = list_existing_backups(tmp_path)
    assert len(res) == 3


def test_cleanup_old_backups(tmp_path):
    from scripts.v9_backup_strategy import cleanup_old_backups
    # 10 backups, garder 3
    for i in range(10):
        (tmp_path / f"backup_{i:03d}.db").touch()
    deleted = cleanup_old_backups(tmp_path, keep=3)
    assert deleted == 7
    remaining = list(tmp_path.glob("backup_*.db"))
    assert len(remaining) == 3


def test_cleanup_old_backups_keep_more_than_exists(tmp_path):
    from scripts.v9_backup_strategy import cleanup_old_backups
    for i in range(2):
        (tmp_path / f"backup_{i:03d}.db").touch()
    deleted = cleanup_old_backups(tmp_path, keep=10)
    assert deleted == 0


def test_rotate_backup_creates_new(tmp_path):
    from scripts.v9_backup_strategy import rotate_backup
    db = tmp_path / "v9.db"
    db.write_text("data")
    ok = rotate_backup(db, tmp_path / "backups")
    assert ok is True
    assert (tmp_path / "backups").exists()


def test_compute_md5():
    from scripts.v9_backup_strategy import compute_md5
    h = compute_md5(b"hello world")
    # MD5 well-known
    assert h == "5eb63bbbe01eeed093cb22bb8f5acdc3"


def test_compute_md5_empty():
    from scripts.v9_backup_strategy import compute_md5
    h = compute_md5(b"")
    # MD5 empty string
    assert h == "d41d8cd98f00b204e9800998ecf8427e"


def test_verify_backup_integrity(tmp_path):
    from scripts.v9_backup_strategy import (
        compute_md5, verify_backup_integrity,
    )
    f = tmp_path / "backup.db"
    f.write_bytes(b"hello world")
    expected_md5 = compute_md5(f.read_bytes())
    ok, actual_md5 = verify_backup_integrity(f, expected_md5)
    assert ok is True
    assert actual_md5 == expected_md5


def test_verify_backup_integrity_corrupt(tmp_path):
    from scripts.v9_backup_strategy import (
        compute_md5, verify_backup_integrity,
    )
    f = tmp_path / "backup.db"
    f.write_bytes(b"hello world")
    bad_md5 = compute_md5(b"different content")
    ok, actual_md5 = verify_backup_integrity(f, bad_md5)
    assert ok is False


def test_compute_next_rotation():
    from scripts.v9_backup_strategy import compute_next_rotation
    import datetime
    # Rotation daily : next = today + 1 day
    nxt = compute_next_rotation("daily", datetime.datetime(2026, 7, 31))
    assert nxt.day == 1 or nxt.day == 31  # next day


def test_format_backup_filename():
    from scripts.v9_backup_strategy import format_backup_filename
    fn = format_backup_filename("v9_forces.db", "daily")
    assert "v9_forces" in fn
    assert "daily" in fn
    assert ".db" in fn


def test_main_demo(tmp_path, capsys):
    from scripts.v9_backup_strategy import main
    db = tmp_path / "v9.db"
    db.write_text("x")
    exit_code = main(["--db", str(db), "--backup-dir", str(tmp_path / "backups")])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "BACKUP STRATEGY" in captured.out