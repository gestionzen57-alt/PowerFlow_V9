"""Tests unitaires — core.v9.behavior_analyzer.BehaviorAnalyzer."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from core.v9.behavior_analyzer import BehaviorAnalyzer, INTENSITES, PHASES, QUALIFICATIONS
from core.v9.db_schema import get_connection, init_db
from core.v9.scene_db import SCENES_COLUMNS, init_scene_db

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scenes_sample.json"

DEFAULT_SYMBOL = "EURUSD"
DEFAULT_TIMEFRAME = "M5"


# ── Fabriques de scènes ────────────────────────────────────

def _default_cinematique(**overrides) -> dict:
    base = {
        "angle": 0.0,
        "courbure": 0.0,
        "pente": 0.0,
        "pliure": {"detectee": False, "severite": None},
        "acceleration_deceleration": "stable",
        "rotation_force": {"detectee": False, "sens": None},
        "compression_extension": {"etat": "neutre", "intensite": 0.0},
    }
    base.update(overrides)
    return base


def make_scene(
    scene_id: str,
    timestamp: str,
    snapshot_id: str,
    coalitions: list | None = None,
    antagonismes: list | None = None,
    cinematique: dict | None = None,
    mtf_confirmed: bool = False,
) -> dict:
    return {
        "schema_version": "1.0",
        "scene_id": scene_id,
        "timestamp": timestamp,
        "timeframes_concernes": [DEFAULT_TIMEFRAME],
        "forces_snapshot_ref": {"snapshot_id": snapshot_id, "timestamp": timestamp},
        "zone": {
            "prix": {"niveau_reference": 1.0, "borne_basse": None, "borne_haute": None},
            "structure": "zone de test",
            "niveau": "mineure",
        },
        "coalitions": coalitions or [],
        "antagonismes": antagonismes or [],
        "cinematique_locale": cinematique or _default_cinematique(),
        "confluences_mtf": {
            "emboitement_detecte": mtf_confirmed,
            "cascades_temporelles": [],
            "signatures_coherence": [],
        },
        "contexte_temporel": {"session": "Londres", "fenetre": "mi-session"},
    }


def _insert_forces_snapshot(db_path: Path, snapshot_id: str, symbol: str, timeframe: str, timestamp: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO forces_snapshots "
            "(snapshot_id, schema_version, timestamp, source, symbol, timeframe, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd, "
            "stale, created_at) "
            "VALUES (?, '1.0', ?, 'MT4_SDI', ?, ?, 50,50,50,50,50,50,50,50, 0, ?)",
            (snapshot_id, timestamp, symbol, timeframe, timestamp),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_scene(db_path: Path, scene: dict) -> None:
    conn = get_connection(db_path)
    try:
        ref = scene["forces_snapshot_ref"]
        values = [
            scene["scene_id"],
            scene["schema_version"],
            scene["timestamp"],
            json.dumps(scene["timeframes_concernes"]),
            ref["snapshot_id"],
            ref["timestamp"],
            json.dumps(scene["zone"]),
            json.dumps(scene["coalitions"]),
            json.dumps(scene["antagonismes"]),
            json.dumps(scene["cinematique_locale"]),
            json.dumps(scene["confluences_mtf"]),
            json.dumps(scene["contexte_temporel"]),
            False,
            "live",
            scene["timestamp"],
        ]
        col_names = ", ".join(SCENES_COLUMNS)
        placeholders = ", ".join(["?"] * len(SCENES_COLUMNS))
        conn.execute(f"INSERT INTO scenes ({col_names}) VALUES ({placeholders})", values)
        conn.commit()
    finally:
        conn.close()


def _setup(tmp_path: Path, memory_subdir: str = "memory") -> tuple[Path, BehaviorAnalyzer]:
    db_path = tmp_path / "v9_behavior_test.db"
    init_db(db_path)
    init_scene_db(db_path)
    analyzer = BehaviorAnalyzer(db_path=db_path, config={"memory_dir": tmp_path / memory_subdir})
    return db_path, analyzer


def _add_scene(
    db_path: Path,
    scene_id: str,
    timestamp: str,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    **scene_kwargs,
) -> dict:
    snapshot_id = f"fs-{scene_id}"
    _insert_forces_snapshot(db_path, snapshot_id, symbol, timeframe, timestamp)
    scene = make_scene(scene_id, timestamp, snapshot_id, **scene_kwargs)
    _insert_scene(db_path, scene)
    return scene


def _load_fixture_scenes() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)["scenes"]


# ── Qualifications ─────────────────────────────────────────

def test_qualification_bascule(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z",
        antagonismes=[
            {"devises_en_conflit": ["GBP", "USD"], "intensite_conflit": 45.0,
             "bascule_equilibre": {"detectee": True, "sens": "GBP"}}
        ],
        cinematique=_default_cinematique(
            pliure={"detectee": True, "severite": 22.0},
            acceleration_deceleration="acceleration",
            compression_extension={"etat": "extension", "intensite": 30.0},
        ),
    )
    behavior = analyzer.analyze_scene("s1")
    assert behavior["comportement"]["qualification"] == "bascule"


def test_qualification_maintien(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(db_path, "s1", "2026-07-05T14:00:00.000Z")
    behavior = analyzer.analyze_scene("s1")
    assert behavior["comportement"]["qualification"] == "maintien"


def test_qualification_lutte_forces(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z",
        antagonismes=[
            {"devises_en_conflit": ["GBP", "USD"], "intensite_conflit": 55.0,
             "bascule_equilibre": {"detectee": False, "sens": None}}
        ],
    )
    behavior = analyzer.analyze_scene("s1")
    assert behavior["comportement"]["qualification"] == "lutte_forces"


def test_qualification_contraction(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 18.0}
        ),
    )
    behavior = analyzer.analyze_scene("s1")
    assert behavior["comportement"]["qualification"] == "contraction"


def test_qualification_extension(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z",
        cinematique=_default_cinematique(
            compression_extension={"etat": "extension", "intensite": 18.0}
        ),
    )
    behavior = analyzer.analyze_scene("s1")
    assert behavior["comportement"]["qualification"] == "extension"


def test_qualification_annulation(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z",
        antagonismes=[
            {"devises_en_conflit": ["GBP", "USD"], "intensite_conflit": 20.0,
             "bascule_equilibre": {"detectee": True, "sens": "USD"}}
        ],
    )
    analyzer.analyze_scene("s1")

    _add_scene(
        db_path, "s2", "2026-07-05T14:05:00.000Z",
        antagonismes=[
            {"devises_en_conflit": ["GBP", "USD"], "intensite_conflit": 20.0,
             "bascule_equilibre": {"detectee": True, "sens": "GBP"}}
        ],
    )
    behavior = analyzer.analyze_scene("s2")
    assert behavior["comportement"]["qualification"] == "annulation"


def test_qualification_rotation_leadership(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z",
        coalitions=[
            {"devises_alignees": ["AUD", "NZD"], "intensite_alignement": 64.5, "leader": "NZD",
             "rotation_leadership": {"detectee": True, "ancien_leader": "AUD", "nouveau_leader": "NZD"}}
        ],
    )
    behavior = analyzer.analyze_scene("s1")
    assert behavior["comportement"]["qualification"] == "rotation_leadership"


# ── Intensité ────────────────────────────────────────────

def test_intensite_levels(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    cases = [
        ("faible", 10.0, "faible"),
        ("moderee", 30.0, "moderee"),
        ("forte", 55.0, "forte"),
        ("extreme", 80.0, "extreme"),
    ]
    for i, (label, strength, expected) in enumerate(cases):
        scene_id = f"s-int-{label}"
        _add_scene(
            db_path, scene_id, f"2026-07-05T15:{i:02d}:00.000Z",
            symbol="AUDCAD",
            cinematique=_default_cinematique(
                compression_extension={"etat": "neutre", "intensite": strength}
            ),
        )
        behavior = analyzer.analyze_scene(scene_id)
        assert behavior["comportement"]["intensite"] == expected


# ── Phase ────────────────────────────────────────────────

def test_phase_detection_sequence(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    intensities = [10.0, 30.0, 55.0, 80.0, 30.0]
    expected_phases = ["initiation", "developpement", "culmination", "culmination", "resolution"]

    for i, (strength, expected_phase) in enumerate(zip(intensities, expected_phases)):
        scene_id = f"s-phase-{i}"
        _add_scene(
            db_path, scene_id, f"2026-07-05T16:{i:02d}:00.000Z",
            symbol="NZDCHF",
            cinematique=_default_cinematique(
                compression_extension={"etat": "compression", "intensite": strength}
            ),
        )
        behavior = analyzer.analyze_scene(scene_id)
        assert behavior["comportement"]["qualification"] == "contraction"
        assert behavior["comportement"]["phase"] == expected_phase


# ── Transitions ──────────────────────────────────────────

def test_transition_comportement_precedent_et_point_de_rupture(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="USDCHF",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 15.0}
        ),
    )
    analyzer.analyze_scene("s1")

    _add_scene(
        db_path, "s2", "2026-07-05T14:05:00.000Z", symbol="USDCHF",
        antagonismes=[
            {"devises_en_conflit": ["USD", "CHF"], "intensite_conflit": 45.0,
             "bascule_equilibre": {"detectee": True, "sens": "USD"}}
        ],
        cinematique=_default_cinematique(
            pliure={"detectee": True, "severite": 22.0},
            acceleration_deceleration="acceleration",
            compression_extension={"etat": "extension", "intensite": 30.0},
        ),
    )
    behavior = analyzer.analyze_scene("s2")

    transitions = behavior["transitions"]
    assert transitions["comportement_precedent"] == "contraction"
    assert transitions["point_de_rupture"]["detecte"] is True
    assert transitions["point_de_rupture"]["timestamp"] == "2026-07-05T14:05:00.000Z"
    assert transitions["point_de_rupture"]["declencheur"]


def test_sens_transition_escalade(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="EURGBP",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 10.0}
        ),
    )
    analyzer.analyze_scene("s1")
    _add_scene(
        db_path, "s2", "2026-07-05T14:05:00.000Z", symbol="EURGBP",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 55.0}
        ),
    )
    behavior = analyzer.analyze_scene("s2")
    assert behavior["transitions"]["sens_transition"] == "escalade"


def test_sens_transition_desescalade(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="EURJPY",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 55.0}
        ),
    )
    analyzer.analyze_scene("s1")
    _add_scene(
        db_path, "s2", "2026-07-05T14:05:00.000Z", symbol="EURJPY",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 10.0}
        ),
    )
    behavior = analyzer.analyze_scene("s2")
    assert behavior["transitions"]["sens_transition"] == "desescalade"


def test_sens_transition_inversion(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="GBPCAD",
        cinematique=_default_cinematique(
            compression_extension={"etat": "compression", "intensite": 20.0}
        ),
    )
    analyzer.analyze_scene("s1")
    _add_scene(
        db_path, "s2", "2026-07-05T14:05:00.000Z", symbol="GBPCAD",
        cinematique=_default_cinematique(
            compression_extension={"etat": "extension", "intensite": 20.0}
        ),
    )
    behavior = analyzer.analyze_scene("s2")
    assert behavior["transitions"]["sens_transition"] == "inversion"


def test_sens_transition_neutre(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    intensities = [10.0, 30.0, 55.0, 55.0]
    for i, strength in enumerate(intensities):
        scene_id = f"s-neutre-{i}"
        _add_scene(
            db_path, scene_id, f"2026-07-05T17:{i:02d}:00.000Z", symbol="CADJPY",
            cinematique=_default_cinematique(
                compression_extension={"etat": "compression", "intensite": strength}
            ),
        )
        behavior = analyzer.analyze_scene(scene_id)

    assert behavior["comportement"]["phase"] == "culmination"
    assert behavior["transitions"]["sens_transition"] == "neutre"


# ── Comparaison cas connus ─────────────────────────────────

def test_comparaison_cas_connus_similarite(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    ant = [
        {"devises_en_conflit": ["EUR", "USD"], "intensite_conflit": 45.0,
         "bascule_equilibre": {"detectee": True, "sens": "EUR"}}
    ]
    cin = _default_cinematique(
        pliure={"detectee": True, "severite": 20.0},
        acceleration_deceleration="acceleration",
        angle=30.0,
        pente=2.0,
        compression_extension={"etat": "extension", "intensite": 28.0},
    )
    _add_scene(db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="EURUSD",
               antagonismes=copy.deepcopy(ant), cinematique=copy.deepcopy(cin))
    analyzer.analyze_scene("s1")

    _add_scene(db_path, "s2", "2026-07-05T15:00:00.000Z", symbol="EURUSD",
               antagonismes=copy.deepcopy(ant), cinematique=copy.deepcopy(cin))
    behavior = analyzer.analyze_scene("s2")

    comparaison = behavior["comparaison_cas_connus"]
    assert comparaison["similarite_score"] is not None
    assert comparaison["similarite_score"] >= 0.65
    assert len(comparaison["cas_references"]) == 1
    assert comparaison["variante_de_comportement_connu"]["est_variante"] is True


def test_comparaison_cas_connus_aucun_cas(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="CHFJPY",
        antagonismes=[
            {"devises_en_conflit": ["CHF", "JPY"], "intensite_conflit": 45.0,
             "bascule_equilibre": {"detectee": True, "sens": "CHF"}}
        ],
        cinematique=_default_cinematique(
            pliure={"detectee": True, "severite": 20.0},
            acceleration_deceleration="acceleration",
            compression_extension={"etat": "extension", "intensite": 28.0},
        ),
    )
    behavior = analyzer.analyze_scene("s1")
    comparaison = behavior["comparaison_cas_connus"]
    assert comparaison["similarite_score"] is None
    assert comparaison["cas_references"] == []
    assert comparaison["variante_de_comportement_connu"]["est_variante"] is False


# ── Confiance basse ─────────────────────────────────────────

def test_confiance_basse_reponse_valide(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="NZDUSD")
    behavior = analyzer.analyze_scene("s1")

    assert behavior is not None
    assert behavior["comportement"]["qualification"] == "maintien"
    assert behavior["comportement"]["confiance_qualification"] < 50
    assert isinstance(behavior["comportement"]["confiance_qualification"], int)


# ── Format JSON ──────────────────────────────────────────

def test_output_json_format_valid_against_format_comportements(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(
        db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="USDCAD",
        antagonismes=[
            {"devises_en_conflit": ["USD", "CAD"], "intensite_conflit": 45.0,
             "bascule_equilibre": {"detectee": True, "sens": "USD"}}
        ],
        cinematique=_default_cinematique(
            pliure={"detectee": True, "severite": 22.0},
            acceleration_deceleration="acceleration",
            compression_extension={"etat": "extension", "intensite": 30.0},
        ),
    )
    behavior = analyzer.analyze_scene("s1")

    required_top = {
        "behavior_id", "schema_version", "timestamp", "scene_id_ref", "scene_timestamp",
        "symbol", "timeframe", "window_start", "window_end",
        "comportement", "transitions", "comparaison_cas_connus", "meta",
    }
    assert required_top.issubset(behavior.keys())
    assert behavior["schema_version"] == "1.0"
    assert behavior["scene_id_ref"] == "s1"

    comp = behavior["comportement"]
    assert comp["qualification"] in QUALIFICATIONS
    assert comp["intensite"] in INTENSITES
    assert comp["phase"] in PHASES
    assert 0 <= comp["confiance_qualification"] <= 100
    assert isinstance(comp["description_courte"], str) and comp["description_courte"]

    transitions = behavior["transitions"]
    assert {"comportement_precedent", "point_de_rupture", "sens_transition"}.issubset(transitions.keys())
    assert {"detecte", "timestamp", "declencheur"}.issubset(transitions["point_de_rupture"].keys())

    comparaison = behavior["comparaison_cas_connus"]
    assert {
        "similarite_score", "cas_references", "singularites_locales", "variante_de_comportement_connu",
    }.issubset(comparaison.keys())
    assert {"est_variante", "comportement_reference", "ecarts"}.issubset(
        comparaison["variante_de_comportement_connu"].keys()
    )

    assert behavior["meta"]["produit_par"] == "behavior-analyzer"

    # round-trip JSON valide
    reparsed = json.loads(json.dumps(behavior))
    assert reparsed["behavior_id"] == behavior["behavior_id"]


# ── Écriture DB / mémoire ──────────────────────────────────

def test_write_behavior_to_db(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    _add_scene(db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="GBPJPY")
    behavior = analyzer.analyze_scene("s1")

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT behavior_id, scene_id_ref, symbol, timeframe, qualification "
            "FROM behaviors WHERE behavior_id = ?",
            (behavior["behavior_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == behavior["behavior_id"]
    assert row[1] == "s1"
    assert row[2] == "GBPJPY"
    assert row[3] == DEFAULT_TIMEFRAME
    assert row[4] == behavior["comportement"]["qualification"]


def test_write_memory_hypothese(tmp_path):
    db_path, analyzer = _setup(tmp_path, memory_subdir="memory_test")
    _add_scene(db_path, "s1", "2026-07-05T14:00:00.000Z", symbol="AUDUSD")
    behavior = analyzer.analyze_scene("s1")

    content = analyzer.memory_temp_path.read_text(encoding="utf-8")
    assert behavior["behavior_id"] in content
    assert '"statut": "hypothese"' in content
    assert '"couche_origine": "comportements"' in content
    assert '"comportement"' in content


# ── Scénario complet (fixture 6 scènes) ─────────────────────

def test_full_sequence_from_fixture(tmp_path):
    db_path, analyzer = _setup(tmp_path)
    scenes = _load_fixture_scenes()
    symbol, timeframe = "GBPUSD", "M5"

    behaviors = []
    for scene in scenes:
        snapshot_id = scene["forces_snapshot_ref"]["snapshot_id"]
        _insert_forces_snapshot(db_path, snapshot_id, symbol, timeframe, scene["timestamp"])
        _insert_scene(db_path, scene)
        behaviors.append(analyzer.analyze_scene(scene["scene_id"]))

    assert len(behaviors) == 6
    assert behaviors[0]["comportement"]["qualification"] == "maintien"
    assert behaviors[1]["comportement"]["qualification"] == "maintien"

    assert behaviors[2]["comportement"]["qualification"] == "bascule"
    assert behaviors[2]["transitions"]["point_de_rupture"]["detecte"] is True
    assert behaviors[2]["comportement"]["confiance_qualification"] >= 70

    assert behaviors[3]["comportement"]["qualification"] == "bascule"
    assert behaviors[4]["comportement"]["qualification"] == "bascule"

    assert behaviors[5]["comportement"]["qualification"] != "bascule"
    assert behaviors[5]["transitions"]["comportement_precedent"] == "bascule"
    assert behaviors[5]["transitions"]["point_de_rupture"]["detecte"] is True

    for behavior in behaviors:
        assert behavior["scene_id_ref"] in {s["scene_id"] for s in scenes}
        assert behavior["symbol"] == symbol
        assert behavior["timeframe"] == timeframe
