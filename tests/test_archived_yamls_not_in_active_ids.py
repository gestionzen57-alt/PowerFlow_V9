"""Tests de non-régression — archivage GRAMMAR_GRAVITE/GRAMMAR_INVERSION
(Phase 9.8 Phase B, livrable B5).

Classe C (archiver) — docs/audit/AUDIT_DOCTRINE_REPORT.md §5.2 : aucune donnée
source V9 équivalente confirmée. Déplacés vers
core/v9/principles/_archive/, retirés du chargement actif.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.config import PRINCIPLE_ACTIVE_IDS, PRINCIPLES_DIR
from core.v9.principle_engine import load_principles_from_yaml

ARCHIVED_IDS = ["GRAMMAR_GRAVITE", "GRAMMAR_INVERSION"]
ARCHIVE_DIR = PRINCIPLES_DIR / "_archive"


def test_archived_ids_never_in_active_ids():
    for archived_id in ARCHIVED_IDS:
        assert archived_id not in PRINCIPLE_ACTIVE_IDS, (
            f"{archived_id} est archivé (classe C) — il ne doit jamais figurer "
            f"dans PRINCIPLE_ACTIVE_IDS"
        )


def test_archived_ids_absent_from_active_catalogue():
    ids = {p.principle_id for p in load_principles_from_yaml()}
    for archived_id in ARCHIVED_IDS:
        assert archived_id not in ids, (
            f"{archived_id} apparaît encore dans le catalogue actif — "
            f"load_principles_from_yaml() ne doit pas parcourir _archive/"
        )


def test_archived_yaml_files_exist_on_disk():
    """L'archivage n'est pas une suppression (CHARTE Règle 3) : les fichiers
    restent versionnés et lisibles dans _archive/."""
    for archived_id in ARCHIVED_IDS:
        path = ARCHIVE_DIR / f"{archived_id}.yaml"
        assert path.exists(), f"{path} devrait exister (archivage, pas suppression)"


def test_archive_manifest_documents_both_entries():
    manifest = ARCHIVE_DIR / "ARCHIVE_MANIFEST.md"
    assert manifest.exists()
    text = manifest.read_text(encoding="utf-8")
    for archived_id in ARCHIVED_IDS:
        assert archived_id in text


def test_catalogue_shrinks_from_27_to_25():
    principles = load_principles_from_yaml()
    assert len(principles) == 25
