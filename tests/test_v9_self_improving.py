"""tests/test_v9_self_improving.py — Phase 33 motion CEO 48h.

Tests pour v9_self_improving_loop.
"""
import pytest
from pathlib import Path


def test_detect_gaps_missing_test(tmp_path, monkeypatch):
    """detect_gaps detecte les scripts sans tests."""
    from scripts.v9_self_improving_loop import detect_gaps
    # Mock le _ROOT pour pointer sur tmp_path
    monkeypatch.setattr("scripts.v9_self_improving_loop._ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts" / "v9_test_module.py").write_text(
        '"""v9_test_module — module V9."""\n'
        "x = 1\n"
    )
    gaps = detect_gaps()
    assert any(g["type"] == "missing_test" for g in gaps)


def test_detect_gaps_missing_docstring(tmp_path, monkeypatch):
    """detect_gaps detecte les scripts sans docstring."""
    from scripts.v9_self_improving_loop import detect_gaps
    monkeypatch.setattr("scripts.v9_self_improving_loop._ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts" / "v9_no_docstring.py").write_text("x = 1\n")
    gaps = detect_gaps()
    assert any(
        g["type"] == "missing_docstring"
        and "v9_no_docstring" in g["script"]
        for g in gaps
    )


def test_fix_missing_docstring(tmp_path):
    """fix_missing_docstring ajoute un docstring."""
    from scripts.v9_self_improving_loop import fix_missing_docstring
    script = tmp_path / "v9_test.py"
    script.write_text("from pathlib import Path\nx = 1\n")
    fixed = fix_missing_docstring(script)
    assert fixed is True
    content = script.read_text(encoding="utf-8")
    assert '"""v9_test — module V9."""' in content


def test_fix_missing_docstring_already_present(tmp_path):
    """fix_missing_docstring ne double pas si deja documente."""
    from scripts.v9_self_improving_loop import fix_missing_docstring
    script = tmp_path / "v9_test.py"
    script.write_text('"""Deja documente."""\nx = 1\n')
    fixed = fix_missing_docstring(script)
    assert fixed is False


def test_fix_missing_docstring_missing_file(tmp_path):
    """fix_missing_docstring retourne False si fichier absent."""
    from scripts.v9_self_improving_loop import fix_missing_docstring
    fixed = fix_missing_docstring(tmp_path / "absent.py")
    assert fixed is False


@pytest.mark.slow
def test_run_pytest_quick_smoke():
    """run_pytest_quick retourne tuple valide (slow : 180s)."""
    from scripts.v9_self_improving_loop import run_pytest_quick
    passed, failed, total = run_pytest_quick()
    assert passed >= 400
    assert total >= passed


def test_run_pytest_quick_skip():
    """run_pytest_quick est skip en CI rapide."""
    # Skip ce test, voir test_run_pytest_quick_smoke (slow).
    pytest.skip("slow test, run separately")


def test_main_loop_small_runs(tmp_path, monkeypatch):
    """main_loop execute N iterations sans crash."""
    import scripts.v9_self_improving_loop as sil
    monkeypatch.setattr(sil, "REPORT_PATH",
                        tmp_path / "test_self_improving.json")
    monkeypatch.setattr(sil, "_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    result = sil.main_loop(max_iterations=1, fix_docs=False, run_tests=False)
    assert "iterations" in result
    assert len(result["iterations"]) == 1