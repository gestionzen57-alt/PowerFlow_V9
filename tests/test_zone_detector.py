"""Tests unitaires — ZoneDetector (gap zone_diagnostics, Phase 9) PowerFlow V9."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from core.v9.db_schema import FORCES_COLUMNS, get_connection, init_db
from core.v9.zone_detector import ZoneDetector, ZoneDetectorError

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
    snapshot_id = f"v9-zone-{uuid.uuid4().hex[:10]}"
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


def read_zone_diagnostics(db_path: Path, snapshot_id: str) -> list[dict]:
    """Lit les diagnostics de zone pour un snapshot."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM zone_diagnostics WHERE forces_snapshot_ref = ? ORDER BY currency",
            (snapshot_id,),
        ).fetchall()
        columns = [d[1] for d in conn.execute("PRAGMA table_info(zone_diagnostics)").fetchall()]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()


def gbp_zone(results: list[dict]) -> dict:
    return next(r for r in results if r["currency"] == "GBP")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


def test_neutral_when_force_near_50(db_path: Path) -> None:
    """Force à 50.0 → z-score proche de 0 → état NEUTRAL."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert zone["state"] == "NEUTRAL"
    assert abs(float(zone["z_current"])) < 0.5


def test_early_extreme_when_force_deviates(db_path: Path) -> None:
    """Force à 75.0 (z-score ~1.0) → EARLY_EXTREME."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 75.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert zone["state"] == "EARLY_EXTREME"
    assert float(zone["z_current"]) > 0.5


def test_rupture_when_force_extreme(db_path: Path) -> None:
    """Force très extrême (z-score ~2.0) → RUPTURE."""
    # Série [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 100] : stdev ~15.8, z ~3.16
    snapshot_id = insert_series(db_path, [50.0]*10 + [100.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert zone["state"] == "RUPTURE"
    assert float(zone["z_current"]) > 1.5


def test_accumulating_after_early_extreme_same_direction(db_path: Path) -> None:
    """Deux snapshots consécutifs dans l'extrême, même direction → ACCUMULATING."""
    # Série de base neutre, puis entrée dans l'extrême
    sid1 = insert_bar(db_path, bar_time=0, force_gbp=50.0)
    sid2 = insert_bar(db_path, bar_time=1, force_gbp=50.0)
    sid3 = insert_bar(db_path, bar_time=2, force_gbp=50.0)
    sid4 = insert_bar(db_path, bar_time=3, force_gbp=75.0)  # EARLY_EXTREME
    ZoneDetector(db_path=db_path).detect(sid4)

    sid5 = insert_bar(db_path, bar_time=4, force_gbp=78.0)  # même direction → ACCUMULATING
    detector = ZoneDetector(db_path=db_path)
    detector.detect(sid5)
    results = read_zone_diagnostics(db_path, sid5)
    zone = gbp_zone(results)
    assert zone["state"] == "ACCUMULATING"


def test_leaking_after_early_extreme_opposite_direction(db_path: Path) -> None:
    """Deux snapshots dans l'extrême, direction opposée → LEAKING."""
    sid1 = insert_bar(db_path, bar_time=0, force_gbp=50.0)
    sid2 = insert_bar(db_path, bar_time=1, force_gbp=50.0)
    sid3 = insert_bar(db_path, bar_time=2, force_gbp=50.0)
    sid4 = insert_bar(db_path, bar_time=3, force_gbp=75.0)  # EARLY_EXTREME (UP)
    ZoneDetector(db_path=db_path).detect(sid4)

    sid5 = insert_bar(db_path, bar_time=4, force_gbp=25.0)  # direction opposée → LEAKING
    detector = ZoneDetector(db_path=db_path)
    detector.detect(sid5)
    results = read_zone_diagnostics(db_path, sid5)
    zone = gbp_zone(results)
    assert zone["state"] == "LEAKING"


def test_bars_in_extreme_increments(db_path: Path) -> None:
    """bars_in_extreme s'incrémente tant qu'on reste dans l'extrême."""
    for i in range(3):
        sid = insert_bar(db_path, bar_time=i, force_gbp=75.0)
        ZoneDetector(db_path=db_path).detect(sid)

    results = read_zone_diagnostics(db_path, sid)
    zone = gbp_zone(results)
    assert int(zone["bars_in_extreme"]) >= 3


def test_tension_score_non_zero_in_extreme(db_path: Path) -> None:
    """tension_score > 0 quand on est dans l'extrême."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 80.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert float(zone["tension_score"]) > 0


def test_tension_score_zero_in_neutral(db_path: Path) -> None:
    """tension_score = 0 quand on est en zone neutre."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert float(zone["tension_score"]) == 0.0


def test_persists_one_row_per_currency(db_path: Path) -> None:
    """Une ligne par devise dans zone_diagnostics."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    assert len(results) == len(DEVISES)
    assert {r["currency"] for r in results} == set(DEVISES)


def test_missing_snapshot_raises(db_path: Path) -> None:
    """Snapshot inexistant → ZoneDetectorError."""
    detector = ZoneDetector(db_path=db_path)
    with pytest.raises(ZoneDetectorError):
        detector.detect("does-not-exist")


def test_idempotent_insert(db_path: Path) -> None:
    """INSERT OR REPLACE : re-détecter le même snapshot ne crée pas de doublon."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 75.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    detector.detect(snapshot_id)  # second call

    conn = get_connection(db_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM zone_diagnostics WHERE forces_snapshot_ref = ?",
            (snapshot_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == len(DEVISES)  # pas de doublon


def test_z_extreme_dir_up_when_positive_z(db_path: Path) -> None:
    """z_current > 0 → z_extreme_dir = UP."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 80.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert zone["z_extreme_dir"] == "UP"


def test_z_extreme_dir_down_when_negative_z(db_path: Path) -> None:
    """z_current < 0 → z_extreme_dir = DOWN."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 20.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert zone["z_extreme_dir"] == "DOWN"


def test_zone_level_equals_abs_z(db_path: Path) -> None:
    """zone_level = |z_current|."""
    snapshot_id = insert_series(db_path, [50.0, 50.0, 80.0])
    detector = ZoneDetector(db_path=db_path)
    detector.detect(snapshot_id)
    results = read_zone_diagnostics(db_path, snapshot_id)
    zone = gbp_zone(results)
    assert float(zone["zone_level"]) == pytest.approx(abs(float(zone["z_current"])), abs=0.01)
