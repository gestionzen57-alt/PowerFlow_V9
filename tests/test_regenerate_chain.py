"""Tests — idempotence et sûreté du rejeu de scripts/regenerate_chain.py.

Couvre le bug de non-idempotence : scene_id/behavior_id/window_id/
exploitability_id/signal_id/decision_id sont générés avec un suffixe
aléatoire (uuid4) à chaque appel de run_chain(), donc rejouer la chaîne
sur une DB déjà peuplée duplique silencieusement les tables dérivées.
Le fix impose --replace-derived (delete ciblé + régénération complète)
ou un refus explicite par défaut si la DB dérivée n'est pas vide.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from scripts.regenerate_chain import DERIVED_TABLES, main

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


def _insert_forces_snapshot(db_path: Path, *, bar_time: int, force_gbp: float = 40.0) -> str:
    snapshot_id = f"v9-regen-{uuid.uuid4().hex[:10]}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": f"2026-07-05T14:{bar_time:02d}:00.000Z",
        "source": "MT4_SDI",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "bar_time": bar_time,
        "is_closed_bar": True,
        "high": 1.0900, "low": 1.0800, "close": 1.0860,
        "force_usd": 50.0, "force_gbp": force_gbp, "force_eur": 65.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 2.5,
        "compression_extension_etat": "neutre", "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": f"2026-07-05T14:{bar_time:02d}:00.100Z",
    })
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(FORCES_COLUMNS)
        placeholders = ", ".join(["?"] * len(FORCES_COLUMNS))
        conn.execute(
            f"INSERT INTO forces_snapshots ({col_names}) VALUES ({placeholders})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return snapshot_id


def _seed(db_path: Path, n: int = 2) -> None:
    init_db(db_path)
    for i in range(n):
        _insert_forces_snapshot(db_path, bar_time=i, force_gbp=40.0 + i * 5)


def _counts(db_path: Path) -> dict[str, int]:
    conn = get_connection(db_path)
    try:
        result = {}
        for table in DERIVED_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
            ).fetchone()
            result[table] = (
                conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if row else 0
            )
        return result
    finally:
        conn.close()


def test_first_run_on_empty_db_populates_all_layers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Shadow mode désactivé dans ce test (le shadow génère des signaux/
    décisions supplémentaires qui fausseraient les comptes — le test porte
    sur la régénération, pas sur le shadow)."""
    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "0")
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    _seed(db_path, n=2)

    exit_code = main([], db_path=db_path, memory_dir=memory_dir)

    assert exit_code == 0
    counts = _counts(db_path)
    assert counts["scenes"] == 2
    assert counts["behaviors"] == 2
    assert counts["windows"] == 2
    assert counts["exploitability"] == 2
    assert counts["signals"] == 2
    assert counts["decisions"] == 2
    assert counts["regime_snapshots"] == 2 * len(DEVISES)
    assert counts["principle_evaluations"] > 0


def test_second_run_without_flag_refuses_and_does_not_duplicate(tmp_path: Path) -> None:
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    _seed(db_path, n=2)

    assert main([], db_path=db_path, memory_dir=memory_dir) == 0
    before = _counts(db_path)

    exit_code = main([], db_path=db_path, memory_dir=memory_dir)

    assert exit_code == 2
    assert _counts(db_path) == before


def test_replace_derived_regenerates_without_duplication(tmp_path: Path) -> None:
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    _seed(db_path, n=2)

    assert main([], db_path=db_path, memory_dir=memory_dir) == 0
    before = _counts(db_path)

    exit_code = main(["--replace-derived"], db_path=db_path, memory_dir=memory_dir)

    assert exit_code == 0
    assert _counts(db_path) == before


def test_dry_run_never_writes(tmp_path: Path) -> None:
    db_path = tmp_path / "v9_forces.db"
    memory_dir = tmp_path / "memory"
    _seed(db_path, n=2)

    assert main(["--dry-run"], db_path=db_path, memory_dir=memory_dir) == 0
    assert _counts(db_path) == {table: 0 for table in DERIVED_TABLES}

    assert main([], db_path=db_path, memory_dir=memory_dir) == 0
    populated = _counts(db_path)

    assert main(["--dry-run"], db_path=db_path, memory_dir=memory_dir) == 0
    assert _counts(db_path) == populated

    assert main(["--dry-run", "--replace-derived"], db_path=db_path, memory_dir=memory_dir) == 0
    assert _counts(db_path) == populated
