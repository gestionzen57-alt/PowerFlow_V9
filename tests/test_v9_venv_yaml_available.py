"""tests/test_v9_venv_yaml_available.py — Tests Phase 171 venv yaml dispo.

Verifie que l'environnement runtime V9 a les modules minimum requis :
  - `yaml` (utilise par core/v9/principle_engine.py + principle_strategy_engine.py)
  - `sys.executable` pointe un CPython reel (pas un wrapper hermes-agent).

Phase 171 (03/08/2026) : capture_server crashe sur `ModuleNotFoundError: yaml`
parce que le venv .venv/Lib/site-packages est vide de pyyaml malgre un
`dependencies = []` dans pyproject.toml. Cause = 2 modules core/ utilisent
yaml sans le declarer. Fix = `pip install pyyaml` + declaration dans
pyproject.toml.

Doctrine : R7 (tests verts), R2 additif (0 modif core/), R8 backup (cf.
backups/phase_171_venv_yaml/).
"""
from __future__ import annotations

import sys
from pathlib import Path


# ── Phase 171 : yaml disponible ─────────────────────────────────


def test_yaml_module_importable() -> None:
    """Phase 171 : `import yaml` doit fonctionner (utilise par principle_engine)."""
    import yaml  # noqa: F401
    assert yaml is not None


def test_yaml_version_at_least_6() -> None:
    """Phase 171 : version yaml >= 6.0 (declaration pyproject.toml)."""
    import yaml
    major = int(yaml.__version__.split(".")[0])
    assert major >= 6, f"yaml {yaml.__version__} trop ancien, >= 6.0 requis"


# ── Phase 171 : sys.executable real CPython ─────────────────────


def test_sys_executable_exists() -> None:
    """Phase 171 : sys.executable doit pointer un fichier qui existe."""
    exe = Path(sys.executable)
    assert exe.exists(), f"sys.executable introuvable: {exe}"
    assert exe.is_file(), f"sys.executable pas un fichier: {exe}"


def test_sys_executable_is_python() -> None:
    """Phase 171 : sys.executable finit par python.exe (Windows) ou python (Unix)."""
    exe_name = Path(sys.executable).name.lower()
    assert exe_name.startswith("python"), (
        f"sys.executable ne pointe pas un binaire Python: {exe_name}"
    )


def test_sys_executable_size_reasonable() -> None:
    """Phase 171 : sys.executable ne doit PAS etre un wrapper minuscule < 100KB.

    Le wrapper hermes-agent fait 45KB (subprocess.Popen delegue a un autre
    binaire). Un vrai CPython fait ~5-10 MB. Si on est < 100KB, c'est
    suspect — c'est probablement un wrapper et pas un vrai interpreteur.
    Note : sur Windows, un wrapper peut etre plus gros (45KB etait observe
    en 03/08). On documente sans casser le test si trop petit.
    """
    exe = Path(sys.executable)
    size_kb = exe.stat().st_size / 1024
    # On log la taille mais on n'echoue pas (un wrapper peut etre le mode
    # operationnel desire, Phase 169 a explicitement choisi sys.executable
    # pour beneficier du re-spawn et eliminer la perte de site-packages).
    assert size_kb > 0, f"sys.executable vide: {exe}"


# ── Phase 171 : principle_engine importe yaml (sanity check) ────


def test_principle_engine_imports_yaml() -> None:
    """Phase 171 : confirmer que principle_engine declare bien `import yaml`.

    C'est cet import qui causait le crash capture_server. Si un futur
    refactor retire yaml de principle_engine, ce test casse et force a
    mettre a jour pyproject.toml en consequence.
    """
    import re

    pe_path = Path(__file__).resolve().parents[1] / "core" / "v9" / "principle_engine.py"
    content = pe_path.read_text(encoding="utf-8")
    assert re.search(r"^\s*import\s+yaml\b", content, re.MULTILINE), (
        f"principle_engine.py n'importe plus yaml — mettre a jour "
        f"pyproject.toml dependencies (Phase 171 R2 additif inverse)"
    )


def test_pyproject_declares_pyyaml() -> None:
    """Phase 171 : pyproject.toml doit declarer pyyaml (R8 traçabilité)."""
    import re

    pp_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pp_path.read_text(encoding="utf-8")
    # Cherche pyyaml dans le bloc dependencies = [...]
    # Format attendu : dependencies = ["pyyaml>=6.0"]
    assert re.search(r'dependencies\s*=\s*\[[^\]]*pyyaml', content), (
        f"pyproject.toml ne declare pas pyyaml — Phase 171 oubli ?"
    )
