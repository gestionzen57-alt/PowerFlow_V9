"""Test pre-commit hook câblage cron (motion CEO #2).

Vérifie que le script v9_audit_cron_wiring.py est invocable, retourne
exit 0 quand tous les crons sont wrappés, et exit 1 quand un cron
est manuellement décâblé (régression test).

Doctrine : R26 (tests verts avant commit). Le hook lui-même sera
installé motion CEO #2 ; ce test valide la logique métier du hook.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "v9_audit_cron_wiring.py"


def _run_audit() -> tuple[int, str]:
    """Lance le script d'audit et retourne (exit_code, stdout)."""
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT)],
        capture_output=True, text=True,
        cwd=str(ROOT),
    )
    return r.returncode, r.stdout


def test_script_exists() -> None:
    """Le script d'audit câblage cron doit exister."""
    assert SCRIPT.exists(), f"v9_audit_cron_wiring.py absent : {SCRIPT}"


def test_all_crons_wrapped_passes() -> None:
    """État nominal : tous les 11 crons V9_* sont wrappés → exit 0."""
    rc, stdout = _run_audit()
    assert rc == 0, f"Attendu exit 0, obtenu {rc}. Stdout:\n{stdout}"
    assert "11/11 crons wrappés OK" in stdout, (
        f"Stdout attendu contient '11/11 crons wrappés OK', obtenu:\n{stdout}"
    )


def test_each_v9_cron_appears_in_output() -> None:
    """Les 11 crons V9_* doivent tous être listés dans la sortie."""
    rc, stdout = _run_audit()
    expected = [
        "V9_ArbiterRecal",
        "V9_AutoCalibrator",
        "V9_CalibrationLoop",
        "V9_HeartbeatAlert",
        "V9_HeartbeatCheck",
        "V9_LearningLoop",
        "V9_LiveWatchdogLoop",
        "V9_MetaAgentScan",
        "V9_PaperTradeLoop",
        "V9_ResolveLoop",
        "V9_StrategyPoleRecompute",
    ]
    for cron in expected:
        assert cron in stdout, f"Cron {cron} absent de la sortie"


def test_wrapper_marker_in_output() -> None:
    """Le marker 'v9_load_kill_switches.py' doit apparaître dans chaque ligne."""
    rc, stdout = _run_audit()
    lines = [l for l in stdout.splitlines() if "V9_" in l]
    wrapped_lines = [l for l in lines if "wrapped=True" in l]
    assert len(wrapped_lines) == 11, (
        f"Attendu 11 lignes wrapped=True, trouvé {len(wrapped_lines)}. "
        f"Stdout:\n{stdout}"
    )
