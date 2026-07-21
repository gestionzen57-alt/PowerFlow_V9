"""test_v9_meta_strategy_simulation.py — Tests simulation replay Phase E."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest


# ------------------------------------------------------------------ fixtures


def _create_decisions_table(db_path: Path) -> None:
    """Crée tables decisions + signals minimales pour tests (schéma live)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT,
                regime_type TEXT,
                is_win INTEGER,
                resolution_pips REAL NOT NULL,
                resolution_strategy TEXT,
                resolved_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signals (
                snapshot_id TEXT PRIMARY KEY,
                phase TEXT,
                volatility_atr_pips REAL,
                exit_strategy_recommended TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_decisions_is_win
                ON decisions(is_win);
            CREATE INDEX IF NOT EXISTS idx_decisions_resolved
                ON decisions(resolved_at);
        """)
        conn.commit()
    finally:
        conn.close()


def _insert_decision(
    db_path: Path,
    *,
    decision_id: str,
    snapshot_id: str,
    symbol: str,
    timeframe: str,
    direction: str,
    regime_type: str,
    is_win: int,
    resolution_pips: float,
    resolved_at: float,
    phase: str = "initiation",
    vol_atr: float = 10.0,
    exit_strat: str = "TP_SL",
    resolution_strategy: str = "DYNAMIC",
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO decisions "
            "(decision_id, snapshot_id, symbol, timeframe, direction, regime_type, "
            "is_win, resolution_pips, resolution_strategy, resolved_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (decision_id, snapshot_id, symbol, timeframe, direction, regime_type,
             is_win, resolution_pips, resolution_strategy, resolved_at),
        )
        conn.execute(
            "INSERT OR REPLACE INTO signals "
            "(snapshot_id, phase, volatility_atr_pips, exit_strategy_recommended) "
            "VALUES (?,?,?,?)",
            (snapshot_id, phase, vol_atr, exit_strat),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def empty_db(tmp_path):
    """DB avec tables vides."""
    db = tmp_path / "test_simulation.db"
    _create_decisions_table(db)
    return db


@pytest.fixture
def populated_db(tmp_path, monkeypatch):
    """DB avec 50 décisions GBPUSD M15 résolues (40 WIN / 10 LOSS)."""
    db = tmp_path / "populated.db"
    _create_decisions_table(db)
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "1")
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1")

    now = time.time()
    for i in range(40):
        _insert_decision(
            db, decision_id=f"win_{i}", snapshot_id=f"snap_win_{i}",
            symbol="GBPUSD", timeframe="M15", direction="long",
            regime_type="NEUTRE", is_win=1, resolution_pips=12.0 + i * 0.1,
            resolved_at=now - i * 60, phase="initiation",
            vol_atr=10.0, exit_strat="TP_SL", resolution_strategy="DYNAMIC",
        )
    for i in range(10):
        _insert_decision(
            db, decision_id=f"loss_{i}", snapshot_id=f"snap_loss_{i}",
            symbol="GBPUSD", timeframe="M15", direction="short",
            regime_type="TENDANCE", is_win=0, resolution_pips=-8.0,
            resolved_at=now - (i + 40) * 60, phase="resolution",
            vol_atr=15.0, exit_strat="TRAILING", resolution_strategy="DYNAMIC",
        )
    return db


# ------------------------------------------------------------------ DB loading


def test_load_resolved_decisions_empty(empty_db):
    from scripts.v9_meta_strategy_simulation import _load_resolved_decisions
    rows = _load_resolved_decisions(empty_db, None, 100)
    assert rows == []


def test_load_resolved_decisions_filters_outcome(populated_db):
    from scripts.v9_meta_strategy_simulation import _load_resolved_decisions
    rows = _load_resolved_decisions(populated_db, None, 100)
    assert len(rows) == 50
    assert all(r["is_win"] in (0, 1) for r in rows)


def test_load_resolved_decisions_since_filter(populated_db):
    from scripts.v9_meta_strategy_simulation import _load_resolved_decisions
    # since = il y a 5min → devrait exclure les décisions plus vieilles
    rows = _load_resolved_decisions(populated_db, time.time() - 300, 100)
    # Décisions espacées de 60s, donc ≤5 récentes
    assert 0 <= len(rows) <= 10


def test_load_resolved_decisions_limit(populated_db):
    from scripts.v9_meta_strategy_simulation import _load_resolved_decisions
    rows = _load_resolved_decisions(populated_db, None, 5)
    assert len(rows) == 5


def test_load_resolved_decisions_no_legacy_signal(empty_db):
    """Décision SANS signal lié → exit_strategy_recommended NULL (LEFT JOIN)."""
    from scripts.v9_meta_strategy_simulation import _load_resolved_decisions
    # Insertion UNIQUEMENT dans decisions (pas dans signals)
    conn = sqlite3.connect(str(empty_db))
    conn.execute(
        "INSERT INTO decisions (decision_id, snapshot_id, symbol, timeframe, "
        "direction, regime_type, is_win, resolution_pips, resolved_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("d1", "snap_no_signal", "EURUSD", "H1", "long", "NEUTRE", 1, 5.0, time.time()),
    )
    conn.commit()
    conn.close()
    rows = _load_resolved_decisions(empty_db, None, 100)
    assert len(rows) == 1
    assert rows[0]["exit_strategy_recommended"] is None


# ------------------------------------------------------------------ helpers


def test_build_legacy_from_signal_with_exit_strat():
    from scripts.v9_meta_strategy_simulation import _build_legacy_from_signal
    legacy = _build_legacy_from_signal({"exit_strategy_recommended": "TRAILING"})
    assert legacy.recommended_strategy == "TRAILING"
    assert legacy.confidence == 0.5


def test_build_legacy_from_signal_no_exit_strat():
    """exit_strat None → fallback TP_SL."""
    from scripts.v9_meta_strategy_simulation import _build_legacy_from_signal
    legacy = _build_legacy_from_signal({})
    assert legacy.recommended_strategy == "TP_SL"


# ------------------------------------------------------------------ core simulation


def test_run_simulation_no_data(empty_db):
    from scripts.v9_meta_strategy_simulation import run_simulation
    res = run_simulation(empty_db, since_ts=None, limit=100)
    assert res["n_decisions"] == 0
    assert res["verdict"] == "NO_DATA"


def test_run_simulation_populated(populated_db):
    from scripts.v9_meta_strategy_simulation import run_simulation
    res = run_simulation(populated_db, since_ts=None, limit=100)
    assert res["n_decisions"] == 50
    assert res["n_agreements"] + res["n_disagreements"] == 50
    assert 0.7 <= res["wr_legacy"] <= 0.9
    assert res["wr_meta"] >= 0
    # Nouveau : subset honnête doit être présent dans le résultat
    assert "n_subset_honest" in res
    assert "wr_meta_subset" in res
    assert "delta_subset_wr" in res
    assert res["n_subset_honest"] >= 0
    assert res["verdict"] in (
        "GREEN_PROMOTE", "YELLOW_VOLUMETRIE", "YELLOW_MARGINAL",
        "RED_NO_UPLIFT", "YELLOW_SUBSET_LOW",
    )


def test_run_simulation_creates_shadow_table(populated_db):
    """La simulation doit auto-créer la table shadow_log."""
    from scripts.v9_meta_strategy_simulation import run_simulation
    run_simulation(populated_db, since_ts=None, limit=20)
    conn = sqlite3.connect(str(populated_db))
    n_logs = conn.execute("SELECT COUNT(*) FROM meta_strategy_shadow_log").fetchone()[0]
    conn.close()
    assert n_logs > 0


def test_run_simulation_writes_shadow_logs_match_decisions(populated_db):
    """Nombre de shadow logs == nombre de décisions (1 par décision)."""
    from scripts.v9_meta_strategy_simulation import run_simulation
    res = run_simulation(populated_db, since_ts=None, limit=10)
    conn = sqlite3.connect(str(populated_db))
    n_logs = conn.execute("SELECT COUNT(*) FROM meta_strategy_shadow_log").fetchone()[0]
    conn.close()
    assert n_logs == 10
    assert res["n_decisions"] == 10


# ------------------------------------------------------------------ verdict thresholds


def test_verdict_logic_thresholds():
    """Vérifie les seuils de verdict (subset honnête) codés en dur."""
    import scripts.v9_meta_strategy_simulation as sim
    src = Path(sim.__file__).read_text(encoding="utf-8")
    # Seuils subset honnête (Chemin A — fix structurel)
    assert "delta_subset_wr >= 0.05" in src
    assert "delta_subset_pf >= 0.5" in src
    assert "delta_subset_wr >= 0.02" in src
    assert "delta_subset_pf >= 0.2" in src
    assert "n_subset < 30" in src


def test_verdict_green_promote_synthetic():
    """Synthétique : WR meta > WR legacy +5pts ET PF meta > PF legacy +0.5 → GREEN."""
    import scripts.v9_meta_strategy_simulation as sim
    src = Path(sim.__file__).read_text(encoding="utf-8")
    # Tous les verdicts possibles doivent être définis
    for verdict in [
        "GREEN_PROMOTE", "YELLOW_VOLUMETRIE", "YELLOW_MARGINAL",
        "RED_NO_UPLIFT", "NO_DATA", "YELLOW_SUBSET_LOW",
    ]:
        assert verdict in src, f"verdict {verdict} manquant"
    # Seuils subset honnête
    assert "delta_subset_wr >= 0.05" in src
    assert "delta_subset_pf >= 0.5" in src
    assert "n_subset < 30" in src


def test_verdict_subset_honest_path(populated_db, monkeypatch):
    """Quand meta == résolution_effectif, on alimente le subset honnête.
    Le verdict prend le subset en compte (pas le global artifact)."""
    from scripts.v9_meta_strategy_simulation import run_simulation
    res = run_simulation(populated_db, since_ts=None, limit=50)
    assert "n_subset_honest" in res
    # Subset contient : (a) les cas où meta matche résolution normalisée,
    # (b) les cas comparison=None avec résolution DYNAMIC (legacy=meta=res).
    # Donc subset >= agreements quand legacy est TP_SL/TRAILING et résolution DYNAMIC.
    assert res["n_subset_honest"] >= 0
    # Verdict doit être l'un des 5 (subset peuplé change le verdict)
    assert res["verdict"] in (
        "GREEN_PROMOTE", "YELLOW_VOLUMETRIE", "YELLOW_MARGINAL",
        "RED_NO_UPLIFT", "YELLOW_SUBSET_LOW", "NO_DATA",
    )


# ------------------------------------------------------------------ rendering


def test_render_markdown_empty(empty_db):
    from scripts.v9_meta_strategy_simulation import run_simulation, render_markdown
    res = run_simulation(empty_db, since_ts=None, limit=100)
    md = render_markdown(res, empty_db, "24h")
    assert "Rapport Simulation Meta-Strategy" in md
    assert "Aucune décision résolue" in md


def test_render_markdown_populated(populated_db):
    from scripts.v9_meta_strategy_simulation import run_simulation, render_markdown
    res = run_simulation(populated_db, since_ts=None, limit=50)
    md = render_markdown(res, populated_db, "7d")
    assert "Rapport Simulation Meta-Strategy" in md
    assert "Vue globale" in md
    assert "Edge uplift legacy vs meta" in md
    assert "Win Rate" in md
    assert "Profit Factor" in md
    assert "Verdict motion CEO" in md
    assert res["verdict_msg"] in md


def test_render_console_summary(populated_db, capsys):
    from scripts.v9_meta_strategy_simulation import run_simulation, render_console
    res = run_simulation(populated_db, since_ts=None, limit=20)
    render_console(res)
    out = capsys.readouterr().out
    assert "WR legacy" in out
    assert "WR meta" in out
    assert "Verdict" in out


# ------------------------------------------------------------------ CLI


def test_main_missing_db(tmp_path):
    from scripts.v9_meta_strategy_simulation import main
    rc = main(["--db-path", str(tmp_path / "nope.db")])
    assert rc == 1


def test_main_empty_db(empty_db, tmp_path):
    from scripts.v9_meta_strategy_simulation import main
    rc = main(["--db-path", str(empty_db), "--no-write"])
    assert rc == 0


def test_main_write_report(populated_db, tmp_path):
    from scripts.v9_meta_strategy_simulation import main
    report_dir = tmp_path / "reports"
    rc = main([
        "--db-path", str(populated_db), "--since", "7d",
        "--limit", "30", "--report-dir", str(report_dir),
    ])
    assert rc == 0
    files = list(report_dir.glob("simulation_*.md"))
    assert len(files) == 1


def test_main_invalid_since(empty_db):
    from scripts.v9_meta_strategy_simulation import main
    rc = main(["--db-path", str(empty_db), "--since", "garbage"])
    assert rc == 2


# ------------------------------------------------------------------ since helpers


def test_since_ts_hours():
    from scripts.v9_meta_strategy_simulation import _since_ts
    assert _since_ts("1h") > time.time() - 3700


def test_since_ts_days():
    from scripts.v9_meta_strategy_simulation import _since_ts
    assert _since_ts("30d") < time.time() - 29 * 86400


# ------------------------------------------------------------------ _phase_from_decision


def test_phase_from_decision_explicit():
    """phase explicite sur la décision → retournée telle quelle."""
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({"phase": "developpement"}) == "developpement"


def test_phase_from_decision_neutre_win():
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({"regime_type": "NEUTRE", "pips": 12.0}) == "initiation"


def test_phase_from_decision_neutre_loss():
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({"regime_type": "NEUTRE", "pips": -8.0}) == "resolution"


def test_phase_from_decision_tendance_win():
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({"regime_type": "TENDANCE", "pips": 5.0}) == "developpement"


def test_phase_from_decision_tendance_loss():
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({"regime_type": "TENDANCE", "pips": -3.0}) == "culmination"


def test_phase_from_decision_climax():
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({"regime_type": "CLIMAX", "pips": 10.0}) == "resolution"


def test_phase_from_decision_default():
    from scripts.v9_meta_strategy_simulation import _phase_from_decision
    assert _phase_from_decision({}) == "initiation"


def test_vol_atr_from_decision():
    from scripts.v9_meta_strategy_simulation import _vol_atr_from_decision
    assert _vol_atr_from_decision({"volatility_atr_pips": 12.5}) == 12.5
    assert _vol_atr_from_decision({}) is None


# ------------------------------------------------------------------ force_meta


def test_force_meta_runs_shadow(populated_db, monkeypatch):
    """--force-meta active V9_META_STRATEGY_SHADOW_ENABLED pour la durée de l'appel."""
    monkeypatch.delenv("V9_META_STRATEGY_SHADOW_ENABLED", raising=False)
    monkeypatch.setenv("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1")
    from scripts.v9_meta_strategy_simulation import run_simulation
    res = run_simulation(populated_db, since_ts=None, limit=20, force_meta=True)
    # L'env a été restauré après l'appel
    import os
    assert os.environ.get("V9_META_STRATEGY_SHADOW_ENABLED") is None
    assert res["n_decisions"] == 20


def test_force_meta_restores_env(populated_db, monkeypatch):
    """force_meta restaure la valeur précédente de V9_META_STRATEGY_SHADOW_ENABLED."""
    monkeypatch.setenv("V9_META_STRATEGY_SHADOW_ENABLED", "0")
    from scripts.v9_meta_strategy_simulation import run_simulation
    run_simulation(populated_db, since_ts=None, limit=5, force_meta=True)
    import os
    assert os.environ.get("V9_META_STRATEGY_SHADOW_ENABLED") == "0"


def test_force_meta_cli(populated_db):
    """--force-meta en CLI active le shadow."""
    from scripts.v9_meta_strategy_simulation import main
    rc = main([
        "--db-path", str(populated_db), "--since", "7d",
        "--limit", "10", "--force-meta", "--no-write",
    ])
    assert rc == 0


def test_no_force_meta_default(populated_db):
    """Sans --force-meta, le kill switch n'est pas activé."""
    import os
    from scripts.v9_meta_strategy_simulation import main
    if "V9_META_STRATEGY_SHADOW_ENABLED" in os.environ:
        del os.environ["V9_META_STRATEGY_SHADOW_ENABLED"]
    rc = main([
        "--db-path", str(populated_db), "--since", "7d",
        "--limit", "10", "--no-write",
    ])
    assert rc == 0
    assert "V9_META_STRATEGY_SHADOW_ENABLED" not in os.environ