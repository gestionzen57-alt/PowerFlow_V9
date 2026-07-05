"""Tests unitaires — core.v9.forces_reader.ForcesReader."""

from __future__ import annotations

from core.v9.forces_reader import ForcesReader, ForcesReaderError
from core.v9.stale_gate import StaleGate

BASE_TIME = 1_751_700_000  # epoch secondes arbitraire


def make_raw(
    *,
    symbol: str = "GBPUSD",
    timeframe: str = "M5",
    bar_time: int = BASE_TIME,
    force_gbp: float = 50.0,
    force_usd: float = 40.0,
    force_eur: float = 45.0,
    force_jpy: float = 30.0,
    force_cad: float = 35.0,
    force_chf: float = 42.0,
    force_aud: float = 38.0,
    force_nzd: float = 33.0,
    timestamp: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "snapshot_id": f"v9-test-{bar_time}",
        "timestamp": timestamp or _iso(bar_time),
        "source": "MT4_SDI",
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_time": bar_time,
        "bar_close_time": bar_time + 300,
        "server_time": bar_time,
        "capture_time": bar_time,
        "shift": 1,
        "is_closed_bar": True,
        "open": 1.2500, "high": 1.2550, "low": 1.2480, "close": 1.2530,
        "tick_volume": 120,
        "spread_points": 10, "spread_price": 0.0001,
        "bid": 1.2529, "ask": 1.2531, "mid": 1.2530,
        "force_usd": force_usd,
        "force_gbp": force_gbp,
        "force_eur": force_eur,
        "force_jpy": force_jpy,
        "force_cad": force_cad,
        "force_chf": force_chf,
        "force_aud": force_aud,
        "force_nzd": force_nzd,
    }


def _iso(epoch_s: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def _fresh_gate() -> StaleGate:
    return StaleGate({"M5": 35_000, "M1": 5_000})


def test_transform_produces_row_matching_format_forces():
    reader = ForcesReader(stale_gate=_fresh_gate())
    now_ms = BASE_TIME * 1000 + 100

    result = reader.transform(make_raw(), now_ms=now_ms)

    assert "row" in result and "format_forces_entry" in result
    row = result["row"]
    assert row["symbol"] == "GBPUSD"
    assert row["timeframe"] == "M5"
    assert row["force_gbp"] == 50.0
    assert row["schema_version"] == "1.0"

    entry = result["format_forces_entry"]
    assert entry["devise"] == "GBP"
    assert entry["timeframe"] == "M5"
    assert set(entry["croisement"].keys()) == {"detecte", "devise_partenaire", "direction"}


def test_first_snapshot_no_previous_state():
    reader = ForcesReader(stale_gate=_fresh_gate())
    now_ms = BASE_TIME * 1000 + 100

    result = reader.transform(make_raw(), now_ms=now_ms)
    row = result["row"]

    assert row["direction"] == "neutre"
    assert row["vitesse"] == 0.0
    assert row["croisement_detecte"] is False
    assert row["recroisement_detecte"] is False
    assert row["rejet_repulsion_detecte"] is False


def test_direction_haussiere_then_baissiere_then_neutre():
    reader = ForcesReader(stale_gate=_fresh_gate())
    now_ms = BASE_TIME * 1000

    r1 = reader.transform(make_raw(bar_time=BASE_TIME, force_gbp=50.0), now_ms=now_ms)
    assert r1["row"]["direction"] == "neutre"  # premier snapshot

    r2 = reader.transform(make_raw(bar_time=BASE_TIME + 300, force_gbp=55.0), now_ms=now_ms + 300_000)
    assert r2["row"]["direction"] == "haussiere"

    r3 = reader.transform(make_raw(bar_time=BASE_TIME + 600, force_gbp=48.0), now_ms=now_ms + 600_000)
    assert r3["row"]["direction"] == "baissiere"

    r4 = reader.transform(make_raw(bar_time=BASE_TIME + 900, force_gbp=48.0), now_ms=now_ms + 900_000)
    assert r4["row"]["direction"] == "neutre"


def test_vitesse_calculation():
    reader = ForcesReader(stale_gate=_fresh_gate())
    now_ms = BASE_TIME * 1000

    reader.transform(make_raw(bar_time=BASE_TIME, force_gbp=50.0), now_ms=now_ms)
    result = reader.transform(
        make_raw(bar_time=BASE_TIME + 300, force_gbp=56.0), now_ms=now_ms + 300_000
    )

    # delta_force=6.0 sur delta_time=300s => 0.02 force/s
    assert abs(result["row"]["vitesse"] - 0.02) < 1e-9


def test_croisement_detection_between_base_and_quote():
    reader = ForcesReader(stale_gate=_fresh_gate())
    now_ms = BASE_TIME * 1000

    # t0 : GBP (40) < USD (50) -> pas de croisement possible (premier snapshot)
    reader.transform(
        make_raw(bar_time=BASE_TIME, force_gbp=40.0, force_usd=50.0), now_ms=now_ms
    )
    # t1 : GBP (60) > USD (50) -> ordre relatif inverse => croisement détecté
    result = reader.transform(
        make_raw(bar_time=BASE_TIME + 300, force_gbp=60.0, force_usd=50.0),
        now_ms=now_ms + 300_000,
    )

    row = result["row"]
    assert row["croisement_detecte"] is True
    assert row["croisement_partenaire"] == "USD"
    assert row["croisement_direction"] == "haussiere"


def test_stale_gate_applied_but_row_still_returned():
    reader = ForcesReader(stale_gate=_fresh_gate())
    # timestamp vieux de 60s, seuil M5 = 35s => stale
    old_time = BASE_TIME
    now_ms = (BASE_TIME + 60) * 1000

    result = reader.transform(make_raw(bar_time=old_time), now_ms=now_ms)
    row = result["row"]

    assert row["stale"] is True
    assert row["age_ms"] == 60_000
    assert row["stale_threshold_ms"] == 35_000
    # La ligne est complète malgré stale=True : jamais bloquée/supprimée.
    assert row["force_gbp"] == 50.0


def test_unknown_timeframe_rejected():
    reader = ForcesReader(stale_gate=_fresh_gate())
    raw = make_raw(timeframe="M99")
    try:
        reader.transform(raw)
        assert False, "devait lever ForcesReaderError"
    except ForcesReaderError:
        pass


def test_missing_required_field_rejected():
    reader = ForcesReader(stale_gate=_fresh_gate())
    raw = make_raw()
    del raw["force_usd"]
    try:
        reader.transform(raw)
        assert False, "devait lever ForcesReaderError"
    except ForcesReaderError:
        pass
