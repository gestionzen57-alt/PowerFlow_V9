"""Tests unitaires — RegimeDetector (gap V8 regime_snapshots, Phase 9) PowerFlow V9."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.regime_detector import RegimeDetector, RegimeDetectorError

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]


def insert_bar(
    db_path: Path,
    *,
    symbol: str = "EURUSD",
    timeframe: str = "M5",
    bar_time: int,
    force_gbp: float,
    stale: bool = False,
) -> str:
    """Insère un snapshot de forces ; seule force_gbp varie, les autres
    devises restent neutres (50.0, hors zone extrême)."""
    snapshot_id = f"v9-regime-{uuid.uuid4().hex[:10]}"
    row = {c: None for c in FORCES_COLUMNS}
    row.update({
        "snapshot_id": snapshot_id,
        "schema_version": "1.0",
        "timestamp": f"2026-07-05T14:{bar_time:02d}:00.000Z",
        "source": "MT4_SDI",
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_time": bar_time,
        "is_closed_bar": True,
        "force_usd": 50.0, "force_gbp": force_gbp, "force_eur": 50.0, "force_jpy": 50.0,
        "force_cad": 50.0, "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "direction": "neutre",
        "stale": stale,
        "created_at": f"2026-07-05T14:{bar_time:02d}:00.100Z",
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


def insert_series(db_path: Path, forces: list[float], **kwargs) -> str:
    """Insère une série de barres (bar_time = index) ; retourne le
    snapshot_id de la DERNIÈRE barre insérée."""
    snapshot_id = ""
    for i, force in enumerate(forces):
        snapshot_id = insert_bar(db_path, bar_time=i, force_gbp=force, **kwargs)
    return snapshot_id


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


def gbp_regime(results: list[dict]) -> dict:
    return next(r for r in results if r["currency"] == "GBP")


def test_palier_established_after_n_min_flat_bars(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0, 50.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    assert gbp_regime(results)["regime_type"] == "PALIER"


def test_neutre_when_run_length_below_n_min(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 50.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    assert gbp_regime(results)["regime_type"] == "NEUTRE"


def test_cassure_after_established_palier(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0, 50.0, 53.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    regime = gbp_regime(results)
    assert regime["regime_type"] == "CASSURE"
    assert regime["cassure_direction"] == "UP"
    assert regime["cassure_type"] == "INDETERMINEE"
    assert regime["palier_level"] == pytest.approx(50.0)


def test_extension_continues_after_cassure(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0, 50.0, 53.0, 55.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    regime = gbp_regime(results)
    assert regime["regime_type"] == "EXTENSION"
    assert regime["cassure_direction"] == "UP"


def test_retour_equilibre_in_extreme_zone(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 85.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    regime = gbp_regime(results)
    assert regime["regime_type"] == "RETOUR_EQUILIBRE"
    assert regime["mean_reversion_zone"] is True or regime["mean_reversion_zone"] == 1


def test_rejet_violent_reversal_at_extreme(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 82.0, 78.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    regime = gbp_regime(results)
    assert regime["regime_type"] == "REJET"
    assert regime["cassure_direction"] == "DOWN"
    assert regime["cassure_type"] == "INDETERMINEE"


def test_first_bar_alone_is_neutre_outside_extreme(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    assert gbp_regime(results)["regime_type"] == "NEUTRE"


def test_persists_one_row_per_currency(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0])
    detector = RegimeDetector(db_path=db_path)
    results = detector.detect(snapshot_id)
    assert len(results) == len(DEVISES)
    assert {r["currency"] for r in results} == set(DEVISES)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM regime_snapshots WHERE forces_snapshot_ref = ?",
            (snapshot_id,),
        ).fetchone()
    finally:
        conn.close()
    assert rows[0] == len(DEVISES)


def test_missing_snapshot_raises(db_path: Path) -> None:
    detector = RegimeDetector(db_path=db_path)
    with pytest.raises(RegimeDetectorError):
        detector.detect("does-not-exist")


def test_lookback_window_truncates_history(db_path: Path) -> None:
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0, 50.0])
    detector_full = RegimeDetector(db_path=db_path)
    assert gbp_regime(detector_full.detect(snapshot_id))["regime_type"] == "PALIER"

    detector_short = RegimeDetector(db_path=db_path, config={"lookback_bars": 2})
    assert gbp_regime(detector_short.detect(snapshot_id))["regime_type"] == "NEUTRE"
