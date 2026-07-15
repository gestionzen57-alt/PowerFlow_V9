"""Tests Phase 14 — learning_offset_applier + intégration arbiter."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from core.v9.learning_offset_applier import (
    LEARNING_OFFSET_ENABLED_ENV,
    LEARNING_OFFSET_MULT_BOUNDS,
    LEARNING_OFFSET_MULT_NEUTRAL,
    LEARNING_OFFSET_WR_BASELINE,
    LearningOffsetApplier,
    _compute_multiplier_from_wr,
    learning_offset_enabled,
)


# ─── Tests unitaires sur le mapping WR -> multiplicateur ─────


class TestMultiplierMapping:
    """Phase 14 §1 — mapping discret WR observé -> multiplicateur dans
    [LEARNING_OFFSET_MULT_BOUNDS]. Vérifie les invariants de bornes et la
    progression monotone autour de WR_baseline=0.50."""

    def test_wr_neutral_returns_neutral(self):
        """WR=50% (neutre) => mult=1.00 strictement."""
        assert _compute_multiplier_from_wr(LEARNING_OFFSET_WR_BASELINE) == 1.0

    def test_wr_at_or_above_65_caps_high(self):
        """WR=70% => mult=LEARNING_OFFSET_MULT_BOUNDS[1] (cap supérieur)."""
        hi = LEARNING_OFFSET_MULT_BOUNDS[1]
        assert _compute_multiplier_from_wr(0.70) == pytest.approx(hi)

    def test_wr_at_or_above_80_still_caps(self):
        """WR=80% (saturation) => cap inchangé."""
        hi = LEARNING_OFFSET_MULT_BOUNDS[1]
        assert _compute_multiplier_from_wr(0.80) == pytest.approx(hi)

    def test_wr_94_caps(self):
        """WR=94% (cas réel §2.1 haussière) => cap supérieur."""
        hi = LEARNING_OFFSET_MULT_BOUNDS[1]
        assert _compute_multiplier_from_wr(0.94) == pytest.approx(hi)

    def test_wr_at_or_below_35_caps_low(self):
        """WR=35% => mult=LEARNING_OFFSET_MULT_BOUNDS[0] (cap inférieur)."""
        lo = LEARNING_OFFSET_MULT_BOUNDS[0]
        assert _compute_multiplier_from_wr(0.35) == pytest.approx(lo)

    def test_wr_below_35_caps(self):
        """WR=20% => cap inférieur inchangé."""
        lo = LEARNING_OFFSET_MULT_BOUNDS[0]
        assert _compute_multiplier_from_wr(0.20) == pytest.approx(lo)

    def test_wr_55_boost_linear(self):
        """WR=55% (légèrement haussier) => mult=1.05 (= baseline + 0.05)."""
        assert _compute_multiplier_from_wr(0.55) == pytest.approx(1.05)

    def test_wr_45_reduce_linear(self):
        """WR=45% (légèrement baissier) => mult=0.95 (= baseline - 0.05)."""
        assert _compute_multiplier_from_wr(0.45) == pytest.approx(0.95)


# ─── Tests intégration DB sur learning_proposals ────────────────


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    """Crée une DB jetable + table learning_proposals (schéma minimal)."""
    db_path = tmp_path / "test_learning.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE learning_proposals (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            window_days INTEGER NOT NULL,
            target TEXT NOT NULL,
            rationale TEXT NOT NULL,
            observed_wr REAL NOT NULL,
            observed_n INTEGER NOT NULL,
            score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            notes TEXT DEFAULT ''
        );
        """
    )
    c.commit()
    return c


def _insert(c: sqlite3.Connection, *, status: str, target: str,
            observed_wr: float, observed_n: int = 100, score: float = 50.0,
            proposal_id: str = "abc"):
    c.execute(
        "INSERT INTO learning_proposals "
        "(id, created_at, window_days, target, rationale, observed_wr, "
        " observed_n, score, status, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (proposal_id, "2026-07-15T00:00:00", 7, target,
         "test", observed_wr, observed_n, score, status, ""),
    )
    c.commit()


class TestLoadApprovedOffsets:
    """Phase 14 §2 — filtre learning_proposals : APPROVED + bon target + meilleure
    WR par direction."""

    def test_no_proposals_returns_empty(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                # patch le get_connection pour pointer sur notre DB
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    offsets = applier._load_approved_offsets(c)
        finally:
            c.close()
        assert offsets == {}

    def test_pending_not_loaded(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            _insert(c, status="PENDING", target="signal:haussiere:weight_offset",
                    observed_wr=0.94, proposal_id="p1")
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction("haussiere")
        finally:
            c.close()
        # PENDING n'est pas chargé -> neutre.
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_approved_loaded(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.60, proposal_id="p1", observed_n=500, score=50.0)
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction("haussiere")
        finally:
            c.close()
        # WR=60% => mult = 1.0 + clamp(0.10, ...) = 1.10
        assert mult == pytest.approx(1.10)
        assert basis == "approved"

    def test_best_wr_wins(self, tmp_path):
        """Plusieurs APPROVED pour la même direction : on garde la MEILLEURE
        WR (multiplicateur dominant)."""
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.55, proposal_id="p_weak", observed_n=100, score=10.0)
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.62, proposal_id="p_strong", observed_n=500, score=70.0)
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction("haussiere")
        finally:
            c.close()
        # WR=62% => mult = 1.0 + clamp(0.12, ...) = 1.12
        assert mult == pytest.approx(1.12)
        assert basis == "approved"

    def test_other_target_not_loaded(self, tmp_path):
        """Un target mal formé (autre que weight_offset) n'est pas chargé."""
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="principle:COALITION_NODE:confiance_offset",
                    observed_wr=0.95, proposal_id="p1")
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction("haussiere")
        finally:
            c.close()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"


class TestComputeOffsetForDirection:
    """Phase 14 §3 — gating par kill switch + valeurs sentinelles."""

    def test_neutral_direction_returns_neutral(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction("neutre")
        finally:
            c.close()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_none_direction_returns_neutral(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction(None)
        finally:
            c.close()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_kill_switch_off_returns_neutral(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.94, proposal_id="p1", observed_n=1000, score=80.0)
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=False):
                with patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                    mult, basis = applier.compute_offset_for_direction("haussiere")
        finally:
            c.close()
        # Kill switch OFF (R25 strict) -> neutre, même si une APPROVED existe.
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_runtime_exception_returns_neutral(self, tmp_path):
        """R6 : toute exception DB retourne (neutre, 'neutral'), pas de plantage."""
        c = _make_db(tmp_path)
        try:
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True):
                with patch("core.v9.learning_offset_applier.get_connection",
                           side_effect=RuntimeError("DB indisponible")):
                    mult, basis = applier.compute_offset_for_direction("haussiere")
        finally:
            c.close()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"


class TestKillSwitch:
    """Phase 14 §4 — kill switch OS env var."""

    def test_kill_switch_default_off(self):
        """Par défaut, sans env var : OFF (R25 strict)."""
        with patch.dict("os.environ", {}, clear=False):
            # pylint: disable=import-outside-toplevel
            import os as _os
            _os.environ.pop(LEARNING_OFFSET_ENABLED_ENV, None)
            assert learning_offset_enabled() is False

    def test_kill_switch_explicit_on(self):
        with patch.dict("os.environ", {LEARNING_OFFSET_ENABLED_ENV: "1"}):
            assert learning_offset_enabled() is True

    def test_kill_switch_explicit_off(self):
        with patch.dict("os.environ", {LEARNING_OFFSET_ENABLED_ENV: "0"}):
            assert learning_offset_enabled() is False

    def test_kill_switch_other_value_treated_off(self):
        """Valeur != '1' traitée comme OFF (fail-closed)."""
        with patch.dict("os.environ", {LEARNING_OFFSET_ENABLED_ENV: "true"}):
            assert learning_offset_enabled() is False


# ─── Test intégration arbiter ───────────────────────────────────


class TestArbiterIntegration:
    """Phase 14 §5 — Arbiter.consolidate() expose learning_offset_multiplier
    / learning_offset_basis / learning_offset_direction dans le dict de sortie.
    Test smoke : on vérifie que la clé existe, valeurs par défaut neutre."""

    def test_arbiter_return_keys_present(self):
        from core.v9.arbiter import Arbiter
        arb = Arbiter()
        # Appel à un snapshot qui n'existe pas -> early return avec clés OK.
        result = arb.consolidate("non-existent-snapshot-id")
        assert "learning_offset_multiplier" in result
        assert "learning_offset_basis" in result
        assert "learning_offset_direction" in result
        # Par défaut (kill switch OFF, 0 APPROVED) tout est neutre.
        assert result["learning_offset_multiplier"] == LEARNING_OFFSET_MULT_NEUTRAL
        assert result["learning_offset_basis"] == "neutral"
        assert result["learning_offset_direction"] is None

    def test_arbiter_singleton_idempotent(self):
        """Le singleton _get_learning_offset_applier est idempotent (R25 clean)."""
        from core.v9 import arbiter as arb_module

        a1 = arb_module._get_learning_offset_applier()
        a2 = arb_module._get_learning_offset_applier()
        assert a1 is a2  # même instance
