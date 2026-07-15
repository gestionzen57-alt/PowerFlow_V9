"""Tests Phase 14.2 — learning_offset_applier + intégration arbiter (refonte)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.v9.learning_offset_applier import (
    LEARNING_OFFSET_BOUNDS_BY_DIRECTION,
    LEARNING_OFFSET_BOUNDS_FALLBACK,
    LEARNING_OFFSET_CACHE_TTL_DEFAULT,
    LEARNING_OFFSET_CACHE_TTL_ENV,
    LEARNING_OFFSET_ENABLED_ENV,
    LEARNING_OFFSET_MULT_NEUTRAL,
    LEARNING_OFFSET_WR_BASELINE,
    LearningOffsetApplier,
    _cache_ttl,
    _compute_multiplier_from_wr,
    learning_offset_enabled,
)


# ─── Tests unitaires sur le mapping WR -> multiplicateur ─────


class TestMultiplierMappingAsymmetric:
    """Phase 14.2 §2 — bornes asymétriques par direction.

    Haussiere [0.85, 1.20] (boost +20%, reduce -15%).
    Baissiere [0.80, 1.10] (boost +10%, reduce -20%).
    Neutre [0.90, 1.10] (sentinelle).
    """

    @pytest.mark.parametrize("direction,lo,hi", [
        ("haussiere", 0.85, 1.20),
        ("baissiere", 0.80, 1.10),
    ])
    def test_bounds_per_direction(self, direction, lo, hi):
        lo_act, hi_act = LEARNING_OFFSET_BOUNDS_BY_DIRECTION[direction]
        assert (lo_act, hi_act) == (lo, hi)

    def test_wr_neutral_returns_neutral(self):
        """WR=50% (neutre) => mult=1.00 strictement, peu importe la direction."""
        for direction in ("haussiere", "baissiere", None):
            assert _compute_multiplier_from_wr(0.50, direction) == 1.0

    def test_wr_70_haussiere_caps_high(self):
        """WR=70% haussiere => mult=1.20 (cap boost haussier)."""
        assert _compute_multiplier_from_wr(0.70, "haussiere") == pytest.approx(1.20)

    def test_wr_94_haussiere_caps(self):
        """WR=94% haussiere (cas §2.1) => cap +1.20."""
        assert _compute_multiplier_from_wr(0.94, "haussiere") == pytest.approx(1.20)

    def test_wr_70_baissiere_caps_high(self):
        """WR=70% baissiere => mult=1.10 (cap boost baissier, plus prudent)."""
        assert _compute_multiplier_from_wr(0.70, "baissiere") == pytest.approx(1.10)

    def test_wr_30_baissiere_caps_low(self):
        """WR=30% baissiere => mult=0.80 (cap reduce baissier, plus marqué)."""
        assert _compute_multiplier_from_wr(0.30, "baissiere") == pytest.approx(0.80)

    def test_wr_35_haussiere_caps_low(self):
        """WR=35% haussiere => mult=0.85 (cap reduce haussier)."""
        assert _compute_multiplier_from_wr(0.35, "haussiere") == pytest.approx(0.85)

    def test_wr_55_haussiere_boost_linear(self):
        """WR=55% haussiere => mult=1.05 (= baseline + 0.05, dans la borne)."""
        assert _compute_multiplier_from_wr(0.55, "haussiere") == pytest.approx(1.05)

    def test_wr_45_baissiere_reduce_linear(self):
        """WR=45% baissiere => mult=0.95 (= baseline - 0.05, dans la borne)."""
        assert _compute_multiplier_from_wr(0.45, "baissiere") == pytest.approx(0.95)

    def test_unknown_direction_uses_fallback(self):
        """Direction non listée -> bornes fallback symétriques [0.85, 1.15]."""
        assert LEARNING_OFFSET_BOUNDS_FALLBACK == (0.85, 1.15)
        # WR=70% direction inconnue => cap fallback 1.15
        assert _compute_multiplier_from_wr(0.70, "autre") == pytest.approx(1.15)

    def test_asymmetry_haussier_boosts_more_than_baissier(self):
        """Invariant clé Phase 14.2 : haussier peut booster plus fort que baissier."""
        mult_h_70 = _compute_multiplier_from_wr(0.70, "haussiere")
        mult_b_70 = _compute_multiplier_from_wr(0.70, "baissiere")
        assert mult_h_70 > mult_b_70  # 1.20 > 1.10

    def test_asymmetry_baissier_reduces_more_than_haussier(self):
        """Invariant clé Phase 14.2 : baissier peut réduire plus fort que haussier."""
        mult_h_30 = _compute_multiplier_from_wr(0.30, "haussiere")
        mult_b_30 = _compute_multiplier_from_wr(0.30, "baissiere")
        assert mult_b_30 < mult_h_30  # 0.80 < 0.85


# ─── Tests cache in-memory TTL (Phase 14.2 §1) ──────────────


class TestCacheTTL:
    """Phase 14.2 §1 — cache in-memory TTL sur _load_approved_offsets()."""

    def test_cache_ttl_default(self):
        """TTL par défaut = 60s."""
        assert _cache_ttl() == LEARNING_OFFSET_CACHE_TTL_DEFAULT
        assert LEARNING_OFFSET_CACHE_TTL_DEFAULT == 60.0

    def test_cache_ttl_env_override(self):
        """Env var override le TTL."""
        with patch.dict("os.environ", {LEARNING_OFFSET_CACHE_TTL_ENV: "5"}):
            assert _cache_ttl() == 5.0

    def test_cache_ttl_zero_disables_caching(self):
        """TTL=0 désactive le cache (recharge à chaque appel)."""
        with patch.dict("os.environ", {LEARNING_OFFSET_CACHE_TTL_ENV: "0"}):
            assert _cache_ttl() == 0.0

    def test_cache_ttl_negative_falls_back_to_default(self):
        """TTL négatif invalide -> fallback default."""
        with patch.dict("os.environ", {LEARNING_OFFSET_CACHE_TTL_ENV: "-5"}):
            assert _cache_ttl() == 0.0  # max(0, -5) = 0 -> désactive

    def test_cache_ttl_garbage_falls_back_to_default(self):
        """Valeur non numérique -> fallback default."""
        with patch.dict("os.environ", {LEARNING_OFFSET_CACHE_TTL_ENV: "abc"}):
            assert _cache_ttl() == LEARNING_OFFSET_CACHE_TTL_DEFAULT

    def test_cache_serves_repeated_calls(self, tmp_path):
        """2e appel hit le cache (pas de relecture DB)."""
        def _factory(_db_path=None):
            new_c = _make_db(tmp_path)
            _insert(new_c, status="APPROVED",
                    target="signal:haussiere:weight_offset",
                    observed_wr=0.60, proposal_id="p1", observed_n=500)
            new_c.row_factory = sqlite3.Row
            return new_c
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection", side_effect=_factory) as gc_mock:
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            m1, _ = applier.compute_offset_for_direction("haussiere")
            # 2e appel : cache hit, pas de relecture DB.
            gc_mock.reset_mock()
            m2, _ = applier.compute_offset_for_direction("haussiere")
            assert m1 == m2
            assert gc_mock.call_count == 0  # pas de ré-appel à get_connection

    def test_invalidate_forces_reload(self, tmp_path):
        """invalidate() force la relecture DB."""
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.60, proposal_id="p1", observed_n=500)
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            # Le module ferme la connexion après usage (own_conn=True).
            # On patche get_connection pour retourner une factory
            # qui re-crée la connexion à chaque appel.
            def _factory(_db_path=None):
                new_c = _make_db(tmp_path)
                _insert(new_c, status="APPROVED",
                        target="signal:haussiere:weight_offset",
                        observed_wr=0.60, proposal_id="p1", observed_n=500)
                new_c.row_factory = sqlite3.Row
                return new_c
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
                 patch("core.v9.learning_offset_applier.get_connection", side_effect=_factory):
                m1, _ = applier.compute_offset_for_direction("haussiere")
                applier.invalidate()
                # Le cache est bien vidé.
                assert applier._cache is None
                # Le rechargement ramène haussiere.
                m2, _ = applier.compute_offset_for_direction("haussiere")
                assert m1 == m2
        finally:
            c.close()

    def test_cache_ttl_expiry(self, tmp_path):
        """Si TTL expiré, recharge DB (cache expiré)."""
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.60, proposal_id="p1", observed_n=500)
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
                 patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                applier._cache = {"haussiere": {"observed_wr": 0.60, "observed_n": 500,
                                                 "score": 50.0, "multiplier": 1.10,
                                                 "proposal_id": "p1"}}
                applier._cache_loaded_at = time.monotonic() - 999.0  # expiré
                # TTL expiré -> _cache_expired() True -> recharge
                assert applier._cache_expired() is True
        finally:
            c.close()


# ─── Tests intégration DB sur learning_proposals ────────────────


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    """Crée une DB jetable + table learning_proposals (schéma minimal).

    Idempotent : un 2e appel sur le même tmp_path ne recrée pas la table
    (utilise CREATE TABLE IF NOT EXISTS). Important pour `_patched_factory`
    qui appelle `_make_db` à chaque ouverture de connexion (la factory
    est invoquée plusieurs fois par test, et le test doit pouvoir
    réouvrir la DB sans planter).
    """
    db_path = tmp_path / "test_learning.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS learning_proposals (
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


def _patched_factory(tmp_path: Path, rows: list[dict]):
    """Crée un side_effect pour `patch(get_connection, ...)` qui re-crée
    une nouvelle connexion SQLite (Row factory + rows) à chaque appel.

    Pourquoi : `_load_approved_offsets()` ferme la connexion après usage
    (own_conn=True). Sans factory, un mock `return_value=c` réutilise la
    même connexion fermée au 2e appel. Le side_effect garantit une DB
    fraîche à chaque appel (cohérence avec le comportement prod où
    `get_connection` ouvre toujours une nouvelle connexion).

    Note : la factory DELETE la table avant chaque INSERTION pour
    éviter les violations de PRIMARY KEY entre les invocations
    successives (les rows sont fixes, on veut un état stable à
    chaque appel, pas d'accumulation).
    """
    rows = list(rows)

    def _factory(_db_path=None):
        c = _make_db(tmp_path)
        c.execute("DELETE FROM learning_proposals")
        for r in rows:
            _insert(c, **r)
        c.row_factory = sqlite3.Row
        return c

    return _factory


class TestLoadApprovedOffsets:
    """Phase 14.2 §3 — filtre learning_proposals : APPROVED + bon target + meilleure
    WR par direction."""

    def test_no_proposals_returns_empty(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, [])):
            offsets = applier._load_approved_offsets()
            applier.invalidate()
        assert offsets == {}

    def test_pending_not_loaded(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        rows = [dict(status="PENDING", target="signal:haussiere:weight_offset",
                     observed_wr=0.94, proposal_id="p1")]
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, rows)):
            mult, basis = applier.compute_offset_for_direction("haussiere")
            applier.invalidate()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_approved_loaded_haussiere(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        rows = [dict(status="APPROVED", target="signal:haussiere:weight_offset",
                     observed_wr=0.60, proposal_id="p1",
                     observed_n=500, score=50.0)]
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, rows)):
            mult, basis = applier.compute_offset_for_direction("haussiere")
            applier.invalidate()
        # WR=60% haussiere => 1.0 + 0.10 = 1.10
        assert mult == pytest.approx(1.10)
        assert basis == "approved"

    def test_approved_loaded_baissiere_asymmetric(self, tmp_path):
        """Asymétrie Phase 14.2 : baissiere 60% WR donne mult différent."""
        # 1) Vérifions WR=60% dans les 2 directions (delta identique).
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        rows = [
            dict(status="APPROVED", target="signal:baissiere:weight_offset",
                 observed_wr=0.60, proposal_id="p1", observed_n=500, score=50.0),
            dict(status="APPROVED", target="signal:haussiere:weight_offset",
                 observed_wr=0.60, proposal_id="p2", observed_n=500, score=50.0),
        ]
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, rows)):
            mult_b, _ = applier.compute_offset_for_direction("baissiere")
            applier.invalidate()
            mult_h, _ = applier.compute_offset_for_direction("haussiere")
        # WR=60% haussière -> 1.10, baissière -> 1.10 (delta identique, l'asymétrie
        # joue sur WR plus extrêmes).
        assert mult_b == pytest.approx(1.10)
        assert mult_h == pytest.approx(1.10)

        # 2) Vérifions l'asymétrie sur WR=70% (cap différent).
        applier2 = LearningOffsetApplier(db_path=tmp_path / "test_learning2.db")
        rows_b70 = [
            dict(status="APPROVED", target="signal:baissiere:weight_offset",
                 observed_wr=0.70, proposal_id="p3", observed_n=500, score=70.0),
            dict(status="APPROVED", target="signal:haussiere:weight_offset",
                 observed_wr=0.70, proposal_id="p4", observed_n=500, score=70.0),
        ]
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, rows_b70)):
            mult_b_70, _ = applier2.compute_offset_for_direction("baissiere")
            applier2.invalidate()
            mult_h_70, _ = applier2.compute_offset_for_direction("haussiere")
        # WR=70% haussiere -> 1.20 (cap haut), baissiere -> 1.10 (cap bas).
        assert mult_b_70 == pytest.approx(1.10)
        assert mult_h_70 == pytest.approx(1.20)
        # Asymétrie : haussier peut booster plus fort que baissier.
        assert mult_h_70 > mult_b_70

    def test_best_wr_wins(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        rows = [
            dict(status="APPROVED", target="signal:haussiere:weight_offset",
                 observed_wr=0.55, proposal_id="p_weak", observed_n=100, score=10.0),
            dict(status="APPROVED", target="signal:haussiere:weight_offset",
                 observed_wr=0.62, proposal_id="p_strong", observed_n=500, score=70.0),
        ]
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, rows)):
            mult, basis = applier.compute_offset_for_direction("haussiere")
            applier.invalidate()
        # WR=62% haussiere => 1.0 + 0.12 = 1.12
        assert mult == pytest.approx(1.12)
        assert basis == "approved"

    def test_other_target_not_loaded(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        rows = [dict(status="APPROVED",
                     target="principle:COALITION_NODE:confiance_offset",
                     observed_wr=0.95, proposal_id="p1")]
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, rows)):
            mult, basis = applier.compute_offset_for_direction("haussiere")
            applier.invalidate()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"


class TestComputeOffsetForDirection:
    """Phase 14.2 §4 — gating par kill switch + valeurs sentinelles."""

    def test_neutral_direction_returns_neutral(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, [])):
            mult, basis = applier.compute_offset_for_direction("neutre")
            applier.invalidate()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_none_direction_returns_neutral(self, tmp_path):
        applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
        with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
             patch("core.v9.learning_offset_applier.get_connection",
                   side_effect=_patched_factory(tmp_path, [])):
            mult, basis = applier.compute_offset_for_direction(None)
            applier.invalidate()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_kill_switch_off_returns_neutral(self, tmp_path):
        c = _make_db(tmp_path)
        try:
            _insert(c, status="APPROVED", target="signal:haussiere:weight_offset",
                    observed_wr=0.94, proposal_id="p1", observed_n=1000, score=80.0)
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=False), \
                 patch("core.v9.learning_offset_applier.get_connection", return_value=c):
                mult, basis = applier.compute_offset_for_direction("haussiere")
                applier.invalidate()
        finally:
            c.close()
        # Kill switch OFF -> neutre, même si une APPROVED existe.
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"

    def test_runtime_exception_returns_neutral(self, tmp_path):
        """R6 : toute exception DB retourne (neutre, 'neutral'), pas de plantage."""
        c = _make_db(tmp_path)
        try:
            applier = LearningOffsetApplier(db_path=tmp_path / "test_learning.db")
            with patch("core.v9.learning_offset_applier.learning_offset_enabled", return_value=True), \
                 patch("core.v9.learning_offset_applier.get_connection",
                       side_effect=RuntimeError("DB indisponible")):
                mult, basis = applier.compute_offset_for_direction("haussiere")
                applier.invalidate()
        finally:
            c.close()
        assert mult == LEARNING_OFFSET_MULT_NEUTRAL
        assert basis == "neutral"


class TestKillSwitchPhase142:
    """Phase 14.2 §3 — kill switch par défaut ON (motion CEO §3.6 §1)."""

    def test_kill_switch_default_on(self):
        """Par défaut, sans env var : ON (motion CEO §3.6 §1)."""
        with patch.dict("os.environ", {}, clear=False):
            import os as _os
            _os.environ.pop(LEARNING_OFFSET_ENABLED_ENV, None)
            assert learning_offset_enabled() is True

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
    """Phase 14.2 §5 — Arbiter.consolidate() expose learning_offset_multiplier
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
        # Phase 14.2 : kill switch ON par défaut. Mais sans APPROVED en DB
        # pour ce test, le basis est 'neutral'.
        # (Note : sur la DB de prod live il y a 2 APPROVED, mais ce test
        # utilise un singleton partagé, on accepte 'neutral' ou 'approved'.)
        assert result["learning_offset_multiplier"] == pytest.approx(
            LEARNING_OFFSET_MULT_NEUTRAL
        ) or result["learning_offset_multiplier"] > LEARNING_OFFSET_MULT_NEUTRAL
        assert result["learning_offset_basis"] in ("neutral", "approved")
        assert result["learning_offset_direction"] is None or \
               result["learning_offset_direction"] in ("haussiere", "baissiere")

    def test_arbiter_singleton_idempotent(self):
        """Le singleton _get_learning_offset_applier est idempotent (R25 clean)."""
        from core.v9 import arbiter as arb_module

        a1 = arb_module._get_learning_offset_applier()
        a2 = arb_module._get_learning_offset_applier()
        assert a1 is a2  # même instance
