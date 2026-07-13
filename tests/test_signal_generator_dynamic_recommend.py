"""Tests d'intégration — signal_generator P1 DYNAMIC recommendation (autopilot 2026-07-13).

Couvre :
- Les nouvelles colonnes exit_strategy_recommended, tp_pips_recommended,
  sl_pips_recommended sont peuplées pour les signaux actifs et absents
- La valeur suit DYNAMIC_PROFILES du exit_simulator
- La stratégie par défaut reste DYNAMIC (pas de dépendance à l'activation)
- Rétrocompat : signal_generator fonctionne sur une DB sans ces colonnes
  (via le _ensure_column de init_signal_db)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.exit_simulator import DYNAMIC_PROFILES, DYNAMIC_DEFAULT
from core.v9.signal_generator import (
    SignalGenerator,
    _recommend_dynamic_for_active,
    _recommend_dynamic_for_absent,
)
from core.v9.signal_db import SIGNALS_COLUMNS


# ── Helpers recommendation ─────────────────────────────────────────


def test_recommend_dynamic_structure(monkeypatch):
    """Le helper retourne bien {strategy, tp_pips, sl_pips, session_marche, scale}.
    Brief O4 CEO 2026-07-13 — asie/london/overlap = DYNAMIC tradable.
    Test doit être stable hors fenêtre NY/after (qui retourne None)."""
    from core.v9 import signal_generator as _sg_mod
    class _LondonNow:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 10, 0, 0, tzinfo=tz)
    monkeypatch.setattr(_sg_mod, "datetime", _LondonNow)
    sig = SignalGenerator.__new__(SignalGenerator)  # skip init
    rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    assert "strategy" in rec
    assert "tp_pips" in rec
    assert "sl_pips" in rec
    assert "session_marche" in rec
    assert "scale" in rec
    assert rec["strategy"] == "DYNAMIC"


def test_recommend_dynamic_session_aware(monkeypatch):
    """Selon l'heure UTC, la session et donc le profil change."""
    sig = SignalGenerator.__new__(SignalGenerator)
    # Fixer l'heure UTC à midi (overlap)
    class _FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr("core.v9.signal_generator.datetime", _FixedDateTime)
    rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    assert rec["session_marche"] == "overlap"
    assert rec["tp_pips"] == DYNAMIC_PROFILES["overlap"]["tp_pips"]


def test_recommend_dynamic_absent_returns_same(monkeypatch):
    """Signal absent : recommendation = recommendation active (DYNAMIC sur asie/london/overlap).
    Mocké à 10h UTC = london (hors NY/after qui retourne None Brief O4)."""
    from core.v9 import signal_generator as _sg_mod
    class _LondonNow:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 10, 0, 0, tzinfo=tz)
    monkeypatch.setattr(_sg_mod, "datetime", _LondonNow)
    sig = SignalGenerator.__new__(SignalGenerator)
    rec = _recommend_dynamic_for_absent(sig, "GBPUSD", "M15")
    assert rec["strategy"] == "DYNAMIC"


# ── Colonnes signal_db ────────────────────────────────────────────────


def test_signals_columns_includes_dynamic_rec(tmp_path):
    """SIGNALS_COLUMNS inclut les 3 nouvelles colonnes."""
    expected = ["exit_strategy_recommended", "tp_pips_recommended", "sl_pips_recommended"]
    for col in expected:
        assert col in SIGNALS_COLUMNS, f"Colonne {col} manquante dans SIGNALS_COLUMNS"


def test_init_signal_db_creates_dynamic_columns(tmp_path):
    """init_signal_db crée la table avec les 3 colonnes (via CREATE TABLE
    + _ensure_column rétrocompat)."""
    from core.v9.signal_db import init_signal_db

    db_path = tmp_path / "v9_test.db"
    init_signal_db(db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        assert "exit_strategy_recommended" in cols
        assert "tp_pips_recommended" in cols
        assert "sl_pips_recommended" in cols
    finally:
        conn.close()


def test_init_signal_db_migrates_existing_db_without_columns(tmp_path):
    """Si la table signals existe sans les colonnes P1 (DB legacy),
    init_signal_db les ajoute via _ensure_column."""
    from core.v9.signal_db import init_signal_db

    db_path = tmp_path / "v9_test.db"
    # Crée une table signals SANS les colonnes P1 (legacy)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT UNIQUE,
                schema_version TEXT,
                timestamp TEXT,
                snapshot_id TEXT,
                symbol TEXT,
                timeframe TEXT,
                currency TEXT,
                direction TEXT,
                confiance INTEGER,
                horizon TEXT,
                principes_source_json TEXT,
                regime_type TEXT,
                exploitability_id TEXT,
                exploitability_statut TEXT,
                raison_absence TEXT,
                stale BOOLEAN,
                source_type TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    # Maintenant applique init_signal_db — doit ajouter les 3 colonnes
    init_signal_db(db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        assert "exit_strategy_recommended" in cols
        assert "tp_pips_recommended" in cols
        assert "sl_pips_recommended" in cols
    finally:
        conn.close()


def test_default_dynamic_profile_is_DYNAMIC(monkeypatch):
    """Profil par défaut DYNAMIC si session tradable. Brief O4 : NY/after
    retournent strategy=None — donc ce test doit être à une heure
    tradable pour valider le fallback profil."""
    from core.v9 import signal_generator as _sg_mod
    class _LondonNow:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 13, 10, 0, 0, tzinfo=tz)
    monkeypatch.setattr(_sg_mod, "datetime", _LondonNow)
    sig = SignalGenerator.__new__(SignalGenerator)
    rec = _recommend_dynamic_for_active(sig, "GBPUSD", "M15")
    profile = DYNAMIC_PROFILES.get(rec["session_marche"], DYNAMIC_DEFAULT)
    assert rec["tp_pips"] == float(profile["tp_pips"])
    assert rec["sl_pips"] == float(profile["sl_pips"])
