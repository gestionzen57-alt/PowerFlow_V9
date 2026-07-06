"""Tests unitaires — core.v9.scene_builder.SceneBuilder."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.scene_builder import SceneBuilder, SceneBuilderError
from core.v9.scene_db import init_scene_db

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "forces_snapshots_sample.json"

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


def _flat_forces(**overrides: float) -> dict[str, float]:
    base = {d: 50.0 for d in DEVISES}
    for devise, value in overrides.items():
        base[devise.upper()] = value
    return base


def _row(timestamp: str, timeframe: str = "M5", **force_overrides: float) -> dict:
    row = {"timestamp": timestamp, "timeframe": timeframe}
    forces = _flat_forces(**force_overrides)
    for devise, value in forces.items():
        row[f"force_{devise.lower()}"] = value
    return row


def _default_row(**overrides) -> dict:
    base = {
        "snapshot_id": overrides.get("snapshot_id", f"v9-test-{uuid.uuid4().hex[:8]}"),
        "schema_version": "1.0",
        "timestamp": "2026-07-05T14:00:00.000Z",
        "source": "MT4_SDI",
        "symbol": "EURUSD",
        "timeframe": "M5",
        "bar_time": None, "bar_close_time": None, "server_time": None, "capture_time": None,
        "shift": None, "is_closed_bar": True,
        "open": None, "high": 1.0900, "low": 1.0800, "close": 1.0860,
        "tick_volume": None, "spread_points": None, "spread_price": None,
        "bid": None, "ask": None, "mid": None,
        "force_usd": 50.0, "force_gbp": 50.0, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "neutre", "vitesse": 0.0,
        "croisement_detecte": False, "croisement_partenaire": None, "croisement_direction": None,
        "recroisement_detecte": False, "recroisement_contexte": None,
        "rejet_repulsion_detecte": False, "rejet_intensite": None,
        "compression_extension_etat": "neutre", "compression_extension_intensite": 0.0,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": "2026-07-05T14:00:00.100Z",
    }
    base.update(overrides)
    return base


def _insert_row(db_path: Path, **overrides) -> str:
    row = _default_row(**overrides)
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(FORCES_COLUMNS)
        placeholders = ", ".join(["?"] * len(FORCES_COLUMNS))
        conn.execute(
            f"INSERT INTO forces_snapshots ({col_names}) VALUES ({placeholders})",
            [row.get(c) for c in FORCES_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()
    return row["snapshot_id"]


def _load_fixture() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)["snapshots"]


def _insert_fixture(db_path: Path) -> None:
    for snapshot in _load_fixture():
        _insert_row(db_path, **snapshot)


def _make_builder(tmp_path: Path) -> SceneBuilder:
    db_path = tmp_path / "v9_scenes_test.db"
    init_db(db_path)
    return SceneBuilder(db_path=db_path, config={"memory_dir": tmp_path / "memory"})


# ── Coalitions ──────────────────────────────────────────

def test_detect_coalition_two_currencies_aligned(tmp_path):
    builder = _make_builder(tmp_path)
    forces = _flat_forces(USD=62.0, EUR=59.0)
    directions = {d: "neutre" for d in DEVISES}
    directions["USD"] = "haussiere"
    directions["EUR"] = "haussiere"

    coalitions = builder._detect_coalitions(forces, directions)

    assert len(coalitions) == 1
    coalition = coalitions[0]
    assert set(coalition["devises_alignees"]) == {"USD", "EUR"}
    assert coalition["leader"] == "USD"
    assert coalition["intensite_alignement"] == (62.0 + 59.0) / 2


def test_no_coalition_when_scattered(tmp_path):
    builder = _make_builder(tmp_path)
    forces = {"USD": 80.0, "GBP": 20.0, "EUR": 65.0, "JPY": 10.0,
              "CAD": 45.0, "CHF": 90.0, "AUD": 2.0, "NZD": 55.0}
    directions = {"USD": "haussiere", "GBP": "baissiere", "EUR": "haussiere", "JPY": "baissiere",
                  "CAD": "neutre", "CHF": "haussiere", "AUD": "baissiere", "NZD": "haussiere"}

    coalitions = builder._detect_coalitions(forces, directions)

    assert coalitions == []


# ── Antagonismes ────────────────────────────────────────

def test_detect_antagonism_opposite_currencies(tmp_path):
    builder = _make_builder(tmp_path)
    forces = _flat_forces(USD=70.0, EUR=30.0)
    directions = {d: "neutre" for d in DEVISES}
    directions["USD"] = "haussiere"
    directions["EUR"] = "baissiere"

    antagonismes = builder._detect_antagonisms(forces, directions)

    assert len(antagonismes) == 1
    conflict = antagonismes[0]
    assert set(conflict["devises_en_conflit"]) == {"USD", "EUR"}
    assert conflict["intensite_conflit"] == 40.0


def test_bascule_equilibre_order_change(tmp_path):
    builder = _make_builder(tmp_path)
    prev_forces = _flat_forces(USD=40.0, GBP=50.0)
    curr_forces = _flat_forces(USD=60.0, GBP=50.0)
    prev_directions = {d: "neutre" for d in DEVISES}
    curr_directions = {d: "neutre" for d in DEVISES}
    curr_directions["USD"] = "haussiere"

    antagonismes = builder._detect_antagonisms(
        curr_forces, curr_directions, prev_forces, prev_directions
    )

    match = next(a for a in antagonismes if set(a["devises_en_conflit"]) == {"USD", "GBP"})
    assert match["bascule_equilibre"]["detectee"] is True
    assert match["bascule_equilibre"]["sens"] == "USD"


# ── Cinématique ─────────────────────────────────────────

def test_cinematics_angle_pente_with_history(tmp_path):
    builder = _make_builder(tmp_path)
    history = [
        _row("2026-07-05T14:00:00.000Z", USD=50.0, EUR=50.0),
        _row("2026-07-05T14:05:00.000Z", USD=55.0, EUR=53.0),
        _row("2026-07-05T14:10:00.000Z", USD=60.0, EUR=56.0),
    ]
    forces_now = _flat_forces(USD=60.0, EUR=56.0)

    cinematique = builder._compute_cinematics(forces_now, history)

    assert cinematique["pente"] > 0
    assert isinstance(cinematique["angle"], float)
    assert cinematique["acceleration_deceleration"] in {"acceleration", "deceleration", "stable"}


def test_pliure_detection(tmp_path):
    builder = _make_builder(tmp_path)
    # pente nulle sur les 2 premiers points, puis saut brutal
    history = [
        _row("2026-07-05T14:00:00.000Z", USD=50.0),
        _row("2026-07-05T14:05:00.000Z", USD=50.0),
        _row("2026-07-05T14:10:00.000Z", USD=90.0),
    ]
    forces_now = _flat_forces(USD=90.0)

    cinematique = builder._compute_cinematics(forces_now, history)

    assert cinematique["pliure"]["detectee"] is True
    assert cinematique["pliure"]["severite"] > 0


def test_compression_vs_extension(tmp_path):
    builder = _make_builder(tmp_path)

    stable_history = [
        _row("2026-07-05T14:00:00.000Z", USD=52.0),
        _row("2026-07-05T14:05:00.000Z", USD=52.0),
        _row("2026-07-05T14:10:00.000Z", USD=52.0),
        _row("2026-07-05T14:15:00.000Z", USD=52.0),
    ]
    extension_now = _flat_forces(USD=95.0)
    cinematique_ext = builder._compute_cinematics(extension_now, stable_history + [
        _row("2026-07-05T14:20:00.000Z", USD=95.0)
    ])
    assert cinematique_ext["compression_extension"]["etat"] == "extension"

    wide_history = [
        _row("2026-07-05T14:00:00.000Z", USD=95.0),
        _row("2026-07-05T14:05:00.000Z", USD=95.0),
        _row("2026-07-05T14:10:00.000Z", USD=95.0),
        _row("2026-07-05T14:15:00.000Z", USD=95.0),
    ]
    compression_now = _flat_forces(USD=51.0)
    cinematique_comp = builder._compute_cinematics(compression_now, wide_history + [
        _row("2026-07-05T14:20:00.000Z", USD=51.0)
    ])
    assert cinematique_comp["compression_extension"]["etat"] == "compression"


# ── Vélocité réelle ─────────────────────────────────────

def test_velocite_fields_present_in_cinematique(tmp_path):
    """Vérifie que les 3 nouveaux champs sont présents dans le retour de
    _compute_cinematics, même avec fallback 0.0."""
    builder = _make_builder(tmp_path)
    history = [
        _row("2026-07-05T14:00:00.000Z", USD=50.0),
        _row("2026-07-05T14:05:00.000Z", USD=55.0),
    ]
    forces_now = _flat_forces(USD=55.0)
    cinematique = builder._compute_cinematics(forces_now, history)

    assert "velocite_moyenne" in cinematique
    assert "acceleration_vraie" in cinematique
    assert "dispersion_velocite" in cinematique
    assert isinstance(cinematique["velocite_moyenne"], float)
    assert isinstance(cinematique["acceleration_vraie"], float)
    assert isinstance(cinematique["dispersion_velocite"], float)


def test_velocite_fallback_zero_when_vitesse_missing(tmp_path):
    """Fallback 0.0 quand la colonne vitesse est absente (replay ancien)."""
    builder = _make_builder(tmp_path)
    # rows sans colonne vitesse (simule données pré-vitesse)
    history = [
        {"timestamp": "2026-07-05T14:00:00.000Z", "timeframe": "M5",
         "force_usd": 50.0, "force_gbp": 50.0, "force_eur": 50.0,
         "force_jpy": 50.0, "force_cad": 50.0, "force_chf": 50.0,
         "force_aud": 50.0, "force_nzd": 50.0},
        {"timestamp": "2026-07-05T14:05:00.000Z", "timeframe": "M5",
         "force_usd": 55.0, "force_gbp": 50.0, "force_eur": 50.0,
         "force_jpy": 50.0, "force_cad": 50.0, "force_chf": 50.0,
         "force_aud": 50.0, "force_nzd": 50.0},
    ]
    forces_now = _flat_forces(USD=55.0)
    cinematique = builder._compute_cinematics(forces_now, history)

    assert cinematique["velocite_moyenne"] == 0.0
    assert cinematique["acceleration_vraie"] == 0.0
    assert cinematique["dispersion_velocite"] == 0.0


def test_velocite_nonzero_with_vitesse_column(tmp_path):
    """Vérifie des valeurs non nulles quand la colonne vitesse est présente
    avec des bar_time exploitables."""
    builder = _make_builder(tmp_path)
    history = [
        _row("2026-07-05T14:00:00.000Z", USD=50.0),
        _row("2026-07-05T14:05:00.000Z", USD=55.0),
    ]
    # Injecter vitesse et bar_time dans les rows
    history[0]["vitesse"] = 0.001
    history[0]["bar_time"] = 1000
    history[1]["vitesse"] = 0.005
    history[1]["bar_time"] = 1300  # delta_t = 300s

    forces_now = _flat_forces(USD=55.0)
    cinematique = builder._compute_cinematics(forces_now, history)

    # velocite_moyenne = vitesse du dernier snapshot
    assert cinematique["velocite_moyenne"] == 0.005
    # acceleration_vraie = (0.005 - 0.001) / 300, arrondi à 6 décimales = 1.3e-05
    assert cinematique["acceleration_vraie"] == 0.000013
    # dispersion_velocite = std([0.001, 0.005])
    assert cinematique["dispersion_velocite"] == pytest.approx(0.002, abs=1e-6)


def test_velocite_fields_in_output_json(tmp_path):
    """Vérifie que les 3 champs sont présents dans le JSON de scène complet
    (test d'intégration avec build_scene)."""
    db_path = tmp_path / "v9_velocite.db"
    init_db(db_path)
    _insert_fixture(db_path)
    builder = SceneBuilder(db_path=db_path, config={"memory_dir": tmp_path / "memory"})

    scene = builder.build_scene("v9-fixture-m5-003")

    assert "velocite_moyenne" in scene["cinematique_locale"]
    assert "acceleration_vraie" in scene["cinematique_locale"]
    assert "dispersion_velocite" in scene["cinematique_locale"]


# ── Confluences MTF ─────────────────────────────────────

def test_mtf_confluence_htf_coalition_found_in_ltf(tmp_path):
    db_path = tmp_path / "v9_mtf.db"
    init_db(db_path)
    _insert_fixture(db_path)
    builder = SceneBuilder(db_path=db_path, config={"memory_dir": tmp_path / "memory"})

    scene = builder.build_scene("v9-fixture-m5-003")

    assert "H4" in scene["timeframes_concernes"]
    assert "M5" in scene["timeframes_concernes"]
    assert scene["confluences_mtf"]["emboitement_detecte"] is True
    cascade = next(
        c for c in scene["confluences_mtf"]["cascades_temporelles"]
        if c["de_timeframe"] == "H4" and c["vers_timeframe"] == "M5"
    )
    assert "USD" in cascade["description"] and "EUR" in cascade["description"]


# ── Contexte temporel ───────────────────────────────────

def test_contexte_temporel_session_londres_10h(tmp_path):
    builder = _make_builder(tmp_path)

    contexte = builder._identify_context("2026-07-05T10:00:00.000Z")

    assert contexte["session"] == "Londres"
    assert contexte["fenetre"] in {"ouverture de session", "mi-session", "cloture de session"}


# ── Format JSON / DB / mémoire ──────────────────────────

REQUIRED_TOP_LEVEL = {
    "schema_version", "scene_id", "timestamp", "timeframes_concernes",
    "forces_snapshot_ref", "zone", "coalitions", "antagonismes",
    "cinematique_locale", "confluences_mtf", "contexte_temporel",
}


def test_output_json_format_valid_against_format_scenes(tmp_path):
    db_path = tmp_path / "v9_format.db"
    init_db(db_path)
    _insert_fixture(db_path)
    builder = SceneBuilder(db_path=db_path, config={"memory_dir": tmp_path / "memory"})

    scene = builder.build_scene("v9-fixture-m5-003")

    assert REQUIRED_TOP_LEVEL.issubset(scene.keys())
    assert scene["schema_version"] == "1.0"
    assert set(scene["forces_snapshot_ref"].keys()) == {"snapshot_id", "timestamp"}
    assert scene["forces_snapshot_ref"]["snapshot_id"] == "v9-fixture-m5-003"
    assert isinstance(scene["coalitions"], list)
    assert isinstance(scene["antagonismes"], list)
    assert {"prix", "structure", "niveau"}.issubset(scene["zone"].keys())
    cinematique_keys = {
        "angle", "courbure", "pente", "pliure", "acceleration_deceleration",
        "rotation_force", "compression_extension",
        "velocite_moyenne", "acceleration_vraie", "dispersion_velocite",
    }
    assert cinematique_keys.issubset(scene["cinematique_locale"].keys())
    assert {"emboitement_detecte", "cascades_temporelles", "signatures_coherence"}.issubset(
        scene["confluences_mtf"].keys()
    )
    assert {"session", "fenetre"}.issubset(scene["contexte_temporel"].keys())

    # round-trip JSON valide
    reparsed = json.loads(json.dumps(scene))
    assert reparsed["scene_id"] == scene["scene_id"]


def test_build_scene_unknown_snapshot_raises(tmp_path):
    builder = _make_builder(tmp_path)
    try:
        builder.build_scene("does-not-exist")
        assert False, "devait lever SceneBuilderError"
    except SceneBuilderError:
        pass


def test_write_scene_to_db(tmp_path):
    db_path = tmp_path / "v9_write.db"
    init_db(db_path)
    _insert_fixture(db_path)
    builder = SceneBuilder(db_path=db_path, config={"memory_dir": tmp_path / "memory"})

    scene = builder.build_scene("v9-fixture-m5-003")
    builder._write_scene_to_db(scene)

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT scene_id, forces_snapshot_ref, stale, coalitions_json "
            "FROM scenes WHERE scene_id = ?",
            (scene["scene_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == scene["scene_id"]
    assert row[1] == "v9-fixture-m5-003"
    assert bool(row[2]) is False
    assert json.loads(row[3]) == scene["coalitions"]


def test_write_memory_hypothese(tmp_path):
    db_path = tmp_path / "v9_memory.db"
    init_db(db_path)
    _insert_fixture(db_path)
    memory_dir = tmp_path / "memory"
    builder = SceneBuilder(db_path=db_path, config={"memory_dir": memory_dir})

    scene = builder.build_scene("v9-fixture-m5-003")
    builder._write_memory(scene, statut="hypothese")

    content = (memory_dir / "memory_temp.md").read_text(encoding="utf-8")
    assert scene["scene_id"] in content
    assert '"statut": "hypothese"' in content
    assert '"hypothese_coalition"' in content
    assert '"couche_origine": "scenes"' in content
