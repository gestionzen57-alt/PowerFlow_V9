"""Tests REGISTRY — Sprint V9 2026-07-07."""
from __future__ import annotations

import pytest

from agents.REGISTRY import REGISTRY, get, list_agents, list_cognitifs


def test_registry_has_five_cognitive_agents():
    cognitifs = list_cognitifs()
    assert len(cognitifs) == 5
    assert "force_reader" in cognitifs
    assert "scene_builder" in cognitifs
    assert "behavior_analyst" in cognitifs
    assert "gatekeeper" in cognitifs
    assert "decision_maker" in cognitifs


def test_registry_has_supervisor_and_reviewer():
    agents = list_agents()
    assert "supervisor" in agents
    assert "reviewer" in agents


def test_registry_no_llm_in_loop():
    """Règle 18 : aucun appel LLM dans la boucle chaude."""
    for name, meta in REGISTRY.items():
        assert "llm" not in meta.get("module", "").lower()
        # Vérifie que 'model' ou 'openai' ou 'qwen' ne sont pas import
        mod = meta.get("module", "").lower()
        assert "openai" not in mod
        assert "qwen" not in mod
        assert "deepseek" not in mod


def test_registry_no_federation_rpc():
    """Anti-fédération V8 : pas de RPC/HTTP dans les modules agents."""
    for name, meta in REGISTRY.items():
        mod = meta.get("module", "")
        assert "rpc" not in mod.lower()
        assert "federation" not in mod.lower()
        assert "gateway" not in mod.lower()


def test_get_existing():
    assert get("force_reader") is not None
    assert get("force_reader")["couche"] == 2


def test_get_missing_returns_none():
    assert get("inexistant") is None


def test_list_agents_meta():
    meta = list_agents("meta")
    assert "supervisor" in meta
    assert "reviewer" in meta


def test_each_cognitive_has_io_schema():
    for name in list_cognitifs():
        meta = get(name)
        assert "input_schema" in meta, f"{name} manque input_schema"
        assert "output_schema" in meta, f"{name} manque output_schema"
