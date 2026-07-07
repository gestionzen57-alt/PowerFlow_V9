"""Tests unitaires — Arbiter (core/v9/arbiter.py, Phase 10).

Couvre 6 cas exigés par le brief :
  1. test_consolidate_un_signal_baissier
  2. test_consolidate_direction_majoritaire
  3. test_consolidate_neutre_si_vide
  4. test_consolidate_plafond_confiance_1_principe
  5. test_consolidate_principes_source_union
  6. test_consolidate_lecture_seule_no_write

+ tests annexes : confiance_brute, plafonne_sous_2_principes False,
  arbiter_version, snapshot_id propagation, principes JSON malformé.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9 import config, db_schema
from core.v9.arbiter import ARBITER_VERSION, CONFIANCE_PLAFOND_SOUS_2_PRINCIPES, Arbiter
from core.v9.db_schema import init_db
from core.v9.decision_db import init_decision_db


# ---------- Fixtures ----------


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "v9_arbiter_test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(db_schema, "DB_PATH", path)
    init_db(path)
    init_decision_db(path)
    return path


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _insert_decision(
    db_path: Path,
    *,
    snapshot_id: str = "snap_test",
    decision_id: str | None = None,
    direction: str = "haussiere",
    confiance: int = 75,
    principes: list[str] | None = None,
    source_type: str = "live",
    timestamp: str = "2026-07-07T10:00:00+00:00",
) -> str:
    if decision_id is None:
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id, "1.0", timestamp, snapshot_id, "sig_test",
                "surveiller", "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", direction, confiance,
                json.dumps(principes or []), "{}", source_type, timestamp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return decision_id


# ---------- Tests ----------


def test_consolidate_un_signal_baissier(db_path: Path) -> None:
    """Cas 1 — 1 décision baissière conf 80, 2 principes → résultat simple."""
    _insert_decision(db_path, snapshot_id="snap_bear",
                     direction="baissiere", confiance=80,
                     principes=["NODE_BIRTH_FAST", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"])
    arbiter = Arbiter(db_path=db_path)
    result = arbiter.consolidate("snap_bear")

    assert result["direction"] == "baissiere"
    assert result["confiance_arbitree"] == 80
    assert result["confiance_brute"] == 80
    assert result["plafonne_sous_2_principes"] is False
    assert result["nb_principes_actifs"] == 2
    assert sorted(result["principes_source"]) == sorted(
        ["NODE_BIRTH_FAST", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT"]
    )
    assert result["arbiter_version"] == ARBITER_VERSION
    assert result["nb_decisions_consolidees"] == 1
    assert result["nb_decisions_totales"] == 1
    assert result["snapshot_id"] == "snap_bear"


def test_consolidate_direction_majoritaire(db_path: Path) -> None:
    """Cas 2 — 3 décisions (2 haussières, 1 baissière) → direction=haussiere
    et confiance = moyenne des 2 haussières uniquement."""
    _insert_decision(db_path, snapshot_id="snap_mix",
                     decision_id="dec_h1", direction="haussiere", confiance=80,
                     principes=["P1"])
    _insert_decision(db_path, snapshot_id="snap_mix",
                     decision_id="dec_h2", direction="haussiere", confiance=90,
                     principes=["P2"])
    _insert_decision(db_path, snapshot_id="snap_mix",
                     decision_id="dec_b1", direction="baissiere", confiance=95,
                     principes=["P3"])

    result = Arbiter(db_path=db_path).consolidate("snap_mix")

    assert result["direction"] == "haussiere"
    assert result["confiance_arbitree"] == 85  # moyenne (80+90)/2
    assert result["nb_decisions_consolidees"] == 2
    assert result["nb_decisions_totales"] == 3
    assert sorted(result["principes_source"]) == ["P1", "P2"]


def test_consolidate_neutre_si_vide(db_path: Path) -> None:
    """Cas 3 — aucune décision directionnelle → neutre, confiance=0."""
    result = Arbiter(db_path=db_path).consolidate("snap_vide")

    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0
    assert result["principes_source"] == []
    assert result["nb_principes_actifs"] == 0
    assert result["nb_decisions_consolidees"] == 0


def test_consolidate_neutre_si_que_neutre(db_path: Path) -> None:
    """Décisions non-directionnelles (direction='neutre') ignorées → vide."""
    _insert_decision(db_path, snapshot_id="snap_neutres",
                     direction="neutre", confiance=0,
                     principes=[])
    result = Arbiter(db_path=db_path).consolidate("snap_neutres")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0


def test_consolidate_neutre_si_que_replay(db_path: Path) -> None:
    """Décisions avec source_type='replay' sont ignorées."""
    _insert_decision(db_path, snapshot_id="snap_replay",
                     direction="haussiere", confiance=90,
                     principes=["P1"], source_type="replay")
    result = Arbiter(db_path=db_path).consolidate("snap_replay")
    assert result["direction"] == "neutre"
    assert result["confiance_arbitree"] == 0


def test_consolidate_plafond_confiance_1_principe(db_path: Path) -> None:
    """Cas 4 — 1 seul principe actif → confiance_arbitree plafonnée à 74."""
    _insert_decision(db_path, snapshot_id="snap_plafond",
                     direction="haussiere", confiance=95,
                     principes=["P_UNIQUE"])

    result = Arbiter(db_path=db_path).consolidate("snap_plafond")

    assert result["direction"] == "haussiere"
    assert result["confiance_brute"] == 95  # avant plafond
    assert result["confiance_arbitree"] == CONFIANCE_PLAFOND_SOUS_2_PRINCIPES
    assert result["plafonne_sous_2_principes"] is True
    assert result["nb_principes_actifs"] == 1


def test_consolidate_plafond_pas_applique_2_principes(db_path: Path) -> None:
    """Avec ≥ 2 principes, pas de plafond."""
    _insert_decision(db_path, snapshot_id="snap_2p",
                     direction="haussiere", confiance=95,
                     principes=["P1", "P2"])
    result = Arbiter(db_path=db_path).consolidate("snap_2p")
    assert result["confiance_arbitree"] == 95
    assert result["plafonne_sous_2_principes"] is False


def test_consolidate_plafond_pas_applique_si_deja_bas(db_path: Path) -> None:
    """Si confiance_brute ≤ 74, le plafond n'est pas marqué actif
    (plafonne_sous_2_principes=False) — la valeur ne change pas mais
    on n'indique pas un plafonnement trompeur."""
    _insert_decision(db_path, snapshot_id="snap_low",
                     direction="haussiere", confiance=60,
                     principes=["P_UNIQUE"])
    result = Arbiter(db_path=db_path).consolidate("snap_low")
    assert result["confiance_arbitree"] == 60
    assert result["confiance_brute"] == 60
    assert result["plafonne_sous_2_principes"] is False


def test_consolidate_principes_source_union(db_path: Path) -> None:
    """Cas 5 — plusieurs décisions même direction → union des principes."""
    _insert_decision(db_path, snapshot_id="snap_union",
                     decision_id="dec_u1", direction="haussiere",
                     confiance=80, principes=["P_A", "P_B"])
    _insert_decision(db_path, snapshot_id="snap_union",
                     decision_id="dec_u2", direction="haussiere",
                     confiance=85, principes=["P_B", "P_C"])
    _insert_decision(db_path, snapshot_id="snap_union",
                     decision_id="dec_u3", direction="haussiere",
                     confiance=90, principes=["P_C", "P_D"])

    result = Arbiter(db_path=db_path).consolidate("snap_union")

    # Union : P_A, P_B, P_C, P_D (4 uniques, ordre de 1ère apparition)
    assert result["principes_source"] == ["P_A", "P_B", "P_C", "P_D"]
    assert result["nb_principes_actifs"] == 4


def test_consolidate_lecture_seule_no_write(db_path: Path) -> None:
    """Cas 6 — l'Arbiter ne crée AUCUNE nouvelle rangée en DB.

    On compte les rangées AVANT puis APRÈS plusieurs consolidates, le
    total doit rester identique. Aucune table 'arbiter_results' ou autre
    ne doit apparaître.
    """
    _insert_decision(db_path, snapshot_id="snap_ro",
                     direction="haussiere", confiance=85,
                     principes=["P1", "P2"])

    conn = _connect(db_path)
    try:
        tables_before = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        count_decisions_before = conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]
    finally:
        conn.close()

    arbiter = Arbiter(db_path=db_path)
    arbiter.consolidate("snap_ro")
    arbiter.consolidate("snap_ro")
    arbiter.consolidate("snap_ro")

    conn = _connect(db_path)
    try:
        tables_after = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        count_decisions_after = conn.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]
    finally:
        conn.close()

    assert tables_before == tables_after, "Arbiter ne doit créer aucune table"
    assert count_decisions_before == count_decisions_after, "Arbiter ne doit écrire dans decisions"


def test_consolidate_principes_json_malformed(db_path: Path) -> None:
    """principes_json corrompu (non-JSON) → liste vide tolérée."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO decisions ("
            " decision_id, schema_version, timestamp, snapshot_id, signal_id,"
            " action, symbol, timeframe, currency,"
            " scene_id, behavior_id, window_id, exploitability_id,"
            " regime_type, direction, confiance,"
            " principes_json, contexte_complet_json, source_type, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "dec_bad_json", "1.0", "2026-07-07T10:00:00+00:00",
                "snap_bad", "sig_test", "surveiller", "GBPUSD", "M15", "GBP",
                "scene_t", "behav_t", "win_t", "exploit_t",
                "tendance", "haussiere", 80,
                "{not valid json", "{}", "live",
                "2026-07-07T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    result = Arbiter(db_path=db_path).consolidate("snap_bad")
    assert result["direction"] == "haussiere"
    assert result["principes_source"] == []
    assert result["nb_principes_actifs"] == 0


def test_consolidate_snapshot_id_isolated(db_path: Path) -> None:
    """Les décisions d'autres snapshot_id ne sont jamais incluses."""
    _insert_decision(db_path, snapshot_id="snap_A",
                     direction="haussiere", confiance=90,
                     principes=["P_A1", "P_A2"])
    _insert_decision(db_path, snapshot_id="snap_B",
                     direction="baissiere", confiance=70,
                     principes=["P_B1"])

    res_a = Arbiter(db_path=db_path).consolidate("snap_A")
    res_b = Arbiter(db_path=db_path).consolidate("snap_B")

    assert res_a["direction"] == "haussiere"
    assert res_a["principes_source"] == ["P_A1", "P_A2"]
    assert res_b["direction"] == "baissiere"
    assert res_b["principes_source"] == ["P_B1"]


def test_consolidate_timestamp_max(db_path: Path) -> None:
    """Le timestamp du résultat = max(timestamps décisions consolidées)."""
    _insert_decision(db_path, snapshot_id="snap_ts",
                     decision_id="dec_ts1", direction="haussiere",
                     confiance=80, principes=["P1"],
                     timestamp="2026-07-07T10:00:00+00:00")
    _insert_decision(db_path, snapshot_id="snap_ts",
                     decision_id="dec_ts2", direction="haussiere",
                     confiance=85, principes=["P1"],
                     timestamp="2026-07-07T10:05:00+00:00")
    result = Arbiter(db_path=db_path).consolidate("snap_ts")
    assert result["timestamp"] == "2026-07-07T10:05:00+00:00"


def test_consolidate_moyenne_arrondie(db_path: Path) -> None:
    """Moyenne confiance arrondie à l'entier le plus proche.

    Avec 1 seul principe, le plafond à 74 s'applique — on utilise donc
    2 principes pour tester l'arrondi pur.
    """
    _insert_decision(db_path, snapshot_id="snap_avg",
                     decision_id="dec_a1", direction="haussiere",
                     confiance=80, principes=["P1", "P2"])
    _insert_decision(db_path, snapshot_id="snap_avg",
                     decision_id="dec_a2", direction="haussiere",
                     confiance=81, principes=["P1", "P2"])
    # Moyenne = 80.5 → round → 80 (banker's rounding Python : 80.5 → 80)
    result = Arbiter(db_path=db_path).consolidate("snap_avg")
    assert isinstance(result["confiance_arbitree"], int)
    assert result["confiance_arbitree"] in (80, 81)  # tolérance banker's rounding
    assert result["plafonne_sous_2_principes"] is False