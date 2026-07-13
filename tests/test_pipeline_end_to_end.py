"""test_pipeline_end_to_end.py — Gardien permanent du pipeline V9 bout-en-bout.

Vérifie que la chaîne complète V9 fonctionne déterministiquement :

    Forces → Scene              [réel : SceneBuilder]
              → Behavior          [injecté : heuristique single-snapshot instable]
              → Window            [injecté : idem]
              → Exploitability    [injecté : idem]
              → Zone              [injecté : ZoneDetector = multi-snapshot]
              → Regime            [injecté : RegimeDetector = multi-snapshot]
              → Principe ACTIVE   [injecté : seul PRICE_LAG_*
                                      nécessite historique d'accumulation]
              → SignalGenerator   [réel : c'est ce qu'on teste]
              → DecisionLogger    [réel : c'est ce qu'on teste]
              → decisions.direction IS NOT NULL, confiance > 0

Ce test aurait détecté les 5 bugs silencieux du 2026-07-06 :
  1. fallbacks cross-TF qui écrasaient (ANTAGONIST_NODE 0/1728)
  2. REGIMES_INADEQUATS trop larges (signaux rejetés)
  3. window=absente + conf=élevée mal filtrée (exploitabilité)
  4. principes perdus (signal_generator ne chargeait pas la quote)
  5. _load_signal ORDER BY id DESC (signaux directionnels invisibles)

Il devient le gardien de régression permanent de la chaîne complète :
à exécuter à chaque modification de `_load_shared_context`,
`signal_generator.generate()`, `decision_logger.log()`, ou de toute
couche intermédiaire.

Règles :
  - DB SQLite en tmp (ignore_cleanup_errors=True pour Windows WAL).
  - Pas de dépendance à data/v9_forces.db ni à datetime.now() non mocké.
  - Tous les timestamps figés en 2026-07-05T17:00Z (reproductibilité).
  - SceneBuilder.build_scene() traversera la couche Scene en réel.
  - Les heuristiques instables en single-snapshot (behavior, window,
    exploitability, zone, regime, principe ACTIVE PRICE_LAG) sont
    injectées pour reproduire ce qu'on observe en live après
    quelques snapshots — leurs classes sont testées indépendamment
    par leurs propres tests unitaires.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.decision_logger import DecisionLogger
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS, init_exploitability_db
from core.v9.principle_db import PRINCIPLE_EVALUATIONS_COLUMNS, init_principle_db
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db
from core.v9.scene_builder import SceneBuilder
from core.v9.signal_generator import SignalGenerator
from core.v9.window_db import WINDOWS_COLUMNS, init_window_db
from core.v9.zone_db import ZONE_DIAGNOSTICS_COLUMNS, init_zone_db


# ── Timestamps figés (reproductibilité) ────────────────────────────────
FIXED_TS = "2026-07-05T17:00:00.000Z"
CREATED_AT = "2026-07-05T17:00:00.500Z"


# ══════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """DB SQLite tmp + toutes les tables V9 initialisées."""
    path = tmp_path / "v9_e2e_test.db"
    init_db(path)                       # forces_snapshots
    init_behavior_db(path)              # behaviors
    init_window_db(path)                # windows
    init_exploitability_db(path)        # exploitability
    init_zone_db(path)                  # zone_diagnostics
    init_regime_db(path)                # regime_snapshots
    init_principle_db(path)             # principle_evaluations
    # Note : scene_db, signal_db, decision_db sont initialisés par
    # leurs classes constructeur respectives (lazy init).
    return path


@pytest.fixture
def memory_dir(tmp_path: Path) -> Path:
    """Répertoire memory_dir pour SceneBuilder."""
    p = tmp_path / "memory"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ══════════════════════════════════════════════════════════════════════
# HELPERS D'INSERTION
# ══════════════════════════════════════════════════════════════════════
def _row_insert(db_path: Path, table: str, columns: list, values: dict) -> None:
    """Helper générique pour insérer une rangée complète (NULL pour colonnes absentes)."""
    col_names = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    conn = get_connection(db_path)
    try:
        conn.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            [values.get(c) for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def _insert_forces_snapshot(db_path: Path) -> str:
    """Snapshot forces calibré : GBPUSD M5, force_gbp=85 (extrémum UP),
    bid/ask/mid cohérents."""
    snapshot_id = f"v9-e2e-{uuid.uuid4().hex[:8]}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0",
        "timestamp": FIXED_TS, "source": "TEST_E2E",
        "symbol": "GBPUSD", "timeframe": "M5",
        "bar_time": 1700004000, "bar_close_time": 1700003999,
        "server_time": 1700004000, "capture_time": 1700004000,
        "shift": 0, "is_closed_bar": True,
        "open": 1.27000, "high": 1.27250, "low": 1.26800, "close": 1.27200,
        "tick_volume": 1000, "spread_points": 5, "spread_price": 0.00005,
        "bid": 1.27198, "ask": 1.27203, "mid": 1.27200,
        "force_usd": 50.0, "force_gbp": 85.0, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "vitesse": 5.0,
        "croisement_detecte": False, "croisement_partenaire": None,
        "croisement_direction": None, "recroisement_detecte": False,
        "recroisement_contexte": None, "rejet_repulsion_detecte": False,
        "rejet_intensite": None,
        "compression_extension_etat": "compression",
        "compression_extension_intensite": 1.5,
        "stale": False, "age_ms": 100, "stale_threshold_ms": 35000,
        "created_at": CREATED_AT,
    })
    _row_insert(db_path, "forces_snapshots", FORCES_COLUMNS, row)
    return snapshot_id


def _insert_behavior(db_path: Path, scene_id: str) -> str:
    """Injecte un behavior qualifié (bascule/forte/developpement) calé pour passer
    le downstream filter WindowGate→ExploitabilityEvaluator (heuristique single-snapshot)."""
    behavior_id = f"beh-e2e-{uuid.uuid4().hex[:8]}"
    row = {c: None for c in BEHAVIOR_COLUMNS}
    row.update({
        "behavior_id": behavior_id, "schema_version": "1.0",
        "timestamp": FIXED_TS, "scene_id_ref": scene_id,
        "scene_timestamp": FIXED_TS,
        "symbol": "GBPUSD", "timeframe": "M5",
        "window_start": FIXED_TS, "window_end": FIXED_TS,
        "qualification": "bascule", "intensite": "forte",
        "phase": "developpement", "confiance_qualification": 80,
        "description_courte": "Bascule GBPUSD M5 — injection e2e test.",
        "comportement_precedent": "maintien",
        "point_de_rupture_detecte": False, "point_de_rupture_timestamp": None,
        "point_de_rupture_declencheur": None, "sens_transition": "escalade",
        "similarite_score": 0.88, "cas_references_json": "[]",
        "singularites_locales_json": "[]",
        "est_variante": False, "comportement_reference": None,
        "ecarts_json": "[]", "stale": False, "source_type": "test",
        "created_at": CREATED_AT,
    })
    _row_insert(db_path, "behaviors", BEHAVIOR_COLUMNS, row)
    return behavior_id


def _insert_window(db_path: Path, behavior_id: str) -> str:
    """Injecte une window 'ouverte' (vs 'absente' single-snapshot) pour passer le filtre."""
    window_id = f"win-e2e-{uuid.uuid4().hex[:8]}"
    row = {c: None for c in WINDOWS_COLUMNS}
    row.update({
        "window_id": window_id, "schema_version": "1.0", "timestamp": FIXED_TS,
        "behavior_id": behavior_id, "behavior_qualification": "bascule",
        "behavior_confiance": 80,
        "statut": "ouverte", "type_fenetre": "directionnelle",
        "niveau_confiance": 80,
        "timestamp_ouverture": FIXED_TS, "timestamp_fermeture": None,
        "fragilite_detectee": False, "fragilite_raison": None,
        "conditions_invalidation_json": "[]",
        "stale": False, "source_type": "test", "created_at": CREATED_AT,
    })
    _row_insert(db_path, "windows", WINDOWS_COLUMNS, row)
    return window_id


def _insert_exploitability(db_path: Path, window_id: str) -> str:
    """Injecte une exploitability 'exploitable' avec confiance élevée (passe le filtre
    SignalGenerator._determine_absence_reason)."""
    exploitability_id = f"exp-e2e-{uuid.uuid4().hex[:8]}"
    row = {c: None for c in EXPLOITABILITY_COLUMNS}
    row.update({
        "exploitability_id": exploitability_id, "schema_version": "1.0",
        "timestamp": FIXED_TS, "window_id": window_id,
        "window_statut": "ouverte", "window_niveau_confiance": 80,
        "statut": "exploitable", "raison_refus": None,
        "niveau_confiance_global": 85,
        "validation_hitl_requise": False, "validation_hitl_raison": None,
        "replay_cas_compares_json": "[]", "replay_nombre_cas": 0,
        "replay_synthese": "Replay e2e",
        "stale": False, "source_type": "test", "created_at": CREATED_AT,
    })
    _row_insert(db_path, "exploitability", EXPLOITABILITY_COLUMNS, row)
    return exploitability_id


def _insert_zone(db_path: Path, snapshot_id: str, currency: str,
                 state: str = "ACCUMULATING", tension: float = 0.8,
                 z_extreme_dir: str = "UP", z_current: float = 1.0) -> None:
    """Injecte un zone_diagnostic cohérent (state=ACCUMULATING + tension>=0.5 +
    z_extreme_dir=UP → déclenche PRICE_LAG_AT_NODE_BIRTH en live)."""
    row = {c: None for c in ZONE_DIAGNOSTICS_COLUMNS}
    row.update({
        "zone_diagnostic_id": f"zd-{uuid.uuid4().hex[:8]}",
        "schema_version": "1.0", "timestamp": FIXED_TS,
        "forces_snapshot_ref": snapshot_id,
        "symbol": "GBPUSD", "timeframe": "M5", "currency": currency,
        "force_value": 85.0 if currency == "GBP" else 50.0,
        "z_current": z_current, "z_extreme_dir": z_extreme_dir,
        "prev_z_extreme_dir": z_extreme_dir, "state": state,
        "prev_state": "NEUTRAL", "bars_in_extreme": 1,
        "tension_score": tension, "absorbed_pullback_count": 0,
        "stale": False, "source_type": "test", "created_at": CREATED_AT,
    })
    _row_insert(db_path, "zone_diagnostics", ZONE_DIAGNOSTICS_COLUMNS, row)


def _insert_regime(db_path: Path, snapshot_id: str, currency: str,
                   regime_type: str = "CASSURE") -> None:
    """Injecte un regime_snapshot. CASSURE n'est PAS dans REGIMES_INADEQUATS
    (cf. core/v9/config.py), donc autorisé par SignalGenerator."""
    row = {c: None for c in REGIME_SNAPSHOTS_COLUMNS}
    row.update({
        "regime_id": f"reg-{uuid.uuid4().hex[:8]}",
        "schema_version": "1.0", "timestamp": FIXED_TS,
        "forces_snapshot_ref": snapshot_id,
        "symbol": "GBPUSD", "timeframe": "M5", "currency": currency,
        "force_value": 85.0 if currency == "GBP" else 50.0,
        "regime_type": regime_type, "cassure_type": "haussiere",
        "cassure_direction": "UP", "z_current": 1.0,
        "mean_reversion_zone": False, "stale": False,
        "source_type": "test", "created_at": CREATED_AT,
    })
    _row_insert(db_path, "regime_snapshots", REGIME_SNAPSHOTS_COLUMNS, row)


def _insert_principle(db_path: Path, snapshot_id: str,
                      principle_id: str = "PRICE_LAG_AT_NODE_BIRTH",
                      direction: str = "haussiere", confidence: int = 90,
                      currency: str = "GBP", triggered: int = 1) -> None:
    """Injecte un principle_evaluation ACTIVE+triggered pour piloter SignalGenerator.
    Reproduit ce que PrincipleEngine aurait produit en live après quelques
    snapshots de zone ACCUMULATING — le moteur officiel n'aurait pas
    déclenché en single-snapshot (PRICE_LAG_*) ; la scène multi-snapshot
    est testée séparément dans test_principle_engine.py.
    """
    row = {c: None for c in PRINCIPLE_EVALUATIONS_COLUMNS}
    row.update({
        "evaluation_id": f"eval-{uuid.uuid4().hex[:12]}",
        "schema_version": "1.0", "timestamp": FIXED_TS,
        "snapshot_id": snapshot_id, "principle_id": principle_id,
        "v9_status": "ACTIVE", "kind": "node_rule",
        "symbol": "GBPUSD", "timeframe": "M5", "currency": currency,
        "triggered": triggered, "direction": direction, "confidence": confidence,
        "anti_signal_bias": False, "reason": "state_ACCUMULATING_tension_0.8",
        "context_json": json.dumps({
            "state": "ACCUMULATING", "tension_score": 0.8,
            "pf_mid": 1.27200, "z_extreme_dir": "UP",
        }),
        "source_type": "test", "created_at": CREATED_AT,
    })
    _row_insert(db_path, "principle_evaluations", PRINCIPLE_EVALUATIONS_COLUMNS, row)


# ══════════════════════════════════════════════════════════════════════
# TEST PRINCIPAL — le gardien permanent du pipeline bout-en-bout
# ══════════════════════════════════════════════════════════════════════
def test_pipeline_snapshot_produces_directional_decision(
    db_path: Path, memory_dir: Path, monkeypatch
) -> None:
    """Pipeline bout-en-bout déterministe.

    Brief O4 CEO 2026-07-13 — on mocke datetime à 10h UTC = London (session
    tradable), car NY/after retournent exit_strategy=None (defense-in-depth)
    et feraient échouer ce test_runtime-dépendant (Brief O4 actif depuis
    commit bd1ca6f). Toutes les assertions logiques restent valides.
    """
    # Mock datetime.now(timezone.utc) → heure stable london 10h pour reproductibilité
    from datetime import datetime as _dt, timezone as _tz
    from core.v9 import signal_generator as _sg_mod

    class _FixedDateTime:
        @classmethod
        def now(cls, tz=None):
            return _dt(2026, 7, 13, 10, 0, 0, tzinfo=tz or _tz.utc)

    monkeypatch.setattr(_sg_mod, "datetime", _FixedDateTime)

    # ── 1. Snapshot forces ─────────────────────────────────────────
    snapshot_id = _insert_forces_snapshot(db_path)

    # ── 2. Scene (réel) ────────────────────────────────────────────
    scene_builder = SceneBuilder(db_path=db_path, config={"memory_dir": memory_dir})
    scene = scene_builder.build_scene(snapshot_id)
    scene_builder._write_scene_to_db(scene)
    scene_id = scene["scene_id"]
    assert scene_id, "SceneBuilder n'a pas produit de scene_id"

    # ── 3. Behavior → Window → Exploitability (injectés) ──────────
    behavior_id = _insert_behavior(db_path, scene_id)
    window_id = _insert_window(db_path, behavior_id)
    _insert_exploitability(db_path, window_id)

    # ── 4. Zone + Regime + Principe ACTIVE (injectés) ──────────────
    _insert_zone(db_path, snapshot_id, currency="GBP",
                 state="ACCUMULATING", tension=0.8,
                 z_extreme_dir="UP", z_current=1.0)
    _insert_zone(db_path, snapshot_id, currency="USD",
                 state="NEUTRAL", tension=0.0,
                 z_extreme_dir=None, z_current=0.0)
    _insert_regime(db_path, snapshot_id, currency="GBP",
                   regime_type="CASSURE")
    _insert_regime(db_path, snapshot_id, currency="USD",
                   regime_type="NEUTRE")
    _insert_principle(db_path, snapshot_id,
                      principle_id="PRICE_LAG_AT_NODE_BIRTH",
                      direction="haussiere", confidence=90, currency="GBP")

    # ── 5. SignalGenerator (réel) ──────────────────────────────────
    signal_generator = SignalGenerator(db_path=db_path, source_type="test")
    signal = signal_generator.generate(snapshot_id)

    # Assertion B : le signal DOIT être directionnel+exploitable.
    assert signal["direction"] is not None and signal["direction"] != "neutre", (
        f"SignalGenerator a produit un signal NON directionnel : "
        f"direction={signal['direction']}, "
        f"raison_absence={signal.get('raison_absence')}, "
        f"exploitability_statut={signal.get('exploitability_statut')}. "
        f"Pipeline mal calibré."
    )
    assert signal["confiance"] > 0
    assert signal["raison_absence"] is None, (
        f"raison_absence non null : {signal['raison_absence']}"
    )
    assert signal["exploitability_statut"] == "exploitable"
    signal_id = signal["signal_id"]

    # ── 6. DecisionLogger (réel) ───────────────────────────────────
    decision_logger = DecisionLogger(db_path=db_path, source_type="test")
    decision = decision_logger.log(snapshot_id)

    # ── 7. Assertions finales ──────────────────────────────────────
    # 7.a. Le bug session 2 fixé : direction IS NOT NULL.
    assert decision["direction"] is not None and decision["direction"] != "neutre", (
        f"DecisionLogger a produit aucune_action malgré signal directionnel "
        f"exploitable : action={decision['action']}, "
        f"direction={decision['direction']}. "
        f"RÉGRESSION du fix _load_signal (commit d2f6c60) ou nouveaux bugs "
        f"dans _determine_action."
    )
    # 7.b. Confiance positive.
    assert decision["confiance"] > 0, (
        f"Confiance=0 malgré signal directionnel : {decision['confiance']}. "
        f"Signal conf était {signal['confiance']}."
    )
    # 7.c. Action cohérente avec signal exploitable + court terme.
    assert decision["action"] in {"preparer_entree", "surveiller", "observer"}, (
        f"Action inattendue : {decision['action']}"
    )
    # 7.d. Contexte complet peuplé (preuve que le pipeline a été traversé).
    ctx = decision["contexte_complet"]
    assert ctx["scene"] is not None, "contexte.scene manquant"
    assert ctx["behavior"] is not None
    assert ctx["window"] is not None
    assert ctx["exploitability"] is not None
    assert len(ctx["principle_evaluations"]) >= 1

    # 7.e. Vérification DB : au moins 1 décision directionnelle existe.
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = list(conn.execute(
            "SELECT decision_id, direction, confiance, action, snapshot_id, signal_id "
            "FROM decisions WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchall())
    finally:
        conn.close()
    assert len(rows) >= 1, f"Attendu ≥1 décision pour ce snapshot, trouvé {len(rows)}"
    target = next((r for r in rows if r["direction"] is not None and r["direction"] != "neutre"), None)
    assert target is not None, (
        f"Aucune décision directionnelle dans les {len(rows)} rangées : "
        f"rows={[(r['direction'], r['confiance'], r['action']) for r in rows]}"
    )
    assert target["confiance"] > 0
    assert target["snapshot_id"] == snapshot_id
    assert target["signal_id"] == signal_id
