"""Test unitaire — conformité PRINCIPLE_ACTIVE_IDS vs catalogue YAML (Phase C1 doctrine realign)."""

from __future__ import annotations

from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import load_principles_from_yaml


def test_principle_active_ids_are_unique():
    assert len(PRINCIPLE_ACTIVE_IDS) == len(set(PRINCIPLE_ACTIVE_IDS))


def test_principle_active_ids_count_is_27():
    assert len(PRINCIPLE_ACTIVE_IDS) == 27


def test_principle_active_ids_match_yaml_catalogue_exactly():
    catalogue_ids = {p.principle_id for p in load_principles_from_yaml()}
    assert set(PRINCIPLE_ACTIVE_IDS) == catalogue_ids


def test_no_active_id_is_orphan_of_a_yaml_file():
    catalogue_ids = {p.principle_id for p in load_principles_from_yaml()}
    orphans = set(PRINCIPLE_ACTIVE_IDS) - catalogue_ids
    assert orphans == set()
