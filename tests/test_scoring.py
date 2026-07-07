"""Tests unitaires — v9_scoring.py (Phase 13 amorce).

Couvre 4 cas exigés par le brief :
  1. test_scoring_vide_si_aucune_resolution
  2. test_scoring_calcule_winrate
  3. test_scoring_min_samples_filtre
  4. test_scoring_lecture_seule

+ tests annexes : tri win_rate DESC, principes absents catalogue,
  json output, win_rate=None sur 0 sample, gestion JSON malformé.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.db_schema import init_db
from core.v9.decision_db import init_decision_db
from core.v9.principle_db import init_principle_db
import scripts.v9_scoring as sc


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "v9_scoring_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)
    init_decision_db(path)
    init_principle_db(path)
    return path


def _insert_decision(
    db_path: Path,
    *,
    snapshot_id: str = "snap_test",
    decision_id: str | None = None,
    is_win: int | None = None,
    resolution_pips: float | None = None,
    resolved_at: str | None = None,
    principes: list[str] | None = None,
) -> None:
    if decision_id is None:
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at,"
            " is_win, resolution_pips, resolved_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id, "1.0", "2026-07-07T10:00:00+00:00",
                snapshot_id, "sig_test", "surveiller",
                "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", "haussiere", 80,
                json.dumps(principes or []), "{}", "live",
                "2026-07-07T10:00:00+00:00",
                is_win, resolution_pips, resolved_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_principle(
    db_path: Path,
    *,
    principle_id: str,
    v9_status: str = "ACTIVE",
) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO principles ("
            " principle_id, version, origin, kind, source_status, v9_status,"
            " scope_timeframes_json, scope_currencies_json,"
            " conditions_json, emits_json, bounds_json,"
            " anti_signal_bias, notes, created_by, created_at_source, synced_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                principle_id, 1, "test", "node_rule", "ACTIVE", v9_status,
                "[]", "[]", "[]", "[]", "{}", False, "test",
                "test", "2026-07-07T10:00:00+00:00",
                "2026-07-07T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _count_paper_trades(db_path: Path) -> int:
    """Vérifie que la table paper_trades n'est pas utilisée par scoring
    (mais compte quand même pour test lecture_seule)."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        try:
            return conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        except sqlite3.OperationalError:
            return 0
    finally:
        conn.close()


# ---------- Tests ----------


def test_scoring_vide_si_aucune_resolution(db_path: Path) -> None:
    """Cas 1 — 0 décision résolue → scoring vide + message d'invite."""
    # Catalogue avec 3 principes ACTIVE
    for p in ("P_A", "P_B", "P_C"):
        _insert_principle(db_path, principle_id=p)

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
        total = sc._total_resolved(conn)
    finally:
        conn.close()

    assert total == 0
    assert len(scoring) == 3
    for r in scoring:
        assert r["nb"] == 0
        assert r["wins"] == 0
        assert r["win_rate"] is None


def test_scoring_vide_si_aucune_resolution_message() -> None:
    """Le format console affiche le message d'invite v9_resolve_decision.py."""
    out = sc._format_console([], total_resolved=0)
    assert "Aucune décision résolue" in out
    assert "v9_resolve_decision.py" in out


def test_scoring_calcule_winrate(db_path: Path) -> None:
    """Cas 2 — win rate calculé correctement par principe."""
    # Catalogue
    _insert_principle(db_path, principle_id="P_GOOD")
    _insert_principle(db_path, principle_id="P_BAD")
    _insert_principle(db_path, principle_id="P_NEVER")

    # Décisions résolues
    # P_GOOD : 3 wins / 4 total → 75%
    _insert_decision(db_path, snapshot_id="s1", decision_id="d1",
                     is_win=1, resolution_pips=10.0, resolved_at="2026-07-07T11:00:00+00:00",
                     principes=["P_GOOD"])
    _insert_decision(db_path, snapshot_id="s2", decision_id="d2",
                     is_win=1, resolution_pips=12.0, resolved_at="2026-07-07T11:01:00+00:00",
                     principes=["P_GOOD"])
    _insert_decision(db_path, snapshot_id="s3", decision_id="d3",
                     is_win=1, resolution_pips=8.0, resolved_at="2026-07-07T11:02:00+00:00",
                     principes=["P_GOOD"])
    _insert_decision(db_path, snapshot_id="s4", decision_id="d4",
                     is_win=0, resolution_pips=-5.0, resolved_at="2026-07-07T11:03:00+00:00",
                     principes=["P_GOOD"])

    # P_BAD : 1 win / 4 total → 25%
    _insert_decision(db_path, snapshot_id="s5", decision_id="d5",
                     is_win=1, resolution_pips=5.0, resolved_at="2026-07-07T11:04:00+00:00",
                     principes=["P_BAD"])
    _insert_decision(db_path, snapshot_id="s6", decision_id="d6",
                     is_win=0, resolution_pips=-3.0, resolved_at="2026-07-07T11:05:00+00:00",
                     principes=["P_BAD"])
    _insert_decision(db_path, snapshot_id="s7", decision_id="d7",
                     is_win=0, resolution_pips=-7.0, resolved_at="2026-07-07T11:06:00+00:00",
                     principes=["P_BAD"])
    _insert_decision(db_path, snapshot_id="s8", decision_id="d8",
                     is_win=0, resolution_pips=-2.0, resolved_at="2026-07-07T11:07:00+00:00",
                     principes=["P_BAD"])

    # P_NEVER : 0 décision résolue → reste dans catalogue avec N=0

    # Décision NON résolue (is_win NULL) — ignorée
    _insert_decision(db_path, snapshot_id="s_unres",
                     decision_id="d_unres",
                     is_win=None, resolution_pips=None, resolved_at=None,
                     principes=["P_GOOD"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
        total = sc._total_resolved(conn)
    finally:
        conn.close()

    assert total == 8  # les 8 résolues

    stats = {r["principle_id"]: r for r in scoring}
    assert stats["P_GOOD"]["nb"] == 4
    assert stats["P_GOOD"]["wins"] == 3
    assert stats["P_GOOD"]["win_rate"] == 0.75

    assert stats["P_BAD"]["nb"] == 4
    assert stats["P_BAD"]["wins"] == 1
    assert stats["P_BAD"]["win_rate"] == 0.25

    assert stats["P_NEVER"]["nb"] == 0
    assert stats["P_NEVER"]["wins"] == 0
    assert stats["P_NEVER"]["win_rate"] is None


def test_scoring_tri_winrate_desc(db_path: Path) -> None:
    """Tri : win_rate DESC, puis nb DESC, puis principle_id ASC."""
    _insert_principle(db_path, principle_id="P_LOW")     # 50% / 2 trades
    _insert_principle(db_path, principle_id="P_HIGH")    # 100% / 3 trades
    _insert_principle(db_path, principle_id="P_MEDIUM")  # 66% / 3 trades

    # P_LOW : 1/2
    _insert_decision(db_path, decision_id="d_l1",
                     is_win=1, resolution_pips=1.0, resolved_at="2026-07-07T11:00:00+00:00",
                     principes=["P_LOW"])
    _insert_decision(db_path, decision_id="d_l2",
                     is_win=0, resolution_pips=-1.0, resolved_at="2026-07-07T11:01:00+00:00",
                     principes=["P_LOW"])

    # P_HIGH : 3/3
    for i, did in enumerate(("d_h1", "d_h2", "d_h3")):
        _insert_decision(db_path, decision_id=did,
                         is_win=1, resolution_pips=1.0,
                         resolved_at=f"2026-07-07T11:0{i+2}:00+00:00",
                         principes=["P_HIGH"])

    # P_MEDIUM : 2/3
    _insert_decision(db_path, decision_id="d_m1",
                     is_win=1, resolution_pips=1.0, resolved_at="2026-07-07T11:10:00+00:00",
                     principes=["P_MEDIUM"])
    _insert_decision(db_path, decision_id="d_m2",
                     is_win=1, resolution_pips=1.0, resolved_at="2026-07-07T11:11:00+00:00",
                     principes=["P_MEDIUM"])
    _insert_decision(db_path, decision_id="d_m3",
                     is_win=0, resolution_pips=-1.0, resolved_at="2026-07-07T11:12:00+00:00",
                     principes=["P_MEDIUM"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
    finally:
        conn.close()

    # Ordre attendu : P_HIGH (100%) > P_MEDIUM (66%) > P_LOW (50%)
    assert [r["principle_id"] for r in scoring[:3]] == ["P_HIGH", "P_MEDIUM", "P_LOW"]


def test_scoring_min_samples_filtre(db_path: Path) -> None:
    """Cas 3 — min_samples=N filtre les principes avec nb < N."""
    _insert_principle(db_path, principle_id="P_BIG")    # 10 décisions
    _insert_principle(db_path, principle_id="P_SMALL")  # 2 décisions

    for i in range(10):
        _insert_decision(db_path, decision_id=f"d_b{i}",
                         is_win=1, resolution_pips=1.0,
                         resolved_at=f"2026-07-07T11:{i:02d}:00+00:00",
                         principes=["P_BIG"])
    for i in range(2):
        _insert_decision(db_path, decision_id=f"d_s{i}",
                         is_win=1, resolution_pips=1.0,
                         resolved_at=f"2026-07-07T12:{i:02d}:00+00:00",
                         principes=["P_SMALL"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring_no_filter = sc._compute_scoring(conn, min_samples=0)
        scoring_filter_5 = sc._compute_scoring(conn, min_samples=5)
    finally:
        conn.close()

    pids_no = {r["principle_id"] for r in scoring_no_filter}
    pids_5 = {r["principle_id"] for r in scoring_filter_5}

    assert pids_no == {"P_BIG", "P_SMALL"}
    assert pids_5 == {"P_BIG"}  # P_SMALL (nb=2) filtré
    assert len(scoring_filter_5) == 1


def test_scoring_lecture_seule(db_path: Path) -> None:
    """Cas 4 — v9_scoring ne crée aucune table ni n'écrit en DB."""
    _insert_principle(db_path, principle_id="P_TEST")
    _insert_decision(db_path, decision_id="d_ro",
                     is_win=1, resolution_pips=1.0, resolved_at="2026-07-07T11:00:00+00:00",
                     principes=["P_TEST"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        tables_before = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        decisions_before = conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]
        principles_before = conn.execute(
            "SELECT COUNT(*) FROM principles"
        ).fetchone()[0]
    finally:
        conn.close()

    # Lance le scoring plusieurs fois
    for _ in range(3):
        conn = sqlite3.connect(str(db_path), timeout=30)
        try:
            sc._compute_scoring(conn)
            sc._total_resolved(conn)
        finally:
            conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        tables_after = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        decisions_after = conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]
        principles_after = conn.execute(
            "SELECT COUNT(*) FROM principles"
        ).fetchone()[0]
    finally:
        conn.close()

    assert tables_before == tables_after
    assert decisions_before == decisions_after
    assert principles_before == principles_after


def test_scoring_principe_hors_catalogue(db_path: Path) -> None:
    """Un principe observé en décision mais absent du catalogue est listé
    avec in_catalogue=False."""
    # Pas de catalogue — uniquement des décisions résolues
    _insert_decision(db_path, decision_id="d_orphan",
                     is_win=1, resolution_pips=1.0,
                     resolved_at="2026-07-07T11:00:00+00:00",
                     principes=["P_ORPHAN"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
    finally:
        conn.close()

    assert len(scoring) == 1
    assert scoring[0]["principle_id"] == "P_ORPHAN"
    assert scoring[0]["in_catalogue"] is False
    assert scoring[0]["nb"] == 1
    assert scoring[0]["wins"] == 1


def test_scoring_decision_non_resolue_ignoree(db_path: Path) -> None:
    """is_win NULL n'apparaît pas dans le comptage (mais la décision existe)."""
    _insert_principle(db_path, principle_id="P_X")

    # 3 résolues (win) + 5 non résolues — toutes pour P_X
    for i in range(3):
        _insert_decision(db_path, decision_id=f"d_r{i}",
                         snapshot_id=f"sr{i}",
                         is_win=1, resolution_pips=1.0,
                         resolved_at=f"2026-07-07T11:{i:02d}:00+00:00",
                         principes=["P_X"])
    for i in range(5):
        _insert_decision(db_path, decision_id=f"d_u{i}",
                         snapshot_id=f"su{i}",
                         is_win=None, resolution_pips=None, resolved_at=None,
                         principes=["P_X"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
        total = sc._total_resolved(conn)
    finally:
        conn.close()

    assert total == 3  # seules les résolues
    assert scoring[0]["nb"] == 3
    assert scoring[0]["wins"] == 3
    assert scoring[0]["win_rate"] == 1.0


def test_scoring_principes_multiples(db_path: Path) -> None:
    """Une décision avec 2 principes compte pour les 2 principes."""
    _insert_principle(db_path, principle_id="P_A")
    _insert_principle(db_path, principle_id="P_B")

    _insert_decision(db_path, decision_id="d_multi_win",
                     is_win=1, resolution_pips=1.0,
                     resolved_at="2026-07-07T11:00:00+00:00",
                     principes=["P_A", "P_B"])
    _insert_decision(db_path, decision_id="d_a_only_loss",
                     is_win=0, resolution_pips=-1.0,
                     resolved_at="2026-07-07T11:01:00+00:00",
                     principes=["P_A"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
    finally:
        conn.close()

    stats = {r["principle_id"]: r for r in scoring}
    # P_A : 2 décisions résolues (1 win + 1 loss) → 50%
    assert stats["P_A"]["nb"] == 2
    assert stats["P_A"]["wins"] == 1
    assert stats["P_A"]["win_rate"] == 0.5
    # P_B : 1 décision résolue (1 win) → 100%
    assert stats["P_B"]["nb"] == 1
    assert stats["P_B"]["wins"] == 1
    assert stats["P_B"]["win_rate"] == 1.0


def test_scoring_principes_json_malformed(db_path: Path) -> None:
    """principes_json mal formé → compté comme 0 principe (ignore)."""
    _insert_principle(db_path, principle_id="P_OK")

    # Insertion directe avec JSON malformé (impossible via _insert_decision
    # qui valide le JSON) — on fait un INSERT brut.
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at,"
            " is_win, resolution_pips, resolved_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "d_bad", "1.0", "2026-07-07T10:00:00+00:00",
                "snap_bad", "sig_test", "surveiller",
                "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", "haussiere", 80,
                "{not valid", "{}", "live",
                "2026-07-07T10:00:00+00:00",
                1, 1.0, "2026-07-07T11:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        total = sc._total_resolved(conn)
        scoring = sc._compute_scoring(conn)
    finally:
        conn.close()

    # La décision compte dans total (is_win non NULL) mais pas dans les
    # comptages par principe (json_each échoue silencieusement).
    assert total == 1
    pids = {r["principle_id"] for r in scoring}
    assert "P_OK" in pids  # du catalogue
    # Aucun principe issu de la décision malformée
    for r in scoring:
        if r["nb"] > 0:
            assert r["principle_id"] == "P_OK"


def test_scoring_format_console_avec_donnees(db_path: Path) -> None:
    """Le format console produit un tableau structuré."""
    _insert_principle(db_path, principle_id="P_WIN")
    _insert_decision(db_path, decision_id="d_f1",
                     is_win=1, resolution_pips=1.0,
                     resolved_at="2026-07-07T11:00:00+00:00",
                     principes=["P_WIN"])

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
        total = sc._total_resolved(conn)
    finally:
        conn.close()

    out = sc._format_console(scoring, total)
    assert "P_WIN" in out
    assert "Total décisions résolues : 1" in out
    assert "100.0%" in out
    # Pas de message d'invite car > 0 résolution
    assert "Aucune décision résolue" not in out


def test_scoring_total_resolved_db_principes_absent(db_path: Path) -> None:
    """Si la table principles n'existe pas → scoring vide, pas de crash."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        scoring = sc._compute_scoring(conn)
    finally:
        conn.close()
    assert scoring == []