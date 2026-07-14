"""Tests — catalogue YAML 27 principes, 25 ACTIVE (2026-07-10, +SIGNAL_OPEN SHADOW).
Mise a jour 2026-07-14 : +1 ADAPTIVE_VOL_GATE SHADOW (P3-CONSUME Hermes) = 27."""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import load_principles_from_yaml

def test_yaml_loads_27_unique_ids():
    """27 YAMLs : 25 ACTIVE + 2 SHADOW (SIGNAL_OPEN CEO 2026-07-10
    + ADAPTIVE_VOL_GATE Hermes 2026-07-14 P3-CONSUME)."""
    principles = load_principles_from_yaml()
    ids = [p.principle_id for p in principles]
    assert len(set(ids)) == 27, f"Attendu 27 IDs uniques, obtenu {len(set(ids))}"
    assert "ADAPTIVE_VOL_GATE" in set(ids)

def test_principle_active_ids_count_is_25():
    assert len(PRINCIPLE_ACTIVE_IDS) == 25, (
        f"Attendu 25 ACTIVE (9 node_rule + 16 grammar), "
        f"obtenu {len(PRINCIPLE_ACTIVE_IDS)}"
    )

def test_all_active_ids_exist_in_yaml():
    principles = load_principles_from_yaml()
    yaml_ids = {p.principle_id for p in principles}
    for aid in PRINCIPLE_ACTIVE_IDS:
        assert aid in yaml_ids, f"{aid} dans ACTIVE mais absent du YAML"
