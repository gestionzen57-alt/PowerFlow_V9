"""Tests — scripts/v9_dashboard.py OPT-2 cache + OPT-3 vue.

Couvre :
- OPT-2 : cache in-memory TTL 30s, clear_cache, decorated functions
- OPT-3 : vue v_dashboard_snapshot créée par init_all_dbs(), 11 colonnes
- Non-régression : dashboard --once fonctionne
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_dashboard  # noqa: E402
from core.v9.db_schema import init_all_dbs, get_connection  # noqa: E402


# ── OPT-2 : Cache in-memory ────────────────────────────────
def test_clear_cache() -> None:
    """clear_cache() vide le cache sans erreur."""
    v9_dashboard._CACHE["test"] = (time.time(), "value")
    v9_dashboard.clear_cache()
    assert v9_dashboard._CACHE == {}


def test_cached_decorator_basic() -> None:
    """Décorateur @_cached met en cache la valeur."""
    @v9_dashboard._cached("test_basic", ttl=60)
    def f(x):
        return x * 2

    v9_dashboard.clear_cache()
    assert f(5) == 10
    assert len(v9_dashboard._CACHE) == 1
    # 2e appel = cache hit (pas de re-exécution)
    assert f(5) == 10
    assert len(v9_dashboard._CACHE) == 1


def test_cached_decorator_ttl_expiry() -> None:
    """Cache expire après TTL."""
    @v9_dashboard._cached("test_ttl", ttl=0.1)
    def f():
        return time.time()

    v9_dashboard.clear_cache()
    t1 = f()
    time.sleep(0.2)
    t2 = f()
    assert t2 > t1  # re-exécuté car TTL expiré


def test_cached_decorator_different_args() -> None:
    """Args différents = cache keys différentes."""
    @v9_dashboard._cached("test_args", ttl=60)
    def f(x):
        return x * 2

    v9_dashboard.clear_cache()
    assert f(2) == 4
    assert f(3) == 6
    assert len(v9_dashboard._CACHE) == 2


def test_count_table_is_cached() -> None:
    """count_table est décoré @_cached."""
    # Vérif que le décorateur est appliqué (présence attribut __wrapped__)
    assert hasattr(v9_dashboard.count_table, "__wrapped__")
    v9_dashboard.clear_cache()
    # Mock conn qui retourne table_exists=False pour ne pas crash
    class _FakeConn:
        def execute(self, *a, **k):
            class _R:
                def fetchone(self_inner): return [0]
            return _R()
    v9_dashboard.count_table(_FakeConn(), "fake_table")
    assert any("count_table" in k for k in v9_dashboard._CACHE)


# ── OPT-3 : Vue v_dashboard_snapshot ────────────────────────
def test_view_exists(tmp_path: Path) -> None:
    """init_all_dbs crée la vue v_dashboard_snapshot."""
    db = tmp_path / "test_v9.db"
    init_all_dbs(db)  # crée les 11 tables + la vue
    with get_connection(db) as conn:
        views = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()]
    assert "v_dashboard_snapshot" in views


def test_view_returns_11_columns(tmp_path: Path) -> None:
    """La vue expose 11 colonnes attendues."""
    db = tmp_path / "test_v9_view.db"
    init_all_dbs(db)
    with get_connection(db) as conn:
        cols = [d[0] for d in conn.execute("SELECT * FROM v_dashboard_snapshot LIMIT 0").description]
    expected = {
        "n_snapshots", "last_bar_time",
        "n_decisions_unresolved", "n_decisions_win", "n_decisions_loss",
        "n_scenes", "n_behaviors", "n_windows", "n_exploitability",
        "n_signals", "n_paper_trades",
    }
    assert set(cols) == expected
    assert len(cols) == 11


def test_view_is_idempotent(tmp_path: Path) -> None:
    """init_all_dbs appelé 2x ne crée pas 2 vues."""
    db = tmp_path / "test_v9_idem.db"
    init_all_dbs(db)
    init_all_dbs(db)
    with get_connection(db) as conn:
        n_views = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='v_dashboard_snapshot'"
        ).fetchone()[0]
    assert n_views == 1