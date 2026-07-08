"""Tests unitaires — DOCTRINE.md, table de synthèse (Phase 9.8 Phase B, livrable B2).

Verrouillage structurel : la table des « 30 règles immuables » doit toujours
compter exactement 30 lignes numérotées, et les 4 règles révisées (R11, R20',
R25', R27) doivent porter leur nouvelle formulation — voir
docs/audit/AUDIT_DOCTRINE_REPORT.md (frictions R20/R25/R27 §3.1, F1/F2 §3.2).
"""

from __future__ import annotations

import re
from pathlib import Path

DOCTRINE_PATH = Path(__file__).resolve().parent.parent / "docs" / "DOCTRINE.md"

RULE_ROW_RE = re.compile(r"^\|\s*\*{0,2}(\d+)'?\*{0,2}\s*\|", re.MULTILINE)


def _doctrine_text() -> str:
    return DOCTRINE_PATH.read_text(encoding="utf-8")


def test_doctrine_file_exists():
    assert DOCTRINE_PATH.exists()


def test_doctrine_table_has_exactly_30_numbered_rules():
    text = _doctrine_text()
    numbers = [int(m.group(1)) for m in RULE_ROW_RE.finditer(text)]
    assert numbers == list(range(1, 31)), f"numérotation attendue 1..30, reçu: {numbers}"


def test_rule_20_prime_replaces_calibration_first():
    text = _doctrine_text()
    assert "20'" in text
    assert "Lecture-first" in text
    assert "Calibration-first" in text  # référence à la règle remplacée, pour traçabilité


def test_rule_25_prime_replaces_hit_rate_gate():
    text = _doctrine_text()
    assert "25'" in text
    assert "Vocabulaire descriptif" in text
    assert "hit_rate >= 60%" not in text.split("25'")[0].split("24 |")[-1]


def test_rule_27_no_longer_auto_deletes_dormant_fields():
    text = _doctrine_text()
    rule_27_row = [line for line in text.splitlines() if line.startswith("| **27**")]
    assert rule_27_row, "ligne Règle 27 introuvable"
    assert "supprimé de la chaîne" not in rule_27_row[0]
    assert "suppression automatique" in rule_27_row[0]


def test_rule_11_documents_9_plus_1_architecture():
    text = _doctrine_text()
    rule_11_row = [line for line in text.splitlines() if line.startswith("| 11 |")]
    assert rule_11_row, "ligne Règle 11 introuvable"
    assert "9+1" in rule_11_row[0]
    assert "node_rule" in rule_11_row[0]
    assert "grammar" in rule_11_row[0]


def test_doctrine_references_audit_report_for_revised_rules():
    text = _doctrine_text()
    assert "docs/audit/AUDIT_DOCTRINE_REPORT.md" in text
