"""tests/test_v9_phase35.py — Phase 35 motion CEO 48h.

Tests pour v9_module_index.
"""
import pytest
from pathlib import Path


def test_extract_docstring_with_docstring(tmp_path):
    from scripts.v9_module_index import extract_docstring
    p = tmp_path / "test.py"
    p.write_text('"""v9_test — module V9."""\nx = 1\n')
    assert extract_docstring(p) == "v9_test — module V9."


def test_extract_docstring_no_docstring(tmp_path):
    from scripts.v9_module_index import extract_docstring
    p = tmp_path / "test.py"
    p.write_text("x = 1\n")
    assert extract_docstring(p) == "(no docstring)"


def test_extract_docstring_missing_file(tmp_path):
    from scripts.v9_module_index import extract_docstring
    assert extract_docstring(tmp_path / "absent.py") == "(read error)"


def test_extract_cli_info(tmp_path):
    from scripts.v9_module_index import extract_cli_info
    p = tmp_path / "test.py"
    p.write_text('''
import argparse
def main():
    parser = argparse.ArgumentParser(
        description="V9 test CLI description"
    )
''')
    info = extract_cli_info(p)
    assert "V9 test CLI" in info


def test_extract_cli_info_no_parser(tmp_path):
    from scripts.v9_module_index import extract_cli_info
    p = tmp_path / "test.py"
    p.write_text("x = 1\n")
    assert extract_cli_info(p) == ""


def test_has_tests(tmp_path):
    from scripts.v9_module_index import has_tests
    script = tmp_path / "v9_test.py"
    script.write_text("x = 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    test = tests / "test_v9_test.py"
    test.write_text("x = 1\n")
    assert has_tests(script, tests) is True


def test_has_tests_missing(tmp_path):
    from scripts.v9_module_index import has_tests
    script = tmp_path / "v9_test.py"
    script.write_text("x = 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    assert has_tests(script, tests) is False


def test_generate_index(tmp_path, monkeypatch):
    from scripts.v9_module_index import generate_index
    import scripts.v9_module_index as mi
    monkeypatch.setattr(mi, "_ROOT", tmp_path)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    # Creer 3 modules avec/sans tests
    (scripts_dir / "v9_test_a.py").write_text(
        '"""v9_test_a — first test module."""\nx = 1\n'
    )
    (scripts_dir / "v9_test_b.py").write_text("x = 1\n")
    (tests_dir / "test_v9_test_a.py").write_text("def test_x(): pass\n")
    output = tmp_path / "INDEX.md"
    result = generate_index(scripts_dir, tests_dir, output)
    assert result["n_modules"] == 2
    assert result["n_with_tests"] == 1
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "INDEX DES MODULES" in content
    assert "v9_test_a" in content


def test_generate_index_missing_scripts(monkeypatch, tmp_path):
    from scripts.v9_module_index import generate_index
    import scripts.v9_module_index as mi
    monkeypatch.setattr(mi, "_ROOT", tmp_path)
    result = generate_index(tmp_path / "absent", tmp_path / "tests",
                              tmp_path / "INDEX.md")
    assert "error" in result


def test_main_runs(monkeypatch, capsys, tmp_path):
    from scripts.v9_module_index import main
    import scripts.v9_module_index as mi
    monkeypatch.setattr(mi, "_ROOT", tmp_path)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (scripts_dir / "v9_x.py").write_text('"""v9_x — doc."""\n')
    monkeypatch.setattr(mi, "INDEX_PATH", tmp_path / "INDEX.md")
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MODULE INDEX GENERATOR" in captured.out