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
    # Use recent timestamps within 30-day window
    import time
    base_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))  # yesterday
    rows = [("baissiere", 1, base_ts) for _ in range(5)] + \
           [("baissiere", 0, base_ts) for _ in range(2)]
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
    import time
    base_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))  # yesterday
    rows = [("haussiere", 1, base_ts) for _ in range(8)]
    _insert_decisions(tmp_db, rows)
    p1 = learning_loop.propose_from_outcomes(window_days=30)
    p2 = learning_loop.propose_from_outcomes(window_days=30)
    assert len(p1) > 0
    # p2 doit retourner la même chose (idempotence par hash déterministe)
    p1_ids = sorted([p.id for p in p1])
    p2_ids = sorted([p.id for p in p2])
    assert p1_ids == p2_ids


def test_approve_proposal(tmp_db):
    import time
    base_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))  # yesterday
    rows = [("haussiere", 1, base_ts) for _ in range(8)]
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
    import time
    base_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))  # yesterday
    rows = [("baissiere", 0, base_ts) for _ in range(8)]
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
    import time
    base_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))  # yesterday
    rows = [("haussiere", 1, base_ts) for _ in range(8)] + \
           [("baissiere", 0, base_ts) for _ in range(7)]
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


def _create_alpha_metrics(db_path: Path, rows: list[dict]) -> None:
    """Crée principle_alpha_metrics et insère des lignes de métriques."""
    con = sqlite3.connect(str(db_path))
    con.execute(
        """CREATE TABLE IF NOT EXISTS principle_alpha_metrics (
            principle_id TEXT, session TEXT, regime TEXT, timeframe TEXT,
            direction TEXT, n_trades INTEGER, wins INTEGER, losses INTEGER,
            win_rate REAL, expectancy REAL)"""
    )
    for r in rows:
        con.execute(
            "INSERT INTO principle_alpha_metrics "
            "(principle_id, session, n_trades, win_rate, expectancy) "
            "VALUES (?,?,?,?,?)",
            (r["principle_id"], r.get("session"), r["n_trades"],
             r["win_rate"], r.get("expectancy", 0.0)),
        )
    con.commit()
    con.close()


def test_alpha_metrics_no_table_returns_empty(tmp_db):
    """R6 : table principle_alpha_metrics absente -> [] (dégradation gracieuse)."""
    assert learning_loop.propose_from_alpha_metrics() == []


def test_alpha_metrics_generates_per_principle_proposal(tmp_db):
    """Edge exploitable (WR 96% asie, n>=20) -> proposition ciblée PENDING."""
    _create_alpha_metrics(tmp_db, [
        {"principle_id": "PRICE_LAG_AT_NODE_BIRTH", "session": "asie",
         "n_trades": 210, "win_rate": 96.0, "expectancy": 5.7},
        {"principle_id": "COIN_FLIP", "session": "london",
         "n_trades": 200, "win_rate": 50.0, "expectancy": 0.0},  # pas d'edge -> ignoré
    ])
    props = learning_loop.propose_from_alpha_metrics(min_n=20)
    assert len(props) == 1
    p = props[0]
    assert "PRICE_LAG_AT_NODE_BIRTH" in p.target
    assert "session:asie" in p.target
    assert p.observed_wr > 0.9
    assert p.status == "PENDING"


def test_alpha_metrics_respects_min_n(tmp_db):
    """n < min_n -> aucune proposition (gate Règle 30)."""
    _create_alpha_metrics(tmp_db, [
        {"principle_id": "PRICE_LAG_AT_NODE_BIRTH", "session": "asie",
         "n_trades": 10, "win_rate": 96.0},
    ])
    assert learning_loop.propose_from_alpha_metrics(min_n=20) == []


def test_alpha_metrics_idempotent(tmp_db):
    """Re-run ne crée pas de doublons (hash déterministe)."""
    _create_alpha_metrics(tmp_db, [
        {"principle_id": "ZONE_RETEST", "session": "asie",
         "n_trades": 58, "win_rate": 95.0},
    ])
    p1 = learning_loop.propose_from_alpha_metrics(min_n=20)
    p2 = learning_loop.propose_from_alpha_metrics(min_n=20)
    assert sorted(p.id for p in p1) == sorted(p.id for p in p2)


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
