"""tests/test_v9_phase79.py — Phase 79 motion CEO 48H (P3.2 audit Perplexity).

Tests pour kiss_audit.
"""
import pytest


def test_deprecated_modules_defined():
    from scripts.v9_kiss_audit import DEPRECATED_MODULES
    assert len(DEPRECATED_MODULES) == 4


def test_scan_deprecated_modules():
    from scripts.v9_kiss_audit import scan_deprecated_modules
    res = scan_deprecated_modules()
    assert len(res) == 4
    # Tous les modules du rapport Perplexity existent
    for m in res:
        assert m["exists"] is True
        assert "path" in m
        assert "reason" in m


def test_count_total_dead_loc_positive():
    from scripts.v9_kiss_audit import count_total_dead_loc
    total = count_total_dead_loc()
    assert total > 1000  # >1000 LOC


def test_recommend_suppression_conservative():
    from scripts.v9_kiss_audit import recommend_suppression
    recs = recommend_suppression(conservative=True)
    assert len(recs) >= 4
    assert any("conservateur" in r for r in recs)


def test_recommend_suppression_aggressive():
    from scripts.v9_kiss_audit import recommend_suppression
    recs = recommend_suppression(conservative=False)
    assert len(recs) >= 4
    assert any("agressif" in r for r in recs)


def test_main_demo(capsys):
    from scripts.v9_kiss_audit import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "KISS/DRY AUDIT" in captured.out
    assert "DEPRECATED" in captured.out
    assert "Total LOC" in captured.out


def test_deprecated_module_has_fallback():
    """Chaque module deprecated doit avoir un fallback documente."""
    from scripts.v9_kiss_audit import DEPRECATED_MODULES
    for m in DEPRECATED_MODULES:
        assert "fallback" in m
        assert len(m["fallback"]) > 0


def test_scan_loc_consistent():
    """Le LOC scan doit etre coherent (approximatif mais realiste)."""
    from scripts.v9_kiss_audit import scan_deprecated_modules
    res = scan_deprecated_modules()
    for m in res:
        # LOC actuel doit etre proche de l'estimation (entre 50% et 200%)
        est = m["loc"]
        actual = m["loc_actual"]
        assert 0.5 * est <= actual <= 2.0 * est