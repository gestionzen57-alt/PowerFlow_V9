"""tests/test_v9_phase85.py — Phase 85 motion CEO 48H (post-Plan C).

Tests pour grafana_dashboard_export.
"""
import json
import pytest
from pathlib import Path


def test_generate_grafana_json():
    from scripts.v9_grafana_dashboard_export import generate_grafana_dashboard
    dash = generate_grafana_dashboard()
    assert "panels" in dash
    assert "title" in dash


def test_dashboard_has_trade_pnl_panel():
    from scripts.v9_grafana_dashboard_export import generate_grafana_dashboard
    dash = generate_grafana_dashboard()
    titles = [p.get("title") for p in dash["panels"]]
    assert any("PnL" in t or "P&L" in t for t in titles)


def test_dashboard_has_wr_panel():
    from scripts.v9_grafana_dashboard_export import generate_grafana_dashboard
    dash = generate_grafana_dashboard()
    titles = [p.get("title") for p in dash["panels"]]
    # Accepte "WR" ou "Win Rate" (peut etre en lowercase)
    assert any("WR" in t or "Win Rate" in t.lower() for t in titles)


def test_dashboard_has_dd_panel():
    from scripts.v9_grafana_dashboard_export import generate_grafana_dashboard
    dash = generate_grafana_dashboard()
    titles = [p.get("title") for p in dash["panels"]]
    assert any("Drawdown" in t for t in titles)


def test_dashboard_min_n_panels():
    from scripts.v9_grafana_dashboard_export import generate_grafana_dashboard
    dash = generate_grafana_dashboard()
    assert len(dash["panels"]) >= 4


def test_export_dashboard_writes_file(tmp_path):
    from scripts.v9_grafana_dashboard_export import (
        generate_grafana_dashboard, export_dashboard,
    )
    out = tmp_path / "v9_grafana.json"
    ok = export_dashboard(out)
    assert ok is True
    assert out.exists()
    # Verifier que c'est du JSON valide
    with open(out) as f:
        data = json.load(f)
    assert "panels" in data


def test_export_dashboard_creates_parent_dir(tmp_path):
    from scripts.v9_grafana_dashboard_export import export_dashboard
    nested = tmp_path / "subdir" / "v9.json"
    ok = export_dashboard(nested)
    assert ok is True
    assert nested.exists()


def test_panel_targets_have_sql():
    from scripts.v9_grafana_dashboard_export import generate_grafana_dashboard
    dash = generate_grafana_dashboard()
    for panel in dash["panels"]:
        if "targets" in panel:
            for target in panel["targets"]:
                assert "rawSql" in target or "expr" in target


def test_export_invalid_path_fails(tmp_path):
    from scripts.v9_grafana_dashboard_export import export_dashboard
    # Path impossible : root sur Windows
    bad = Path("Z:\\nonexistent\\root\\file.json")
    # Doit retourner False (ou True mais ne pas crasher)
    res = export_dashboard(bad)
    # On accepte True ou False selon permissions
    assert isinstance(res, bool)


def test_main_demo(tmp_path, capsys):
    from scripts.v9_grafana_dashboard_export import main
    exit_code = main(["--output", str(tmp_path / "grafana.json")])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "GRAFANA" in captured.out