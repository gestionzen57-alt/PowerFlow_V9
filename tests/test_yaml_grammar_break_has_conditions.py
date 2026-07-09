"""Tests — GRAMMAR_BREAK conditions réelles (promu ACTIVE 2026-07-10)."""
from __future__ import annotations
from core.v9.principle_engine import load_principles_from_yaml

GRAMMAR_BREAK_ID = "GRAMMAR_BREAK"

def _record():
    for p in load_principles_from_yaml():
        if p.principle_id == GRAMMAR_BREAK_ID:
            return p
    raise AssertionError(f"{GRAMMAR_BREAK_ID} absent du catalogue YAML")

def test_grammar_break_yaml_has_conditions():
    p = _record()
    assert p.kind == "grammar"
    assert len(p.conditions) >= 1
    fields = {c["field"] for c in p.conditions}
    assert "coalition_mtf_score" in fields or "risk_sentiment" in fields

def test_grammar_break_is_active():
    p = _record()
    assert p.v9_status == "ACTIVE"
