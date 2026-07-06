"""test_context_propagation.py — Gardien de la cohérence inter-couches V9.

Ce test vérifie que chaque champ produit par les couches amont et marqué
PROPAGÉ dans docs/architecture/CONTEXT_CONTRACT.md est effectivement
présent dans le contexte retourné par PrincipleEngine._load_shared_context().

Il ne teste PAS la valeur des champs — uniquement leur présence.
Il échoue si un champ PROPAGÉ est absent du contexte (régression de propagation).

Ce test est le gardien automatique de CONTEXT_CONTRACT.md.
À faire tourner à chaque CI et à chaque modification de _load_shared_context.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.v9.db_schema import get_connection, init_db
from core.v9.principle_engine import PrincipleEngine
from core.v9.scene_db import init_scene_db
from core.v9.behavior_db import init_behavior_db
from core.v9.window_db import init_window_db
from core.v9.exploitability_db import init_exploitability_db


# ── Champs PROPAGÉS attendus dans le contexte (CONTEXT_CONTRACT.md) ──
# Toute modification de ce set doit être accompagnée d'une mise à jour
# de docs/architecture/CONTEXT_CONTRACT.md.
EXPECTED_CONTEXT_FIELDS = {
    # Forces
    "pf_mid",
    "stale",
    # Cross-TF
    "h1_dir",
    "h1_state",
    "m5_dir",
    "m5_state",
    # Coalitions
    "coalitions_count",
    "coalition_strength",
    "coalition_rotation_detectee",
    "coalition_rotation_ancien_leader",
    "coalition_rotation_nouveau_leader",
    "coalition_mtf_score",
    "coalition_mtf_depth",
    # Antagonismes
    "antagonismes_count",
    "bascule_detectee",
    "bascule_devise_dominante",
    "bascule_intensite",
    # Cinématique
    "pente",
    "courbure",
    "velocite_moyenne",
    "acceleration_vraie",
    "dispersion_velocite",
    "pliure_detectee",
    "pliure_severite",
    # Risk assessment
    "risk_sentiment",
    "risk_confidence",
    "risk_on_score",
    "risk_off_score",
    "persistance_confirmee",
    # Contexte temporel
    "session_marche",
    "heure_utc",
    "jour_semaine",
    "marche_ouvert",
    # Comportements
    "qualification",
    "intensite",
    "phase",
    "confiance_qualification",
    "point_de_rupture_detecte",
    "sens_transition",
    # Fenêtres
    "window_statut",
    "type_fenetre",
    "niveau_confiance",
    "fragilite_detectee",
    # Exploitabilité
    "exploitability_statut",
    "niveau_confiance_global",
}


def _make_snapshot_id() -> str:
    return f"snap_{uuid.uuid4().hex[:12]}"


def _make_scene_id() -> str:
    return f"scene-{uuid.uuid4().hex[:12]}"


def _make_behavior_id() -> str:
    return f"beh_{uuid.uuid4().hex[:12]}"


def _make_window_id() -> str:
    return f"win_{uuid.uuid4().hex[:12]}"


def _insert_full_chain(conn: sqlite3.Connection, snapshot_id: str) -> dict:
    """Insère une chaîne complète Forces→Scènes→Comportements→Fenêtres
    dans la DB de test. Retourne les IDs créés."""
    # Migration locale : garantit les colonnes attendues par le test
    # qui peuvent manquer sur des DB créées avant leur ajout (pattern
    # _ensure_column rétrocompatible, voir scene_db.py).
    for table, cols in (
        ("forces_snapshots", [("source_type", "TEXT"), ("collected_at", "TEXT")]),
        ("behaviors", [("scene_timestamp", "TEXT")]),
        ("windows", [("symbol", "TEXT"), ("timeframe", "TEXT"),
                     ("behavior_qualification", "TEXT"),
                     ("behavior_confiance", "INTEGER"),
                     ("timestamp_ouverture", "TEXT"),
                     ("timestamp_fermeture", "TEXT"),
                     ("fragilite_raison", "TEXT")]),
    ):
        for col_name, col_type in cols:
            existing = {d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    conn.commit()

    now = datetime.now(timezone.utc).isoformat()

    # Forces
    conn.execute(
        "INSERT INTO forces_snapshots "
        "(snapshot_id, schema_version, timestamp, symbol, timeframe, "
        " force_usd, force_gbp, force_eur, force_jpy, force_cad, "
        " force_chf, force_aud, force_nzd, mid, stale, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (snapshot_id, "v9", now, "GBPUSD", "M5",
         52.0, 58.0, 50.0, 45.0, 53.0, 44.0, 57.0, 56.0,
         1.2700, 0, now),
    )

    scene_id = _make_scene_id()
    risk_assessment = {
        "risk_sentiment": "RISK_ON",
        "risk_confidence": 75,
        "risk_on_score": 0.8,
        "risk_off_score": 0.1,
        "dominant_bloc": ["AUD", "NZD", "CAD"],
        "refuge_bloc_direction": "baissiere",
        "procyclique_bloc_direction": "haussiere",
        "persistance_confirmee": True,
    }
    cinematique = {
        "angle": 15.0, "courbure": 0.1, "pente": 0.5,
        "pliure": {"detectee": False, "severite": None},
        "acceleration_deceleration": "stable",
        "rotation_force": {"detectee": False, "sens": None},
        "compression_extension": {"etat": "neutre", "intensite": 2.0},
        "velocite_moyenne": 0.05,
        "acceleration_vraie": 0.001,
        "dispersion_velocite": 0.01,
    }
    coalitions = [
        {
            "devises_alignees": ["AUD", "NZD"],
            "intensite_alignement": 56.5,
            "leader": "GBP",
            "rotation_leadership": {"detectee": True, "ancien_leader": "AUD", "nouveau_leader": "GBP"},
            "age_bars": 5,
            "intensite_trend": "montante",
            "stabilite": 0.8,
        }
    ]
    antagonismes = [
        {
            "devises_en_conflit": ["GBP", "JPY"],
            "intensite_conflit": 35.0,
            "bascule_equilibre": {"detectee": True, "sens": "GBP"},
        }
    ]
    contexte_temporel = {"session": "Londres", "fenetre": "mi-session"}
    confluences_mtf = {
        "emboitement_detecte": True,
        "cascades_temporelles": [],
        "signatures_coherence": [],
        "coalition_mtf_score": 3,
        "coalition_mtf_depth": "H1",
    }
    conn.execute(
        "INSERT INTO scenes "
        "(scene_id, schema_version, timestamp, timeframes_concernes, "
        " forces_snapshot_ref, forces_snapshot_timestamp, "
        " zone_json, coalitions_json, antagonismes_json, "
        " cinematique_json, confluences_mtf_json, contexte_temporel_json, "
        " risk_assessment_json, stale, source_type, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            scene_id, "v9", now,
            json.dumps(["M5"]),
            snapshot_id, now,
            json.dumps({"prix": {}, "structure": "zone neutre", "niveau": "mineure"}),
            json.dumps(coalitions),
            json.dumps(antagonismes),
            json.dumps(cinematique),
            json.dumps(confluences_mtf),
            json.dumps(contexte_temporel),
            json.dumps(risk_assessment),
            0, "test", now,
        ),
    )

    behavior_id = _make_behavior_id()
    conn.execute(
        "INSERT INTO behaviors "
        "(behavior_id, schema_version, timestamp, scene_id_ref, "
        " scene_timestamp, symbol, timeframe, window_start, window_end, "
        " qualification, intensite, phase, confiance_qualification, "
        " description_courte, comportement_precedent, "
        " point_de_rupture_detecte, point_de_rupture_timestamp, "
        " point_de_rupture_declencheur, sens_transition, "
        " similarite_score, cas_references_json, singularites_locales_json, "
        " est_variante, comportement_reference, ecarts_json, "
        " stale, source_type, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            behavior_id, "v9", now, scene_id, now,
            "GBPUSD", "M5", now, now,
            "extension", "forte", "developpement", 75,
            "Extension observée sur GBPUSD M5.",
            "maintien",
            1, now, "pliure cinématique",
            "escalade",
            0.88, json.dumps([]), json.dumps([]),
            0, None, json.dumps([]),
            0, "test", now,
        ),
    )

    window_id = _make_window_id()
    conn.execute(
        "INSERT INTO windows "
        "(window_id, schema_version, timestamp, behavior_id, "
        " symbol, timeframe, statut, type_fenetre, "
        " niveau_confiance, fragilite_detectee, stale, source_type, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            window_id, "v9", now, behavior_id,
            "GBPUSD", "M5",
            "ouverte", "directionnelle",
            72, 0, 0, "test", now,
        ),
    )
    conn.commit()
    return {"snapshot_id": snapshot_id, "scene_id": scene_id,
            "behavior_id": behavior_id, "window_id": window_id}


@pytest.fixture
def db_with_chain():
    """DB temporaire avec une chaîne complète Forces→Scènes→Comportements→Fenêtres."""
    # ignore_cleanup_errors=True (Python 3.10+) évite PermissionError sur
    # Windows quand le WAL .db-wal/.db-shm reste verrouillé à la sortie.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_propagation.db"
        # init_db crée forces_snapshots (la table source du test)
        init_db(db_path)
        engine = PrincipleEngine(db_path=db_path)
        conn = get_connection(db_path)
        conn.row_factory = sqlite3.Row
        init_scene_db(db_path)
        init_behavior_db(db_path)
        init_window_db(db_path)
        init_exploitability_db(db_path)
        snapshot_id = _make_snapshot_id()
        ids = _insert_full_chain(conn, snapshot_id)
        conn.close()
        yield db_path, engine, ids


class TestContextPropagation:
    """Vérifie que tous les champs PROPAGÉS de CONTEXT_CONTRACT.md
    sont présents dans le contexte retourné par _load_shared_context."""

    def test_all_propagated_fields_present(self, db_with_chain):
        """Échec si un champ PROPAGÉ est absent du contexte.
        C'est le test gardien de CONTEXT_CONTRACT.md."""
        db_path, engine, ids = db_with_chain
        engine.db_path = db_path
        conn = engine._connect()
        try:
            result = engine._load_shared_context(conn, ids["snapshot_id"])
        finally:
            conn.close()

        context = result["context"]
        missing = EXPECTED_CONTEXT_FIELDS - set(context.keys())
        assert not missing, (
            f"Champs PROPAGÉS absents du contexte (régression de propagation):\n"
            + "\n".join(f"  - {f}" for f in sorted(missing))
            + "\n\nMettre à jour _load_shared_context() ET CONTEXT_CONTRACT.md."
        )

    def test_no_none_on_full_chain(self, db_with_chain):
        """Vérifie qu'aucun champ critique n'est None quand la chaîne est complète."""
        db_path, engine, ids = db_with_chain
        engine.db_path = db_path
        conn = engine._connect()
        try:
            result = engine._load_shared_context(conn, ids["snapshot_id"])
        finally:
            conn.close()

        context = result["context"]
        # Ces champs ne doivent jamais être None quand la chaîne est alimentée
        critical_non_none = [
            "pf_mid", "coalitions_count", "antagonismes_count",
            "risk_sentiment", "risk_confidence",
            "coalition_mtf_score", "coalition_mtf_depth",
            "session_marche", "marche_ouvert",
            "bascule_detectee", "coalition_rotation_detectee",
        ]
        for field in critical_non_none:
            assert context.get(field) is not None, (
                f"Champ critique '{field}' est None alors que la chaîne est complète."
            )

    def test_fallbacks_when_scene_absent(self, db_with_chain):
        """Vérifie les fallbacks quand scene_row est absent (snapshot sans scène)."""
        db_path, engine, ids = db_with_chain
        # Créer un snapshot sans scène associée
        conn = engine._connect()
        now = datetime.now(timezone.utc).isoformat()
        bare_snap_id = _make_snapshot_id()
        conn.execute(
            "INSERT INTO forces_snapshots "
            "(snapshot_id, schema_version, timestamp, symbol, timeframe, "
            " force_usd, force_gbp, force_eur, force_jpy, force_cad, "
            " force_chf, force_aud, force_nzd, mid, stale, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bare_snap_id, "v9", now, "EURUSD", "H1",
             50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0,
             1.1000, 0, now),
        )
        conn.commit()
        engine.db_path = db_path
        try:
            result = engine._load_shared_context(conn, bare_snap_id)
        finally:
            conn.close()

        context = result["context"]
        # Fallbacks attendus quand aucune scène n'existe
        assert context["risk_sentiment"] == "NEUTRE"
        assert context["risk_confidence"] == 0
        assert context["coalition_rotation_detectee"] is False
        assert context["bascule_detectee"] is False
        assert context["coalition_mtf_score"] == 0
        assert context["session_marche"] == "inconnu"
        assert context["marche_ouvert"] is True

    def test_context_contract_is_subset_of_actual_context(self, db_with_chain):
        """Vérifie que EXPECTED_CONTEXT_FIELDS est un sous-ensemble du contexte réel.
        Détecte les champs déclarés dans le contrat mais jamais produits."""
        db_path, engine, ids = db_with_chain
        engine.db_path = db_path
        conn = engine._connect()
        try:
            result = engine._load_shared_context(conn, ids["snapshot_id"])
        finally:
            conn.close()

        actual_keys = set(result["context"].keys())
        declared_missing = EXPECTED_CONTEXT_FIELDS - actual_keys
        assert not declared_missing, (
            f"Champs déclarés PROPAGÉS dans CONTEXT_CONTRACT mais absents du contexte réel:\n"
            + "\n".join(f"  - {f}" for f in sorted(declared_missing))
        )
