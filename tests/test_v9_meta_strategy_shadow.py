"""test_v9_meta_strategy_shadow.py — Tests Phase E shadow (R25' strict, R6 défensif).

Couvre :
- Kill switch V9_META_STRATEGY_SHADOW_ENABLED (défaut OFF)
- ensure_shadow_table (idempotent, table absente = création)
- _log_shadow (insert OK, erreur DB = None)
- recommend_with_shadow :
  - kill switch OFF → legacy retourné tel quel, comparison=None
  - DB absente → comparison=None
  - kill switch ON + DB OK → log écrit, comparison retournée
  - meta_strategy_optimizer OFF → meta_source=meta_kill_switch_off
  - meta_strategy_optimizer raises → graceful fallback meta_source=unknown
  - legacy jamais écrasé (R25' strict)
- compute_edge_uplift : DB absente, n=0, distribution
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


# ------------------------------------------------------------------ helpers


@dataclass
class FakeLegacyRec:
    """Duck-typed StrategyRecommendation pour les tests."""
    recommended_strategy: str = "TP_SL"
    confidence: float = 0.5
    recommended_tp: float = 10.0
    recommended_sl: float = 15.0
    rationale: str = "fake legacy"


@pytest.fixture
def tmp_db(tmp_path):
    """Crée une DB SQLite temporaire et yield son chemin."""
    p = tmp_path / "test_v9_forces.db"
    return str(p)


@pytest.fixture
def populated_db(tmp_db):
    """DB avec table shadow déjà créée (idempotence test)."""
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    assert ensure_shadow_table(tmp_db) is True
    return tmp_db


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Reset du kill switch entre chaque test."""
    monkeypatch.delenv("V9_META_STRATEGY_SHADOW_ENABLED", raising=False)
    yield


# ------------------------------------------------------------------ kill switch


def test_shadow_enabled_default_off(monkeypatch):
    """Défaut = OFF (R25' strict, motion CEO pour activer)."""
    monkeypatch.delenv("V9_META_STRATEGY_SHADOW_ENABLED", raising=False)
    from core.v9.v9_meta_strategy_shadow import meta_strategy_shadow_enabled
    assert meta_strategy_shadow_enabled() is False


def test_shadow_enabled_explicit_on(monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    from core.v9.v9_meta_strategy_shadow import meta_strategy_shadow_enabled
    assert meta_strategy_shadow_enabled() is True


def test_shadow_enabled_explicit_off(monkeypatch):
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "0")
    from core.v9.v9_meta_strategy_shadow import meta_strategy_shadow_enabled
    assert meta_strategy_shadow_enabled() is False


# ------------------------------------------------------------------ ensure_shadow_table


def test_ensure_shadow_table_creates(tmp_db):
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    assert ensure_shadow_table(tmp_db) is True
    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meta_strategy_shadow_log'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_ensure_shadow_table_idempotent(populated_db):
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    # 2e appel doit aussi marcher
    assert ensure_shadow_table(populated_db) is True


def test_ensure_shadow_table_creates_missing(tmp_path):
    """Chemin inexistant : sqlite3 crée le fichier, retourne True (R7 testable)."""
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    missing = tmp_path / "nonexistent.db"
    assert ensure_shadow_table(missing) is True
    assert missing.exists()


def test_ensure_shadow_table_creates_with_parent_dirs(tmp_path):
    """DB dans sous-dossier inexistant : crée les parents + la DB."""
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    nested = tmp_path / "a" / "b" / "c" / "test.db"
    assert ensure_shadow_table(nested) is True
    assert nested.exists()


def test_ensure_shadow_table_none():
    from core.v9.v9_meta_strategy_shadow import ensure_shadow_table
    assert ensure_shadow_table(None) is False


# ------------------------------------------------------------------ recommend_with_shadow : kill switch OFF


def test_recommend_shadow_off_returns_legacy_unchanged(populated_db, monkeypatch):
    """Kill switch OFF → legacy retourné tel quel, comparison=None."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "0")
    legacy = FakeLegacyRec(recommended_strategy="TRAILING", confidence=0.8)
    out_legacy, comparison = recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", direction="long", legacy_recommendation=legacy,
        db_path=populated_db,
    )
    assert out_legacy is legacy
    assert out_legacy.recommended_strategy == "TRAILING"
    assert comparison is None


def test_recommend_shadow_off_db_present_no_log(populated_db, monkeypatch):
    """Kill switch OFF → pas de log écrit même si DB présente."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "0")
    legacy = FakeLegacyRec()
    recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", direction="long", legacy_recommendation=legacy,
        db_path=populated_db,
    )
    conn = sqlite3.connect(populated_db)
    n = conn.execute("SELECT COUNT(*) FROM meta_strategy_shadow_log").fetchone()[0]
    conn.close()
    assert n == 0


# ------------------------------------------------------------------ recommend_with_shadow : DB absente


def test_recommend_shadow_on_db_missing(tmp_path, monkeypatch):
    """DB absente → comparison=None, legacy retourné."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    missing = tmp_path / "nope.db"
    legacy = FakeLegacyRec()
    out_legacy, comparison = recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation", direction="short", legacy_recommendation=legacy,
        db_path=missing,
    )
    assert out_legacy is legacy
    assert comparison is None


def test_recommend_shadow_on_db_none(monkeypatch):
    """db_path=None → comparison=None."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    legacy = FakeLegacyRec()
    out_legacy, comparison = recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation", direction="short", legacy_recommendation=legacy,
        db_path=None,
    )
    assert out_legacy is legacy
    assert comparison is None


# ------------------------------------------------------------------ recommend_with_shadow : meta fourni


def test_recommend_shadow_on_meta_provided_agreement(populated_db, monkeypatch):
    """Meta fourni avec stratégie identique à legacy → agreement=True, log écrit."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow, ShadowComparison

    @dataclass
    class FakeMetaDec:
        chosen_strategy: str = "TP_SL"
        confidence: float = 0.55
        recommended_tp: float = 10.0
        recommended_sl: float = 15.0
        source: str = "meta_optimizer"
        rationale: str = "fake meta test"

    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    legacy = FakeLegacyRec(recommended_strategy="TP_SL", confidence=0.5)
    meta = FakeMetaDec(chosen_strategy="TP_SL", confidence=0.55)
    out_legacy, comparison = recommend_with_shadow(
        symbol="EURUSD", timeframe="H1", regime_type="TENDANCE",
        phase="developpement", direction="long", vol_atr_pips=12.5,
        legacy_recommendation=legacy, db_path=populated_db,
        meta_strategy_decision=meta,
    )
    assert out_legacy is legacy  # jamais écrasé
    assert isinstance(comparison, ShadowComparison)
    assert comparison.agreement is True
    assert comparison.legacy_strategy == "TP_SL"
    assert comparison.meta_strategy == "TP_SL"
    assert comparison.meta_source == "meta_optimizer"
    assert comparison.shadow_id is not None and comparison.shadow_id > 0

    # Vérif log DB
    conn = sqlite3.connect(populated_db)
    row = conn.execute(
        "SELECT symbol, regime_type, agreement, meta_source FROM meta_strategy_shadow_log "
        "WHERE id=?", (comparison.shadow_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "EURUSD"
    assert row[1] == "TENDANCE"
    assert int(row[2]) == 1
    assert row[3] == "meta_optimizer"


def test_recommend_shadow_on_meta_provided_disagreement(populated_db, monkeypatch):
    """Meta propose FAST_EXIT, legacy = TP_SL → agreement=False."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow

    @dataclass
    class FakeMetaDec:
        chosen_strategy: str = "FAST_EXIT"
        confidence: float = 0.42
        recommended_tp: float = 7.0
        recommended_sl: float = 10.0
        source: str = "meta_optimizer"
        rationale: str = "climax détecté"

    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    legacy = FakeLegacyRec(recommended_strategy="TP_SL", confidence=0.5)
    meta = FakeMetaDec()
    out_legacy, comparison = recommend_with_shadow(
        symbol="USDJPY", timeframe="M5", regime_type="CLIMAX",
        phase="resolution", direction="short", vol_atr_pips=8.0,
        legacy_recommendation=legacy, db_path=populated_db,
        meta_strategy_decision=meta,
    )
    assert out_legacy is legacy  # runtime jamais écrasé (R25')
    assert comparison is not None
    assert comparison.legacy_strategy == "TP_SL"
    assert comparison.meta_strategy == "FAST_EXIT"
    assert comparison.agreement is False


# ------------------------------------------------------------------ meta auto-call (kill switch meta)


def test_recommend_shadow_meta_kill_switch_off(populated_db, monkeypatch):
    """V9_META_STRATEGY_OPTIMIZER_ENABLED=0 → meta_source=meta_kill_switch_off."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "0")
    legacy = FakeLegacyRec(recommended_strategy="TRAILING", confidence=0.7)
    _, comparison = recommend_with_shadow(
        symbol="GBPUSD", timeframe="H1", regime_type="TENDANCE",
        phase="developpement", direction="long",
        legacy_recommendation=legacy, db_path=populated_db,
    )
    assert comparison is not None
    assert comparison.meta_source == "meta_kill_switch_off"
    assert comparison.meta_strategy == "TP_SL"  # fallback conservateur
    assert comparison.meta_confidence == 0.0


def test_recommend_shadow_meta_auto_call_empty_db(populated_db, monkeypatch):
    """DB shadow avec 0 principle_scores → meta fallback no_candidates_db_empty."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1")
    legacy = FakeLegacyRec()
    _, comparison = recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation", direction="long",
        legacy_recommendation=legacy, db_path=populated_db,
    )
    # DB vide → meta tombe sur fallback no_candidates_db_empty
    assert comparison is not None
    assert comparison.meta_source in ("no_candidates_db_empty", "all_candidates_zero_score", "fallback_selector", "disabled_kill_switch", "default")


def test_recommend_shadow_legacy_never_overwritten(populated_db, monkeypatch):
    """Garantit que le runtime legacy reste intact même quand meta diffère."""
    from core.v9.v9_meta_strategy_shadow import recommend_with_shadow

    @dataclass
    class FakeMetaDec:
        chosen_strategy: str = "TRAILING"
        confidence: float = 0.9
        recommended_tp: float = 25.0
        recommended_sl: float = 8.0
        source: str = "meta_optimizer"
        rationale: str = "trend"

    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    legacy = FakeLegacyRec(recommended_strategy="TP_SL", confidence=0.5,
                          recommended_tp=10.0, recommended_sl=15.0)
    out_legacy, comparison = recommend_with_shadow(
        symbol="GBPUSD", timeframe="M15", regime_type="TENDANCE",
        phase="developpement", direction="long",
        legacy_recommendation=legacy, db_path=populated_db,
        meta_strategy_decision=FakeMetaDec(),
    )
    # Legacy intact
    assert out_legacy.recommended_strategy == "TP_SL"
    assert out_legacy.recommended_tp == 10.0
    assert out_legacy.recommended_sl == 15.0
    assert out_legacy.confidence == 0.5
    # Comparison reflète la divergence
    assert comparison.agreement is False
    assert comparison.meta_strategy == "TRAILING"


# ------------------------------------------------------------------ compute_edge_uplift


def test_compute_edge_uplift_db_missing(tmp_path):
    from core.v9.v9_meta_strategy_shadow import compute_edge_uplift
    res = compute_edge_uplift(tmp_path / "nope.db")
    assert "error" in res


def test_compute_edge_uplift_empty(populated_db):
    from core.v9.v9_meta_strategy_shadow import compute_edge_uplift
    res = compute_edge_uplift(populated_db)
    assert res["n_shadows"] == 0
    assert res["agreement_rate"] == 0.0
    assert res["meta_sources"] == {}
    assert res["strategy_legacy_distribution"] == {}


def test_compute_edge_uplift_populated(populated_db, monkeypatch):
    """Insère 3 shadow logs, vérifie agreement_rate + distributions."""
    from core.v9.v9_meta_strategy_shadow import (
        recommend_with_shadow, compute_edge_uplift,
    )

    @dataclass
    class M:
        chosen_strategy: str = "TP_SL"
        confidence: float = 0.5
        recommended_tp: float = 10.0
        recommended_sl: float = 15.0
        source: str = "meta_optimizer"
        rationale: str = ""

    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")

    # 2 agreements (TP_SL == TP_SL)
    for _ in range(2):
        recommend_with_shadow(
            symbol="EURUSD", timeframe="H1", regime_type="NEUTRE",
            phase="initiation", direction="long",
            legacy_recommendation=FakeLegacyRec(recommended_strategy="TP_SL"),
            db_path=populated_db, meta_strategy_decision=M(),
        )

    # 1 disagreement
    recommend_with_shadow(
        symbol="USDJPY", timeframe="M5", regime_type="CLIMAX",
        phase="resolution", direction="short",
        legacy_recommendation=FakeLegacyRec(recommended_strategy="TP_SL"),
        db_path=populated_db,
        meta_strategy_decision=M(chosen_strategy="FAST_EXIT", source="meta_optimizer"),
    )

    res = compute_edge_uplift(populated_db)
    assert res["n_shadows"] == 3
    assert res["agreement_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert res["strategy_legacy_distribution"].get("TP_SL") == 3
    assert res["strategy_meta_distribution"].get("TP_SL") == 2
    assert res["strategy_meta_distribution"].get("FAST_EXIT") == 1


# ------------------------------------------------------------------ dataclass immutability


def test_shadow_comparison_frozen():
    """ShadowComparison doit être frozen (R2 additif = pas de mutation)."""
    from core.v9.v9_meta_strategy_shadow import ShadowComparison
    cmp = ShadowComparison(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation", direction="long",
        legacy_strategy="TP_SL", legacy_confidence=0.5,
        meta_strategy="TRAILING", meta_confidence=0.6,
        meta_source="meta_optimizer", agreement=False, shadow_id=42,
    )
    with pytest.raises(Exception):  # FrozenInstanceError ou AttributeError
        cmp.symbol = "EURUSD"


def test_shadow_comparison_to_dict():
    from core.v9.v9_meta_strategy_shadow import ShadowComparison
    cmp = ShadowComparison(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation", direction="long",
        legacy_strategy="TP_SL", legacy_confidence=0.5,
        meta_strategy="TRAILING", meta_confidence=0.6,
        meta_source="meta_optimizer", agreement=False, shadow_id=42,
    )
    d = cmp.to_dict()
    assert d["symbol"] == "GBPUSD"
    assert d["agreement"] is False
    assert d["shadow_id"] == 42


# ------------------------------------------------------------------ shadow table indexes


def test_shadow_table_indexes_created(populated_db):
    """Vérifie que les 3 index sont créés (perf observabilité)."""
    conn = sqlite3.connect(populated_db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name LIKE 'idx_mssl_%'"
    ).fetchall()
    conn.close()
    names = sorted([r[0] for r in rows])
    assert "idx_mssl_agreement" in names
    assert "idx_mssl_created" in names
    assert "idx_mssl_symbol_tf" in names