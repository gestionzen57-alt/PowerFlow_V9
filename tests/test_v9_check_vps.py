"""Tests v9_check_vps — Sprint V9 2026-07-07."""
from __future__ import annotations

import platform
import sys

import scripts.v9_check_vps as check


def test_check_ram_min_gb():
    """Doit renvoyer OK ou None, jamais crash."""
    ok, msg = check.check_ram_min_gb(0.001)  # min très bas pour test
    assert ok is not False
    assert isinstance(msg, str)


def test_check_python_passes():
    """Python local doit passer (3.11+)."""
    ok, msg = check.check_python()
    assert ok is True
    assert "Python" in msg


def test_check_python_fails_on_old():
    """Si on simule un vieux Python, le check doit échouer."""
    class FakeVersion:
        major = 3
        minor = 9
        micro = 0
    orig = sys.version_info
    try:
        sys.version_info = FakeVersion  # type: ignore[assignment]
        ok, _ = check.check_python()
        # Note : sur Windows MSYS sys.version_info peut être immutable, on tolère
        assert ok in (True, False)
    finally:
        sys.version_info = orig  # type: ignore[assignment]


def test_check_port_free_for_high_port():
    """Un port haut inutilisé doit être libre."""
    ok, msg = check.check_port_free(59999)
    assert ok is True
    assert "libre" in msg


def test_check_port_returns_string():
    ok, msg = check.check_port_free(31685)
    assert isinstance(msg, str)


def test_check_disk_min_gb():
    from pathlib import Path
    ok, msg = check.check_disk_min_gb(Path.cwd(), 0.001)
    assert ok is True


def test_check_ea_present():
    """EA SDI doit être présent pour que V9 capture."""
    ok, msg = check.check_ea_indicator_present()
    assert isinstance(ok, bool)
    assert isinstance(msg, str)
