"""tests/test_v9_capture_watchdog_anti_doublon.py — Tests Phase 151 anti-doublon.

Vérifie que `check_no_duplicates()` du watchdog capture_server détecte
correctement les write contention (= cause racine corruption Phase 149).

Doctrine : R7 (tests verts), R2 additif (nouveau fichier test, 0 modif core/).
"""
from __future__ import annotations

from unittest.mock import patch

import scripts.v9_capture_watchdog as wd


def test_check_no_duplicates_zero_when_no_capture() -> None:
    """Aucun capture_server → 0 doublon."""
    with patch.object(wd, "list_capture_pids", return_value=[]):
        extra = wd.check_no_duplicates()
    assert extra == 0


def test_check_no_duplicates_zero_when_singleton() -> None:
    """1 seul capture_server → 0 doublon (cas normal)."""
    with patch.object(wd, "list_capture_pids", return_value=[1234]):
        extra = wd.check_no_duplicates()
    assert extra == 0


def test_check_no_duplicates_detects_two() -> None:
    """2 capture_server → 1 doublon (cause corruption Phase 149)."""
    with patch.object(wd, "list_capture_pids", return_value=[1234, 5678]):
        extra = wd.check_no_duplicates()
    assert extra == 1


def test_check_no_duplicates_detects_three() -> None:
    """3 capture_server → 2 doublons (cas extrême, write contention triple)."""
    with patch.object(wd, "list_capture_pids", return_value=[1, 2, 3]):
        extra = wd.check_no_duplicates()
    assert extra == 2
