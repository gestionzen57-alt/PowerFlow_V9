"""Tests unitaires — validate-coherence.py.

Couvre 6 cas (le brief demande 6 minimum) :
  1. test_check1_orphelin_scene : scene sans snapshot → ERREUR
  2. test_check2_decision_sans_signal : ERREUR
  3. test_check3_signal_sans_principe : ERREUR
  4. test_check5_doublon_decision : WARNING
  5. test_check7_confiance_hors_plage : ERREUR
  6. test_all_ok : DB propre → exit 0

Plus quelques tests annexes (check4 stale, check6 principes muets,
JSON output, fix-report, vc.summarize).
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.db_schema import init_db
from core.v9.principle_db import init_principle_db
from core.v9.scene_db import init_scene_db
from core.v9.behavior_db import init_behavior_db
from core.v9.window_db import init_window_db
from core.v9.exploitability_db import init_exploitability_db
from core.v9.signal_db import init_signal_db
from core.v9.decision_db import init_decision_db


# Le script `scripts/validate-coherence.py` contient un tiret — non
# importable directement. On charge le module dynamiquement par chemin.
_VALIDATE_COHERENCE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "validate-coherence.py"
_spec = importlib.util.spec_from_file_location("validate_coherence", _VALIDATE_COHERENCE_PATH)
assert _spec is not None and _spec.loader is not None
vc = importlib.util.module_from_spec(_spec)
sys.modules["validate_coherence"] = vc
_spec.loader.exec_module(vc)


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """DB fraîche avec toutes les tables initialisées, isolée via monkeypatch."""
    path = tmp_path / "v9_coherence_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)
    init_scene_db(path)
    init_behavior_db(path)
    init_window_db(path)
    init_exploitability_db(path)
    init_principle_db(path)
    init_signal_db(path)
    init_decision_db(path)
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_offset(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_decision(
    conn: sqlite3.Connection,
    *,
    decision_id: str = "dec_test00001",
    snapshot_id: str | None = None,
    signal_id: str | None = "sig_test00001",
    direction: str | None = "haussiere",
    confiance: int | None = 75,
    timestamp: str | None = None,
    source_type: str = "live",
) -> None:
    conn.execute(
        "INSERT INTO decisions ("
        " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
        " action, symbol, timeframe, currency,"
        " scene_id, behavior_id, window_id, exploitability_id,"
        " regime_type, direction, confiance,"
        " principes_json, contexte_complet_json, source_type, created_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            decision_id, "1.0", timestamp or _now_iso(), snapshot_id, signal_id,
            "surveiller", "GBPUSD", "M15", "GBP",
            "scene_test", "behav_test", "win_test", "exploit_test",
            "tendance", direction, confiance,
            "[]", "{}", source_type, timestamp or _now_iso(),
        ),
    )
    conn.commit()


def _insert_signal(
    conn: sqlite3.Connection,
    *,
    signal_id: str = "sig_test00001",
    snapshot_id: str | None = "snap_test00001",
    direction: str | None = "haussiere",
    confiance: int = 75,
    principes_source_json: str = '["NODE_BIRTH_FAST"]',
    timestamp: str | None = None,
    source_type: str = "live",
) -> None:
    conn.execute(
        "INSERT INTO signals ("
        " signal_id, schema_version, timestamp, snapshot_id,"
        " symbol, timeframe, currency, direction, confiance, horizon,"
        " principes_source_json, regime_type, exploitability_id,"
        " exploitability_statut, raison_absence, stale, source_type, created_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            signal_id, "1.0", timestamp or _now_iso(), snapshot_id,
            "GBPUSD", "M15", "GBP", direction, confiance, "court_terme",
            principes_source_json, "tendance", "exploit_test",
            "exploitable", None, False, source_type, timestamp or _now_iso(),
        ),
    )
    conn.commit()


def _insert_scene(
    conn: sqlite3.Connection,
    *,
    scene_id: str = "scene_test00001",
    forces_snapshot_ref: str | None = "snap_test00001",
    timestamp: str | None = None,
    source_type: str = "live",
) -> None:
    conn.execute(
        "INSERT INTO scenes ("
        " scene_id, schema_version, timestamp, timeframes_concernes,"
        " forces_snapshot_ref, forces_snapshot_timestamp,"
        " zone_json, coalitions_json, antagonismes_json, cinematique_json,"
        " confluences_mtf_json, contexte_temporel_json, risk_assessment_json,"
        " stale, source_type, created_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            scene_id, "1.0", timestamp or _now_iso(), "M15",
            forces_snapshot_ref, timestamp or _now_iso(),
            "{}", "[]", "[]", "{}", "{}", "{}", "{}",
            False, source_type, timestamp or _now_iso(),
        ),
    )
    conn.commit()


def _insert_forces_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_id: str = "snap_test00001",
    timestamp: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO forces_snapshots ("
        " snapshot_id, schema_version, timestamp, source,"
        " symbol, timeframe, bar_time, is_closed_bar,"
        " open, high, low, close, tick_volume, spread_points, spread_price,"
        " bid, ask, mid,"
        " force_usd, force_gbp, force_eur, force_jpy,"
        " force_cad, force_chf, force_aud, force_nzd,"
        " direction, vitesse,"
        " croisement_detecte, croisement_partenaire, croisement_direction,"
        " recroisement_detecte, recroisement_contexte,"
        " rejet_repulsion_detecte, rejet_intensite,"
        " compression_extension_etat, compression_extension_intensite,"
        " stale, age_ms, stale_threshold_ms, created_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            snapshot_id, "1.0", timestamp or _now_iso(), "MT4_SDI",
            "GBPUSD", "M15", 1, True,
            1.0, 1.0, 1.0, 1.0, 100, 10, 0.00010,
            1.0, 1.0, 1.0,
            50.0, 50.0, 50.0, 50.0,
            50.0, 50.0, 50.0, 50.0,
            "haussiere", 0.0,
            False, None, None,
            False, None,
            False, 0.0,
            "neutre", 0.0,
            False, 0, 1000, timestamp or _now_iso(),
        ),
    )
    conn.commit()


def _insert_principle(
    conn: sqlite3.Connection,
    *,
    principle_id: str = "TEST_PRINCIPLE_ACTIVE",
    v9_status: str = "ACTIVE",
) -> None:
    conn.execute(
        "INSERT INTO principles ("
        " principle_id, version, origin, kind, source_status, v9_status,"
        " scope_timeframes_json, scope_currencies_json,"
        " conditions_json, emits_json, bounds_json,"
        " anti_signal_bias, notes, created_by, created_at_source, synced_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            principle_id, 1, "test", "node_rule", "ACTIVE", v9_status,
            "[]", "[]", "[]", "[]", "{}", False, "test", "test",
            _now_iso(), _now_iso(),
        ),
    )
    conn.commit()


# ---------- Tests ----------


def test_check1_orphelin_scene(db_path: Path) -> None:
    """Scene qui pointe vers un snapshot inexistant → ERREUR."""
    conn = _connect(db_path)
    try:
        # Snapshot inexistant — pas de forces_snapshots inséré.
        _insert_scene(conn, scene_id="scene_orphan_001",
                      forces_snapshot_ref="snap_DOES_NOT_EXIST")
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check1_orphans(conn)
    finally:
        conn.close()

    assert result["status"] == "ERROR"
    assert result["count"] == 1
    assert result["issues"][0]["table"] == "scenes"
    assert result["issues"][0]["id"] == "scene_orphan_001"
    assert result["issues"][0]["missing_ref"] == "snap_DOES_NOT_EXIST"


def test_check2_decision_sans_signal(db_path: Path) -> None:
    """Decision qui pointe vers un signal_id inexistant → ERREUR."""
    conn = _connect(db_path)
    try:
        _insert_decision(conn, decision_id="dec_orphan_001",
                         signal_id="sig_DOES_NOT_EXIST")
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check2_decisions_without_signal(conn)
    finally:
        conn.close()

    assert result["status"] == "ERROR"
    assert result["count"] == 1
    assert result["issues"][0]["decision_id"] == "dec_orphan_001"
    assert result["issues"][0]["missing_signal_id"] == "sig_DOES_NOT_EXIST"


def test_check3_signal_sans_principe(db_path: Path) -> None:
    """Signal directionnel avec principes_source_json vide → ERREUR."""
    conn = _connect(db_path)
    try:
        _insert_signal(conn, signal_id="sig_no_principe_001",
                       direction="haussiere",
                       principes_source_json="[]")
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check3_signals_without_principles(conn)
    finally:
        conn.close()

    assert result["status"] == "ERROR"
    assert result["count"] == 1
    assert result["issues"][0]["signal_id"] == "sig_no_principe_001"
    assert result["issues"][0]["direction"] == "haussiere"


def test_check3_signal_neutre_ok(db_path: Path) -> None:
    """Signal avec direction='neutre' (pas directionnel) → pas d'erreur
    même si principes_source_json vide (cas légitime pour signal absent)."""
    conn = _connect(db_path)
    try:
        _insert_signal(conn, signal_id="sig_neutre_001",
                       direction="neutre",
                       principes_source_json="[]")
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check3_signals_without_principles(conn)
    finally:
        conn.close()

    assert result["status"] == "OK"
    assert result["count"] == 0


def test_check4_live_stale(db_path: Path) -> None:
    """Rangée live avec timestamp > 24h → WARNING."""
    conn = _connect(db_path)
    try:
        # Signal avec timestamp vieux (>24h) et source_type='live'
        old_ts = _iso_offset(-48)
        _insert_signal(conn, signal_id="sig_stale_001",
                       timestamp=old_ts, source_type="live")
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check4_live_stale_snapshots(conn)
    finally:
        conn.close()

    assert result["status"] == "WARNING"
    assert result["count"] >= 1
    assert any(i["table"] == "signals" for i in result["issues"])


def test_check4_live_recent_ok(db_path: Path) -> None:
    """Rangée live avec timestamp < 24h → OK."""
    conn = _connect(db_path)
    try:
        _insert_signal(conn, signal_id="sig_recent_001",
                       timestamp=_iso_offset(-1), source_type="live")
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check4_live_stale_snapshots(conn)
    finally:
        conn.close()

    assert result["status"] == "OK"


def test_check5_doublon_decision(db_path: Path) -> None:
    """2 décisions sur même snapshot_id+direction+confiance → WARNING."""
    conn = _connect(db_path)
    try:
        _insert_decision(conn, decision_id="dec_dup_001",
                         snapshot_id="snap_dup", direction="haussiere",
                         confiance=75)
        _insert_decision(conn, decision_id="dec_dup_002",
                         snapshot_id="snap_dup", direction="haussiere",
                         confiance=75)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check5_decision_duplicates(conn)
    finally:
        conn.close()

    assert result["status"] == "WARNING"
    assert result["count"] == 1
    issue = result["issues"][0]
    assert issue["snapshot_id"] == "snap_dup"
    assert issue["direction"] == "haussiere"
    assert issue["confiance"] == 75
    assert "dec_dup_001" in issue["decision_ids"]
    assert "dec_dup_002" in issue["decision_ids"]


def test_check5_doublon_different_direction_ok(db_path: Path) -> None:
    """2 décisions sur même snapshot_id mais direction différente → OK."""
    conn = _connect(db_path)
    try:
        _insert_decision(conn, decision_id="dec_diff_001",
                         snapshot_id="snap_diff", direction="haussiere",
                         confiance=75)
        _insert_decision(conn, decision_id="dec_diff_002",
                         snapshot_id="snap_diff", direction="baissiere",
                         confiance=60)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check5_decision_duplicates(conn)
    finally:
        conn.close()

    assert result["status"] == "OK"


def test_check6_principes_actifs_sans_eval(db_path: Path) -> None:
    """Principe ACTIVE jamais évalué sur 12h → WARNING."""
    conn = _connect(db_path)
    try:
        _insert_principle(conn, principle_id="PRINCIPE_MUET", v9_status="ACTIVE")
        # Pas d'insertion dans principle_evaluations
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check6_principles_no_recent_eval(conn)
    finally:
        conn.close()

    assert result["status"] == "WARNING"
    assert any(i["principle_id"] == "PRINCIPE_MUET" for i in result["issues"])


def test_check7_confiance_hors_plage(db_path: Path) -> None:
    """Decision directionnelle avec confiance=0 ET decision confiance=150
    → 2 ERREURS."""
    conn = _connect(db_path)
    try:
        _insert_decision(conn, decision_id="dec_conf_zero",
                         direction="haussiere", confiance=0)
        _insert_decision(conn, decision_id="dec_conf_over",
                         direction="haussiere", confiance=150)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check7_confiance_out_of_range(conn)
    finally:
        conn.close()

    assert result["status"] == "ERROR"
    assert result["count"] == 2
    reasons = {i["reason"] for i in result["issues"]}
    assert any("confiance=0" in r for r in reasons)
    assert any("confiance > 100" in r for r in reasons)


def test_check7_confiance_ok(db_path: Path) -> None:
    """Decision directionnelle avec confiance=75 → OK."""
    conn = _connect(db_path)
    try:
        _insert_decision(conn, decision_id="dec_ok", direction="haussiere",
                         confiance=75)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check7_confiance_out_of_range(conn)
    finally:
        conn.close()

    assert result["status"] == "OK"


def test_check7_confiance_neutre_zero_ok(db_path: Path) -> None:
    """Decision NON directionnelle (neutre) avec confiance=0 → OK
    (zero confiance sur signal neutre est légitime)."""
    conn = _connect(db_path)
    try:
        _insert_decision(conn, decision_id="dec_neutre_zero",
                         direction="neutre", confiance=0)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        result = vc.check7_confiance_out_of_range(conn)
    finally:
        conn.close()

    assert result["status"] == "OK"


def test_all_ok(db_path: Path) -> None:
    """DB propre — toutes les FK valides, données cohérentes → exit 0."""
    conn = _connect(db_path)
    try:
        # Chaîne complète valide
        _insert_forces_snapshot(conn, snapshot_id="snap_clean")
        _insert_scene(conn, scene_id="scene_clean",
                      forces_snapshot_ref="snap_clean")
        _insert_signal(conn, signal_id="sig_clean", snapshot_id="snap_clean",
                       direction="haussiere",
                       principes_source_json='["NODE_BIRTH_FAST"]')
        _insert_decision(conn, decision_id="dec_clean",
                         snapshot_id="snap_clean", signal_id="sig_clean",
                         direction="haussiere", confiance=75)
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        results = vc.run_all_checks(conn)
        summary = vc.summarize(results)
    finally:
        conn.close()

    assert summary["exit_code"] == 0
    assert summary["counts"]["error"] == 0
    assert summary["counts"]["warning"] == 0
    for r in results:
        if r["check"] not in ("4_live_stale", "6_principles_no_eval"):
            # 4 et 6 peuvent remonter des warnings pré-existants si tables
            # peuplées ailleurs — sur DB vide ce sont OK.
            assert r["status"] == "OK", f"check {r['check']} failed: {r}"


def test_summarize_exit_codes() -> None:
    """vc.summarize() retourne le bon exit_code selon les statuts."""
    results = [
        {"check": "a", "label": "A", "status": "OK", "issues": [], "count": 0},
        {"check": "b", "label": "B", "status": "WARNING", "issues": [], "count": 0},
        {"check": "c", "label": "C", "status": "ERROR", "issues": [], "count": 0},
    ]
    s = vc.summarize(results)
    assert s["exit_code"] == 2  # ERROR > WARNING > OK

    s2 = vc.summarize([{"check": "a", "label": "A", "status": "WARNING",
                         "issues": [], "count": 0}])
    assert s2["exit_code"] == 1

    s3 = vc.summarize([{"check": "a", "label": "A", "status": "OK",
                         "issues": [], "count": 0}])
    assert s3["exit_code"] == 0


def test_format_console_contains_check_labels() -> None:
    """Le format console liste tous les checks."""
    results = [{"check": "x_test", "label": "Test label", "status": "OK",
                "issues": [], "count": 0}]
    out = vc.format_console(results, vc.summarize(results))
    assert "x_test" in out
    assert "Test label" in out
    assert "OK=" in out


def test_format_fix_report_skips_ok() -> None:
    """Le fix-report ne mentionne que les checks non-OK."""
    results = [
        {"check": "ok_one", "label": "OK 1", "status": "OK",
         "issues": [], "count": 0},
        {"check": "warn_one", "label": "Warn 1", "status": "WARNING",
         "issues": [{"id": "x"}], "count": 1},
    ]
    out = vc.format_fix_report(results)
    assert "ok_one" not in out
    assert "warn_one" in out


def test_main_json_output(db_path: Path, capsys) -> None:
    """--json produit une sortie JSON parsable."""
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["validate-coherence", "--json"]
        rc = vc.main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "summary" in data
    assert "checks" in data
    assert data["summary"]["exit_code"] in (0, 1, 2)
    assert rc == data["summary"]["exit_code"]


def test_main_fix_report_output(db_path: Path, capsys) -> None:
    """--fix-report produit le rapport de cohérence."""
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["validate-coherence", "--fix-report"]
        rc = vc.main()
    finally:
        sys.argv = old_argv

    captured = capsys.readouterr()
    assert "V9 DB" in captured.out
    assert rc in (0, 1, 2)


def test_table_exists_helper(db_path: Path) -> None:
    """vc._table_exists détecte les tables présentes et absentes."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        assert vc._table_exists(conn, "decisions") is True
        assert vc._table_exists(conn, "table_qui_existe_pas") is False
    finally:
        conn.close()


def test_parse_iso_helper() -> None:
    """vc._parse_iso gère les variantes ISO UTC."""
    assert vc._parse_iso("2026-07-07T10:00:00+00:00") is not None
    assert vc._parse_iso("2026-07-07T10:00:00Z") is not None
    assert vc._parse_iso("invalid") is None
    assert vc._parse_iso(None) is None