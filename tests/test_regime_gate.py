"""Tests — Regime gate (Chantier A, 2026-07-18) PowerFlow V9.

Couvre les 3 briques additives derrière le kill switch V9_REGIME_GATE_ENABLED :
  1. RegimeDetector.get_current_regime()  — projection 6->3 + confidence
  2. ExploitabilityEvaluator._apply_regime_gate() + evaluate_window()
  3. le passthrough garanti quand le kill switch est OFF (défaut).

Le gate ne bloque qu'un régime "volatile" dominant les 8 devises avec une
confiance > seuil (défaut 0.7). Lecture N-1 : on seed directement
`regime_snapshots` (le régime persisté au snapshot précédent).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.v9.db_schema import get_connection, init_db
from core.v9.exploitability_evaluator import ExploitabilityEvaluator
from core.v9.regime_detector import RegimeDetector, init_regime_db

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def seed_regime(
    db_path: Path,
    ref: str,
    regime_types: list[str],
    *,
    symbol: str = "EURUSD",
    timeframe: str = "M5",
    timestamp: str = "2026-07-05T14:00:00.000Z",
) -> None:
    """Insère 8 lignes regime_snapshots (une par devise) pour un même
    `forces_snapshot_ref`, chacune avec le regime_type fourni."""
    assert len(regime_types) == len(DEVISES)
    init_regime_db(db_path)
    conn = get_connection(db_path)
    try:
        for ccy, rtype in zip(DEVISES, regime_types):
            conn.execute(
                "INSERT INTO regime_snapshots "
                "(regime_id, forces_snapshot_ref, symbol, timeframe, currency, "
                " regime_type, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"{ref}-{ccy}", ref, symbol, timeframe, ccy, rtype, timestamp),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


# ── get_current_regime() : projection 6 -> 3 + confidence ──────────

def test_get_current_regime_trending_high_confidence(db_path: Path) -> None:
    seed_regime(db_path, "ref_trend", ["CASSURE"] * 8)
    regime = RegimeDetector(db_path=db_path).get_current_regime("EURUSD", "M5")
    assert regime["regime"] == "trending"
    assert regime["confidence"] == pytest.approx(1.0)
    assert regime["source"] == "detector"


def test_get_current_regime_volatile_high_confidence(db_path: Path) -> None:
    seed_regime(db_path, "ref_vol", ["REJET"] * 8)
    regime = RegimeDetector(db_path=db_path).get_current_regime("EURUSD", "M5")
    assert regime["regime"] == "volatile"
    assert regime["confidence"] == pytest.approx(1.0)


def test_get_current_regime_ranging_from_palier(db_path: Path) -> None:
    seed_regime(db_path, "ref_range", ["PALIER"] * 8)
    regime = RegimeDetector(db_path=db_path).get_current_regime("EURUSD", "M5")
    assert regime["regime"] == "ranging"


def test_get_current_regime_majority_vote_and_confidence(db_path: Path) -> None:
    # 5 REJET (volatile) + 3 PALIER (ranging) -> volatile majoritaire, conf 5/8.
    seed_regime(db_path, "ref_mix", ["REJET"] * 5 + ["PALIER"] * 3)
    regime = RegimeDetector(db_path=db_path).get_current_regime("EURUSD", "M5")
    assert regime["regime"] == "volatile"
    assert regime["confidence"] == pytest.approx(5 / 8)


def test_get_current_regime_missing_data_fallback(db_path: Path) -> None:
    # Aucune ligne regime_snapshots -> fallback ranging, jamais de crash.
    regime = RegimeDetector(db_path=db_path).get_current_regime("EURUSD", "M5")
    assert regime["regime"] == "ranging"
    assert regime["confidence"] == 0.0
    assert regime["source"] == "fallback"
    assert regime["ts"] is None


def test_get_current_regime_picks_latest_ref(db_path: Path) -> None:
    seed_regime(db_path, "ref_old", ["CASSURE"] * 8, timestamp="2026-07-05T14:00:00.000Z")
    seed_regime(db_path, "ref_new", ["REJET"] * 8, timestamp="2026-07-05T14:05:00.000Z")
    regime = RegimeDetector(db_path=db_path).get_current_regime("EURUSD", "M5")
    assert regime["regime"] == "volatile"  # dernier ref (REJET) l'emporte


# ── _apply_regime_gate() : kill switch + seuil ─────────────────────

@pytest.fixture
def evaluator(tmp_path: Path) -> ExploitabilityEvaluator:
    return ExploitabilityEvaluator(
        db_path=tmp_path / "v9_test.db",
        config={
            "memory_dir": tmp_path / "memory",
            "replay_outcomes_path": tmp_path / "replay_outcomes.json",
        },
    )


UPSTREAM = {"symbol": "EURUSD", "timeframe": "M5"}


def test_gate_off_is_passthrough(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "0")
    seed_regime(evaluator.db_path, "ref_vol", ["REJET"] * 8)
    gate = evaluator._apply_regime_gate("exploitable", UPSTREAM)
    assert gate["applied"] is False
    assert gate["enabled"] is False


def test_gate_on_volatile_blocks(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    seed_regime(evaluator.db_path, "ref_vol", ["REJET"] * 8)
    gate = evaluator._apply_regime_gate("exploitable", UPSTREAM)
    assert gate["applied"] is True
    assert gate["raison"] == "regime_volatile"
    assert gate["regime"] == "volatile"


def test_gate_on_trending_passes(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    seed_regime(evaluator.db_path, "ref_trend", ["CASSURE"] * 8)
    gate = evaluator._apply_regime_gate("exploitable", UPSTREAM)
    assert gate["applied"] is False
    assert gate["regime"] == "trending"


def test_gate_on_ranging_passes(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    seed_regime(evaluator.db_path, "ref_range", ["PALIER"] * 8)
    gate = evaluator._apply_regime_gate("exploitable", UPSTREAM)
    assert gate["applied"] is False


def test_gate_on_volatile_low_conf_passes(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    # volatile majoritaire mais conf 5/8=0.625 <= seuil 0.7 -> ne bloque pas.
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    seed_regime(evaluator.db_path, "ref_mix", ["REJET"] * 5 + ["PALIER"] * 3)
    gate = evaluator._apply_regime_gate("exploitable", UPSTREAM)
    assert gate["regime"] == "volatile"
    assert gate["applied"] is False


def test_gate_never_touches_already_refuse(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    seed_regime(evaluator.db_path, "ref_vol", ["REJET"] * 8)
    gate = evaluator._apply_regime_gate("refuse", UPSTREAM)
    assert gate["applied"] is False


def test_gate_missing_regime_data_passes(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    # aucune donnée régime -> fallback ranging -> passe (jamais de crash)
    gate = evaluator._apply_regime_gate("exploitable", UPSTREAM)
    assert gate["applied"] is False


# ── Intégration evaluate_window() : le statut bascule bien ─────────

def _load_window(statut: str) -> dict:
    with open(FIXTURES_DIR / "windows_sample.json", encoding="utf-8") as f:
        for w in json.load(f):
            if w["statut"] == statut:
                return w
    raise KeyError(statut)


def test_evaluate_window_gate_off_unchanged(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "0")
    raw = _load_window("ouverte")
    evaluator.insert_window(raw)
    seed_regime(evaluator.db_path, "ref_vol", ["REJET"] * 8)
    result = evaluator.evaluate_window(raw["window_id"])
    assert result["statut"] == "exploitable"  # comportement historique intact


def test_evaluate_window_gate_on_volatile_refuses(evaluator: ExploitabilityEvaluator, monkeypatch) -> None:
    monkeypatch.setenv("V9_REGIME_GATE_ENABLED", "1")
    raw = _load_window("ouverte")
    evaluator.insert_window(raw)
    seed_regime(evaluator.db_path, "ref_vol", ["REJET"] * 8)
    result = evaluator.evaluate_window(raw["window_id"])
    assert result["statut"] == "refuse"
    assert result["raison_refus"] == "regime_volatile"
    assert result["meta"]["regime_gate"]["applied"] is True
