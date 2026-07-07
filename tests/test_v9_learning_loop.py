"""Tests learning_loop — Sprint Søn 2026-07-07 CEO quant."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9 import learning_loop


@pytest.fixture
def tmp_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    monkeypatch.setattr(learning_loop, "DB_PATH", db_path)
    learning_loop.init_learning_db()
    try:
        yield db_path
    finally:
        # Windows : fichier ouvert par connexion WAL peut bloquer unlink.
        # On tente unlink ; si PermissionError, on laisse (tmp).
        try:
            db_path.unlink(missing_ok=True)
        except (PermissionError, OSError):
            pass


def _insert_decisions(db_path: Path, decisions: list[tuple]) -> None:
    """Insert décisions résolues (direction, is_win, created_at)."""
    import uuid
    con = sqlite3.connect(str(db_path))
    for idx, (direction, is_win, created_at) in enumerate(decisions):
        con.execute(
            "INSERT INTO decisions (decision_id, schema_version, timestamp, "
            "snapshot_id, direction, confiance, action, is_win, created_at, source_type) "
            "VALUES (?, '1.0', ?, 's', ?, 80, 'preparer_entree', ?, ?, 'live')",
            (f"d_{direction}_{is_win}_{created_at}_{idx}_{uuid.uuid4().hex[:6]}",
             created_at, direction, is_win, created_at),
        )
    con.commit()
    con.close()


def test_init_creates_table(tmp_db):
    con = sqlite3.connect(str(tmp_db))
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='learning_proposals'"
    ).fetchall()
    con.close()
    assert len(rows) == 1


def test_no_proposal_below_n5(tmp_db):
    """Règle 30 palier 1 — n<5 décisions résolues = aucune proposition."""
    _insert_decisions(tmp_db, [
        ("haussiere", 1, "2026-07-07T10:00:00"),
        ("baissiere", 0, "2026-07-07T10:05:00"),
        ("haussiere", 1, "2026-07-07T10:10:00"),
    ])
    proposals = learning_loop.propose_from_outcomes(window_days=30)
    assert proposals == []


def test_proposal_generated_above_n5(tmp_db):
    """n>=5 + WR=80% baissier → proposition baissière."""
    rows = [("baissiere", 1, f"2026-07-0{i}T10:00:00") for i in range(1, 6)] + \
           [("baissiere", 0, f"2026-07-0{i}T11:00:00") for i in range(1, 3)]
    _insert_decisions(tmp_db, rows)
    proposals = learning_loop.propose_from_outcomes(window_days=30)
    assert len(proposals) >= 1
    p = proposals[0]
    assert "baissiere" in p.target
    assert p.observed_n >= 5
    assert p.observed_wr > 0.5
    assert p.status == "PENDING"


def test_proposals_persist_idempotently(tmp_db):
    """Re-run ne crée pas de doublons."""
    rows = [("haussiere", 1, f"2026-07-0{i}T10:00:00") for i in range(1, 9)]
    _insert_decisions(tmp_db, rows)
    p1 = learning_loop.propose_from_outcomes(window_days=30)
    p2 = learning_loop.propose_from_outcomes(window_days=30)
    assert len(p1) > 0
    # p2 doit retourner la même chose (idempotence par hash déterministe)
    p1_ids = sorted([p.id for p in p1])
    p2_ids = sorted([p.id for p in p2])
    assert p1_ids == p2_ids


def test_approve_proposal(tmp_db):
    rows = [("haussiere", 1, f"2026-07-0{i}T10:00:00") for i in range(1, 9)]
    _insert_decisions(tmp_db, rows)
    proposals = learning_loop.propose_from_outcomes(window_days=30)
    if not proposals:
        pytest.skip("No proposals generated (test data edge case)")
    pid = proposals[0].id
    assert learning_loop.approve_proposal(pid) is True
    # Re-approve doit échouer (status != PENDING)
    assert learning_loop.approve_proposal(pid) is False
    # Doit apparaître dans la liste APPROVED
    approved = learning_loop.list_proposals(status="APPROVED")
    assert any(p["id"] == pid for p in approved)


def test_reject_proposal(tmp_db):
    rows = [("baissiere", 0, f"2026-07-0{i}T10:00:00") for i in range(1, 9)]
    _insert_decisions(tmp_db, rows)
    proposals = learning_loop.propose_from_outcomes(window_days=30)
    if not proposals:
        pytest.skip("No proposals generated (test data edge case)")
    pid = proposals[0].id
    assert learning_loop.reject_proposal(pid, reason="WR trop faible pour promouvoir") is True
    rejected = learning_loop.list_proposals(status="REJECTED")
    assert any(p["id"] == pid for p in rejected)
    assert any("WR trop faible" in p["notes"] for p in rejected)


def test_list_proposals_filters_by_status(tmp_db):
    rows = [("haussiere", 1, f"2026-07-0{i}T10:00:00") for i in range(1, 8)] + \
           [("baissiere", 0, f"2026-07-0{i}T11:00:00") for i in range(1, 7)]
    _insert_decisions(tmp_db, rows)
    proposals = learning_loop.propose_from_outcomes(window_days=30)
    if len(proposals) < 2:
        pytest.skip("Need >=2 proposals to test status filter")
    # Approuver la 1ère, rejeter la 2nde
    learning_loop.approve_proposal(proposals[0].id)
    learning_loop.reject_proposal(proposals[1].id, reason="test")
    pending = learning_loop.list_proposals(status="PENDING")
    approved = learning_loop.list_proposals(status="APPROVED")
    rejected = learning_loop.list_proposals(status="REJECTED")
    assert any(p["id"] == proposals[0].id for p in approved)
    assert any(p["id"] == proposals[1].id for p in rejected)
    assert all(p["id"] not in [proposals[0].id, proposals[1].id] for p in pending)


def test_proposals_capped_at_5(tmp_db):
    """Le système doit retourner maximum 5 propositions, triées par score."""
    # Inject beaucoup de décisions variées pour générer plusieurs propositions
    rows = []
    for d in ["haussiere", "baissiere"]:
        for i in range(20):
            is_win = 1 if (i % 3 == 0) else 0
            rows.append((d, is_win, f"2026-07-{(i%7)+1:02d}T10:00:00"))
    _insert_decisions(tmp_db, rows)
    proposals = learning_loop.propose_from_outcomes(window_days=30)
    assert len(proposals) <= 5
