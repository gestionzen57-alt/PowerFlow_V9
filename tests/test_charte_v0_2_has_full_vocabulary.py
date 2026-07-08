"""Tests unitaires — CHARTE_COGNITIVE_V9.md v0.2 (Phase 9.8 Phase B, livrable B1).

Verrouillage structurel du réalignement CHARTE/DOCTRINE (voir
docs/audit/AUDIT_DOCTRINE_REPORT.md frictions F3/F4) : la CHARTE doit porter le
vocabulaire complet utilisé par DOCTRINE.md et le code, et documenter
explicitement la distinction chaîne perceptuelle amont / chaîne opérationnelle
aval qui existait de facto dans le code sans jamais être écrite.
"""

from __future__ import annotations

from pathlib import Path

CHARTE_PATH = Path(__file__).resolve().parent.parent / "docs" / "doctrine" / "CHARTE_COGNITIVE_V9.md"

NEW_VOCABULARY_TERMS = [
    "exploitabilité",
    "principe",
    "signal",
    "décision",
    "arbiter",
    "risk_manager",
    "paper_trade",
    "heartbeat",
]


def _charte_text() -> str:
    return CHARTE_PATH.read_text(encoding="utf-8")


def test_charte_file_exists():
    assert CHARTE_PATH.exists()


def test_charte_version_is_0_2_dated_20260708():
    text = _charte_text()
    assert "Version de chantier : 0.2" in text
    assert "Date : 2026-07-08" in text


def test_charte_vocabulary_has_8_new_terms():
    text = _charte_text().lower()
    for term in NEW_VOCABULARY_TERMS:
        assert f"- {term}" in text, f"terme manquant dans le vocabulaire obligatoire : {term!r}"


def test_charte_distinguishes_amont_and_aval_chains():
    text = _charte_text()
    assert "chaîne perceptuelle amont" in text.lower()
    assert "chaîne opérationnelle aval" in text.lower()


def test_charte_chain_totals_10_layers_6_amont_4_aval():
    text = _charte_text()
    assert "10 couches" in text
    assert "immuable, 6 couches" in text
    assert "évolutive, 4 couches" in text


def test_charte_amont_chain_ends_on_regime_not_execution():
    text = _charte_text()
    amont_section = text.split("### Chaîne perceptuelle amont")[1].split("### Chaîne opérationnelle aval")[0]
    assert "6. Régime" in amont_section
    assert "6. Exécution éventuelle" not in amont_section
