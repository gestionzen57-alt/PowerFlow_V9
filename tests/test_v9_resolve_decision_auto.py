"""Tests — scripts/v9_resolve_decision_auto.py (Phase 9.10).

Couvre :
- _parse_iso — parsing ISO8601 avec/sans Z
- _compute_mfe — MFE haussière/baissière/edge cases
- _fetch_unresolved — filtre action=preparer_entree, is_win NULL
- _fetch_entry_mid — récupère mid via forces_snapshots
- _fetch_future_mids — fenêtre temporelle, fallback M15
- resolve_one — cas complet (haussiere/baissiere, no future)
- apply_resolutions — UPDATE idempotent
- main() — --apply exige --backup, dry-run pas de modification
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_resolve_decision_auto as res  # noqa: E402


# ── Tests purs (pas de DB) ────────────────────────────────────
def test_parse_iso_with_z():
    dt = res._parse_iso("2026-07-08T12:00:00Z")
    assert dt.year == 2026 and dt.hour == 12
    assert dt.tzinfo is not None


def test_parse_iso_with_offset():
    dt = res._parse_iso("2026-07-08T12:00:00+00:00")
    assert dt.year == 2026 and dt.hour == 12


def test_compute_mfe_haussiere():
    # entry=1.25, max futur=1.26 → MFE = +0.01
    mfe = res._compute_mfe("haussiere", 1.25, [1.255, 1.26, 1.258])
    assert abs(mfe - 0.01) < 1e-9


def test_compute_mfe_baissiere():
    # entry=1.25, min futur=1.24 → MFE = +0.01
    mfe = res._compute_mfe("baissiere", 1.25, [1.255, 1.24, 1.245])
    assert abs(mfe - 0.01) < 1e-9


def test_compute_mfe_empty_returns_zero():
    assert res._compute_mfe("haussiere", 1.25, []) == 0.0


def test_compute_mfe_unknown_direction_returns_zero():
    assert res._compute_mfe("neutre", 1.25, [1.30]) == 0.0


# ── Fixtures DB tmp ───────────────────────────────────────────
@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """DB avec decisions + forces_snapshots. 3 décisions :
    - D1 : haussiere, prix futur hausse → WIN
    - D2 : baissiere, prix futur baisse → WIN
    - D3 : haussiere, SANS prix futur (no future prices) → skip si skip_no_future

    La table decisions est créée avec un sous-ensemble des colonnes
    réellement présentes en prod (init_decision_db n'est pas appelé pour
    éviter les migrations ALTER sur fixtures). Les colonnes non testées
    sont NULL par défaut.
    """
    db = tmp_path / "resolve_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY,
            timestamp TEXT,
            snapshot_id TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            action TEXT,
            is_win INTEGER,
            resolution_pips REAL,
            resolved_at TEXT,
            source_type TEXT,
            resolution_strategy TEXT,
            resolution_details TEXT
        );
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            mid REAL
        );
        """
    )
    base = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)
    # D1 : haussiere, prix futur hausse
    conn.execute(
        "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("D1", base.isoformat(), "snap-d1", "GBPUSD", "M15", "haussiere",
          80, "preparer_entree", None, None, None, "live", None, None),
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
        ("snap-d1", base.isoformat(), "GBPUSD", "M15", 1.2500),
    )
    # D2 : baissiere, prix futur baisse
    conn.execute(
        "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("D2", (base + timedelta(hours=1)).isoformat(), "snap-d2", "GBPUSD",
          "M15", "baissiere", 75, "preparer_entree", None, None, None, "live", None, None),
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
        ("snap-d2", (base + timedelta(hours=1)).isoformat(), "GBPUSD", "M15", 1.2600),
    )
    # D3 : haussiere SANS prix futur (decision = base + 6h, pas de forces après)
    conn.execute(
        "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("D3", (base + timedelta(hours=6)).isoformat(), "snap-d3", "GBPUSD",
          "M15", "haussiere", 70, "preparer_entree", None, None, None, "live", None, None),
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
        ("snap-d3", (base + timedelta(hours=6)).isoformat(), "GBPUSD", "M15", 1.2700),
    )
    # Prix futurs M15 pour D1 et D2
    for i, (h, mid) in enumerate([
        (0, 1.252), (1, 1.255), (2, 1.258), (3, 1.260),  # D1 haussiere : 1.250 → 1.260 = +100 pips
        (1, 1.258), (2, 1.255), (3, 1.250), (4, 1.245),  # D2 baissiere : 1.260 → 1.245 = +150 pips
    ]):
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
            (f"future-{h}-{mid}", (base + timedelta(hours=h)).isoformat(),
             "GBPUSD", "M15", mid),
        )
    # D4 : décision 'aucune_action' (doit être ignorée par _fetch_unresolved par défaut)
    conn.execute(
        "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("D4", base.isoformat(), "snap-d4", "GBPUSD", "M15", "haussiere",
          80, "aucune_action", None, None, None, "live", None, None),
    )
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
        ("snap-d4", base.isoformat(), "GBPUSD", "M15", 1.2500),
    )
    # D5 : décision déjà résolue (doit être ignorée)
    conn.execute(
        "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("D5", base.isoformat(), "snap-d5", "GBPUSD", "M15", "haussiere",
          80, "preparer_entree", 1, 50.0, base.isoformat(), "live", None, None),
    )
    conn.commit()
    conn.close()
    return db


def test_fetch_unresolved_filters_correctly(temp_db: Path):
    conn = res._connect(temp_db)
    try:
        rows = res._fetch_unresolved(conn)
        ids = [r["decision_id"] for r in rows]
        # D4 (aucune_action) et D5 (déjà résolu) doivent être exclus
        assert "D4" not in ids
        assert "D5" not in ids
        assert set(ids) == {"D1", "D2", "D3"}
    finally:
        conn.close()


def test_fetch_unresolved_includes_aucune_action(temp_db: Path):
    """Vérifie que _fetch_unresolved inclut les décisions aucune_action
    quand actions=['aucune_action', 'preparer_entree'] est passé."""
    conn = res._connect(temp_db)
    try:
        rows = res._fetch_unresolved(conn, actions=["aucune_action", "preparer_entree"])
        ids = [r["decision_id"] for r in rows]
        # D4 (aucune_action) doit être inclus, D5 (déjà résolu) exclu
        assert "D4" in ids, "D4 (aucune_action) devrait être inclus"
        assert "D5" not in ids
        assert set(ids) == {"D1", "D2", "D3", "D4"}
    finally:
        conn.close()


def test_fetch_unresolved_aucune_action_only(temp_db: Path):
    """Vérifie que _fetch_unresolved ne retourne que les aucune_action
    quand actions=['aucune_action'] est passé."""
    conn = res._connect(temp_db)
    try:
        rows = res._fetch_unresolved(conn, actions=["aucune_action"])
        ids = [r["decision_id"] for r in rows]
        assert set(ids) == {"D4"}
    finally:
        conn.close()


def test_fetch_entry_mid(temp_db: Path):
    conn = res._connect(temp_db)
    try:
        assert res._fetch_entry_mid(conn, "snap-d1") == 1.25
        assert res._fetch_entry_mid(conn, "snap-doesnotexist") is None
    finally:
        conn.close()


def test_fetch_future_mids_basic(temp_db: Path):
    conn = res._connect(temp_db)
    try:
        # D1 : base = 10:00:00, horizon 4h → fenêtre [10:00, 14:00]
        base = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)
        end = base + timedelta(hours=4)
        mids = res._fetch_future_mids(conn, "GBPUSD", "M15",
                                      base.isoformat(), end.isoformat())
        # Au moins 4 prix (D1) + D2 (qui partage partiellement la fenêtre).
        # On vérifie juste que le max est 1.260 (hausse cohérente D1).
        assert len(mids) >= 4
        assert max(mids) == 1.260
    finally:
        conn.close()


def test_fetch_future_mids_fallback_to_m15(tmp_path: Path):
    """Si M5 a < 3 prix mais M15 en a plus, fallback M15."""
    db = tmp_path / "fallback.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT,
            timeframe TEXT, mid REAL
        );
        """
    )
    base = datetime(2026, 7, 7, 10, 0, 0, tzinfo=timezone.utc)
    # M5 : 1 seul prix dans la fenêtre
    conn.execute(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
        ("m5-1", base.isoformat(), "GBPUSD", "M5", 1.25),
    )
    # M15 : 5 prix dans la fenêtre (fallback doit s'activer)
    for i, mid in enumerate([1.251, 1.252, 1.253, 1.254, 1.255]):
        conn.execute(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)",
            (f"m15-{i}", (base + timedelta(minutes=15*i)).isoformat(),
             "GBPUSD", "M15", mid),
        )
    conn.commit()
    conn.close()

    conn = res._connect(db)
    try:
        end = base + timedelta(hours=2)
        mids = res._fetch_future_mids(conn, "GBPUSD", "M5",
                                      base.isoformat(), end.isoformat())
        # M5 : 1 prix à h=0 (= base) exclu par `> strict`. M15 : 4 prix
        # à h=15,30,45min et 1h (le 1er à h=0 aussi exclu). Fallback M15
        # (4 prix) > M5 (0 prix) → utilise M15.
        assert len(mids) == 4
    finally:
        conn.close()


def test_resolve_one_haussiere_wins(temp_db: Path):
    """exit_strategy explicite MFE_ONLY : ce test vérifie le calcul MFE
    lui-même (Phase 9.10), indépendant de DEFAULT_EXIT_STRATEGY (passé à
    DYNAMIC en Brief O1 2026-07-12 — cf. test_resolve_one_default_strategy_is_dynamic)."""
    conn = res._connect(temp_db)
    try:
        # D1 : haussiere, max futur attendu 1.260, entry 1.250 → MFE ≈ +0.010 = +100 pips
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D1'").fetchone()
        result = res.resolve_one(
            conn, dec, horizon_hours=4, skip_no_future=False, exit_strategy="MFE_ONLY",
        )
        assert result["resolved"] is True
        assert result["pips"] == pytest.approx(99.5, abs=0.1)
        assert result["is_win"] == 1
        assert result["n_future_prices"] >= 4
    finally:
        conn.close()


def test_resolve_one_baissiere_wins(temp_db: Path):
    """exit_strategy explicite MFE_ONLY (cf. note test_resolve_one_haussiere_wins)."""
    conn = res._connect(temp_db)
    try:
        # D2 : baissiere, min futur = 1.245, entry = 1.260 → MFE = +0.015 = +150 pips
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D2'").fetchone()
        result = res.resolve_one(
            conn, dec, horizon_hours=4, skip_no_future=False, exit_strategy="MFE_ONLY",
        )
        assert result["resolved"] is True
        assert result["pips"] == pytest.approx(149.5, abs=0.1)
        assert result["is_win"] == 1
    finally:
        conn.close()


def test_resolve_one_no_future_skip(temp_db: Path):
    conn = res._connect(temp_db)
    try:
        # D3 : décision à base+6h, prix dans fixture ne couvrent que [base, base+4h]
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D3'").fetchone()
        # Skip no future : la requête ne doit retourner aucun prix dans la fenêtre
        mids = res._fetch_future_mids(
            conn, "GBPUSD", "M15", dec["timestamp"],
            (res._parse_iso(dec["timestamp"]) + timedelta(hours=4)).isoformat(),
        )
        assert len(mids) == 0, f"attendu 0 prix, got {len(mids)}"
        # Avec skip_no_future=True → resolve_one doit skip
        result = res.resolve_one(conn, dec, horizon_hours=4, skip_no_future=True)
        assert result["resolved"] is False
        assert result["reason"] == "no_future_prices_in_window"
    finally:
        conn.close()


def test_resolve_one_aucune_action_haussiere_wins(temp_db: Path):
    """Vérifie que resolve_one fonctionne aussi pour une décision
    aucune_action (même logique MFE que preparer_entree, exit_strategy
    explicite — cf. note test_resolve_one_haussiere_wins)."""
    conn = res._connect(temp_db)
    try:
        # D4 : haussiere, aucune_action, entry=1.2500, max futur=1.260 → +100 pips
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D4'").fetchone()
        result = res.resolve_one(
            conn, dec, horizon_hours=4, skip_no_future=False, exit_strategy="MFE_ONLY",
        )
        assert result["resolved"] is True
        assert result["pips"] == pytest.approx(99.5, abs=0.1)
        assert result["is_win"] == 1
        assert result["n_future_prices"] >= 4
    finally:
        conn.close()


def test_resolve_one_default_strategy_is_dynamic():
    """Brief O1 (2026-07-12) : le défaut bascule MFE_ONLY -> DYNAMIC pour
    que le fil de l'eau live soit cohérent avec le batch de re-résolution."""
    assert res.DEFAULT_EXIT_STRATEGY == "DYNAMIC"


def test_resolve_one_default_skip_sessions_new_york_after():
    assert res.DEFAULT_SKIP_SESSIONS == "new_york,after"


def test_resolve_one_skips_new_york_without_simulation(temp_db: Path):
    """D1 est à base=10:00 UTC (london). On le force artificiellement en
    session skip via skip_sessions=['london'] pour vérifier qu'AUCUNE
    simulation n'a lieu (pips=0, is_win=0, resolution_strategy_override)."""
    conn = res._connect(temp_db)
    try:
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D1'").fetchone()
        result = res.resolve_one(
            conn, dec, horizon_hours=4, skip_no_future=False,
            exit_strategy="DYNAMIC", skip_sessions=["london"],
        )
        assert result["resolved"] is True
        assert result["is_win"] == 0
        assert result["pips"] == 0.0
        assert result["resolution_strategy_override"] == "SKIPPED"
        assert result["exit_reason"] == "skipped_london"
    finally:
        conn.close()


def test_resolve_one_dynamic_uses_session_profile(temp_db: Path):
    """D1 (london, hour=10 UTC) avec DYNAMIC doit utiliser le profil London
    (TP=8/SL=15), pas le profil Asie par défaut de simulate() sans utc_hour."""
    conn = res._connect(temp_db)
    try:
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D1'").fetchone()
        result = res.resolve_one(
            conn, dec, horizon_hours=4, skip_no_future=False, exit_strategy="DYNAMIC",
        )
        assert result["resolved"] is True
        assert result["session"] == "london"
        assert result["exit_reason"].endswith("_london")
    finally:
        conn.close()


def test_apply_resolutions_updates_db(temp_db: Path):
    conn = res._connect(temp_db)
    try:
        dec1 = conn.execute("SELECT * FROM decisions WHERE decision_id='D1'").fetchone()
        dec2 = conn.execute("SELECT * FROM decisions WHERE decision_id='D2'").fetchone()
        r1 = res.resolve_one(
            conn, dec1, horizon_hours=4, skip_no_future=False, exit_strategy="MFE_ONLY",
        )
        r2 = res.resolve_one(
            conn, dec2, horizon_hours=4, skip_no_future=False, exit_strategy="MFE_ONLY",
        )
        applied = res.apply_resolutions(conn, [r1, r2], exit_strategy="MFE_ONLY")
        assert applied == 2
        # Vérifier que les résolutions sont en DB
        row = conn.execute(
            "SELECT is_win, resolution_pips, resolved_at FROM decisions WHERE decision_id='D1'"
        ).fetchone()
        assert row["is_win"] == 1
        assert row["resolution_pips"] == pytest.approx(99.5, abs=0.1)
        assert row["resolved_at"] is not None
    finally:
        conn.close()


def test_apply_resolutions_skipped_override_writes_skipped_strategy(temp_db: Path):
    """resolution_strategy_override='SKIPPED' doit être écrit tel quel,
    même si --exit-strategy CLI vaut DYNAMIC."""
    conn = res._connect(temp_db)
    try:
        dec = conn.execute("SELECT * FROM decisions WHERE decision_id='D1'").fetchone()
        r = res.resolve_one(
            conn, dec, horizon_hours=4, skip_no_future=False,
            exit_strategy="DYNAMIC", skip_sessions=["london"],
        )
        applied = res.apply_resolutions(conn, [r], exit_strategy="DYNAMIC")
        assert applied == 1
        row = conn.execute(
            "SELECT resolution_strategy FROM decisions WHERE decision_id='D1'"
        ).fetchone()
        assert row["resolution_strategy"] == "SKIPPED"
    finally:
        conn.close()


def test_apply_resolutions_idempotent(temp_db: Path):
    """Une 2e application ne change rien (UPDATE WHERE is_win IS NULL)."""
    conn = res._connect(temp_db)
    try:
        dec1 = conn.execute("SELECT * FROM decisions WHERE decision_id='D1'").fetchone()
        r1 = res.resolve_one(
            conn, dec1, horizon_hours=4, skip_no_future=False, exit_strategy="MFE_ONLY",
        )
        applied1 = res.apply_resolutions(conn, [r1], exit_strategy="MFE_ONLY")
        assert applied1 == 1
        # 2e passe : ne doit rien changer
        applied2 = res.apply_resolutions(conn, [r1], exit_strategy="MFE_ONLY")
        assert applied2 == 0
    finally:
        conn.close()


def test_run_dry_run_does_not_modify(temp_db: Path, capsys):
    plan = res.run(temp_db, init_schema=False)
    assert plan["n_unresolved_total"] == 3
    assert plan["n_resolvable"] >= 2
    # DB inchangée : D1 et D2 toujours is_win=NULL
    conn = sqlite3.connect(str(temp_db))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT is_win FROM decisions WHERE decision_id='D1'").fetchone()
        assert row["is_win"] is None
        row = conn.execute("SELECT is_win FROM decisions WHERE decision_id='D2'").fetchone()
        assert row["is_win"] is None
    finally:
        conn.close()


def test_run_with_aucune_action_included(temp_db: Path):
    """Vérifie que run() avec actions=['aucune_action', 'preparer_entree']
    inclut D4 dans le plan. exit_strategy=MFE_ONLY explicite (ce test
    vérifie le filtrage par action, pas le calcul de pips — le défaut
    DYNAMIC produit un tp_hit_london précoce à +7.5 pips sur ce fixture)."""
    plan = res.run(
        temp_db, init_schema=False, actions=["aucune_action", "preparer_entree"],
        exit_strategy="MFE_ONLY",
    )
    assert plan["n_unresolved_total"] == 4  # D1, D2, D3, D4
    assert plan["n_resolvable"] >= 3  # D1, D2, D4 résolubles
    # Vérifier que D4 est dans les résolutions
    d4_res = [r for r in plan["resolutions"] if r["decision_id"] == "D4"]
    assert len(d4_res) == 1
    assert d4_res[0]["resolved"] is True
    assert d4_res[0]["pips"] == pytest.approx(99.5, abs=0.1)


def test_run_with_aucune_action_only(temp_db: Path):
    """Vérifie que run() avec actions=['aucune_action'] ne cible que D4."""
    plan = res.run(temp_db, init_schema=False, actions=["aucune_action"])
    assert plan["n_unresolved_total"] == 1  # D4 uniquement
    assert plan["resolutions"][0]["decision_id"] == "D4"


def test_main_include_actions_flag(temp_db: Path, capsys):
    """Vérifie que le flag --include-actions fonctionne en CLI."""
    exit_code = res.main([
        "--db", str(temp_db), "--dry-run",
        "--include-actions", "aucune_action,preparer_entree",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Actions incluses" in out
    assert "Décisions non résolues ciblées : 4" in out


def test_run_apply_requires_backup(temp_db: Path, capsys):
    exit_code = res.main(["--db", str(temp_db), "--apply"])
    assert exit_code == 2
    assert "--apply exige --backup" in capsys.readouterr().err


def test_run_apply_rejects_missing_backup_dir(temp_db: Path, capsys):
    exit_code = res.main([
        "--db", str(temp_db), "--apply",
        "--backup", str(temp_db.parent / "nonexistent"),
    ])
    assert exit_code == 2


def test_run_apply_rejects_empty_md5_file(tmp_path: Path, temp_db: Path, capsys):
    backup = tmp_path / "empty_md5"
    backup.mkdir()
    (backup / "md5_pre.txt").write_text("# commentaires\n", encoding="utf-8")
    exit_code = res.main([
        "--db", str(temp_db), "--apply", "--backup", str(backup),
    ])
    assert exit_code == 2


def test_run_apply_full(temp_db: Path, tmp_path: Path, capsys):
    backup = tmp_path / "backup_ok"
    backup.mkdir()
    (backup / "md5_pre.txt").write_text(
        "00000000000000000000000000000000  12345  data.db\n", encoding="utf-8"
    )
    exit_code = res.main([
        "--db", str(temp_db), "--apply", "--backup", str(backup),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "résolutions appliquées" in out
    # DB mise à jour
    conn = sqlite3.connect(str(temp_db))
    try:
        n_resolved = conn.execute(
            "SELECT COUNT(*) FROM decisions WHERE is_win IS NOT NULL"
        ).fetchone()[0]
        # D1 et D2 résolus, D3 skip (no future prices + skip_no_future=False → résolu avec pips=0)
        # Par défaut skip_no_future=False → D3 résolu avec pips=0
        assert n_resolved >= 2
    finally:
        conn.close()


def test_run_json_report(temp_db: Path, tmp_path: Path, capsys):
    report_path = tmp_path / "report.json"
    exit_code = res.main([
        "--db", str(temp_db), "--dry-run", "--report", str(report_path),
    ])
    assert exit_code == 0
    assert report_path.exists()
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert "n_unresolved_total" in parsed
    assert "n_resolvable" in parsed


def test_ensure_perf_index_idempotent(temp_db: Path):
    """L'index perf (symbol, timeframe, timestamp) doit être créé
    idempotemment au premier appel."""
    conn = res._connect(temp_db)
    try:
        # Premier appel : crée
        res._ensure_perf_index(conn)
        # 2e appel : no-op
        res._ensure_perf_index(conn)
        # Vérifier l'index existe (via sqlite_master)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_forces_symbol_timeframe_timestamp",),
        ).fetchone()
        assert row is not None
    finally:
        conn.close()
