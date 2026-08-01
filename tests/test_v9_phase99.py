"""tests/test_v9_phase99.py — Phase 99 motion CEO 48H (Plan C).

Tests pour release_helper.
"""
import pytest


def test_version_constant():
    from scripts.v9_release_helper import VERSION
    assert VERSION == "9.5.0"


def test_tag_name():
    from scripts.v9_release_helper import TAG_NAME
    assert TAG_NAME == "v9.5.0"


def test_build_release_checklist():
    from scripts.v9_release_helper import build_release_checklist
    cl = build_release_checklist()
    assert len(cl) >= 5


def test_checklist_has_required():
    from scripts.v9_release_helper import build_release_checklist
    cl = build_release_checklist()
    assert any(c["required"] for c in cl)


def test_run_pre_release_checks():
    from scripts.v9_release_helper import run_pre_release_checks
    res = run_pre_release_checks()
    assert "version" in res
    assert "tag" in res
    assert "ready_for_tag" in res


def test_run_pre_release_checks_branch():
    from scripts.v9_release_helper import run_pre_release_checks
    res = run_pre_release_checks()
    assert res["branch"] == "feat/v9-foundation-clean"


def test_suggest_release_notes():
    from scripts.v9_release_helper import suggest_release_notes
    notes = suggest_release_notes(commits_n=50)
    assert "v9.5.0" in notes
    assert "PowerFlow V9" in notes
    assert len(notes) > 200


def test_main_demo(capsys, tmp_path):
    from scripts.v9_release_helper import main
    out = tmp_path / "release.json"
    exit_code = main(["--output", str(out)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RELEASE HELPER" in captured.out
    assert out.exists()