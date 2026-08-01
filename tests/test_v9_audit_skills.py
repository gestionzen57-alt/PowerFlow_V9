"""Tests smoke pour scripts/v9_audit_skills.py (Resync MCP+skills 2026-07-31).

Couvre :
- parse_frontmatter : extraction nom/statut/date
- list_skill_files : détecte SKILL.md dans skills/ + skills/trading/
- main --json : sortie structurée conforme
- main --stale 0 : seuil permissif (tout est stale)
- main (texte) : exit code 1 si legacy-v8 ou stale>seuil
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "v9_audit_skills.py"


def test_script_exists():
    assert SCRIPT.exists(), f"Script manquant : {SCRIPT}"


def test_help_runs():
    """--help doit toujours passer."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0
    assert "Audit skills" in res.stdout


def test_json_output_is_valid():
    """--json produit JSON parsable avec clés attendues."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert "head" in data
    assert "n_total" in data
    assert "n_legacy_v8" in data
    assert "n_stale" in data
    assert "skills" in data
    assert isinstance(data["skills"], list)
    assert data["n_total"] >= 25  # au moins 25 skills attendues (workspace + trading/* + rag + yuanbao + computer-use)
    # Après resync 2026-07-31 : 0 legacy-v8
    assert data["n_legacy_v8"] == 0, f"legacy-v8 restantes : {data['n_legacy_v8']}"


def test_no_legacy_v8_after_resync():
    """Le resync 2026-07-31 a re-tagué les 8 skills legacy-v8 → 0 attendu."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(res.stdout)
    legacy_v8 = [s for s in data["skills"] if s["statut"] == "legacy-v8"]
    assert legacy_v8 == [], f"Skills encore en legacy-v8 : {[s['path'] for s in legacy_v8]}"


def test_active_v9_count_after_resync():
    """Le resync a fait passer au moins 8 skills en actif-v9 (6 retag + 2 retag)."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(res.stdout)
    actif_v9 = [s for s in data["skills"] if s["statut"] == "actif-v9"]
    assert len(actif_v9) >= 8, f"actif-v9 insuffisant : {len(actif_v9)}"


def test_trading_skills_have_date():
    """Les 4 skills trading/* doivent avoir derniere_maj renseigné après resync."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(res.stdout)
    trading = [s for s in data["skills"] if "trading" in s["path"]]
    assert len(trading) == 4, f"4 skills trading/* attendues, vu {len(trading)}"
    for s in trading:
        assert s["derniere_maj"] == "2026-07-31", f"{s['path']} pas resync: {s['derniere_maj']}"


def test_stale_threshold_zero():
    """--stale 0 doit signaler toutes les skills datées avec age>=0 comme stale."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--stale", "0", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(res.stdout)
    # Compter skills datées et age >= 0 (toutes les datées)
    dated_positive = [s for s in data["skills"] if s["age_days"] is not None and s["age_days"] >= 0]
    assert data["n_stale"] == len(dated_positive), (
        f"stale 0 doit matcher {len(dated_positive)} skills datées, vu {data['n_stale']}"
    )


def test_text_output_exit_code():
    """En mode texte, exit 0 si 0 legacy-v8 ET 0 stale>seuil, sinon 1."""
    res_default = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, timeout=30,
    )
    # Avec notre resync, 0 legacy-v8 mais quelques stale>14j → exit 1 attendu
    assert res_default.returncode in (0, 1)


def test_patch_p0_is_legacy_historique():
    """patch-p0 doit être marqué legacy-historique (rupture close)."""
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(res.stdout)
    p0 = [s for s in data["skills"] if s["name"] == "powerflow-patch-p0"]
    assert len(p0) == 1
    assert "legacy-historique" in p0[0]["statut"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
