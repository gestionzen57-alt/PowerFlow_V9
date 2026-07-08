"""Tests unitaires — DecisionLogger (couche Décision, Phase 9) PowerFlow V9."""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from core.v9.behavior_db import BEHAVIOR_COLUMNS, init_behavior_db
from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.decision_logger import DecisionLogger, DecisionLoggerError
from core.v9.exploitability_db import EXPLOITABILITY_COLUMNS, init_exploitability_db
from core.v9.principle_db import PRINCIPLE_EVALUATIONS_COLUMNS, init_principle_db
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db
from core.v9.scene_db import SCENES_COLUMNS, init_scene_db
from core.v9.signal_db import SIGNALS_COLUMNS, init_signal_db
from core.v9.window_db import WINDOWS_COLUMNS, init_window_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    init_scene_db(path)
    init_behavior_db(path)
    init_window_db(path)
    init_exploitability_db(path)
    init_regime_db(path)
    init_principle_db(path)
    init_signal_db(path)
    return path


def _insert_row(db_path: Path, table: str, columns: list[str], values: dict) -> None:
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        conn.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            [values.get(c) for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def build_full_chain(
    db_path: Path,
    *,
    symbol: str = "GBPUSD",
    timeframe: str = "M15",
    exploitability_statut: str = "exploitable",
    signal_direction: str | None = "haussiere",
    signal_horizon: str | None = "court_terme",
    signal_confiance: int = 80,
    raison_absence: str | None = None,
    principes_source: list[str] | None = None,
) -> str:
    snapshot_id = f"v9-dec-{uuid.uuid4().hex[:8]}"
    forces_row = {c: None for c in FORCES_COLUMNS}
    forces_row.update({
        "snapshot_id": snapshot_id, "schema_version": "1.0",
        "timestamp": "2026-07-05T17:00:00.000Z", "source": "MT4_SDI",
        "symbol": symbol, "timeframe": timeframe, "bar_time": 1, "is_closed_bar": True,
        "force_usd": 50.0, "force_gbp": 62.0, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "haussiere", "stale": False, "created_at": "2026-07-05T17:00:00.100Z",
    })
    _insert_row(db_path, "forces_snapshots", FORCES_COLUMNS, forces_row)

    scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    scene_row = {c: None for c in SCENES_COLUMNS}
    scene_row.update({
        "scene_id": scene_id, "schema_version": "1.0", "timestamp": "2026-07-05T17:00:00.000Z",
        "timeframes_concernes": timeframe, "forces_snapshot_ref": snapshot_id,
        "coalitions_json": "[]", "antagonismes_json": "[]", "stale": False,
        "created_at": "2026-07-05T17:00:00.200Z",
    })
    _insert_row(db_path, "scenes", SCENES_COLUMNS, scene_row)

    behavior_id = f"beh-{uuid.uuid4().hex[:8]}"
    behavior_row = {c: None for c in BEHAVIOR_COLUMNS}
    behavior_row.update({
        "behavior_id": behavior_id, "schema_version": "1.0", "timestamp": "2026-07-05T17:00:00.000Z",
        "scene_id_ref": scene_id, "symbol": symbol, "timeframe": timeframe,
        "qualification": "bascule", "intensite": "moderee", "phase": "developpement",
        "confiance_qualification": 70, "point_de_rupture_detecte": False,
        "stale": False, "created_at": "2026-07-05T17:00:00.300Z",
    })
    _insert_row(db_path, "behaviors", BEHAVIOR_COLUMNS, behavior_row)

    window_id = f"win-{uuid.uuid4().hex[:8]}"
    window_row = {c: None for c in WINDOWS_COLUMNS}
    window_row.update({
        "window_id": window_id, "schema_version": "1.0", "timestamp": "2026-07-05T17:00:00.000Z",
        "behavior_id": behavior_id, "behavior_qualification": "bascule", "behavior_confiance": 70,
        "statut": "ouverte", "niveau_confiance": 70, "fragilite_detectee": False,
        "conditions_invalidation_json": "[]", "stale": False, "created_at": "2026-07-05T17:00:00.400Z",
    })
    _insert_row(db_path, "windows", WINDOWS_COLUMNS, window_row)

    exploitability_id = f"exp-{uuid.uuid4().hex[:8]}"
    exploitability_row = {c: None for c in EXPLOITABILITY_COLUMNS}
    exploitability_row.update({
        "exploitability_id": exploitability_id, "schema_version": "1.0",
        "timestamp": "2026-07-05T17:00:00.000Z", "window_id": window_id,
        "window_statut": "ouverte", "window_niveau_confiance": 70,
        "statut": exploitability_statut, "niveau_confiance_global": 78,
        "validation_hitl_requise": False, "replay_nombre_cas": 0,
        "stale": False, "created_at": "2026-07-05T17:00:00.500Z",
    })
    _insert_row(db_path, "exploitability", EXPLOITABILITY_COLUMNS, exploitability_row)

    regime_row = {c: None for c in REGIME_SNAPSHOTS_COLUMNS}
    regime_row.update({
        "regime_id": f"regime-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T17:00:00.000Z", "forces_snapshot_ref": snapshot_id,
        "symbol": symbol, "timeframe": timeframe, "currency": "GBP",
        "force_value": 62.0, "regime_type": "CASSURE", "mean_reversion_zone": False,
        "stale": False, "created_at": "2026-07-05T17:00:00.600Z",
    })
    _insert_row(db_path, "regime_snapshots", REGIME_SNAPSHOTS_COLUMNS, regime_row)

    peval_row = {c: None for c in PRINCIPLE_EVALUATIONS_COLUMNS}
    peval_row.update({
        "evaluation_id": f"peval-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T17:00:00.000Z", "snapshot_id": snapshot_id,
        "principle_id": "ZONE_RETEST", "v9_status": "ACTIVE", "kind": "node_rule",
        "symbol": symbol, "timeframe": timeframe, "currency": "GBP",
        "triggered": True, "direction": "haussiere", "confidence": 80,
        "anti_signal_bias": False, "reason": "conditions_remplies", "context_json": "{}",
        "created_at": "2026-07-05T17:00:00.700Z",
    })
    _insert_row(db_path, "principle_evaluations", PRINCIPLE_EVALUATIONS_COLUMNS, peval_row)

    signal_row = {c: None for c in SIGNALS_COLUMNS}
    signal_row.update({
        "signal_id": f"sig-{uuid.uuid4().hex[:8]}", "schema_version": "1.0",
        "timestamp": "2026-07-05T17:00:00.000Z", "snapshot_id": snapshot_id,
        "symbol": symbol, "timeframe": timeframe, "currency": "GBP",
        "direction": signal_direction, "confiance": signal_confiance, "horizon": signal_horizon,
        "principes_source_json": json.dumps(principes_source or (["ZONE_RETEST"] if signal_direction else [])),
        "regime_type": "CASSURE", "exploitability_id": exploitability_id,
        "exploitability_statut": exploitability_statut, "raison_absence": raison_absence,
        "stale": False, "created_at": "2026-07-05T17:00:00.800Z",
    })
    _insert_row(db_path, "signals", SIGNALS_COLUMNS, signal_row)

    return snapshot_id


def test_raises_when_no_signal_logged(db_path: Path):
    with pytest.raises(DecisionLoggerError):
        DecisionLogger(db_path=db_path).log("does-not-exist")


def test_persists_decision_row(db_path: Path):
    snapshot_id = build_full_chain(db_path)
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM decisions WHERE decision_id = ?", (decision["decision_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_action_aucune_action_when_direction_absent(db_path: Path):
    snapshot_id = build_full_chain(
        db_path, signal_direction=None, signal_horizon=None,
        signal_confiance=0, raison_absence="aucun_principe_actif_declenche",
    )
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["action"] == "aucune_action"


def test_action_aucune_action_when_direction_neutre(db_path: Path):
    snapshot_id = build_full_chain(db_path, signal_direction="neutre", signal_horizon="surveillance")
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["action"] == "aucune_action"


def test_action_preparer_entree_when_exploitable_court_terme(db_path: Path):
    snapshot_id = build_full_chain(
        db_path, exploitability_statut="exploitable",
        signal_direction="haussiere", signal_horizon="court_terme",
    )
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["action"] == "preparer_entree"


def test_action_surveiller_when_exploitable_but_surveillance_horizon(db_path: Path):
    snapshot_id = build_full_chain(
        db_path, exploitability_statut="exploitable",
        signal_direction="haussiere", signal_horizon="surveillance",
    )
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["action"] == "surveiller"


def test_action_surveiller_when_watchlist(db_path: Path):
    snapshot_id = build_full_chain(
        db_path, exploitability_statut="watchlist",
        signal_direction="haussiere", signal_horizon="surveillance",
    )
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["action"] == "surveiller"


def test_action_observer_fallback(db_path: Path):
    snapshot_id = build_full_chain(
        db_path, exploitability_statut="refuse",
        signal_direction="haussiere", signal_horizon="surveillance",
    )
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["action"] == "observer"


def test_contexte_complet_contains_full_chain(db_path: Path):
    snapshot_id = build_full_chain(db_path)
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    ctx = decision["contexte_complet"]
    assert ctx["scene"] is not None
    assert ctx["behavior"] is not None
    assert ctx["window"] is not None
    assert ctx["exploitability"] is not None
    assert len(ctx["regime"]) >= 1
    assert len(ctx["principle_evaluations"]) >= 1
    assert ctx["signal"]["snapshot_id"] == snapshot_id


def test_decision_carries_chain_ids(db_path: Path):
    snapshot_id = build_full_chain(db_path)
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["scene_id"] is not None
    assert decision["behavior_id"] is not None
    assert decision["window_id"] is not None
    assert decision["exploitability_id"] is not None


def test_principes_list_sorted_unique(db_path: Path):
    snapshot_id = build_full_chain(
        db_path, principes_source=["ZULU", "ALPHA", "ALPHA"],
    )
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    assert decision["principes"] == ["ALPHA", "ZULU"]


def test_contexte_complet_json_roundtrips(db_path: Path):
    snapshot_id = build_full_chain(db_path)
    decision = DecisionLogger(db_path=db_path).log(snapshot_id)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT contexte_complet_json FROM decisions WHERE decision_id = ?",
            (decision["decision_id"],),
        ).fetchone()
    finally:
        conn.close()
    from core.v9.decision_logger import load_contexte_complet
    parsed = load_contexte_complet(row[0])
    assert parsed["signal"]["snapshot_id"] == snapshot_id


def test_decision_idempotent_same_snapshot_no_duplicate(db_path: Path):
    """Chantier B (2026-07-06) : idempotence decisions — rejouer N fois
    le même snapshot ne doit produire qu'UNE rangée dans decisions.

    Pré-fix : decision_id changeait à chaque appel (timestamp+uuid),
    INSERT OR REPLACE créait une nouvelle rangée (3697 → 3960 sur 3
    snapshots rejoués — voir observation rapport session 2).

    Post-fix : decision_id = uuid5(snapshot_id) — déterministe par
    snapshot. INSERT OR REPLACE écrase vraiment la rangée.
    """
    snap_id = build_full_chain(
        db_path, exploitability_statut="exploitable",
        signal_direction="haussiere", signal_horizon="court_terme",
        signal_confiance=85, raison_absence=None,
    )

    decision_logger = DecisionLogger(db_path=db_path)
    dec1 = decision_logger.log(snap_id)
    dec1_id = dec1["decision_id"]
    assert dec1["action"] == "preparer_entree"

    # 2e appel : decision_id stable (idempotence).
    dec2 = decision_logger.log(snap_id)
    assert dec2["decision_id"] == dec1_id, (
        f"decision_id change entre 2 appels sur le même snapshot : "
        f"{dec1_id} != {dec2['decision_id']}. Régression idempotence."
    )

    dec3 = decision_logger.log(snap_id)
    assert dec3["decision_id"] == dec1_id

    # Vérification DB : UNE SEULE rangée pour ce snapshot_id.
    conn = get_connection(db_path)
    try:
        rows = list(conn.execute(
            "SELECT decision_id FROM decisions WHERE snapshot_id = ?", (snap_id,)
        ).fetchall())
    finally:
        conn.close()
    assert len(rows) == 1, (
        f"Attendu 1 rangée pour ce snapshot_id après 3 appels, "
        f"trouvé {len(rows)} : {rows}. INSERT OR REPLACE n'écrase pas."
    )
    assert rows[0][0] == dec1_id


def test_decision_replaces_nondirectional_with_directional(db_path: Path):
    """Chantier B : si une décision aucune_action existe déjà et qu'un
    rejeu produit une décision directionnelle (cas emblématique session 2),
    le rejeu DOIT écraser l'ancienne.

    Pré-fix : double rangée coexistaient.
    Post-fix : _write_to_db() compare _action_quality() et écrase si
    la nouvelle est strictement meilleure.
    """
    snap_id = build_full_chain(
        db_path, exploitability_statut="non_exploitable",
        signal_direction=None, signal_horizon=None,
        signal_confiance=0, raison_absence="aucun_principe_actif_declenche",
    )
    decision_logger = DecisionLogger(db_path=db_path)
    dec0 = decision_logger.log(snap_id)
    assert dec0["action"] == "aucune_action"
    assert dec0["direction"] is None

    # Bascule le signal en directionnel+exploitable.
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sig_row = conn.execute(
            "SELECT signal_id, exploitability_id FROM signals WHERE snapshot_id=?",
            (snap_id,),
        ).fetchone()
        sig_id = sig_row["signal_id"]
        exp_id = sig_row["exploitability_id"]
        conn.execute(
            "UPDATE signals SET direction='haussiere', confiance=90, "
            "horizon='court_terme', exploitability_statut='exploitable', "
            "raison_absence=NULL, "
            "principes_source_json=? WHERE signal_id=?",
            (json.dumps(["PRICE_LAG_AT_NODE_BIRTH"]), sig_id),
        )
        # Aussi mettre à jour la table exploitability pour cohérence avec
        # chain loader (qui lit l'exploitability réelle, pas le signal).
        conn.execute(
            "UPDATE exploitability SET statut='exploitable', "
            "niveau_confiance_global=85, window_statut='ouverte', "
            "raison_refus=NULL WHERE exploitability_id=?",
            (exp_id,),
        )
        conn.commit()
    finally:
        conn.close()

    dec1 = decision_logger.log(snap_id)
    assert dec1["direction"] == "haussiere", (
        f"Rejeu ne remplace pas l'aucune_action par directionnelle : "
        f"direction={dec1['direction']}, action={dec1['action']}."
    )
    assert dec1["action"] == "preparer_entree"
    assert dec1["confiance"] == 90

    conn = get_connection(db_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE snapshot_id=?", (snap_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 1, f"Attendu 1 rangée, trouvé {n}"


def test_decision_keeps_best_on_multiple_replay(db_path: Path):
    """Chantier B : si la décision directionnelle existe déjà et qu'un
    rejeu produit une décision directionnelle de qualité INFÉRIEURE,
    on garde la meilleure (skip silencieux en DB).
    """
    snap_id = build_full_chain(
        db_path, exploitability_statut="exploitable",
        signal_direction="haussiere", signal_horizon="court_terme",
        signal_confiance=95, raison_absence=None,
    )
    decision_logger = DecisionLogger(db_path=db_path)
    dec_best = decision_logger.log(snap_id)
    assert dec_best["action"] == "preparer_entree"
    assert dec_best["confiance"] == 95
    best_id = dec_best["decision_id"]

    # Bascule en surveillance (qualité 2 < 3) — ne DOIT PAS écraser.
    conn = get_connection(db_path)
    try:
        sig_row = conn.execute(
            "SELECT signal_id FROM signals WHERE snapshot_id=?", (snap_id,)
        ).fetchone()
        conn.execute(
            "UPDATE signals SET horizon='surveillance' WHERE signal_id=?",
            (sig_row[0],),
        )
        conn.commit()
    finally:
        conn.close()

    dec_worse = decision_logger.log(snap_id)
    # decision_id stable (idempotence).
    assert dec_worse["decision_id"] == best_id

    # DB : 1 seule rangée, avec l'ANCIENNE action pré-applied (skip).
    conn = get_connection(db_path)
    try:
        rows = list(conn.execute(
            "SELECT action, confiance FROM decisions WHERE snapshot_id=?", (snap_id,)
        ).fetchall())
    finally:
        conn.close()
    assert len(rows) == 1, f"Attendu 1 rangée, trouvé {len(rows)}"
    assert rows[0][0] == "preparer_entree", (
        f"L'ancienne action=preparer_entree a été écrasée par "
        f"{rows[0][0]}. Skip de qualité inopérant."
    )
    assert rows[0][1] == 95


def test_load_signal_prefers_directional_exploitable_on_same_snapshot(db_path: Path):
    """Bug live 2026-07-06 : même snapshot avec un signal non-exploitable
    ancien (direction=None) puis un signal directionnel exploitable plus
    récent. _load_signal doit privilégier le signal directionnel pour
    permettre une décision directionnelle sur une chaîne déjà décidée
    une première fois avec aucune_action.

    Pré-fix : ORDER BY id DESC LIMIT 1 prenait le signal le plus récent
    par id auto-incrément, mais pas le plus pertinent — un signal
    non-directionnel ancien suivi d'un directionnel nouveau rangeait
    dans cet ordre : neutre ancien → directionnel nouveau. Le bug
    se manifestait quand un AUTRE snapshot avait été traité entre
    temps (ordre des id global), faisant primer un signal non
    directionnel d'un AUTRE snapshot via la clause ORDER BY id DESC.

    Test direct : on insère MANUELLEMENT 2 signaux pour le même snapshot
    avec des caractéristiques différentes et on vérifie que le choix
    se porte sur le signal directionnel+exploitable.
    """
    # Crée 1 chaîne complète (snapshot unique, seul signal directionnel).
    snap_id = build_full_chain(
        db_path, exploitability_statut="exploitable",
        signal_direction="haussiere", signal_horizon="court_terme",
        signal_confiance=85, raison_absence=None,
    )

    # Récupère l'exploitability_id du signal initial pour respecter
    # la cohérence du contexte (la colonne n'est pas UNIQUE mais joue
    # le rôle d'une FK applicative).
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sig0 = conn.execute(
            "SELECT signal_id, exploitability_id FROM signals WHERE snapshot_id=? ORDER BY id ASC LIMIT 1",
            (snap_id,),
        ).fetchone()
        exp_id = sig0["exploitability_id"]
        # UPDATE du signal initial → non-directionnel ancien (bar_time=1
        # représente le moment T0 du snapshot).
        conn.execute(
            "UPDATE signals SET direction=NULL, confiance=0, exploitability_statut='non_exploitable', "
            "raison_absence='exploitabilite_non_exploitable', horizon=NULL WHERE signal_id=?",
            (sig0["signal_id"],),
        )
        # INSERT du 2ème signal directionnel récent (id AUTO_INC > sig0),
        # bar_time=2 représente une réévaluation plus tardive.
        conn.execute(
            "INSERT INTO signals (signal_id, schema_version, timestamp, snapshot_id, "
            "symbol, timeframe, currency, direction, confiance, horizon, "
            "principes_source_json, regime_type, exploitability_id, "
            "exploitability_statut, raison_absence, stale, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("sig-directionnel-recent", "1.0", "2026-07-05T18:00:00.000Z",
             snap_id, "GBPUSD", "M15", "GBP",
             "haussiere", 95, "court_terme",
             '["ZONE_RETEST"]', "CASSURE", exp_id,
             "exploitable", None, False,
             "2026-07-05T18:00:00.500Z"),
        )
        conn.commit()
    finally:
        conn.close()

    # Le signal directionnel récent DOIT être sélectionné.
    dec = DecisionLogger(db_path=db_path).log(snap_id)
    assert dec["direction"] == "haussiere", (
        f"_load_signal a ignoré le signal directionnel récent : "
        f"direction={dec['direction']}"
    )
    assert dec["action"] == "preparer_entree", (
        f"_load_signal a ignoré le signal directionnel récent : "
        f"action={dec['action']}"
    )
    assert dec["confiance"] == 95
