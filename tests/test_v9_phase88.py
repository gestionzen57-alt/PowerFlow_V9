"""tests/test_v9_phase88.py — Phase 88 motion CEO 48H (post-Plan C).

Tests pour pdf_monthly_report.
"""
import pytest
from pathlib import Path


def test_report_sections():
    from scripts.v9_pdf_monthly_report import REPORT_SECTIONS
    assert "summary" in REPORT_SECTIONS
    assert "trades" in REPORT_SECTIONS
    assert "edges" in REPORT_SECTIONS


def test_format_summary_html():
    from scripts.v9_pdf_monthly_report import format_summary_html
    html = format_summary_html(
        wr=0.85, n_trades=100, total_pips=500.0,
        sharpe=1.2, max_dd=50.0, pf=2.5,
    )
    assert "85.00%" in html or "85%" in html
    assert "100" in html
    assert "500" in html


def test_format_trades_table():
    from scripts.v9_pdf_monthly_report import format_trades_table
    trades = [
        {"timestamp": "2026-07-31", "symbol": "GBPUSD", "pips": 25.0,
         "is_win": True},
        {"timestamp": "2026-07-31", "symbol": "EURUSD", "pips": -8.0,
         "is_win": False},
    ]
    html = format_trades_table(trades)
    assert "<table" in html
    assert "GBPUSD" in html
    assert "EURUSD" in html


def test_format_edges_table():
    from scripts.v9_pdf_monthly_report import format_edges_table
    edges = [
        {"name": "L1 GBPUSD 11-13h", "wr": 0.95, "n_trades": 50,
         "total_pips": 250.0},
        {"name": "L8 NEUTRE blacklist", "wr": 0.25, "n_trades": 30,
         "total_pips": -200.0},
    ]
    html = format_edges_table(edges)
    assert "L1" in html
    assert "L8" in html


def test_generate_full_html():
    from scripts.v9_pdf_monthly_report import generate_full_html
    data = {
        "month": "2026-07",
        "wr": 0.85, "n_trades": 100, "total_pips": 500.0,
        "sharpe": 1.2, "max_dd": 50.0, "pf": 2.5,
        "trades": [
            {"timestamp": "2026-07-31", "symbol": "GBPUSD",
             "pips": 25.0, "is_win": True},
        ],
        "edges": [
            {"name": "L1", "wr": 0.95, "n_trades": 50,
             "total_pips": 250.0},
        ],
    }
    html = generate_full_html(data)
    assert "<!DOCTYPE html>" in html or "<html" in html
    assert "2026-07" in html
    assert "85" in html


def test_export_to_file(tmp_path):
    from scripts.v9_pdf_monthly_report import (
        generate_full_html, export_html,
    )
    data = {"month": "2026-07", "wr": 0.85, "n_trades": 100,
            "total_pips": 500.0, "sharpe": 1.2, "max_dd": 50.0,
            "pf": 2.5, "trades": [], "edges": []}
    html = generate_full_html(data)
    out = tmp_path / "report.html"
    ok = export_html(html, out)
    assert ok is True
    assert out.exists()


def test_export_to_file_creates_dir(tmp_path):
    from scripts.v9_pdf_monthly_report import (
        generate_full_html, export_html,
    )
    data = {"month": "2026-07", "wr": 0.85, "n_trades": 100,
            "total_pips": 500.0, "sharpe": 1.2, "max_dd": 50.0,
            "pf": 2.5, "trades": [], "edges": []}
    html = generate_full_html(data)
    nested = tmp_path / "subdir" / "r.html"
    ok = export_html(html, nested)
    assert ok is True
    assert nested.exists()


def test_html_minimal_size():
    from scripts.v9_pdf_monthly_report import generate_full_html
    data = {"month": "2026-07", "wr": 0.85, "n_trades": 100,
            "total_pips": 500.0, "sharpe": 1.2, "max_dd": 50.0,
            "pf": 2.5, "trades": [], "edges": []}
    html = generate_full_html(data)
    assert len(html) > 500  # au moins 500 chars


def test_main_demo(tmp_path, capsys):
    from scripts.v9_pdf_monthly_report import main
    exit_code = main(["--output", str(tmp_path / "report.html"),
                      "--month", "2026-07"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PDF MONTHLY" in captured.out or "MONTHLY REPORT" in captured.out