"""tests/test_v9_phase91.py — Phase 91 motion CEO 48H (post-Plan C).

Tests pour onboarding_doc_gen.
"""
import pytest
from pathlib import Path


def test_sections_defined():
    from scripts.v9_onboarding_doc_gen import SECTIONS
    assert "quickstart" in SECTIONS
    assert "kill_switches" in SECTIONS
    assert "live_deploy" in SECTIONS
    assert "troubleshooting" in SECTIONS


def test_generate_quickstart():
    from scripts.v9_onboarding_doc_gen import generate_quickstart
    md = generate_quickstart()
    assert "# Quickstart" in md or "## Quickstart" in md
    assert "pytest" in md.lower()


def test_generate_kill_switches_doc():
    from scripts.v9_onboarding_doc_gen import generate_kill_switches_doc
    md = generate_kill_switches_doc()
    assert "V9_TRADE_ENGINE_ENABLED" in md
    assert "V9_KILL_DD_PIPS" in md


def test_generate_live_deploy_doc():
    from scripts.v9_onboarding_doc_gen import generate_live_deploy_doc
    md = generate_live_deploy_doc()
    assert "FTMO" in md or "live" in md.lower()
    assert "MT4" in md or "broker" in md.lower()


def test_generate_troubleshooting_doc():
    from scripts.v9_onboarding_doc_gen import generate_troubleshooting_doc
    md = generate_troubleshooting_doc()
    assert "DB" in md or "Telegram" in md
    assert len(md) > 100


def test_generate_full_doc():
    from scripts.v9_onboarding_doc_gen import generate_full_doc
    md = generate_full_doc()
    assert len(md) > 500


def test_export_to_file(tmp_path):
    from scripts.v9_onboarding_doc_gen import (
        generate_full_doc, export_doc,
    )
    md = generate_full_doc()
    out = tmp_path / "ONBOARDING.md"
    ok = export_doc(md, out)
    assert ok is True
    assert out.exists()


def test_export_creates_dir(tmp_path):
    from scripts.v9_onboarding_doc_gen import (
        generate_full_doc, export_doc,
    )
    md = generate_full_doc()
    nested = tmp_path / "subdir" / "ONBOARDING.md"
    ok = export_doc(md, nested)
    assert ok is True
    assert nested.exists()


def test_kill_switch_doc_has_warnings():
    from scripts.v9_onboarding_doc_gen import generate_kill_switches_doc
    md = generate_kill_switches_doc()
    assert "⚠" in md or "WARNING" in md or "warning" in md.lower()


def test_troubleshooting_has_known_issues():
    from scripts.v9_onboarding_doc_gen import generate_troubleshooting_doc
    md = generate_troubleshooting_doc()
    # Au moins 3 problemes connus documentees
    assert md.count("\n- ") >= 3 or md.count("\n## ") >= 3


def test_main_demo(tmp_path, capsys):
    from scripts.v9_onboarding_doc_gen import main
    exit_code = main(["--output", str(tmp_path / "ONBOARDING.md")])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ONBOARDING" in captured.out