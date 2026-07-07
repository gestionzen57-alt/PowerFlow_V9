"""Tests unitaires — v9_daily_report.py (Phase 9.7+).

Couvre 5 cas minimum (brief) + helpers :
  1. test_report_structure
  2. test_snapshots_section_with_data
  3. test_decisions_section_win_loss
  4. test_paper_trades_section
  5. test_no_color_flag
  6. test_json_output
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.db_schema import init_db
from core.v9.decision_db import init_decision_db
from core.v9.paper_trades_db import init_paper_trades_db
from scripts import v9_daily_report as dr


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "v9_daily_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)
    init_decision_db(path)
    init_paper_trades_db(path)
    return path


def _insert_decision(
    db_path: Path,
    *,
    is_win: int | None = None,
    direction: str = "haussiere",
    timestamp: str = "2026-07-07T10:00:00+00:00",
) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at,"
            " is_win, resolution_pips, resolved_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"dec_{uuid.uuid4().hex[:8]}", "1.0", timestamp,
                f"snap_{uuid.uuid4().hex[:8]}", "sig_test", "surveiller",
                "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", direction, 80, "[]", "{}", "live", timestamp,
                is_win,
                10.0 if is_win == 1 else (-5.0 if is_win == 0 else None),
                timestamp if is_win is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_paper_trade(
    db_path: Path,
    *,
    closed: bool = False,
) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO paper_trades ("
            " trade_id, snapshot_id, direction, confiance,"
            " principes_source, opened_at, closed_at, pips_simulated, is_win, risk_go_context"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                f"pt_{uuid.uuid4().hex[:8]}",
                f"snap_{uuid.uuid4().hex[:8]}",
                "haussiere", 85, "[]",
                "2026-07-07T10:00:00+00:00",
                "2026-07-07T11:00:00+00:00" if closed else None,
                10.0 if closed else None,
                1 if closed else None,
                "{}",
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---------- Tests ----------


def test_report_structure(db_path: Path) -> None:
    """Le rapport contient toutes les sections attendues."""
    report = dr.build_report(db_path=db_path)
    expected = {
        "generated_at", "snapshots", "signals", "decisions",
        "paper_trades", "coherence", "scoring", "telegram_logs",
    }
    assert set(report.keys()) >= expected
    assert isinstance(report["snapshots"], dict)
    assert isinstance(report["signals"], dict)
    assert isinstance(report["decisions"], dict)


def test_snapshots_section_with_data(db_path: Path) -> None:
    """Section snapshots : compte les rangées forces_snapshots."""
    # Insertion directe d'un snapshot
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO forces_snapshots ("
            " snapshot_id, schema_version, timestamp, source,"
            " symbol, timeframe, bar_time, is_closed_bar,"
            " open, high, low, close, tick_volume, spread_points, spread_price,"
            " bid, ask, mid,"
            " force_usd, force_gbp, force_eur, force_jpy,"
            " force_cad, force_chf, force_aud, force_nzd,"
            " direction, vitesse,"
            " croisement_detecte, croisement_partenaire, croisement_direction,"
            " recroisement_detecte, recroisement_contexte,"
            " rejet_repulsion_detecte, rejet_intensite,"
            " compression_extension_etat, compression_extension_intensite,"
            " stale, age_ms, stale_threshold_ms, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "snap_test", "1.0", "2026-07-07T10:00:00+00:00", "MT4_SDI",
                "GBPUSD", "M15", 1, True,
                1.0, 1.0, 1.0, 1.0, 100, 10, 0.00010,
                1.0, 1.0, 1.0,
                50.0, 50.0, 50.0, 50.0,
                50.0, 50.0, 50.0, 50.0,
                "haussiere", 0.0,
                False, None, None,
                False, None,
                False, 0.0,
                "neutre", 0.0,
                False, 0, 1000, "2026-07-07T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    report = dr.build_report(db_path=db_path)
    s = report["snapshots"]
    assert s["total_snapshots"] >= 1
    assert s["last_snapshot"] == "2026-07-07T10:00:00+00:00"
    assert "M15" in s["timeframes_actifs_24h"]


def test_decisions_section_win_loss(db_path: Path) -> None:
    """Section decisions : compte WIN / LOSS / unresolved."""
    _insert_decision(db_path, is_win=1, direction="haussiere")
    _insert_decision(db_path, is_win=1, direction="baissiere")
    _insert_decision(db_path, is_win=0, direction="haussiere")
    _insert_decision(db_path, is_win=None, direction="neutre")

    report = dr.build_report(db_path=db_path)
    dec = report["decisions"]
    assert dec["win_total"] == 2
    assert dec["loss_total"] == 1
    assert dec["unresolved_total"] == 1
    assert dec["winrate_pct"] == pytest.approx(2 / 3 * 100, rel=1e-3)


def test_paper_trades_section(db_path: Path) -> None:
    """Section paper_trades : compte ouverts/fermés."""
    _insert_paper_trade(db_path, closed=False)
    _insert_paper_trade(db_path, closed=False)
    _insert_paper_trade(db_path, closed=True)

    report = dr.build_report(db_path=db_path)
    pt = report["paper_trades"]
    assert pt["available"] is True
    assert pt["open"] == 2
    assert pt["closed"] == 1


def test_no_color_flag(capsys) -> None:
    """--no-color fonctionne (pas d'exception, sortie texte)."""
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["v9_daily_report", "--no-color"]
        rc = dr.main()
    finally:
        sys.argv = old_argv
    captured = capsys.readouterr()
    assert rc == 0
    assert "V9 Daily Report" in captured.out


def test_json_output(capsys) -> None:
    """--json produit du JSON parsable."""
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["v9_daily_report", "--json"]
        rc = dr.main()
    finally:
        sys.argv = old_argv
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "generated_at" in data
    assert "snapshots" in data
    assert rc == 0


def test_format_console_no_color_works() -> None:
    """Le format console produit un rapport lisible."""
    report = {
        "generated_at": "2026-07-07T10:00:00+00:00",
        "snapshots": {"total_snapshots": 100, "snapshots_24h": 50,
                      "last_snapshot": "2026-07-07T10:00:00+00:00",
                      "timeframes_actifs_24h": ["M15"]},
        "signals": {"signaux_directionnels_total": 10,
                    "signaux_24h_total": 5,
                    "signaux_24h_directionnels": 3},
        "decisions": {"decisions_24h": 5, "decisions_24h_directionnelles": 3,
                      "win_total": 1, "loss_total": 1, "unresolved_total": 8,
                      "winrate_pct": 50.0},
        "paper_trades": {"available": True, "open": 2, "closed": 1},
        "coherence": {"available": True,
                      "summary": {"counts": {"ok": 5, "warning": 1, "error": 1},
                                  "exit_code": 2},
                      "details": [
                          {"check": "x", "status": "OK", "count": 0},
                      ]},
        "scoring": {"available": True, "total_decisions_resolues": 2,
                    "principes_scores": [
                        {"principle_id": "P1", "nb": 2, "win_rate": 100.0},
                    ]},
        "telegram_logs": {"available": True, "messages_total": 10,
                          "messages_24h": 5, "log_path": "/tmp/log"},
    }
    out = dr.format_console(report, use_color=False)
    assert "V9 Daily Report" in out
    assert "100" in out  # snapshots
    assert "WIN" in out
    assert "P1" in out
    assert "✓" in out or "  ✓" in out  # au moins 1 check OK


def test_format_console_graceful_degrade() -> None:
    """Le format console gère les sections indisponibles sans crash."""
    report = {
        "generated_at": "2026-07-07T10:00:00+00:00",
        "snapshots": {"total_snapshots": 0, "snapshots_24h": 0,
                      "last_snapshot": None, "timeframes_actifs_24h": []},
        "signals": {"signaux_directionnels_total": 0,
                    "signaux_24h_total": 0, "signaux_24h_directionnels": 0},
        "decisions": {"decisions_24h": 0, "decisions_24h_directionnelles": 0,
                      "win_total": 0, "loss_total": 0, "unresolved_total": 0,
                      "winrate_pct": None},
        "paper_trades": {"available": False},
        "coherence": {"available": False, "error": "test"},
        "scoring": {"available": False, "error": "test"},
        "telegram_logs": {"available": False},
    }
    out = dr.format_console(report, use_color=False)
    assert "absente" in out
    assert "indisponible" in out


def test_telegram_logs_parses() -> None:
    """Parse basique du log Telegram (best-effort)."""
    section = dr.section_telegram_logs()
    # Log peut exister ou pas sur le système de test — on vérifie juste
    # que le retour est un dict avec une clé 'available'.
    assert "available" in section


def test_table_exists_helper(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        assert dr._table_exists(conn, "decisions") is True
        assert dr._table_exists(conn, "ghost_table") is False
    finally:
        conn.close()


def test_coherence_section_integrated(db_path: Path) -> None:
    """La section coherence appelle validate-coherence via importlib."""
    report = dr.build_report(db_path=db_path)
    coh = report["coherence"]
    assert coh["available"] is True
    assert "summary" in coh
    assert "details" in coh
    assert len(coh["details"]) == 7  # les 7 checks


def test_scoring_section_integrated(db_path: Path) -> None:
    """La section scoring appelle v9_scoring via import standard."""
    report = dr.build_report(db_path=db_path)
    sco = report["scoring"]
    assert sco["available"] is True
    assert sco["total_decisions_resolues"] == 0