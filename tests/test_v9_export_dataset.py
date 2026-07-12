"""Tests — scripts/v9_export_dataset.py (Brief O5, 2026-07-12).

Couvre :
- fetch_target_decisions — filtre strict DYNAMIC/SKIPPED, ordre chronologique
- chronological_split — ratios ~80/10/10, aucune perte/duplication
- to_classification_jsonl / to_chat_template_jsonl — formats attendus
- build_records — séparation DYNAMIC/SKIPPED, métadonnées extraites,
  erreurs de contexte comptées sans crash
- main() — dry-run n'écrit rien, --apply écrit tous les fichiers + MD5
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.db_schema import FORCES_COLUMNS, init_all_dbs  # noqa: E402
from core.v9.principle_engine import PrincipleEngineError  # noqa: E402
from scripts import v9_export_dataset as exp  # noqa: E402


def _insert_forces_row(
    db_path: Path, snapshot_id: str, symbol: str, timeframe: str, ts: str, bar_time: int = 1,
) -> None:
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0", "timestamp": ts,
        "source": "TEST", "symbol": symbol, "timeframe": timeframe, "bar_time": bar_time,
        "is_closed_bar": True, "mid": 1.25,
        "force_usd": 50.0, "force_gbp": 50.0, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "stale": False, "created_at": ts,
    })
    conn = sqlite3.connect(str(db_path))
    try:
        cols = ", ".join(FORCES_COLUMNS)
        placeholders = ", ".join("?" for _ in FORCES_COLUMNS)
        conn.execute(f"INSERT INTO forces_snapshots ({cols}) VALUES ({placeholders})",
                    [row[c] for c in FORCES_COLUMNS])
        conn.commit()
    finally:
        conn.close()


def _insert_decision(
    db_path: Path, *, decision_id: str, snapshot_id: str, symbol: str = "GBPUSD",
    timeframe: str = "M15", ts: str, is_win: int, pips: float,
    resolution_strategy: str, exit_reason: str = "tp_hit",
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO decisions "
            "(decision_id, snapshot_id, symbol, timeframe, timestamp, direction, "
            " action, is_win, resolution_pips, resolution_strategy, resolution_details) "
            "VALUES (?, ?, ?, ?, ?, 'haussiere', 'preparer_entree', ?, ?, ?, ?)",
            (decision_id, snapshot_id, symbol, timeframe, ts, is_win, pips,
             resolution_strategy, json.dumps({"exit_reason": exit_reason})),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db = tmp_path / "export_test.db"
    init_all_dbs(db)
    return db


def test_fetch_target_decisions_filters_dynamic_and_skipped_only(temp_db: Path):
    _insert_forces_row(temp_db, "snap1", "GBPUSD", "M15", "2026-07-01T00:00:00+00:00")
    _insert_decision(temp_db, decision_id="d1", snapshot_id="snap1",
                     ts="2026-07-01T00:00:00+00:00", is_win=1, pips=10.0,
                     resolution_strategy="DYNAMIC")
    _insert_decision(temp_db, decision_id="d2", snapshot_id="snap1",
                     ts="2026-07-02T00:00:00+00:00", is_win=0, pips=0.0,
                     resolution_strategy="SKIPPED")
    _insert_decision(temp_db, decision_id="d3", snapshot_id="snap1",
                     ts="2026-07-03T00:00:00+00:00", is_win=0, pips=-5.0,
                     resolution_strategy="TP_SL")  # exclu
    _insert_decision(temp_db, decision_id="d4", snapshot_id="snap1",
                     ts="2026-07-04T00:00:00+00:00", is_win=1, pips=1.0,
                     resolution_strategy="MFE_ONLY")  # exclu

    conn = exp._connect(temp_db)
    try:
        rows = exp.fetch_target_decisions(conn)
        ids = [r["decision_id"] for r in rows]
        assert ids == ["d1", "d2"]  # ordre chronologique, TP_SL/MFE_ONLY exclus
    finally:
        conn.close()


def test_chronological_split_ratios_and_completeness():
    records = [{"label": i % 2, "idx": i} for i in range(100)]
    train, val, test = exp.chronological_split(records)
    assert len(train) == 80
    assert len(val) == 10
    assert len(test) == 10
    # Complétude garantie (partition de records) : multiset égal, aucune
    # perte ni duplication. L'ordre de concaténation n'est plus préservé
    # depuis le Brief Q1 (val = blocs entrelacés, pas la dernière tranche).
    assert sorted(train + val + test, key=lambda r: r["idx"]) == records
    assert set(r["idx"] for r in train) & set(r["idx"] for r in val) == set()
    assert set(r["idx"] for r in train) & set(r["idx"] for r in test) == set()
    assert set(r["idx"] for r in val) & set(r["idx"] for r in test) == set()


def test_chronological_split_test_is_pure_forward_holdout():
    # test = toujours les derniers indices (aucune contamination futur->passé).
    records = [{"idx": i} for i in range(100)]
    train, val, test = exp.chronological_split(records)
    assert [r["idx"] for r in test] == list(range(90, 100))
    assert max(r["idx"] for r in train + val) < min(r["idx"] for r in test)


def test_chronological_split_val_is_interleaved_not_contiguous_tail():
    # Brief Q1 : val ne doit plus être une unique tranche contiguë en fin de
    # pool train+val — elle doit être entourée de blocs train des deux côtés
    # (preuve qu'elle échantillonne plusieurs points du temps, pas un seul
    # épisode corrélé).
    records = [{"idx": i} for i in range(900)]
    train, val, test = exp.chronological_split(records)
    val_idx = [r["idx"] for r in val]
    train_idx = [r["idx"] for r in train]
    assert min(train_idx) < min(val_idx)
    assert max(train_idx) > max(val_idx)


def test_chronological_split_small_pool_still_partitions_cleanly():
    # Pool plus petit que BLOCK_MODULO*BLOCK_SIZE_TARGET (cas tests/petits
    # échantillons) : le mécanisme de blocs doit tout de même partitionner
    # proprement, sans division par zéro ni perte.
    records = [{"idx": i} for i in range(5)]
    train, val, test = exp.chronological_split(records)
    assert sorted(r["idx"] for r in train + val + test) == list(range(5))


def test_to_classification_jsonl_format():
    record = {
        "features": {"pf_mid": 1.25, "stale": False},
        "metadata": {"symbol": "GBPUSD", "timeframe": "M15", "session_marche": "asie",
                     "timestamp": "2026-07-01T00:00:00+00:00"},
        "label": 1, "pips": 8.5, "exit_reason": "tp_hit",
    }
    parsed = json.loads(exp.to_classification_jsonl(record))
    assert parsed["features"] == {"pf_mid": 1.25, "stale": False}
    assert parsed["metadata"]["session_marche"] == "asie"
    assert parsed["label"] == 1 and parsed["pips"] == 8.5 and parsed["exit_reason"] == "tp_hit"


def test_to_chat_template_jsonl_format_win():
    record = {"features": {"pf_mid": 1.25}, "label": 1, "pips": 8.5}
    parsed = json.loads(exp.to_chat_template_jsonl(record))
    assert parsed["messages"][0]["role"] == "user"
    assert parsed["messages"][1] == {"role": "assistant", "content": "WIN"}


def test_to_chat_template_jsonl_format_loss():
    record = {"features": {"pf_mid": 1.25}, "label": 0, "pips": -3.0}
    parsed = json.loads(exp.to_chat_template_jsonl(record))
    assert parsed["messages"][1] == {"role": "assistant", "content": "LOSS"}


class _FakeEngine:
    """Simule PrincipleEngine._load_shared_context sans dépendre du schéma
    complet scene/behavior/window (déjà couvert par les tests d'intégration
    dry-run ci-dessous sur la vraie DB)."""

    def __init__(self, fail_for: set[str] | None = None):
        self.fail_for = fail_for or set()

    def _load_shared_context(self, conn, snapshot_id):
        if snapshot_id in self.fail_for:
            raise PrincipleEngineError("contexte introuvable (test)")
        # Forme réelle de PrincipleEngine._load_shared_context() : IDs au
        # niveau racine + sous-dict "context" (contient session_marche).
        return {
            "behavior_id": "beh1", "scene_id": "scn1",
            "context": {"pf_mid": 1.25, "stale": False, "session_marche": "asie"},
        }


def test_build_records_separates_dynamic_and_skipped(temp_db: Path):
    _insert_forces_row(temp_db, "snap1", "GBPUSD", "M15", "2026-07-01T00:00:00+00:00")
    _insert_decision(temp_db, decision_id="d1", snapshot_id="snap1",
                     ts="2026-07-01T00:00:00+00:00", is_win=1, pips=10.0,
                     resolution_strategy="DYNAMIC")
    _insert_decision(temp_db, decision_id="d2", snapshot_id="snap1",
                     ts="2026-07-02T00:00:00+00:00", is_win=0, pips=0.0,
                     resolution_strategy="SKIPPED", exit_reason="skipped_new_york")

    conn = exp._connect(temp_db)
    try:
        rows = exp.fetch_target_decisions(conn)
        dynamic, skipped, n_errors = exp.build_records(conn, rows, _FakeEngine())
    finally:
        conn.close()

    assert n_errors == 0
    assert len(dynamic) == 1 and dynamic[0]["decision_id"] == "d1"
    assert dynamic[0]["label"] == 1
    assert dynamic[0]["exit_reason"] == "tp_hit"
    # session_marche retiré du sous-dict "context" -> métadonnées
    assert "session_marche" not in dynamic[0]["features"]["context"]
    assert dynamic[0]["metadata"]["symbol"] == "GBPUSD"
    assert dynamic[0]["metadata"]["session_marche"] == "asie"

    assert len(skipped) == 1 and skipped[0]["decision_id"] == "d2"
    assert skipped[0]["exit_reason"] == "skipped_new_york"


def test_build_records_counts_context_errors_without_crashing(temp_db: Path):
    _insert_forces_row(temp_db, "snap1", "GBPUSD", "M15", "2026-07-01T00:00:00+00:00")
    _insert_decision(temp_db, decision_id="d1", snapshot_id="snap1",
                     ts="2026-07-01T00:00:00+00:00", is_win=1, pips=10.0,
                     resolution_strategy="DYNAMIC")
    _insert_decision(temp_db, decision_id="d2", snapshot_id="snap_missing",
                     ts="2026-07-02T00:00:00+00:00", is_win=1, pips=5.0,
                     resolution_strategy="DYNAMIC")

    conn = exp._connect(temp_db)
    try:
        rows = exp.fetch_target_decisions(conn)
        dynamic, skipped, n_errors = exp.build_records(
            conn, rows, _FakeEngine(fail_for={"snap_missing"}),
        )
    finally:
        conn.close()

    assert n_errors == 1
    assert len(dynamic) == 1  # d1 seulement, d2 exclue (erreur contexte)


def test_build_data_card_flags_distribution_shift():
    train = [{"label": 1}] * 90 + [{"label": 0}] * 10   # WR 90%
    val = [{"label": 1}] * 10 + [{"label": 0}] * 90      # WR 10%
    test = [{"label": 1}] * 88 + [{"label": 0}] * 12     # WR 88%
    card = exp.build_data_card(train + val + test, [], train, val, test, 0)
    assert "Rupture de distribution" in card


def test_build_data_card_no_warning_when_distributions_close():
    train = [{"label": 1}] * 88 + [{"label": 0}] * 12
    val = [{"label": 1}] * 87 + [{"label": 0}] * 13
    test = [{"label": 1}] * 89 + [{"label": 0}] * 11
    card = exp.build_data_card(train + val + test, [], train, val, test, 0)
    assert "Rupture de distribution" not in card


# ---------- main() CLI — intégration réelle (PrincipleEngine réel) ------


def test_main_dry_run_writes_no_files(temp_db: Path, tmp_path: Path):
    _insert_forces_row(temp_db, "snap1", "GBPUSD", "M15", "2026-07-01T00:00:00+00:00")
    _insert_decision(temp_db, decision_id="d1", snapshot_id="snap1",
                     ts="2026-07-01T00:00:00+00:00", is_win=1, pips=10.0,
                     resolution_strategy="DYNAMIC")
    out_dir = tmp_path / "out"
    rc = exp.main([
        "--db", str(temp_db), "--dry-run",
        "--output", str(out_dir),
        "--card", str(tmp_path / "card.md"),
        "--md5", str(tmp_path / "md5.txt"),
    ])
    assert rc == 0
    assert not out_dir.exists()
    assert not (tmp_path / "card.md").exists()


def test_main_apply_writes_all_files_and_md5(temp_db: Path, tmp_path: Path):
    for i in range(10):
        snap_id = f"snap{i}"
        _insert_forces_row(temp_db, snap_id, "GBPUSD", "M15",
                           f"2026-07-01T{i:02d}:00:00+00:00", bar_time=i + 1)
        strategy = "SKIPPED" if i == 9 else "DYNAMIC"
        _insert_decision(temp_db, decision_id=f"d{i}", snapshot_id=snap_id,
                         ts=f"2026-07-01T{i:02d}:00:00+00:00",
                         is_win=1 if i % 2 == 0 else 0, pips=float(i),
                         resolution_strategy=strategy)

    out_dir = tmp_path / "out"
    card_path = tmp_path / "card.md"
    md5_path = tmp_path / "md5.txt"
    rc = exp.main([
        "--db", str(temp_db), "--apply",
        "--output", str(out_dir), "--card", str(card_path), "--md5", str(md5_path),
    ])
    assert rc == 0

    for name in ("train.jsonl", "val.jsonl", "test.jsonl",
                "train_chat.jsonl", "val_chat.jsonl", "test_chat.jsonl", "skipped.jsonl"):
        assert (out_dir / name).exists(), f"{name} manquant"

    assert card_path.exists()
    assert "V9-trader-mini" in card_path.read_text(encoding="utf-8")
    assert md5_path.exists()
    md5_lines = md5_path.read_text(encoding="utf-8").splitlines()
    assert len(md5_lines) == 7  # 6 splits classification+chat + skipped

    skipped_content = (out_dir / "skipped.jsonl").read_text(encoding="utf-8").strip()
    assert skipped_content  # d9 (SKIPPED) présent
    parsed_skipped = json.loads(skipped_content)
    assert "resolution_pips" not in parsed_skipped["features"]
    assert "is_win" not in parsed_skipped["features"]
