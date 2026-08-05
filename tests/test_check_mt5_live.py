"""check_mt5_live.py — tests unitaires (Phase 28b Étape 3).

Doctrine V10 :
  R7 tests verts cumulés (cible +5 minimum)
  R2 additif pur (smoke fixtures)
  R6 fail-open (MT5 absent → source=UNAVAILABLE, ne crash pas)

Ces tests n'appellent PAS le vrai MT5 (VPS uniquement). Ils utilisent
un mock du module `core.v10.v10_mt5_bridge.get_rates` + DB fallback
sqlite en tmp.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_mt5_live  # noqa: E402
from check_mt5_live import (  # noqa: E402
    DEFAULT_PAIRS,
    DEFAULT_TFS,
    BridgeStateSummary,
    CellStatus,
    Mt5LiveReport,
    check_cell,
    main,
    report_filename,
    run_full_check,
    save_report,
    _safe_get_rates,
    _safe_get_bridge_state,
    _spread_pips,
    _query_db_last_bar,
)


# ─────────────────────────────────────────────────────────────────────
# FAKE DATAFRAME — évite la dépendance pandas en test env
# ─────────────────────────────────────────────────────────────────────

class _FakeTimestamp:
    def __init__(self, epoch_sec: int):
        self._epoch = int(epoch_sec)

    def timestamp(self) -> float:
        return float(self._epoch)

    def isoformat(self) -> str:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self._epoch, tz=timezone.utc).isoformat()


class _FakeIloc:
    """Stub : df[col].iloc[-1] doit fonctionner comme pandas."""

    def __init__(self, series_values: list):
        self._v = list(series_values)

    def __getitem__(self, idx):
        if isinstance(idx, int):
            if idx < 0:
                idx = len(self._v) + idx
            if 0 <= idx < len(self._v):
                return self._v[idx]
            raise IndexError("iloc index out of range")
        if isinstance(idx, slice):
            return self._v[idx]
        raise TypeError(f"iloc cannot index with {type(idx).__name__}")


class _FakeSeries:
    def __init__(self, values: list):
        self._v = list(values)

    @property
    def iloc(self) -> _FakeIloc:
        return _FakeIloc(self._v)

    def tail(self, n: int):
        return _FakeSeries(self._v[-n:] if len(self._v) > n else list(self._v))

    def mean(self) -> float:
        return sum(self._v) / max(len(self._v), 1)


class _FakeDataFrame:
    """Stub minimal imitant l'API pandas DataFrame utilisée par check_mt5_live."""

    def __init__(self, columns: dict):
        # columns: dict nom_col -> list de valeurs alignées
        lengths = {len(v) for v in columns.values()}
        if len(lengths) != 1:
            raise ValueError("all columns must have same length")
        self._c = columns
        self.columns_names = list(columns.keys())
        self._len = list(lengths)[0]

    def __len__(self):
        return self._len

    def __contains__(self, key):
        return key in self._c

    @property
    def columns(self):
        return self.columns_names

    def __getitem__(self, key):
        if key in self._c:
            return _FakeSeries(self._c[key])
        raise KeyError(key)

    def tail(self, n: int):
        sliced = {k: v[-n:] for k, v in self._c.items()}
        return _FakeDataFrame(sliced)

    def to_datetime(self, *args, **kw):
        return self


# ─────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Crée une DB SQLite temporaire avec table forces_snapshots + 30 rows pour EURUSD M30."""
    db = tmp_path / "test_v9_forces.db"
    con = sqlite3.connect(str(db))
    con.execute("""
        CREATE TABLE forces_snapshots (
            bar_time INTEGER, symbol TEXT, timeframe TEXT,
            is_closed_bar INTEGER, open REAL, high REAL, low REAL, close REAL,
            tick_volume REAL, spread REAL
        )
    """)
    rows = [
        (1700000000 + i * 1800, "EURUSD", "M30", 1, 1.10, 1.105, 1.095, 1.10 + i * 0.001,
         1000.0, 10.0)
        for i in range(30)
    ]
    con.executemany(
        "INSERT INTO forces_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)", rows
    )
    con.commit()
    con.close()
    return db


@pytest.fixture
def live_mock_df():
    """Fake DataFrame typique que get_rates retournerait."""
    bar_times = [1700000000 + i * 1800 for i in range(50)]
    closes = [1.10 + i * 0.0001 for i in range(50)]
    spreads = [10.0] * 50
    return _FakeDataFrame({
        "time": bar_times,
        "open": closes,
        "high": [c + 0.005 for c in closes],
        "low": [c - 0.005 for c in closes],
        "close": closes,
        "tick_volume": [1000.0] * 50,
        "spread": spreads,
        "real_volume": [0.0] * 50,
    })


# ─────────────────────────────────────────────────────────────────────
# TESTS BASIQUES (3)
# ─────────────────────────────────────────────────────────────────────

def test_dataclasses_json_serializable():
    """CellStatus, BridgeStateSummary, Mt5LiveReport sont JSON-sérialisables."""
    cell = CellStatus(
        pair="EURUSD", timeframe="M30", source="MT5_LIVE",
        live_ok=True, n_bars=50, last_bar_timestamp="2026-08-05T10:00:00+00:00",
        last_bar_age_seconds=60, spread_mean_pips=0.001, spread_last_pips=0.001,
    )
    bs = BridgeStateSummary(
        bridge_module_path="dummy.py",
        mt5_initialized=True,
        terminal_path="C:/MT5",
        n_rate_calls=1,
    )
    rep = Mt5LiveReport(cells=[cell], bridge_state=bs)
    payload = json.dumps(rep.as_dict())
    assert "EURUSD" in payload
    assert "MT5_LIVE" in payload


def test_report_filename_format():
    """report_filename() suit le pattern R9 mt5_live_status_YYYYMMDD.json."""
    fn = report_filename()
    assert fn.startswith("mt5_live_status_")
    assert fn.endswith(".json")
    assert len(fn) == len("mt5_live_status_YYYYMMDD.json")


def test_spread_pips_conversion():
    """_spread_pips : XXXJPY = *0.01, autres = *0.0001."""
    # XXXJPY
    assert _spread_pips("USDJPY", 10.0) == 0.10  # 10 points * 0.01 = 0.10 pip
    # non-JPY
    assert _spread_pips("EURUSD", 10.0) == 0.001  # 10 points * 0.0001 = 0.001 pip
    # None
    assert _spread_pips("EURUSD", None) is None
    # invalide
    assert _spread_pips("EURUSD", "not_a_number") is None


# ─────────────────────────────────────────────────────────────────────
# TESTS WORKFLOW (3 — au moins 5 requis)
# ─────────────────────────────────────────────────────────────────────

def test_check_cell_live_ok_with_mock(live_mock_df):
    """check_cell retourne MT5_LIVE + n_bars + spread + age quand get_rates OK."""
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(live_mock_df, "")):
        cell = check_cell("EURUSD", "M30")
    assert cell.pair == "EURUSD"
    assert cell.timeframe == "M30"
    assert cell.source == "MT5_LIVE"
    assert cell.live_ok is True
    assert cell.n_bars == 50
    # FakeDataFrame : time column = [epoch_sec] → iloc[-1] = int → ISO via fromtimestamp
    assert cell.last_bar_timestamp != "", f"expected non-empty timestamp, got {cell.last_bar_timestamp!r}"
    assert cell.spread_mean_pips == 0.001  # 10 points * 0.0001
    assert cell.last_bar_age_seconds is not None


def test_check_cell_db_fallback_when_get_rates_returns_none(tmp_db: Path):
    """check_cell → DB_FALLBACK si get_rates=None et DB contient la row."""
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(None, "no data")):
        cell = check_cell("EURUSD", "M30", db_path=tmp_db)
    assert cell.source == "DB_FALLBACK"
    assert cell.live_ok is False
    assert cell.last_bar_timestamp != ""
    assert cell.spread_last_pips is not None
    assert cell.spread_last_pips == 0.001


def test_check_cell_unavailable_when_mt5_and_db_ko(tmp_path: Path):
    """check_cell → UNAVAILABLE si MT5 KO et DB inexistant."""
    missing_db = tmp_path / "no_db_here.db"
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(None, "no data")):
        cell = check_cell("EURUSD", "M30", db_path=missing_db)
    assert cell.source == "UNAVAILABLE"
    assert cell.live_ok is False
    assert cell.error != ""


def test_run_full_check_grid_size_default():
    """run_full_check produit 19 cellules par défaut (6×3 + 1 M1 GBPUSD)."""
    # mock pour éviter tout appel réel
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(None, "mocked")):
        with patch.object(check_mt5_live, "_query_db_last_bar", return_value=None):
            rep = run_full_check(db_path=Path("/nonexistent/path/db.db"))
    assert rep.grid_total_cells == 19
    assert rep.n_pairs == 6
    assert rep.n_tfs == 4  # M30, H1, H4, M1 (added for GBPUSD)
    assert len(rep.cells) == 19
    # sources doivent toutes être UNAVAILABLE (mock + DB inexistant)
    assert rep.grid_unavailable_cells == 19
    assert rep.grid_live_cells == 0
    assert rep.grid_db_fallback_cells == 0


def test_run_full_check_db_only_no_live(tmp_db: Path):
    """run_full_check retourne DB_FALLBACK quand MT5 KO mais DB accessible."""
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(None, "mocked")):
        rep = run_full_check(pairs=("EURUSD",), tfs=("M30",),
                             include_m1_gbpusd=False, db_path=tmp_db)
    assert rep.grid_total_cells == 1
    assert rep.grid_db_fallback_cells == 1
    assert rep.grid_unavailable_cells == 0
    assert rep.cells[0].source == "DB_FALLBACK"
    assert rep.cells[0].pair == "EURUSD"
    assert rep.cells[0].timeframe == "M30"


def test_save_report_writes_json(tmp_path: Path):
    """save_report écrit le JSON sur disque + crée un log companion."""
    rep = Mt5LiveReport(
        timestamp_utc="2026-08-05T00:00:00+00:00",
        grid_total_cells=2,
        grid_live_cells=1,
        grid_db_fallback_cells=1,
        cells=[
            CellStatus(pair="EURUSD", timeframe="M30", source="MT5_LIVE", live_ok=True, n_bars=50),
            CellStatus(pair="GBPUSD", timeframe="M30", source="DB_FALLBACK", live_ok=False, n_bars=1),
        ],
    )
    output = tmp_path / "test_report.json"
    logs_dir = tmp_path / "logs"
    saved = save_report(rep, output, logs_dir=logs_dir)
    assert saved.exists()
    assert saved.read_text(encoding="utf-8").startswith("{")
    parsed = json.loads(saved.read_text(encoding="utf-8"))
    assert parsed["grid_total_cells"] == 2
    assert parsed["grid_live_cells"] == 1
    # log companion doit exister
    log_files = list(logs_dir.glob("*.log"))
    assert len(log_files) >= 1


def test_main_cli_full_smoke(tmp_db: Path):
    """main() CLI run complet → exit code 0 (DB fallback acceptable)."""
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(None, "mocked")):
        rc = main([
            "--pairs", "EURUSD",
            "--tf", "M30",
            "--no-m1",
            "--output", str(tmp_db.parent / "report.json"),
            "--db-path", str(tmp_db),
            "--quiet",
        ])
    assert rc == 0  # 0 car DB_FALLBACK acceptable


def test_main_cli_returns_2_when_all_unavail(tmp_path: Path):
    """main() retourne 2 si tout UNAVAILABLE (panne complète)."""
    missing_db = tmp_path / "nonexistent.db"
    with patch.object(check_mt5_live, "_safe_get_rates", return_value=(None, "mocked")):
        rc = main([
            "--pairs", "EURUSD",
            "--tf", "M30",
            "--no-m1",
            "--output", str(tmp_path / "report.json"),
            "--db-path", str(missing_db),
            "--quiet",
        ])
    assert rc == 2  # 0 live + 0 DB = panne totale


def test_safe_get_bridge_state_returns_dataclass():
    """_safe_get_bridge_state lit l'état bridge sans crash."""
    bs = _safe_get_bridge_state()
    assert isinstance(bs, BridgeStateSummary)
    # bridge_module_path doit être renseigné ou erreur capturée
    assert bs.bridge_module_path != ""


def test_query_db_last_bar_returns_dict_or_none(tmp_db: Path, tmp_path: Path):
    """_query_db_last_bar retourne dict si row existe, None sinon."""
    row = _query_db_last_bar(tmp_db, "EURUSD", "M30")
    assert row is not None
    assert "bar_time" in row
    assert "close" in row

    missing = _query_db_last_bar(tmp_path / "no_db.db", "EURUSD", "M30")
    assert missing is None


def test_check_mt5_live_cli_subprocess(tmp_path: Path):
    """Le script est exécutable en subprocess (R7 smoke test bout-en-bout)."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "check_mt5_live.py"),
        "--pairs", "GBPUSD",
        "--tf", "M30",
        "--no-m1",
        "--quiet",
        "--db-path", str(tmp_path / "nope.db"),
        "--output", str(tmp_path / "subproc_report.json"),
    ]
    # Note : ne fail pas sur MT5 absent (= exit 1 acceptable) ou retour DB fallback (= exit 0)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert res.returncode in (0, 1, 2)  # 0=tout OK, 1=au moins 1 unavail, 2=panne totale
    # Le rapport doit exister sur disque
    out_path = tmp_path / "subproc_report.json"
    assert out_path.exists(), f"Expected report at {out_path}, stderr={res.stderr}"
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "cells" in payload
    assert "grid_total_cells" in payload
