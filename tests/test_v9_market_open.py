"""Tests — scripts/v9_market_open.py (procédure --market-open).

Couvre les fonctions pures/DB de lecture (plausibilité AUD, taux de stale,
dernier snapshot) sur une DB SQLite temporaire, et l'orchestration
`run_market_open` avec les dépendances (boot, health snapshot,
mini-checkpoint) mockées.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts import v9_market_open


def _make_db(tmp_path: Path, rows: list[dict]) -> Path:
    db_path = tmp_path / "v9_forces.db"
    conn = sqlite3.connect(str(db_path))
    columns = [
        "id INTEGER PRIMARY KEY", "created_at TEXT", "symbol TEXT", "timeframe TEXT",
        "stale INTEGER", "force_usd REAL", "force_gbp REAL", "force_eur REAL",
        "force_jpy REAL", "force_cad REAL", "force_chf REAL", "force_aud REAL", "force_nzd REAL",
    ]
    conn.execute(f"CREATE TABLE forces_snapshots ({', '.join(columns)})")
    for row in rows:
        conn.execute(
            "INSERT INTO forces_snapshots "
            "(created_at, symbol, timeframe, stale, force_usd, force_gbp, force_eur, "
            "force_jpy, force_cad, force_chf, force_aud, force_nzd) "
            "VALUES (:created_at, :symbol, :timeframe, :stale, :force_usd, :force_gbp, "
            ":force_eur, :force_jpy, :force_cad, :force_chf, :force_aud, :force_nzd)",
            row,
        )
    conn.commit()
    conn.close()
    return db_path


def _row(**overrides) -> dict:
    base = dict(
        created_at="2026-07-05T21:00:00", symbol="GBPUSD", timeframe="M1", stale=0,
        force_usd=50.0, force_gbp=50.0, force_eur=60.0, force_jpy=50.0,
        force_cad=50.0, force_chf=50.0, force_aud=58.0, force_nzd=62.0,
    )
    base.update(overrides)
    return base


# ── check_aud_plausibility ─────────────────────────────────
def test_aud_plausibility_within_tolerance() -> None:
    row = _row(force_eur=60.0, force_nzd=62.0, force_aud=58.0)
    plausible, msg = v9_market_open.check_aud_plausibility(row)
    assert plausible is True
    assert "plausible" in msg


def test_aud_plausibility_out_of_range() -> None:
    row = _row(force_eur=63.6, force_nzd=62.3, force_aud=39.6)
    plausible, msg = v9_market_open.check_aud_plausibility(row, tolerance=15.0)
    assert plausible is False
    assert "HORS INTERVALLE" in msg


def test_aud_plausibility_at_exact_boundary() -> None:
    # EUR/NZD = (60, 70) -> tolerance 15 -> [45, 85] ; AUD=45 doit passer.
    row = _row(force_eur=60.0, force_nzd=70.0, force_aud=45.0)
    plausible, _ = v9_market_open.check_aud_plausibility(row, tolerance=15.0)
    assert plausible is True


def test_aud_plausibility_missing_field_is_ignored() -> None:
    row = {"force_eur": 60.0, "force_nzd": 62.0}  # force_aud absent
    plausible, msg = v9_market_open.check_aud_plausibility(row)
    assert plausible is True
    assert "ignoree" in msg


# ── latest_forces_row / stale_rate (DB reelle temporaire) ──
def test_latest_forces_row_returns_most_recent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _make_db(tmp_path, [_row(symbol="EURUSD"), _row(symbol="GBPUSD")])
    monkeypatch.setattr(v9_market_open, "DB_PATH", db_path)

    row = v9_market_open.latest_forces_row()
    assert row is not None
    assert row["symbol"] == "GBPUSD"


def test_latest_forces_row_missing_db_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_market_open, "DB_PATH", tmp_path / "absent.db")
    assert v9_market_open.latest_forces_row() is None


def test_stale_rate_computes_percentage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_row(stale=1), _row(stale=0), _row(stale=0), _row(stale=0)]
    db_path = _make_db(tmp_path, rows)
    monkeypatch.setattr(v9_market_open, "DB_PATH", db_path)

    total, stale, rate = v9_market_open.stale_rate()
    assert total == 4
    assert stale == 1
    assert rate == pytest.approx(25.0)


def test_stale_rate_missing_db_returns_zeros(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_market_open, "DB_PATH", tmp_path / "absent.db")
    assert v9_market_open.stale_rate() == (0, 0, 0.0)


# ── run_market_open orchestration (mocked) ─────────────────
def _snapshot(**overrides) -> dict:
    base = {
        "timestamp_utc": "2026-07-05T21:00:00+00:00", "python_ok": True, "modules_ok": True,
        "modules_count": 15, "db_ok": True, "port_available": True, "server_running": True,
        "server_pid": 1, "market_open": False, "market_session": "closed", "db_counts": {},
        "git_branch": "feat/v9-foundation-clean", "git_last_commit": "abc1234 test",
    }
    base.update(overrides)
    return base


def test_run_market_open_stops_if_boot_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_market_open, "read_health_snapshot", lambda: _snapshot())
    monkeypatch.setattr(v9_market_open, "run_boot", lambda write_checkpoint: 1)

    def _boom(**kwargs):
        raise AssertionError("ne doit pas ecrire de checkpoint si le boot echoue")

    monkeypatch.setattr(v9_market_open, "generate_mini_checkpoint", _boom)

    assert v9_market_open.run_market_open() == 1


def test_run_market_open_success_writes_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v9_market_open, "read_health_snapshot", lambda: _snapshot())
    monkeypatch.setattr(v9_market_open, "run_boot", lambda write_checkpoint: 0)
    monkeypatch.setattr(v9_market_open, "health_snapshot_to_observed_lines", lambda snap: ["obs"])
    monkeypatch.setattr(v9_market_open, "latest_forces_row", lambda: None)
    monkeypatch.setattr(v9_market_open, "stale_rate", lambda: (10, 1, 10.0))

    calls = []
    monkeypatch.setattr(
        v9_market_open, "generate_mini_checkpoint",
        lambda **kwargs: calls.append(kwargs) or tmp_path / "dummy.md",
    )

    assert v9_market_open.run_market_open() == 0
    assert len(calls) == 1
    assert calls[0]["kind"] == "market_open"


def test_run_market_open_flags_aud_anomaly_as_ecart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v9_market_open, "read_health_snapshot", lambda: _snapshot())
    monkeypatch.setattr(v9_market_open, "run_boot", lambda write_checkpoint: 0)
    monkeypatch.setattr(v9_market_open, "health_snapshot_to_observed_lines", lambda snap: [])
    monkeypatch.setattr(
        v9_market_open, "latest_forces_row",
        lambda: _row(force_eur=63.6, force_nzd=62.3, force_aud=39.6),
    )
    monkeypatch.setattr(v9_market_open, "stale_rate", lambda: (10, 0, 0.0))

    calls = []
    monkeypatch.setattr(
        v9_market_open, "generate_mini_checkpoint",
        lambda **kwargs: calls.append(kwargs) or tmp_path / "dummy.md",
    )

    assert v9_market_open.run_market_open() == 0
    assert "HORS INTERVALLE" in calls[0]["ecart"]
