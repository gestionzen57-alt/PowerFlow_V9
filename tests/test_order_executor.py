"""Tests — core/v9/order_executor.py (Brief Q5, volet exécution, 2026-07-13).

Le test le plus important de ce fichier est
`test_execution_disabled_blocks_everything` : il prouve que
V9_EXECUTION_ENABLED=0 bloque TOUT ordre, quel que soit l'input (y compris
un ordre parfaitement valide, HITL confirmé, petit lot) — le verrou 1 est
suffisant à lui seul, aucune autre condition ne peut le contourner.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.v9.hitl_reviews_db import insert_review
from core.v9.order_executor import (
    EXECUTION_ENABLED_ENV,
    HITL_LOT_THRESHOLD,
    ExecutionDisabledError,
    HITLConfirmationRequiredError,
    InvalidOrderError,
    OrderRequest,
    _build_order_command,
    _is_hitl_confirmed,
    _send_via_bridge,
    _validate_order,
    build_order_from_paper_risk,
    is_execution_enabled,
    send_order,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_v9_forces.db"


@pytest.fixture
def queue_dir(tmp_path: Path) -> Path:
    return tmp_path / "order_queue"


def _valid_order(**overrides) -> OrderRequest:
    base = dict(
        decision_id="dec-test-001",
        symbol="GBPUSD",
        direction="haussiere",
        lot=0.1,
        sl_pips=15.0,
        tp_pips=10.0,
    )
    base.update(overrides)
    return OrderRequest(**base)


# ── Verrou 1 — LE test le plus important ───────────────────────────────


@pytest.mark.parametrize(
    "order_kwargs",
    [
        {"lot": 0.1},  # petit lot, pas de HITL requis normalement
        {"lot": 5.0, "decision_id": "dec-hitl-approved"},  # gros lot, HITL sera approuvé
        {"lot": 0.5},  # exactement au seuil
        {"lot": 0.51},  # juste au-dessus du seuil
    ],
)
def test_execution_disabled_blocks_everything(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path, order_kwargs: dict
):
    """V9_EXECUTION_ENABLED absent/0 doit bloquer TOUT ordre, même un ordre
    par ailleurs parfaitement valide et HITL-confirmé. C'est le verrou 1,
    et il doit suffire seul."""
    monkeypatch.delenv(EXECUTION_ENABLED_ENV, raising=False)

    # On confirme HITL au cas où — même approuvé, ça ne doit rien changer.
    insert_review("dec-hitl-approved", "approved", reviewer="test", db_path=db_path)

    order = _valid_order(**order_kwargs)
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)

    assert result == {"sent": False, "reason": "execution_disabled"}
    assert not queue_dir.exists() or list(queue_dir.iterdir()) == []


def test_execution_disabled_explicit_zero_also_blocks(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "0")
    result = send_order(_valid_order(), db_path=db_path, queue_dir=queue_dir)
    assert result == {"sent": False, "reason": "execution_disabled"}


def test_is_execution_enabled_reads_env_live(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(EXECUTION_ENABLED_ENV, raising=False)
    assert is_execution_enabled() is False
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    assert is_execution_enabled() is True
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "0")
    assert is_execution_enabled() is False


# ── Verrou 2 — HITL pour lot > seuil ────────────────────────────────────


def test_hitl_required_for_large_lot_without_approval(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    order = _valid_order(lot=1.0, decision_id="dec-no-review")
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)
    assert result == {"sent": False, "reason": "hitl_required"}
    assert list(queue_dir.iterdir()) == [] if queue_dir.exists() else True


def test_hitl_rejected_verdict_blocks(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    insert_review("dec-rejected", "rejected", reviewer="test", db_path=db_path)
    order = _valid_order(lot=1.0, decision_id="dec-rejected")
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)
    assert result == {"sent": False, "reason": "hitl_required"}


def test_hitl_not_required_for_small_lot(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    order = _valid_order(lot=0.1, decision_id="dec-small-lot-no-review")
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)
    assert result["sent"] is True


def test_hitl_at_exact_threshold_not_required(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    """Le seuil est '> HITL_LOT_THRESHOLD', donc == 0.5 ne requiert pas HITL."""
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    order = _valid_order(lot=HITL_LOT_THRESHOLD, decision_id="dec-exact-threshold")
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)
    assert result["sent"] is True


def test_hitl_approved_allows_large_lot(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    insert_review("dec-approved", "approved", reviewer="test", db_path=db_path)
    order = _valid_order(lot=2.0, decision_id="dec-approved")
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)
    assert result["sent"] is True
    assert Path(result["file"]).exists()


def test_is_hitl_confirmed_uses_most_recent_review(db_path: Path):
    insert_review("dec-flip", "rejected", reviewer="a", db_path=db_path)
    insert_review("dec-flip", "approved", reviewer="b", db_path=db_path)
    assert _is_hitl_confirmed("dec-flip", db_path=db_path) is True


def test_is_hitl_confirmed_false_when_no_review(db_path: Path):
    assert _is_hitl_confirmed("dec-never-reviewed", db_path=db_path) is False


# ── Validation — jamais d'ordre nu ──────────────────────────────────────


def test_order_without_sl_raises(monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    order = _valid_order(sl_pips=None)
    with pytest.raises(InvalidOrderError, match="sl_pips"):
        send_order(order, db_path=db_path, queue_dir=queue_dir)


def test_order_without_tp_raises(monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    order = _valid_order(tp_pips=None)
    with pytest.raises(InvalidOrderError, match="sl_pips"):
        send_order(order, db_path=db_path, queue_dir=queue_dir)


def test_order_invalid_lot_raises():
    with pytest.raises(InvalidOrderError, match="lot"):
        _validate_order(_valid_order(lot=0))


def test_order_negative_lot_raises():
    with pytest.raises(InvalidOrderError, match="lot"):
        _validate_order(_valid_order(lot=-1.0))


def test_order_invalid_direction_raises():
    with pytest.raises(InvalidOrderError, match="direction"):
        _validate_order(_valid_order(direction="neutre"))


def test_order_missing_decision_id_raises():
    with pytest.raises(InvalidOrderError, match="decision_id"):
        _validate_order(_valid_order(decision_id=""))


# ── _build_order_command — pur, sans I/O ────────────────────────────────


def test_build_order_command_pure_no_io():
    order = _valid_order(direction="haussiere", lot=0.3)
    payload = _build_order_command(order)
    assert payload["action"] == "BUY"
    assert payload["lot"] == 0.3
    assert payload["symbol"] == "GBPUSD"
    assert "command_id" in payload and "issued_at" in payload


def test_build_order_command_sell_direction():
    order = _valid_order(direction="baissiere")
    payload = _build_order_command(order)
    assert payload["action"] == "SELL"


# ── _send_via_bridge — écriture fichier ─────────────────────────────────


def test_send_via_bridge_writes_json_file(queue_dir: Path):
    order = _valid_order()
    payload = _build_order_command(order)
    result = _send_via_bridge(payload, queue_dir=queue_dir)
    assert result["sent"] is True
    written = json.loads(Path(result["file"]).read_text(encoding="utf-8"))
    assert written["decision_id"] == "dec-test-001"


# ── build_order_from_paper_risk — réutilise le sizing existant ─────────


def test_build_order_from_paper_risk_go_false_raises():
    risk_eval = {"go": False, "raison_blocage": "max_drawdown"}
    with pytest.raises(InvalidOrderError, match="go=False"):
        build_order_from_paper_risk("dec-x", "GBPUSD", "haussiere", risk_eval)


def test_build_order_from_paper_risk_reuses_sizing():
    risk_eval = {"go": True, "position_size": 0.25, "sl_pips": 15.0, "tp_pips": 10.0}
    order = build_order_from_paper_risk("dec-y", "GBPUSD", "baissiere", risk_eval)
    assert order.lot == 0.25
    assert order.sl_pips == 15.0
    assert order.tp_pips == 10.0
    assert order.direction == "baissiere"


# ── End-to-end ───────────────────────────────────────────────────────────


def test_send_order_end_to_end_enabled_small_lot(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, queue_dir: Path
):
    monkeypatch.setenv(EXECUTION_ENABLED_ENV, "1")
    order = _valid_order(lot=0.2, decision_id="dec-e2e-small")
    result = send_order(order, db_path=db_path, queue_dir=queue_dir)
    assert result["sent"] is True
    assert queue_dir.exists()
    files = list(queue_dir.iterdir())
    assert len(files) == 1
    written = json.loads(files[0].read_text(encoding="utf-8"))
    assert written["decision_id"] == "dec-e2e-small"
    assert written["sl_pips"] == 15.0
    assert written["tp_pips"] == 10.0
