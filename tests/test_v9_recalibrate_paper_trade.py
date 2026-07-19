"""Tests recalibrage table TP/SL du PaperTradeResolver (réconciliation 2026-07-20)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import scripts.v9_recalibrate_paper_trade as recal


def _seed_decisions(db_path: Path, rows):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE decisions (timeframe TEXT, regime_type TEXT, "
        "resolution_pips REAL, resolved_at TEXT)"
    )
    conn.executemany(
        "INSERT INTO decisions (timeframe, regime_type, resolution_pips, resolved_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        rows,
    )
    conn.commit()
    conn.close()


def test_recalibrate_shows_diff(tmp_path, capsys):
    db = tmp_path / "f.db"
    _seed_decisions(db, [("M1", "range_calme", p) for p in (5, 6, 7, -30, -40)])
    recal.run(db, n_days=30, dry_run=True, assume_yes=False,
              config_path=tmp_path / "cfg.json")
    out = capsys.readouterr().out
    assert "avant" in out and "après" in out


def test_recalibrate_writes_json_config(tmp_path, monkeypatch):
    db = tmp_path / "f.db"
    _seed_decisions(db, [("M1", "range_calme", p) for p in (5, 6, 7, -30, -40)])
    cfg = tmp_path / "cfg.json"
    monkeypatch.setattr(recal, "DECISIONS_LOG", tmp_path / "DECISIONS_LOG.md")
    recal.run(db, n_days=30, dry_run=False, assume_yes=True, config_path=cfg)
    assert cfg.exists()
    import json
    payload = json.loads(cfg.read_text(encoding="utf-8"))
    assert payload["mode"] == "shadow"
    assert "table" in payload and len(payload["table"]) > 0


def test_recalibrate_appends_decisions_log(tmp_path, monkeypatch):
    db = tmp_path / "f.db"
    _seed_decisions(db, [("M1", "range_calme", p) for p in (5, 6, 7, -30, -40)])
    log = tmp_path / "DECISIONS_LOG.md"
    log.write_text("# LOG\n", encoding="utf-8")
    monkeypatch.setattr(recal, "DECISIONS_LOG", log)
    recal.run(db, n_days=30, dry_run=False, assume_yes=True,
              config_path=tmp_path / "cfg.json")
    content = log.read_text(encoding="utf-8")
    assert "Recalibrage table PaperTradeResolver" in content


def test_recalibrate_dry_run_does_not_write(tmp_path, monkeypatch):
    db = tmp_path / "f.db"
    _seed_decisions(db, [("M1", "range_calme", p) for p in (5, 6, 7, -30, -40)])
    cfg = tmp_path / "cfg.json"
    log = tmp_path / "DECISIONS_LOG.md"
    monkeypatch.setattr(recal, "DECISIONS_LOG", log)
    recal.run(db, n_days=30, dry_run=True, assume_yes=True, config_path=cfg)
    assert not cfg.exists()
    assert not log.exists()
