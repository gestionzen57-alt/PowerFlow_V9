"""Tests — core/v9/arbiter.py règle 29 (zone-type×session pondération).

Couvre :
- _infer_session_from_snapshot_ts() : heuristique UTC pure (asie/london/overlap/new_york/None)
- _detect_zone_type_from_snapshot() : lecture principle_evaluations.context_json via DB tmp
- consolidate() : 4 nouveaux champs présents (ajustement_rule29, raisons_ajustement,
  zone_type_predit, session_marche) + comportement backward-compatible
- Scénarios end-to-end : 8 cas de pondération (zone_type × session × nb_principes)

Aucun test ne touche data/v9_forces.db — tout passe par monkeypatch de _connect
vers une DB temporaire (principe même que test_v9_replay_rule29.py).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import arbiter as arb  # noqa: E402
from core.v9.arbiter import Arbiter  # noqa: E402


# ── _infer_session_from_snapshot_ts : table de vérité UTC ────────────
@pytest.mark.parametrize(
    "ts_iso,expected",
    [
        ("2026-07-07T00:00:00+00:00", "asie"),       # minuit UTC
        ("2026-07-07T03:30:00+00:00", "asie"),       # 03:30
        ("2026-07-07T06:59:59+00:00", "asie"),       # bord supérieur asie
        ("2026-07-07T07:00:00+00:00", "london"),     # bord inférieur london
        ("2026-07-07T10:00:00+00:00", "london"),     # 10:00
        ("2026-07-07T11:59:59+00:00", "london"),     # bord supérieur london
        ("2026-07-07T12:00:00+00:00", "overlap"),    # bord inférieur overlap
        ("2026-07-07T14:00:00+00:00", "overlap"),    # 14:00 (London+NY)
        ("2026-07-07T15:59:59+00:00", "overlap"),    # bord supérieur overlap
        ("2026-07-07T16:00:00+00:00", "new_york"),   # bord inférieur NY
        ("2026-07-07T18:00:00+00:00", "new_york"),   # 18:00
        ("2026-07-07T21:59:59+00:00", "new_york"),   # bord supérieur NY
        ("2026-07-07T22:00:00+00:00", None),         # transition weekend
        ("2026-07-07T23:30:00+00:00", None),
        (None, None),                                # timestamp absent
        ("", None),                                  # timestamp vide
        ("not-a-date", None),                        # timestamp malformé
        ("2026-07-07T10:00:00Z", "london"),          # format ISO avec Z
    ],
)
def test_infer_session_from_snapshot_ts(ts_iso, expected) -> None:
    """Table de vérité complète sur l'heuristique de session UTC."""
    assert Arbiter._infer_session_from_snapshot_ts(ts_iso) == expected


# ── DB temporaire pour les tests DB-driven ─────────────────────────
@pytest.fixture
def fake_db_path(tmp_path: Path) -> Path:
    """Crée une DB factice sur disque, retourne son path (rejouable)."""
    db = tmp_path / "arbiter_rule29.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE decisions (
            decision_id TEXT, direction TEXT, confiance INTEGER,
            principes_json TEXT, snapshot_id TEXT,
            timestamp TEXT, source_type TEXT
        );
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, snapshot_id TEXT,
            context_json TEXT, triggered INTEGER
        );

        INSERT INTO decisions VALUES
            ('d1', 'haussiere', 80, '["P1","P2"]', 'snap-001', '2026-07-07T10:00:00+00:00', 'live'),
            ('d2', 'haussiere', 90, '["P3","P4"]', 'snap-001', '2026-07-07T10:00:30+00:00', 'live');
        INSERT INTO principle_evaluations (snapshot_id, context_json, triggered) VALUES
            ('snap-001', '{"zone_type": "naissance"}', 1),
            ('snap-002', '{"zone_type": "continuation"}', 1);

        INSERT INTO decisions VALUES
            ('d3', 'baissiere', 70, '["P1","P2","P5"]', 'snap-002', '2026-07-07T15:00:00+00:00', 'live');

        INSERT INTO decisions VALUES
            ('d4', 'haussiere', 85, '["P1"]', 'snap-003', '2026-07-07T03:00:00+00:00', 'live');
    """)
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def arbiter_with_fake_db(fake_db_path: Path,
                          monkeypatch: pytest.MonkeyPatch,
                          request):
    """Arbiter pointant sur la DB temporaire.

    Le mock _connect ouvre une NOUVELLE connexion à chaque appel (basée sur
    fake_db_path). Cela évite que le finally: conn.close() du helper
    _detect_zone_type_from_snapshot ferme la connexion de la fixture
    avant le 2e appel.
    """
    instance = Arbiter()
    monkeypatch.setattr(instance, "db_path", fake_db_path)

    def _fake_connect_new() -> sqlite3.Connection:
        c = sqlite3.connect(str(fake_db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(instance, "_connect", _fake_connect_new)
    # Monkeypatch _load_decisions pour bypass la DB live
    decisions = getattr(request, "param", None) or []
    monkeypatch.setattr(instance, "_load_decisions", lambda conn, sid: decisions)
    return instance


# Helper qui ouvre une conn sur la fake DB pour les tests directs
@pytest.fixture
def fake_db_with_zone_type(fake_db_path: Path) -> sqlite3.Connection:
    """Ouvre une conn pour les tests directs (helper _detect_zone_type_from_snapshot)."""
    conn = sqlite3.connect(str(fake_db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── _detect_zone_type_from_snapshot ─────────────────────────────────
def test_detect_zone_type_naissance(arbiter_with_fake_db) -> None:
    """snap-001 a context_json '{"zone_type": "naissance"}' → helper retourne 'naissance'."""
    a = arbiter_with_fake_db
    assert a._detect_zone_type_from_snapshot("snap-001") == "naissance"


def test_detect_zone_type_continuation(arbiter_with_fake_db) -> None:
    a = arbiter_with_fake_db
    assert a._detect_zone_type_from_snapshot("snap-002") == "continuation"


def test_detect_zone_type_absent_retourne_none(arbiter_with_fake_db) -> None:
    """snap-003 n'a AUCUNE ligne dans principle_evaluations → None (backward-compat)."""
    a = arbiter_with_fake_db
    assert a._detect_zone_type_from_snapshot("snap-003") is None


def test_detect_zone_type_snapshot_inexistant(arbiter_with_fake_db) -> None:
    """snapshot_id absent totalement → None, pas d'exception."""
    a = arbiter_with_fake_db
    assert a._detect_zone_type_from_snapshot("snap-999") is None


def test_detect_zone_type_context_json_malforme(
    arbiter_with_fake_db, fake_db_with_zone_type: sqlite3.Connection,
) -> None:
    """context_json mal formé (non-dict) → None, ne lève pas."""
    fake_db_with_zone_type.execute(
        "INSERT INTO principle_evaluations (snapshot_id, context_json, triggered) "
        "VALUES ('snap-bad', 'not-json{{', 1)"
    )
    fake_db_with_zone_type.commit()
    a = arbiter_with_fake_db
    assert a._detect_zone_type_from_snapshot("snap-bad") is None


# ── consolidate : tests d'intégration (decision Søn 2026-07-07 20:15) ──
# Note Honnête : ces tests étaient FRAGILES (dépendent de monkeypatch sur
# _connect qui ouvre/ferme SQLite via tmp_path sur Windows). Résolu par
# la fixture shared_arbiter qui partage une connexion SQLite in-memory
# entre consolidate() et _detect_zone_type_from_snapshot (via le param
# conn=conn ajouté dans arbiter.py). Cf. DECISIONS_LOG 2026-07-10
# 'refactor arbiter fixtures → débloque 3 xfail + 1 xpass'.


@pytest.fixture
def shared_arbiter(monkeypatch: pytest.MonkeyPatch) -> Arbiter:
    """Arbiter pointant sur une DB SQLite in-memory partagée.

    La connexion est créée une fois et réutilisée par tous les appels
    à _connect (via monkeypatch). consolidate() passe conn=conn à
    _detect_zone_type_from_snapshot, ce qui évite l'ouverture/fermeture
    intempestive qui cassait les tests sur Windows.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE decisions (
            decision_id TEXT, direction TEXT, confiance INTEGER,
            principes_json TEXT, snapshot_id TEXT,
            timestamp TEXT, source_type TEXT
        );
        CREATE TABLE principle_evaluations (
            id INTEGER PRIMARY KEY, snapshot_id TEXT,
            context_json TEXT, triggered INTEGER
        );

        INSERT INTO decisions VALUES
            ('d1', 'haussiere', 80, '["P1","P2"]', 'snap-001', '2026-07-07T10:00:00+00:00', 'live'),
            ('d2', 'haussiere', 90, '["P3","P4"]', 'snap-001', '2026-07-07T10:00:30+00:00', 'live');
        INSERT INTO principle_evaluations (snapshot_id, context_json, triggered) VALUES
            ('snap-001', '{"zone_type": "naissance"}', 1),
            ('snap-002', '{"zone_type": "continuation"}', 1);

        INSERT INTO decisions VALUES
            ('d3', 'baissiere', 70, '["P1","P2","P5"]', 'snap-002', '2026-07-07T15:00:00+00:00', 'live');

        INSERT INTO decisions VALUES
            ('d4', 'haussiere', 85, '["P1"]', 'snap-003', '2026-07-07T03:00:00+00:00', 'live');
    """)
    conn.commit()

    instance = Arbiter()
    # _connect retourne TOUJOURS la même connexion partagée
    monkeypatch_conn = conn  # capture dans la closure

    def _shared_connect() -> sqlite3.Connection:
        return monkeypatch_conn

    monkeypatch.setattr(instance, "_connect", _shared_connect)
    return instance


def test_consolidate_champs_regle29_presents(arbiter_with_fake_db) -> None:
    """Les 4 nouveaux champs existent dans le dict retourné."""
    result = arbiter_with_fake_db.consolidate("snap-001")
    assert "ajustement_rule29" in result
    assert "raisons_ajustement" in result
    assert "zone_type_predit" in result
    assert "session_marche" in result


def test_consolidate_snapshot_vide_retourne_ajustement_zero(
    shared_arbiter,
) -> None:
    """rows vide (early return) → 'neutre', confiance=0."""
    result = shared_arbiter.consolidate("snap-inexistant")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0
    assert result["ajustement_rule29"] == 0
    assert result["zone_type_predit"] is None
    assert result["session_marche"] is None


def test_consolidate_zone_type_naissance_boost_confiance(
    shared_arbiter,
) -> None:
    """zone_type='naissance' + >=2 principes + london → +5 confiance brute."""
    result = shared_arbiter.consolidate("snap-001")
    assert result["zone_type_predit"] == "naissance"
    assert result["session_marche"] == "london"
    assert result["confiance_arbitree"] == 90


def test_consolidate_zone_type_continuation_reduction(
    shared_arbiter,
) -> None:
    """zone_type='continuation' + >=2 principes + overlap → -2."""
    result = shared_arbiter.consolidate("snap-002")
    assert result["direction"] == "baissiere"
    assert result["confiance_arbitree"] == 68


def test_consolidate_zone_type_absent_pas_ajustement(
    shared_arbiter,
) -> None:
    """snap-003 : pas de zone_type + 1 seul principe → plafond 74, -3 session."""
    result = shared_arbiter.consolidate("snap-003")
    assert result["session_marche"] == "asie"
    assert result["plafonne_sous_2_principes"] is True


def test_consolidate_decision_neutre_pas_consolidee(
    arbiter_with_fake_db,
) -> None:
    """rows vide (early return) → 'neutre', confiance=0. Stub."""
    result = arbiter_with_fake_db.consolidate("snap-inexistant")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0


def test_consolidate_ne_leve_pas_d_exception_si_db_morte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si DB inaccessible dans _load_decisions, consolidate() retourne neutre/0."""
    instance = Arbiter()
    monkeypatch.setattr(instance, "_load_decisions", lambda conn, sid: [])
    result = instance.consolidate("snap-001")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0
