"""Tests — Dashboard web HITL (Brief Q3, 2026-07-12).

Couvre :
  - core/v9/hitl_reviews_db.py : écriture exclusive dans hitl_reviews,
    jamais dans decisions.
  - core/v9/dashboard_queries.py : lecture seule, filtre file HITL 40-65 /
    low_confidence_block, agrégation P&L paper.
  - scripts/v9_dashboard_web.py : auth basic (temps constant), config
    loader safe, rendu HTML (fonctions pures, sans serveur live).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.decision_logger import DecisionLogger  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.hitl_reviews_db import (  # noqa: E402
    get_all_reviews,
    get_reviews_for_decision,
    insert_review,
)
from core.v9.dashboard_queries import (  # noqa: E402
    get_calibration_view,
    get_hitl_queue,
    get_home_snapshot,
    get_paper_trades,
)
from scripts.v9_dashboard_web import (  # noqa: E402
    _check_basic_auth,
    _load_dashboard_auth_safe,
    render_calibration,
    render_home,
    render_review,
    render_trades,
)
from tests.test_decision_logger import build_full_chain, db_path  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _hitl_branching_on_by_default(monkeypatch: pytest.MonkeyPatch):
    """Depuis 2026-07-18, V9_HITL_BRANCHING_ENABLED est OFF par défaut
    (Søn a coupé les notifs Telegram « décision peu fiable »). Les tests de
    cette suite vérifient le COMPORTEMENT HITL (queue, block) -> on le force
    ON via l'environnement (priorité env > fichier dans kill_switches.get())."""
    monkeypatch.setenv("V9_HITL_BRANCHING_ENABLED", "1")


def _decisions_snapshot(db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id").fetchall()]
    finally:
        conn.close()


# ---------- hitl_reviews : isolation d'écriture ----------


def test_insert_review_writes_only_hitl_reviews_never_decisions(db_path: Path, monkeypatch):
    monkeypatch.setattr("core.v9.decision_logger._load_telegram_config_safe", lambda: None)
    snap_id = build_full_chain(db_path, signal_confiance=50, signal_direction="haussiere")
    dec = DecisionLogger(db_path=db_path).log(snap_id)

    before = _decisions_snapshot(db_path)
    insert_review(dec["decision_id"], "approved", reviewer="test_op", db_path=db_path)
    after = _decisions_snapshot(db_path)

    assert before == after  # decisions strictement inchangée
    reviews = get_reviews_for_decision(dec["decision_id"], db_path=db_path)
    assert len(reviews) == 1
    assert reviews[0]["verdict"] == "approved"
    assert reviews[0]["reviewer"] == "test_op"


def test_insert_review_rejects_invalid_verdict(db_path: Path):
    with pytest.raises(ValueError):
        insert_review("some-decision-id", "maybe", db_path=db_path)


def test_get_all_reviews_empty_db_returns_empty_list(db_path: Path):
    assert get_all_reviews(db_path=db_path) == []


# ---------- get_hitl_queue : filtre confiance ----------


def test_hitl_queue_includes_informative_band(db_path: Path, monkeypatch):
    monkeypatch.setattr("core.v9.decision_logger._load_telegram_config_safe", lambda: None)
    snap_id = build_full_chain(db_path, signal_confiance=50, signal_direction="haussiere")
    DecisionLogger(db_path=db_path).log(snap_id)

    queue = get_hitl_queue(db_path=db_path)
    assert len(queue) == 1
    assert queue[0]["tier"] == "informative_40_65"
    assert queue[0]["confiance"] == 50


def test_hitl_queue_includes_blocked_low_confidence(db_path: Path, monkeypatch):
    monkeypatch.setattr("core.v9.decision_logger._load_telegram_config_safe", lambda: None)
    snap_id = build_full_chain(db_path, signal_confiance=20, signal_direction="haussiere")
    DecisionLogger(db_path=db_path).log(snap_id)

    queue = get_hitl_queue(db_path=db_path)
    assert len(queue) == 1
    assert queue[0]["tier"] == "blocked_low_confidence"


def test_hitl_queue_excludes_high_confidence(db_path: Path, monkeypatch):
    monkeypatch.setattr("core.v9.decision_logger._load_telegram_config_safe", lambda: None)
    snap_id = build_full_chain(db_path, signal_confiance=90, signal_direction="haussiere")
    DecisionLogger(db_path=db_path).log(snap_id)

    assert get_hitl_queue(db_path=db_path) == []


def test_hitl_queue_carries_review_history(db_path: Path, monkeypatch):
    monkeypatch.setattr("core.v9.decision_logger._load_telegram_config_safe", lambda: None)
    snap_id = build_full_chain(db_path, signal_confiance=55, signal_direction="baissiere")
    dec = DecisionLogger(db_path=db_path).log(snap_id)
    insert_review(dec["decision_id"], "rejected", db_path=db_path)

    queue = get_hitl_queue(db_path=db_path)
    assert queue[0]["reviews"][0]["verdict"] == "rejected"


# ---------- lecture seule (pas de crash DB vide) ----------


def test_get_home_snapshot_empty_db_no_crash(db_path: Path):
    snap = get_home_snapshot(db_path=db_path)
    assert snap["paper_pnl"]["n_trades"] == 0


def test_get_paper_trades_empty_db_returns_empty_list(db_path: Path):
    assert get_paper_trades(db_path=db_path) == []


def test_get_calibration_view_empty_db_no_crash(db_path: Path):
    view = get_calibration_view(db_path=db_path)
    assert "session_buckets" in view
    assert view["top_combinations"] == []


def test_get_calibration_view_with_resolved_dynamic_decision_no_crash(db_path: Path, monkeypatch):
    """Régression : get_calibration_view doit fonctionner sur une decisions
    non vide (row_factory doit être posé avant _session_wr_buckets, sinon
    TypeError 'tuple indices must be integers or slices, not str')."""
    monkeypatch.setattr("core.v9.decision_logger._load_telegram_config_safe", lambda: None)
    snap_id = build_full_chain(db_path, signal_confiance=80, signal_direction="haussiere")
    dec = DecisionLogger(db_path=db_path).log(snap_id)

    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE decisions SET resolution_strategy='DYNAMIC', is_win=1, "
            "resolution_pips=5.0 WHERE decision_id=?",
            (dec["decision_id"],),
        )
        conn.commit()
    finally:
        conn.close()

    view = get_calibration_view(db_path=db_path)
    total_n = sum(b["n"] for b in view["session_buckets"].values())
    assert total_n == 1


# ---------- auth ----------


def test_check_basic_auth_valid_credentials():
    import base64

    header = "Basic " + base64.b64encode(b"operateur:secret123").decode()
    assert _check_basic_auth(header, "operateur", "secret123") is True


def test_check_basic_auth_wrong_password():
    import base64

    header = "Basic " + base64.b64encode(b"operateur:wrong").decode()
    assert _check_basic_auth(header, "operateur", "secret123") is False


def test_check_basic_auth_missing_header():
    assert _check_basic_auth(None, "operateur", "secret123") is False


def test_check_basic_auth_malformed_header():
    assert _check_basic_auth("Bearer abcdef", "operateur", "secret123") is False


def test_load_dashboard_auth_safe_missing_file_returns_none(tmp_path: Path):
    assert _load_dashboard_auth_safe(tmp_path / "does_not_exist.json") is None


def test_load_dashboard_auth_safe_valid_file(tmp_path: Path):
    cfg = tmp_path / "dashboard.json"
    cfg.write_text('{"USERNAME": "op", "PASSWORD": "pw"}', encoding="utf-8")
    auth = _load_dashboard_auth_safe(cfg)
    assert auth == {"username": "op", "password": "pw"}


def test_load_dashboard_auth_safe_missing_keys_returns_none(tmp_path: Path):
    cfg = tmp_path / "dashboard.json"
    cfg.write_text('{"USERNAME": ""}', encoding="utf-8")
    assert _load_dashboard_auth_safe(cfg) is None


# ---------- rendu HTML (fonctions pures) ----------


def test_render_home_no_crash_and_escapes_html():
    html_out = render_home({"state": {"decisions": [{"direction": "<script>"}]}, "paper_pnl": {}})
    assert "&lt;script&gt;" in html_out


def test_render_review_no_crash_empty_queue():
    assert "decision_id" in render_review([])


def test_render_trades_no_crash_empty_list():
    assert "trade_id" in render_trades([])


def test_render_calibration_no_crash_empty_view():
    out = render_calibration({"session_buckets": {}, "top_combinations": []})
    assert "Calibration" in out or "session" in out
