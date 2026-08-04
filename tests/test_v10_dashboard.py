"""V10 Dashboard — tests unitaires (Phase 8 Edge Fund).

Couvre les 4 obligations de la Phase 8 + invariants :
  1. test_generate_dashboard_creates_html
  2. test_currency_view_with_data
  3. test_confluence_heatmap_renders
  4. test_signals_view_lists_active
  5. test_backtest_view_passes_threshold
  6. test_backtest_view_fails_threshold
  7. test_history_24h_only_recent
  8. test_no_external_dependency
  9. test_r10_no_ordre_transmis
 10. test_fail_open_no_data

Total ≥ 10 tests.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.v10_dashboard import (  # noqa: E402
    generate_dashboard,
    _read_json_safely,
    _read_signals,
    _read_history_24h,
    _currency_view,
    _confluence_view,
    _signals_view,
    _backtest_view,
    HTML_TEMPLATE,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def data_dir(tmp_path) -> Path:
    """Répertoire data temporaire avec snapshot et backtest JSON."""
    signals = {
        "timestamp": "2026-08-04T12:00:00Z",
        "n_setups_processed": 28,
        "n_signals_found": 2,
        "signals": [
            {
                "pair": "EURUSD",
                "timeframe": "H1",
                "setup_level": "A1",
                "direction": "BULLISH",
                "composite_score": 0.95,
                "confluence_score": 0.92,
                "vsa_state": "MARKUP",
                "bos": "BOS_BULL",
                "session": "LONDON",
                "cot": {"3_decide": "Signal A1 — high conviction."},
            },
            {
                "pair": "USDJPY",
                "timeframe": "M30",
                "setup_level": "A2",
                "direction": "BEARISH",
                "composite_score": 0.78,
                "confluence_score": 0.74,
                "vsa_state": "MARKDOWN",
                "bos": "NONE",
                "session": "NY",
                "cot": {"3_decide": "Signal A2 — medium conviction."},
            },
        ],
        "by_level": {"A1": 1, "A2": 1, "A3": 0, "NONE": 26},
    }
    (tmp_path / "v10_signals_latest.json").write_text(
        json.dumps(signals, indent=2), encoding="utf-8"
    )

    backtest = {
        "kpi": {
            "n_trades": 200,
            "win_rate": 0.62,
            "avg_rr": 1.9,
            "sharpe": 1.5,
            "max_drawdown_pct": 0.08,
            "total_pips": 1240,
            "passed_thresholds": True,
        }
    }
    (tmp_path / "v10_backtest_kpis_latest.json").write_text(
        json.dumps(backtest, indent=2), encoding="utf-8"
    )

    # History 24h
    now = datetime.now(timezone.utc)
    lines = []
    for i in range(10):
        ts = (now - timedelta(hours=i, minutes=10)).isoformat()
        lines.append(json.dumps({
            "timestamp": ts,
            "pair": "EURUSD",
            "timeframe": "H1",
            "setup_level": "A1" if i % 2 == 0 else "A2",
        }))
    (tmp_path / "v10_signals_history.jsonl").write_text("\n".join(lines), encoding="utf-8")
    return tmp_path


# ─────────────────────────────────────────────────────────────────────
# 1. test_generate_dashboard_creates_html
# ─────────────────────────────────────────────────────────────────────
def test_generate_dashboard_creates_html(tmp_path, data_dir):
    output = tmp_path / "dashboard.html"
    res = generate_dashboard(
        data_dir=data_dir,
        output=output,
        git_head="test_head",
    )
    assert res == output
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "V10 Edge Fund Dashboard" in content
    assert "test_head" in content


# ─────────────────────────────────────────────────────────────────────
# 2. test_currency_view_with_data
# ─────────────────────────────────────────────────────────────────────
def test_currency_view_with_data():
    cur = {
        "EURUSD": {"close": 1.1000, "score": 75.0},
        "GBPUSD": {"close": 1.2500, "score": 50.0},
    }
    html = _currency_view(cur)
    assert "EURUSD" in html
    assert "75.0" in html
    assert "GBPUSD" in html


def test_currency_view_handles_missing():
    html = _currency_view(None)
    assert "muted" in html or "absent" in html.lower() or "R6" in html


# ─────────────────────────────────────────────────────────────────────
# 3. test_confluence_heatmap_renders
# ─────────────────────────────────────────────────────────────────────
def test_confluence_heatmap_renders(data_dir):
    snap = _read_signals(data_dir)
    html = _confluence_view(snap)
    # TFs présents en en-tête
    assert "M1" in html
    assert "D1" in html
    # Pairs observées
    assert "EURUSD" in html
    assert "USDJPY" in html


# ─────────────────────────────────────────────────────────────────────
# 4. test_signals_view_lists_active
# ─────────────────────────────────────────────────────────────────────
def test_signals_view_lists_active(data_dir):
    snap = _read_signals(data_dir)
    html = _signals_view(snap)
    # 2 signaux actifs
    assert "EURUSD" in html
    assert "USDJPY" in html
    assert "BULLISH" in html or "BEARISH" in html
    assert "high conviction" in html or "medium conviction" in html


def test_signals_view_no_signal():
    html = _signals_view({"n_signals_found": 0, "signals": []})
    assert "Aucun signal" in html or "no signal" in html.lower()


# ─────────────────────────────────────────────────────────────────────
# 5. test_backtest_view_passes_threshold
# ─────────────────────────────────────────────────────────────────────
def test_backtest_view_passes_threshold():
    data = {"kpi": {"passed_thresholds": True, "win_rate": 0.62, "avg_rr": 1.9,
                     "sharpe": 1.5, "max_drawdown_pct": 0.08,
                     "n_trades": 200, "total_pips": 1240.0}}
    html = _backtest_view(data, [])
    assert "VERDICT" in html
    assert "PASS" in html
    assert "62" in html  # 0.62 → affiché "62.00%"
    assert "1.90" in html
    assert "1.50" in html


# ─────────────────────────────────────────────────────────────────────
# 6. test_backtest_view_fails_threshold
# ─────────────────────────────────────────────────────────────────────
def test_backtest_view_fails_threshold():
    data = {"kpi": {"passed_thresholds": False, "win_rate": 0.45, "avg_rr": 0.5,
                     "sharpe": -14, "max_drawdown_pct": 2.99,
                     "n_trades": 337, "total_pips": -865.2}}
    html = _backtest_view(data, [])
    assert "VERDICT" in html
    assert "FAIL" in html


# ─────────────────────────────────────────────────────────────────────
# 7. test_history_24h_only_recent
# ─────────────────────────────────────────────────────────────────────
def test_history_24h_only_recent(data_dir):
    history = _read_history_24h(data_dir)
    assert len(history) >= 5  # 10 entrées toutes < 24h
    # Toutes les entrées doivent être après maintenant - 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for h in history:
        ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
        assert ts >= cutoff


def test_history_filters_old_entries(tmp_path):
    """Les entrées > 24h doivent être exclues."""
    now = datetime.now(timezone.utc)
    lines = [
        json.dumps({"timestamp": (now - timedelta(hours=1)).isoformat(),
                    "pair": "EURUSD", "setup_level": "A1"}),  # OK
        json.dumps({"timestamp": (now - timedelta(hours=26)).isoformat(),
                    "pair": "GBPUSD", "setup_level": "A2"}),  # KO
    ]
    (tmp_path / "v10_signals_history.jsonl").write_text("\n".join(lines), encoding="utf-8")
    history = _read_history_24h(tmp_path)
    assert len(history) == 1
    assert history[0]["pair"] == "EURUSD"


# ─────────────────────────────────────────────────────────────────────
# 8. test_no_external_dependency — R6 + R10 : zéro dépendance exotique
# ─────────────────────────────────────────────────────────────────────
def test_no_external_dependency():
    """Le dashboard ne doit utiliser que stdlib + pathlib."""
    src = Path(ROOT / "dashboard" / "v10_dashboard.py").read_text(encoding="utf-8")
    # Imports interdits : streamlit, dash, panel, gradio, plotly, etc.
    forbidden = ("import streamlit", "from streamlit",
                 "import dash", "from dash",
                 "import panel", "from panel",
                 "import gradio", "from gradio",
                 "import plotly", "from plotly")
    for f in forbidden:
        assert f not in src, f"Phase 8 violation : {f}"


# ─────────────────────────────────────────────────────────────────────
# 9. test_r10_no_ordre_transmis
# ─────────────────────────────────────────────────────────────────────
def test_r10_no_ordre_transmis():
    src = Path(ROOT / "dashboard" / "v10_dashboard.py").read_text(encoding="utf-8")
    forbidden = ("order_send", "positions_open", "trade_request",
                 "mt5.", "execute_order")
    for f in forbidden:
        assert f not in src, f"R10 violation : {f}"


# ─────────────────────────────────────────────────────────────────────
# 10. test_fail_open_no_data
# ─────────────────────────────────────────────────────────────────────
def test_fail_open_no_data(tmp_path):
    """Si data_dir vide, le dashboard doit quand même se générer (R6)."""
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()
    output = tmp_path / "dash.html"
    res = generate_dashboard(data_dir=empty_dir, output=output, git_head="empty")
    assert res.exists()
    content = output.read_text(encoding="utf-8")
    assert "V10 Edge Fund Dashboard" in content
    # Mention "absent" ou "vide" attendue sur les sections sans data
    assert "muted" in content or "absent" in content.lower()


def test_read_json_safely_handles_corrupt(tmp_path):
    """Fichier JSON corrompu → None (R6)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    res = _read_json_safely(bad)
    assert res is None


def test_read_json_safely_handles_missing(tmp_path):
    """Fichier absent → None (R6)."""
    res = _read_json_safely(tmp_path / "nonexistent.json")
    assert res is None


def test_html_template_contains_all_doctrine_markers():
    """Le template HTML doit contenir toutes les références R1-R10."""
    for k in ("V10 Edge Fund", "Phase 8", "Doctrine", "R10",
              "R7 tests", "capital protégé", "R9 audit"):
        assert k in HTML_TEMPLATE or k.lower() in HTML_TEMPLATE.lower(), (
            f"Marqueur manquant : {k}"
        )
