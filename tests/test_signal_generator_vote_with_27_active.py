"""Test unitaire — le vote SignalGenerator reste correct avec un grand nombre
de principes synthétiques triggered=1 (Phase C3 doctrine realign). Verrouille
le fait qu'il n'existe aucun dénominateur hardcodé (N=10) : le vote est une
pluralité sur les seules évaluations réellement triggered=1, quelle que soit
la taille de PRINCIPLE_ACTIVE_IDS (reste à 10 en config — promotion C1
rejetée en Phase E, cf. DECISIONS_LOG). Les IDs synthétiques ci-dessous
(P0..P26) sont indépendants de PRINCIPLE_ACTIVE_IDS : le test vérifie le
comportement du vote, pas la config réelle."""

from __future__ import annotations

from pathlib import Path

from core.v9.signal_generator import SignalGenerator
from tests.test_signal_generator import build_chain, db_path  # noqa: F401 (fixture)


def test_vote_majority_with_27_synthetic_active_principles(db_path: Path):
    # 16 votes haussiere, 11 votes baissiere -> majorité haussiere, peu
    # importe que ce total (27) corresponde ou non à len(PRINCIPLE_ACTIVE_IDS).
    triggered = [
        {"principle_id": f"P{i}", "direction": "haussiere", "confidence": 70}
        for i in range(16)
    ] + [
        {"principle_id": f"P{i}", "direction": "baissiere", "confidence": 60}
        for i in range(16, 27)
    ]
    snapshot_id = build_chain(db_path, triggered_principles=triggered)

    generator = SignalGenerator(db_path=db_path)
    signal = generator.generate(snapshot_id)

    assert signal["direction"] == "haussiere"
    assert signal["raison_absence"] is None
    assert len(signal["principes_source"]) == 27


def test_vote_tie_among_many_active_principles_returns_neutre(db_path: Path):
    # Egalité stricte 5/5 (peu importe le nombre total d'ACTIVE en config)
    # -> "neutre", cohérent avec le comportement pré-existant (pas de
    # dénominateur à ajuster pour 27 ACTIVE).
    triggered = [
        {"principle_id": f"A{i}", "direction": "haussiere", "confidence": 70}
        for i in range(5)
    ] + [
        {"principle_id": f"B{i}", "direction": "baissiere", "confidence": 70}
        for i in range(5)
    ]
    snapshot_id = build_chain(db_path, triggered_principles=triggered)

    generator = SignalGenerator(db_path=db_path)
    signal = generator.generate(snapshot_id)

    assert signal["direction"] == "neutre"
