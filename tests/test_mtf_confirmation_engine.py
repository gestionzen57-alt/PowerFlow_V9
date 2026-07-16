"""Tests unitaires — MTFConfirmationEngine (stratégie Søn, 2026-07-15) PowerFlow V9."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.mtf_confirmation_engine import MTFConfirmationEngine
from core.v9.regime_db import REGIME_SNAPSHOTS_COLUMNS, init_regime_db

SYMBOL = "GBPUSD"


def _epoch_seconds(timestamp: str) -> int:
    return int(
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )


def insert_forces(
    db_path: Path,
    *,
    timeframe: str,
    timestamp: str,
    bar_time: int | None = None,
    force_gbp: float = 50.0,
    force_usd: float = 50.0,
    croisement_detecte: bool = False,
    croisement_direction: str | None = None,
    symbol: str = SYMBOL,
    stale: bool = False,
) -> str:
    snapshot_id = f"v9-mtf-{uuid.uuid4().hex[:10]}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": timestamp,
        "source": "MT4_SDI",
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_time": bar_time if bar_time is not None else _epoch_seconds(timestamp),
        "is_closed_bar": True,
        "force_usd": force_usd, "force_gbp": force_gbp, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "neutre",
        "croisement_detecte": croisement_detecte,
        "croisement_direction": croisement_direction,
        "stale": stale,
        "created_at": timestamp,
    })
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
    return snapshot_id


def insert_regime(
    db_path: Path,
    *,
    forces_snapshot_ref: str,
    currency: str,
    regime_type: str,
    cassure_direction: str | None = None,
    symbol: str = SYMBOL,
    timeframe: str = "H4",
) -> None:
    row = {c: None for c in REGIME_SNAPSHOTS_COLUMNS}
    row.update({
        "regime_id": f"regime-{uuid.uuid4().hex[:10]}",
        "schema_version": "1.0",
        "timestamp": "2026-07-15T10:00:00.000Z",
        "forces_snapshot_ref": forces_snapshot_ref,
        "symbol": symbol,
        "timeframe": timeframe,
        "currency": currency,
        "regime_type": regime_type,
        "cassure_direction": cassure_direction,
        "stale": False,
        "source_type": "live",
        "created_at": "2026-07-15T10:00:00.000Z",
    })
    conn = get_connection(db_path)
    try:
        col_names = ", ".join(REGIME_SNAPSHOTS_COLUMNS)
        placeholders = ", ".join(["?"] * len(REGIME_SNAPSHOTS_COLUMNS))
        conn.execute(
            f"INSERT INTO regime_snapshots ({col_names}) VALUES ({placeholders})",
            [row.get(c) for c in REGIME_SNAPSHOTS_COLUMNS],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    init_regime_db(path)
    return path


def test_h4_haussier_m15_croisement_haussier(db_path: Path) -> None:
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=70.0, force_usd=30.0,
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP",
        regime_type="CASSURE", cassure_direction="UP",
    )
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=75.0, force_usd=29.0,
        croisement_detecte=True, croisement_direction="haussiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(m15_snap)

    assert result["aligned"] is True
    assert result["conflict"] is False
    assert result["confidence_boost"] == 25
    assert result["direction"] == "haussiere"
    assert result["context_tf"] == "H4"
    assert result["trigger_tf"] == "M15"
    assert result["mtf_setup"] == "sortie_zone_h4_croisement_m15"


def test_h4_neutre_m15_croisement(db_path: Path) -> None:
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=50.0, force_usd=50.0,
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP", regime_type="NEUTRE",
    )
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=75.0, force_usd=29.0,
        croisement_detecte=True, croisement_direction="haussiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(m15_snap)

    assert result["aligned"] is False
    assert result["conflict"] is False
    assert result["confidence_boost"] == 0
    assert result["mtf_setup"] == "no_context"


def test_h4_haussier_m15_croisement_baissier(db_path: Path) -> None:
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=70.0, force_usd=30.0,
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP",
        regime_type="CASSURE", cassure_direction="UP",
    )
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=25.0, force_usd=68.0,
        croisement_detecte=True, croisement_direction="baissiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(m15_snap)

    assert result["aligned"] is False
    assert result["conflict"] is True
    assert result["confidence_boost"] == -15
    assert result["mtf_setup"] == "conflict"
    assert result["context_thesis"] == "haussiere"
    assert result["trigger_confirmation"] == "croisement_baissiere"


def test_find_context_snapshot(db_path: Path) -> None:
    h4_snap_old = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T04:00:00.000Z",
        force_gbp=40.0, force_usd=40.0,
    )
    h4_snap_recent = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=70.0, force_usd=30.0,
    )
    # H4 futur (après le trigger M15) : ne doit jamais être choisi.
    insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T16:00:00.000Z",
        force_gbp=10.0, force_usd=90.0,
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    conn = get_connection(db_path)
    conn.row_factory = __import__("sqlite3").Row
    try:
        found = engine._find_context_snapshot(
            conn, SYMBOL, "H4", "2026-07-15T13:45:00.000Z"
        )
    finally:
        conn.close()

    assert found is not None
    assert found["snapshot_id"] == h4_snap_recent
    assert found["snapshot_id"] != h4_snap_old


def test_no_context_when_trigger_tf_has_no_higher_tf(db_path: Path) -> None:
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T13:00:00.000Z",
        force_gbp=75.0, force_usd=25.0,
        croisement_detecte=True, croisement_direction="haussiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(h4_snap)

    assert result["aligned"] is False
    assert result["mtf_setup"] == "no_context"
    assert result["confidence_boost"] == 0


def test_evaluate_persists_to_mtf_confirmations(db_path: Path) -> None:
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=70.0, force_usd=30.0,
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP",
        regime_type="CASSURE", cassure_direction="UP",
    )
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=75.0, force_usd=29.0,
        croisement_detecte=True, croisement_direction="haussiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    engine.evaluate(m15_snap)

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT aligned, confidence_boost FROM mtf_confirmations "
            "WHERE forces_snapshot_ref = ?",
            (m15_snap,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert bool(row[0]) is True
    assert row[1] == 25


def test_unknown_snapshot_raises(db_path: Path) -> None:
    from core.v9.mtf_confirmation_engine import MTFConfirmationEngineError

    engine = MTFConfirmationEngine(db_path=db_path)
    with pytest.raises(MTFConfirmationEngineError):
        engine.evaluate("does-not-exist")


# ── DIVERSIFY 2026-07-16 — Gap 1 (RETOUR_EQUILIBRE) + Gap 9 (boost pondéré) ──


def test_retour_equilibre_derive_direction_et_aligne(db_path: Path) -> None:
    """RETOUR_EQUILIBRE (cassure_direction NULL) : la direction de la thèse est
    dérivée de la force de la devise de base (mean reversion). GBP sur-acheté
    (>50+deadband) → thèse baissière ; un croisement M15 baissier s'aligne."""
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=70.0, force_usd=30.0,
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP",
        regime_type="RETOUR_EQUILIBRE", cassure_direction=None,
    )
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=25.0, force_usd=68.0,
        croisement_detecte=True, croisement_direction="baissiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(m15_snap)

    assert result["aligned"] is True
    assert result["context_thesis"] == "baissiere"
    assert result["direction"] == "baissiere"
    assert result["confidence_boost"] == 25  # croisement = boost max
    assert result["mtf_setup"] == "retour_equilibre_h4_confirmation_m15"


def test_retour_equilibre_deadband_neutre_pas_de_these(db_path: Path) -> None:
    """GBP proche de l'équilibre (dans le deadband) → pas de direction de
    réversion fiable → no_context (dégradation gracieuse)."""
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=51.0, force_usd=49.0,  # dans le deadband [47, 53]
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP",
        regime_type="RETOUR_EQUILIBRE", cassure_direction=None,
    )
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=75.0, force_usd=29.0,
        croisement_detecte=True, croisement_direction="haussiere",
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(m15_snap)

    assert result["aligned"] is False
    assert result["mtf_setup"] == "no_context"
    assert result["reason"] == "thesis_absente"


def test_boost_spread_est_pondere_sous_le_max(db_path: Path) -> None:
    """Un alignement par spread (pas de croisement discret) donne un boost
    PONDÉRÉ, strictement inférieur au +25 d'un croisement franc (Gap 9)."""
    # H4 GBP sur-vendu (<50-deadband) → RETOUR_EQUILIBRE thèse haussière.
    h4_snap = insert_forces(
        db_path, timeframe="H4", timestamp="2026-07-15T08:00:00.000Z",
        force_gbp=40.0, force_usd=60.0,
    )
    insert_regime(
        db_path, forces_snapshot_ref=h4_snap, currency="GBP",
        regime_type="RETOUR_EQUILIBRE", cassure_direction=None,
    )
    # M15 sans croisement : spread = 75 - 50 = 25 (seuil=20) → alignment_spread
    # haussier. ratio = (25-20)/20 = 0.25 → boost = 12 + 13*0.25 = 15.
    m15_snap = insert_forces(
        db_path, timeframe="M15", timestamp="2026-07-15T13:45:00.000Z",
        force_gbp=75.0, force_usd=50.0,
    )

    engine = MTFConfirmationEngine(db_path=db_path)
    result = engine.evaluate(m15_snap)

    assert result["aligned"] is True
    assert result["direction"] == "haussiere"
    assert result["trigger_confirmation"] == "alignment_spread_haussiere"
    assert 12 <= result["confidence_boost"] < 25
