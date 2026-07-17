"""Tests pour v9_re_resolve_trades — audit CEO papertrade realisme.

2026-07-17 motion CEO « ton papertrade est il realiste verifie tout si v est cohérent ».

L'audit a montré que 89% des paper_trades étaient des backtest artefacts
(pips fixes codés en dur). Le WR 90% est irréaliste.
Le forward-test réel via prix M5 + ExitSimulator donne WR ~23% (perte).
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "v9_re_resolve_trades.py"


def _run_re_resolve(extra_args: list[str] | None = None) -> dict:
    """Invoque le script v9_re_resolve_trades.py et retourne le dict final."""
    args = [sys.executable, str(SCRIPT)]
    if extra_args:
        args.extend(extra_args)
    else:
        args.append("--dry-run")
    p = subprocess.run(
        args, capture_output=True, text=True, timeout=120, cwd=str(ROOT),
    )
    # Trouve la ligne qui commence par '{' et finit par '}' (JSON complet)
    import json
    start_idx = p.stdout.rfind("{")
    if start_idx == -1:
        raise RuntimeError(f"no JSON in output: {p.stdout}")
    return json.loads(p.stdout[start_idx:])


def test_re_resolve_dry_run_returns_valid_structure() -> None:
    """Le dry-run doit retourner un dict avec les clés attendues."""
    r = _run_re_resolve(["--limit", "10", "--dry-run"])
    assert "n_total" in r
    assert "n_re_resolved" in r
    assert "n_changed" in r
    assert "wr_before" in r
    assert "wr_after" in r
    assert "n_artifact" in r
    assert r["dry_run"] is True


def test_re_resolve_artifact_count_is_zero() -> None:
    """Avec le fix epoch, 0 trade en mode ARTIFACT (tous ont prix M5)."""
    r = _run_re_resolve(["--limit", "100", "--dry-run"])
    assert r["n_artifact"] == 0, (
        f"Avec le fix epoch, on doit avoir 0 artifact. "
        f"Got: {r['n_artifact']}/{r['n_re_resolved']}"
    )


def test_re_resolve_changes_results() -> None:
    """Le re-resolve DOIT changer les résultats (sinon bug = pas de fix)."""
    r = _run_re_resolve(["--limit", "200", "--dry-run"])
    assert r["n_changed"] > 0, (
        f"Si n_changed=0, le résolveur ne fait rien (bug). "
        f"Got n_changed={r['n_changed']}/{r['n_re_resolved']}"
    )


def test_re_resolve_wr_realistic() -> None:
    """Le WR après re-resolve doit être PLUS BAS que 90% (backtest artefact).

    Le forward-test via prix M5 réels ne peut pas artificiellement
    être à 90% — c'est statistiquement impossible avec un edge < 30%.
    Si WR > 80% après re-resolve, c'est qu'on a un bug dans le résolveur.
    """
    r = _run_re_resolve(["--limit", "500", "--dry-run"])
    # On accepte une certaine marge (entre 20% et 80%) mais on alerte
    # si on a encore > 80% (suspect) ou < 5% (bug)
    wr_after = r["wr_after"]
    assert 5 <= wr_after <= 80, (
        f"WR after re-resolve suspect: {wr_after}%. "
        f"Si > 80%, le résolveur a un bug. Si < 5%, données M5 cassées."
    )


def test_re_resolve_backup_table_exists() -> None:
    """Le script doit créer une table de backup avant modification."""
    db_path = ROOT / "data" / "v9_forces.db"
    if not db_path.exists():
        pytest.skip("DB non disponible")
    # Backup doit exister après un run dry-run
    _run_re_resolve(["--limit", "5", "--dry-run"])
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='paper_trades_backup_20260717'"
        ).fetchone()
        assert row is not None, "Backup table non créée"
    finally:
        conn.close()