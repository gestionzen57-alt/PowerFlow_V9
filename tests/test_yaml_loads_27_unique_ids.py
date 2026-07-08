"""Test unitaire — conformité PRINCIPLE_ACTIVE_IDS vs catalogue YAML (Phase 9.10, 11 ACTIVE)."""

from __future__ import annotations

from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import load_principles_from_yaml


def test_principle_active_ids_are_unique():
    assert len(PRINCIPLE_ACTIVE_IDS) == len(set(PRINCIPLE_ACTIVE_IDS))


def test_principle_active_ids_count_is_11():
    """2026-07-08 : promotion GRAMMAR_CONTEXTE → 11 ACTIVE."""
    assert len(PRINCIPLE_ACTIVE_IDS) == 11


def test_yaml_catalogue_loads_25_unique_ids():
    catalogue_ids = {p.principle_id for p in load_principles_from_yaml()}
    assert len(catalogue_ids) == 25


def test_principle_active_ids_are_subset_of_yaml_catalogue():
    catalogue_ids = {p.principle_id for p in load_principles_from_yaml()}
    assert set(PRINCIPLE_ACTIVE_IDS).issubset(catalogue_ids)


def test_no_active_id_is_orphan_of_a_yaml_file():
    catalogue_ids = {p.principle_id for p in load_principles_from_yaml()}
    orphans = set(PRINCIPLE_ACTIVE_IDS) - catalogue_ids
    assert orphans == set()
