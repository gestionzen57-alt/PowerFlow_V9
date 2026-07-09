"""Tests — GRAMMAR_PULLBACK conditions réelles (promu ACTIVE 2026-07-10)."""
from __future__ import annotations
from core.v9.principle_engine import load_principles_from_yaml

GRAMMAR_PULLBACK_ID = "GRAMMAR_PULLBACK"

def _record():
    for p in load_principles_from_yaml():
        if p.principle_id == GRAMMAR_PULLBACK_ID:
            return p
    raise AssertionError(f"{GRAMMAR_PULLBACK_ID} absent du catalogue YAML")

def test_grammar_pullback_yaml_has_conditions():
    p = _record()
    assert p.kind == "grammar"
    assert len(p.conditions) >= 1
    fields = {c["field"] for c in p.conditions}
    assert "bascule_detectee" in fields or "qualification" in fields

def test_grammar_pullback_is_active():
    p = _record()
    assert p.v9_status == "ACTIVE"
