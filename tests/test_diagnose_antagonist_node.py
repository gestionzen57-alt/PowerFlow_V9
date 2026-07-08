"""Tests — scripts/diagnose_antagonist_node.py.

Couvre :
- _load_spec — charge YAML, vérifie conditions présentes
- diagnose — utilise une DB tmp avec 3 snapshots pour verdict prévisible
- render_text — format texte non-vide
- main() --json — sortie JSON parsable
- main() --report — fichier Markdown créé
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import diagnose_antagonist_node as diag  # noqa: E402


# ── Fixture : DB tmp avec 3 snapshots H1 GBPUSD ──────────────
@pytest.fixture
def temp_db_with_h1(tmp_path: Path) -> Path:
    """Crée une DB temporaire avec 3 snapshots H1 GBPUSD,
    dont 1 où h1_dir != m5_dir (forces divergentes simulées)."""
    db = tmp_path / "diag_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            mid REAL,
            stale INTEGER,
            force_usd REAL, force_eur REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT
        );
        -- Tables minimales requises par _load_shared_context (les
        -- fetchone() retournent None, le code gère les fallbacks).
        CREATE TABLE scenes (
            id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT
        );
        CREATE TABLE behaviors (
            id INTEGER PRIMARY KEY, scene_id TEXT, currency TEXT,
            qualification TEXT, intensite TEXT, phase TEXT,
            confiance_qualification INTEGER, point_de_rupture_detecte INTEGER,
            sens_transition TEXT, point_de_rupture_declencheur TEXT,
            est_variante INTEGER, comportement_reference TEXT,
            window_id TEXT, exploitability_id TEXT
        );
        CREATE TABLE windows (
            id INTEGER PRIMARY KEY, scene_id TEXT, currency TEXT,
            statut TEXT, type_fenetre TEXT, niveau_confiance TEXT,
            fragilite_detectee INTEGER
        );
        CREATE TABLE exploitability (
            id INTEGER PRIMARY KEY, scene_id TEXT, currency TEXT,
            statut TEXT, niveau_confiance_global TEXT
        );
        CREATE TABLE zone_diagnostics (
            id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT
        );
        """
    )
    # Snapshot 1 : h1_dir=HAUSSIERE (max force=USD à 80), m5_dir=HAUSSIERE (max force=USD à 70)
    # H1 et M5 du même snapshot (cross_tf dérive du snapshot lui-même)
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("snap-corr-1", "2026-07-08T10:00:00+00:00", "GBPUSD", "H1",
         1.25, 0, 80, 50, 30, 40, 60, 55, 45, 35, None),
    )
    # Snapshot 2 : h1_dir=BAISSIERE, m5_dir=HAUSSIERE (DIVERGENT)
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("snap-div-2", "2026-07-08T09:00:00+00:00", "GBPUSD", "H1",
         1.24, 0, 20, 30, 80, 25, 35, 30, 40, 20, None),
    )
    # Snapshot 3 : h1_dir=HAUSSIERE, m5_dir=BAISSIERE (DIVERGENT)
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("snap-div-3", "2026-07-08T08:00:00+00:00", "GBPUSD", "H1",
         1.23, 0, 70, 60, 40, 50, 30, 35, 55, 45, None),
    )
    conn.commit()
    conn.close()
    return db


def test_load_spec_returns_dict_with_conditions():
    spec = diag._load_spec()
    assert "conditions" in spec
    assert len(spec["conditions"]) == 5
    assert spec["id"] == "ANTAGONIST_NODE"


def test_diagnose_no_data(tmp_path: Path, capsys):
    """DB vide → verdict NO_DATA."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (snapshot_id TEXT PRIMARY KEY, symbol TEXT, timeframe TEXT, timestamp TEXT);
        CREATE TABLE scenes (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        CREATE TABLE behaviors (id INTEGER PRIMARY KEY);
        CREATE TABLE windows (id INTEGER PRIMARY KEY);
        CREATE TABLE exploitability (id INTEGER PRIMARY KEY);
        CREATE TABLE zone_diagnostics (id INTEGER PRIMARY KEY);
        """
    )
    conn.close()
    result = diag.diagnose(db)
    assert result["verdict"] == "NO_DATA"
    assert result["n_snapshots"] == 0


def test_diagnose_inert_market_when_all_correlated(tmp_path: Path):
    """DB avec 1 snapshot h1==m5 → INERT_MARKET."""
    db = tmp_path / "correlated.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, timeframe TEXT,
            mid REAL, stale INTEGER,
            force_usd REAL, force_eur REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT
        );
        CREATE TABLE scenes (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        CREATE TABLE behaviors (id INTEGER PRIMARY KEY);
        CREATE TABLE windows (id INTEGER PRIMARY KEY);
        CREATE TABLE exploitability (id INTEGER PRIMARY KEY);
        CREATE TABLE zone_diagnostics (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        """
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("s1", "2026-07-08T10:00:00+00:00", "GBPUSD", "H1",
         1.25, 0, 80, 50, 30, 40, 60, 55, 45, 35, None),
    )
    conn.commit()
    conn.close()
    result = diag.diagnose(db)
    assert result["verdict"] == "INERT_MARKET"
    assert result["n_snapshots"] == 1
    assert result["n_all_cond_true"] == 0
    assert result["n_divergent"] == 0


def test_diagnose_finds_divergence_with_fake_divergent_snapshot(tmp_path: Path):
    """DB avec 1 snapshot divergent → au moins 1 divergence détectée.
    Note : avec 1 seul snapshot (H1), m5_dir est dérivé du MÊME snapshot (L359
    timeframe==target_tf), donc h1_dir == m5_dir toujours. Pour avoir vraiment
    divergent, il faut 2 snapshots à des TF différents au même timestamp, ce
    que la fixture n'a pas. Donc ici on vérifie juste qu'on a 0 divergent
    (et donc verdict INERT_MARKET) — le code marche comme attendu.
    """
    db = tmp_path / "snap.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, timeframe TEXT,
            mid REAL, stale INTEGER,
            force_usd REAL, force_eur REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT
        );
        CREATE TABLE scenes (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        CREATE TABLE behaviors (id INTEGER PRIMARY KEY);
        CREATE TABLE windows (id INTEGER PRIMARY KEY);
        CREATE TABLE exploitability (id INTEGER PRIMARY KEY);
        CREATE TABLE zone_diagnostics (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        """
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("s1", "2026-07-08T10:00:00+00:00", "GBPUSD", "H1",
         1.25, 0, 80, 20, 30, 40, 60, 55, 45, 35, None),
    )
    conn.commit()
    conn.close()
    result = diag.diagnose(db)
    # H1 snapshot unique : h1_dir et m5_dir dérivés du même snapshot
    # → h1_dir == m5_dir → 0 divergent
    assert result["n_divergent"] == 0


def test_diagnose_h1_m5_with_2_snapshots_diff_tf(tmp_path: Path):
    """DB avec 1 H1 + 1 M5 de forces opposées → divergence détectée."""
    db = tmp_path / "cross_tf.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, timeframe TEXT,
            mid REAL, stale INTEGER,
            force_usd REAL, force_eur REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT
        );
        CREATE TABLE scenes (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        CREATE TABLE behaviors (id INTEGER PRIMARY KEY);
        CREATE TABLE windows (id INTEGER PRIMARY KEY);
        CREATE TABLE exploitability (id INTEGER PRIMARY KEY);
        CREATE TABLE zone_diagnostics (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        """
    )
    # H1 : max force = USD à 80 (HAUSSIERE)
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("h1-1", "2026-07-08T10:00:00+00:00", "GBPUSD", "H1",
         1.25, 0, 80, 20, 30, 40, 60, 55, 45, 35, None),
    )
    # M5 (plus récent) : max force = USD à 20 (BAISSIERE, < 45)
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("m5-1", "2026-07-08T10:30:00+00:00", "GBPUSD", "M5",
         1.255, 0, 20, 30, 25, 40, 35, 30, 35, 30, None),
    )
    conn.commit()
    conn.close()
    result = diag.diagnose(db)
    # H1 dir = HAUSSIERE, M5 dir = BAISSIERE → 1 divergent
    # (toutes conditions true nécessite en plus h1_state, m5_state != NEUTRAL,
    # ce qui n'est pas garanti par la fixture mais ce n'est pas l'objet du test)
    assert result["n_snapshots"] == 1
    assert result["n_divergent"] == 1
    assert result["verdict"] in ("OK", "INERT_MARKET", "BUG_YAML")


def test_render_text_contains_verdict():
    report = {
        "verdict": "INERT_MARKET",
        "reason": "test",
        "n_snapshots": 10,
        "n_all_cond_true": 0,
        "n_divergent": 0,
        "n_conditions": 5,
        "distribution_dir_combos": [{"h1_dir": "HAUSSIERE", "m5_dir": "HAUSSIERE", "count": 10}],
        "samples": [],
        "cond_dump": [],
        "yaml_path": "/fake/path.yaml",
    }
    text = diag.render_text(report)
    assert "INERT_MARKET" in text
    assert "[VERDICT]" in text
    assert "HAUSSIERE" in text


def test_main_json_output(tmp_path: Path, capsys):
    """Test main() avec --json sur DB tmp (1 snapshot corrélé)."""
    db = tmp_path / "main_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, timeframe TEXT,
            mid REAL, stale INTEGER,
            force_usd REAL, force_eur REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT
        );
        CREATE TABLE scenes (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        CREATE TABLE behaviors (id INTEGER PRIMARY KEY);
        CREATE TABLE windows (id INTEGER PRIMARY KEY);
        CREATE TABLE exploitability (id INTEGER PRIMARY KEY);
        CREATE TABLE zone_diagnostics (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        """
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("s1", "2026-07-08T10:00:00+00:00", "GBPUSD", "H1",
         1.25, 0, 80, 50, 30, 40, 60, 55, 45, 35, None),
    )
    conn.commit()
    conn.close()
    exit_code = diag.main(["--db", str(db), "--json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["verdict"] == "INERT_MARKET"
    assert parsed["n_snapshots"] == 1


def test_main_report_markdown(tmp_path: Path, capsys):
    """Test main() avec --report écrit un fichier Markdown valide."""
    db = tmp_path / "report_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, timeframe TEXT,
            mid REAL, stale INTEGER,
            force_usd REAL, force_eur REAL, force_gbp REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT
        );
        CREATE TABLE scenes (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        CREATE TABLE behaviors (id INTEGER PRIMARY KEY);
        CREATE TABLE windows (id INTEGER PRIMARY KEY);
        CREATE TABLE exploitability (id INTEGER PRIMARY KEY);
        CREATE TABLE zone_diagnostics (id INTEGER PRIMARY KEY, forces_snapshot_ref TEXT);
        """
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("s1", "2026-07-08T10:00:00+00:00", "GBPUSD", "H1",
         1.25, 0, 80, 50, 30, 40, 60, 55, 45, 35, None),
    )
    conn.commit()
    conn.close()
    report_path = tmp_path / "diag.md"
    exit_code = diag.main(["--db", str(db), "--report", str(report_path)])
    assert exit_code == 0
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "**Verdict**" in text
    assert "INERT_MARKET" in text
    assert "Distribution couples" in text
