"""Test unitaire — latence SignalGenerator.generate() reste acceptable avec
27 principes ACTIVE (Phase C3 doctrine realign). Cible historique < 200ms/
snapshot (cf. principle_engine.py docstring _YAML_CACHE)."""

from __future__ import annotations

import time
from pathlib import Path

from core.v9.signal_generator import SignalGenerator
from tests.test_signal_generator import build_chain, db_path  # noqa: F401 (fixture)


def test_signal_generator_perf_acceptable(db_path: Path):
    triggered = [
        {"principle_id": f"P{i}", "direction": "haussiere", "confidence": 70}
        for i in range(27)
    ]
    snapshot_id = build_chain(db_path, triggered_principles=triggered)

    generator = SignalGenerator(db_path=db_path)
    start = time.perf_counter()
    generator.generate(snapshot_id)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200
