"""Tests unitaires — WindowGate (couche Fenêtres, PowerFlow V9).

Consomme tests/fixtures/behaviors_sample.json, aligné sur
docs/architecture/formats/FORMAT_COMPORTEMENTS.md. Valide la production de
fenêtres au format docs/architecture/formats/FORMAT_FENETRES.md.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.v9 import config
from core.v9.window_db import get_connection
from core.v9.window_gate import WINDOW_STATUTS, WindowGate

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "behaviors_sample.json"


@pytest.fixture
def behaviors() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def gate(tmp_path) -> WindowGate:
    db_path = tmp_path / "v9_windows_test.db"
    memory_path = tmp_path / "memory_temp.md"
    return WindowGate(db_path=db_path, memory_path=memory_path)


def _seed(gate: WindowGate, behaviors: list[dict], upto: int) -> list[dict]:
    """Insère et évalue les comportements [0, upto) dans l'ordre chronologique."""
    windows = []
    for raw in behaviors[:upto]:
        gate.insert_behavior(raw)
        windows.append(gate.evaluate_behavior(raw["behavior_id"]))
    return windows


def _assert_valid_format_fenetres(window: dict) -> None:
    assert set(window["window_id"]) and window["window_id"] != ""
    assert window["schema_version"] == "1.0"
    assert window["timestamp"]
    assert window["behavior_source"]["behavior_id"]
    assert window["statut"] in WINDOW_STATUTS
    assert isinstance(window["niveau_confiance"], int)
    assert 0 <= window["niveau_confiance"] <= 100
    duree = window["duree_de_vie"]
    assert "timestamp_ouverture" in duree
    assert "timestamp_fermeture" in duree
    assert "detectee" in duree["fragilite"]
    assert "raison" in duree["fragilite"]
    assert isinstance(window["conditions_invalidation"], list)
    assert window["meta"]["produit_par"] == "window-gate"
    if window["statut"] == "absente":
        assert window["type_fenetre"] is None


# ── Statut ─────────────────────────────────────────────────

def test_fenetre_absente_maintien(gate, behaviors):
    w = _seed(gate, behaviors, 1)[-1]
    assert behaviors[0]["comportement"]["qualification"] == "maintien"
    assert w["statut"] == "absente"


def test_fenetre_absente_confiance_sous_seuil(gate, behaviors):
    raw = behaviors[0]
    assert raw["comportement"]["confiance_qualification"] < config.CONFIANCE_MIN_FENETRE
    w = _seed(gate, behaviors, 1)[-1]
    assert w["statut"] == "absente"


def test_fenetre_ouverte_bascule_confiance_suffisante(gate, behaviors):
    raw = behaviors[3]
    assert raw["comportement"]["qualification"] == "bascule"
    assert raw["comportement"]["confiance_qualification"] >= config.CONFIANCE_MIN_FENETRE
    w = _seed(gate, behaviors, 4)[-1]
    assert w["statut"] == "ouverte"


def test_fenetre_ouverte_rupture_confiance_suffisante(gate):
    raw = {
        "behavior_id": "beh_test_rupture_0001",
        "schema_version": "1.0",
        "timestamp": "2026-07-05T15:00:00Z",
        "scene_id_ref": "scn_test_0001",
        "scene_timestamp": "2026-07-05T14:58:00Z",
        "symbol": "GBPUSD",
        "timeframe": "M5",
        "window_start": "2026-07-05T14:58:00Z",
        "window_end": "2026-07-05T15:00:00Z",
        "comportement": {
            "qualification": "rupture",
            "intensite": "forte",
            "phase": "developpement",
            "confiance_qualification": 70,
            "description_courte": "Rupture de range GBP/USD.",
        },
        "transitions": {
            "comportement_precedent": None,
            "point_de_rupture": {
                "detecte": True,
                "timestamp": "2026-07-05T14:59:30Z",
                "declencheur": "franchissement de zone",
            },
            "sens_transition": "escalade",
        },
        "comparaison_cas_connus": {
            "similarite_score": 0.5,
            "cas_references": [],
            "singularites_locales": [],
            "variante_de_comportement_connu": {
                "est_variante": False,
                "comportement_reference": None,
                "ecarts": [],
            },
        },
        "meta": {"produit_par": "behavior-analyst", "version_lexique": "1.0"},
    }
    gate.insert_behavior(raw)
    w = gate.evaluate_behavior(raw["behavior_id"])
    assert w["statut"] == "ouverte"
    assert w["type_fenetre"] == "retournement"


def test_fenetre_en_preparation(gate, behaviors):
    raw = behaviors[2]
    assert raw["comportement"]["qualification"] == "preparation_ouverture_fenetre"
    w = _seed(gate, behaviors, 3)[-1]
    assert w["statut"] == "en_preparation"


def test_fenetre_invalidee_annulation(gate, behaviors):
    windows = _seed(gate, behaviors, 6)
    assert behaviors[5]["comportement"]["qualification"] == "annulation"
    w = windows[-1]
    assert w["statut"] == "invalidee"
    assert w["duree_de_vie"]["timestamp_fermeture"] is not None


def test_fenetre_fragile(gate, behaviors):
    windows = _seed(gate, behaviors, 5)
    assert behaviors[4]["comportement"]["qualification"] == "extension"
    w = windows[-1]
    assert w["statut"] == "fragile"
    assert w["duree_de_vie"]["fragilite"]["detectee"] is True


def test_fenetre_ambigue_confiance_faible_mais_qualifie(gate, behaviors):
    raw = behaviors[1]
    assert raw["comportement"]["qualification"] == "contraction"
    assert raw["comportement"]["confiance_qualification"] < config.CONFIANCE_MIN_FENETRE
    w = _seed(gate, behaviors, 2)[-1]
    assert w["statut"] == "ambigue"


# ── type_fenetre ─────────────────────────────────────────────

def test_type_fenetre_null_quand_absente(gate, behaviors):
    w = _seed(gate, behaviors, 1)[-1]
    assert w["statut"] == "absente"
    assert w["type_fenetre"] is None


def test_type_fenetre_retournement_pour_bascule(gate, behaviors):
    w = _seed(gate, behaviors, 4)[-1]
    assert w["type_fenetre"] == "retournement"


def test_type_fenetre_continuation_pour_extension(gate, behaviors):
    w = _seed(gate, behaviors, 5)[-1]
    assert w["type_fenetre"] == "continuation"


# ── Conditions d'invalidation ────────────────────────────────

def test_conditions_invalidation_bascule_deux_conditions(gate, behaviors):
    w = _seed(gate, behaviors, 4)[-1]
    conditions = w["conditions_invalidation"]
    assert len(conditions) == 2
    codes = {c["condition"] for c in conditions}
    assert codes == {"retour_zone_origine", "rotation_leadership_inverse"}


# ── Cycle de vie ─────────────────────────────────────────────

def test_cycle_de_vie_ouverture_puis_fermeture(gate, behaviors):
    windows = _seed(gate, behaviors, 6)
    w_ouverte = windows[3]  # bascule -> ouverte
    w_extension = windows[4]  # extension -> fragile, continuité de la même fenêtre
    w_annulee = windows[5]  # annulation -> invalidee

    assert w_ouverte["duree_de_vie"]["timestamp_ouverture"] is not None
    assert w_ouverte["duree_de_vie"]["timestamp_fermeture"] is None

    assert (
        w_extension["duree_de_vie"]["timestamp_ouverture"]
        == w_ouverte["duree_de_vie"]["timestamp_ouverture"]
    )

    assert w_annulee["duree_de_vie"]["timestamp_fermeture"] is not None
    assert (
        w_annulee["duree_de_vie"]["timestamp_ouverture"]
        == w_ouverte["duree_de_vie"]["timestamp_ouverture"]
    )


# ── Fragilité ────────────────────────────────────────────────

def test_fragilite_confiance_en_baisse(gate, behaviors):
    bascule_raw = behaviors[3]
    gate.insert_behavior(bascule_raw)
    gate.evaluate_behavior(bascule_raw["behavior_id"])

    low_conf_raw = json.loads(json.dumps(bascule_raw))
    low_conf_raw["behavior_id"] = "beh_test_baisse_confiance_0001"
    low_conf_raw["timestamp"] = "2026-07-05T14:38:00Z"
    low_conf_raw["comportement"]["qualification"] = "extension"
    delta = config.FRAGILITE_CONFIANDE_DELTA
    low_conf_raw["comportement"]["confiance_qualification"] = (
        bascule_raw["comportement"]["confiance_qualification"] - delta - 5
    )
    low_conf_raw["stale"] = False

    gate.insert_behavior(low_conf_raw)
    w = gate.evaluate_behavior(low_conf_raw["behavior_id"])
    assert w["duree_de_vie"]["fragilite"]["detectee"] is True
    assert "baisse" in w["duree_de_vie"]["fragilite"]["raison"]


def test_fragilite_stale(gate, behaviors):
    w = _seed(gate, behaviors, 5)[-1]
    assert behaviors[4]["stale"] is True
    assert w["duree_de_vie"]["fragilite"]["detectee"] is True
    assert "stale" in w["duree_de_vie"]["fragilite"]["raison"]


# ── Niveau de confiance ──────────────────────────────────────

def test_niveau_confiance_bonus_malus(gate, behaviors):
    windows = _seed(gate, behaviors, 5)
    w_bascule = windows[3]
    w_extension = windows[4]

    base_bascule = behaviors[3]["comportement"]["confiance_qualification"]
    attendu_bascule = min(
        100, base_bascule + config.BONUS_CONFLUENCE_MTF + config.BONUS_SIMILARITE
    )
    assert w_bascule["niveau_confiance"] == attendu_bascule

    base_extension = behaviors[4]["comportement"]["confiance_qualification"]
    attendu_extension = max(
        0, base_extension - config.MALUS_STALE - config.MALUS_FRAGILITE
    )
    assert w_extension["niveau_confiance"] == attendu_extension


# ── Format / traçabilité ─────────────────────────────────────

def test_format_json_valide_contre_format_fenetres(gate, behaviors):
    for w in _seed(gate, behaviors, 6):
        _assert_valid_format_fenetres(w)


def test_behavior_source_behavior_id_jamais_vide(gate, behaviors):
    for w in _seed(gate, behaviors, 6):
        assert w["behavior_source"]["behavior_id"]


# ── Écriture DB / mémoire ────────────────────────────────────

def test_ecriture_db(gate, behaviors, tmp_path):
    w = _seed(gate, behaviors, 4)[-1]
    conn = get_connection(gate.db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM windows WHERE window_id = ?", (w["window_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["behavior_id"] == w["behavior_source"]["behavior_id"]
    assert row["statut"] == w["statut"]


def test_ecriture_memoire(gate, behaviors):
    w = _seed(gate, behaviors, 4)[-1]
    content = gate.memory_path.read_text(encoding="utf-8")
    assert w["behavior_source"]["behavior_id"] in content
    assert '"type": "fenetre"' in content
