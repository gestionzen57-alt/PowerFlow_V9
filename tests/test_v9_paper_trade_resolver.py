"""Tests PaperTradeResolver — résolution paramétrique (réconciliation 2026-07-20).

Le resolver est déterministe (R18) et défensif (R6). On teste la table
paramétrique (tf × vol × conf × session), la résolution par contexte, la
calibration depuis un historique factice, et l'override de table.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.v9.v9_paper_trade_resolver import (
    PaperTradeResolver,
    ResolutionContext,
)


def _resolver(tmp_path):
    return PaperTradeResolver(db_path=str(tmp_path / "absent.db"))


def _ctx(**kw):
    base = dict(
        vol_regime="NORMAL", session="london", timeframe="M1",
        confiance=80, symbol="GBPUSD", direction="haussiere",
    )
    base.update(kw)
    return ResolutionContext(**base)


def test_resolve_low_vol_m1_short_tp(tmp_path):
    """vol=LOW, tf=M1, conf=80, london → TP=8, SL=10 ; trade +14 pips → win TP."""
    r = _resolver(tmp_path)
    ctx = _ctx(vol_regime="LOW", timeframe="M1", confiance=80, session="london")
    tp, sl = r.tp_sl_for(ctx)
    assert (tp, sl) == (8.0, 10.0)
    out = r.resolve({"pips_simulated": 14.0}, ctx)
    assert out.is_win == 1
    assert out.exit_reason == "tp"
    assert out.pips == 8.0


def test_resolve_high_vol_h1_long_sl(tmp_path):
    """vol=HIGH, tf=H1, conf=85, london → TP=140/SL=160 ; −100 pips → horizon loss."""
    r = _resolver(tmp_path)
    ctx = _ctx(vol_regime="HIGH", timeframe="H1", confiance=85, session="london")
    tp, sl = r.tp_sl_for(ctx)
    assert (tp, sl) == (140.0, 160.0)
    # −100 est entre −160 et +140 → horizon (pas SL), loss car pips<0.
    out = r.resolve({"pips_simulated": -100.0}, ctx)
    assert out.is_win == 0
    assert out.exit_reason == "horizon"
    # −170 franchit le SL.
    out_sl = r.resolve({"pips_simulated": -170.0}, ctx)
    assert out_sl.exit_reason == "sl"
    assert out_sl.pips == -160.0


def test_tp_sl_scales_with_confiance(tmp_path):
    """Même (tf, vol, session), conf=60 vs conf=95 → TP/SL différents."""
    r = _resolver(tmp_path)
    low = r.tp_sl_for(_ctx(vol_regime="NORMAL", timeframe="M1", confiance=60))
    high = r.tp_sl_for(_ctx(vol_regime="NORMAL", timeframe="M1", confiance=95))
    assert low != high
    # conf<70 : TP réduit, SL élargi. conf>=90 : TP élargi, SL réduit.
    assert high[0] > low[0]   # TP plus grand en haute confiance
    assert high[1] < low[1]   # SL plus serré en haute confiance


def test_session_multiplier_sydney(tmp_path):
    """session=sydney → TP/SL réduits de 30% vs london (mult 1.0)."""
    r = _resolver(tmp_path)
    lon = r.tp_sl_for(_ctx(session="london", vol_regime="NORMAL", timeframe="M5"))
    syd = r.tp_sl_for(_ctx(session="sydney", vol_regime="NORMAL", timeframe="M5"))
    assert syd[0] == pytest.approx(lon[0] * 0.7, rel=1e-6)
    assert syd[1] == pytest.approx(lon[1] * 0.7, rel=1e-6)


def test_session_multiplier_overlap(tmp_path):
    """session=overlap → TP/SL augmentés de 10% vs london."""
    r = _resolver(tmp_path)
    lon = r.tp_sl_for(_ctx(session="london", vol_regime="NORMAL", timeframe="M5"))
    ovl = r.tp_sl_for(_ctx(session="overlap", vol_regime="NORMAL", timeframe="M5"))
    assert ovl[0] == pytest.approx(lon[0] * 1.1, rel=1e-6)
    assert ovl[1] == pytest.approx(lon[1] * 1.1, rel=1e-6)


def test_resolve_returns_exit_reason(tmp_path):
    """Chaque résolution retourne un exit_reason cohérent."""
    r = _resolver(tmp_path)
    ctx = _ctx(vol_regime="NORMAL", timeframe="M1", confiance=80, session="london")
    tp, sl = r.tp_sl_for(ctx)  # (12, 15)
    assert r.resolve({"pips_simulated": tp + 5}, ctx).exit_reason == "tp"
    assert r.resolve({"pips_simulated": -(sl + 5)}, ctx).exit_reason == "sl"
    assert r.resolve({"pips_simulated": 3.0}, ctx).exit_reason == "horizon"
    assert r.resolve({"pips_simulated": None}, ctx).exit_reason == "timeout"


def test_calibrate_from_history_runs(tmp_path):
    """Avec une DB factice, calibrate_from_history(7) retourne une table non vide."""
    db = tmp_path / "hist.db"
    _seed_decisions(db, [("M1", "range_calme", p) for p in (5, 6, 7, 20, -3, -2)])
    r = PaperTradeResolver(db_path=str(db))
    table = r.calibrate_from_history(7)
    assert isinstance(table, dict)
    assert len(table) > 0
    assert ("M1", "LOW") in table


def test_calibrate_table_improves_wr(tmp_path):
    """Après calibrate, le score sur l'échantillon test est >= score initial."""
    db = tmp_path / "hist.db"
    # Distribution où un TP serré est nettement meilleur : beaucoup de petits
    # gains (+6..+9) et quelques grosses pertes tronquées par un SL serré.
    pips = [6, 7, 8, 9, 6, 7, 8, 9, -3, -4, -30, -40]
    _seed_decisions(db, [("M5", "range_calme", p) for p in pips])
    r = PaperTradeResolver(db_path=str(db))
    key = ("M5", "LOW")
    base_tp, base_sl = r.get_table()[key]
    base_score = PaperTradeResolver._score_table_entry([float(p) for p in pips], base_tp, base_sl)
    table = r.calibrate_from_history(30)
    new_tp, new_sl = table[key]
    new_score = PaperTradeResolver._score_table_entry([float(p) for p in pips], new_tp, new_sl)
    assert new_score >= base_score


def test_set_table_overrides_default(tmp_path):
    """set_table({("M1","LOW"):(5,-5)}) est respecté par tp_sl_for."""
    r = _resolver(tmp_path)
    r.set_table({("M1", "LOW"): (5.0, 5.0)})
    # conf=80 (pas d'ajustement), session london (mult 1.0) → tel quel.
    tp, sl = r.tp_sl_for(_ctx(vol_regime="LOW", timeframe="M1", confiance=80, session="london"))
    assert (tp, sl) == (5.0, 5.0)


def test_resolve_handles_zero_pips(tmp_path):
    """pips_simulated=0 → is_win=0, exit_reason horizon (0 n'est pas un gain)."""
    r = _resolver(tmp_path)
    ctx = _ctx(vol_regime="NORMAL", timeframe="M1", confiance=80)
    out = r.resolve({"pips_simulated": 0.0}, ctx)
    assert out.is_win == 0
    assert out.exit_reason == "horizon"


def test_resolve_handles_extreme_vol(tmp_path):
    """vol=EXTREME → TP/SL = HIGH × 1.5."""
    r = _resolver(tmp_path)
    high = r.tp_sl_for(_ctx(vol_regime="HIGH", timeframe="M1", confiance=80, session="london"))
    extreme = r.tp_sl_for(_ctx(vol_regime="EXTREME", timeframe="M1", confiance=80, session="london"))
    assert extreme[0] == pytest.approx(high[0] * 1.5, rel=1e-6)
    assert extreme[1] == pytest.approx(high[1] * 1.5, rel=1e-6)


def test_resolver_is_deterministic(tmp_path):
    """2 appels successifs avec même input → même output."""
    r = _resolver(tmp_path)
    ctx = _ctx(vol_regime="HIGH", timeframe="M15", confiance=92, session="overlap")
    a = r.resolve({"pips_simulated": 33.0}, ctx)
    b = r.resolve({"pips_simulated": 33.0}, ctx)
    assert a == b


def test_resolve_unknown_context_uses_fallback(tmp_path):
    """tf/vol inconnus → table de repli (M1, NORMAL), pas de crash (R6)."""
    r = _resolver(tmp_path)
    tp, sl = r.tp_sl_for(_ctx(vol_regime="ZZZ", timeframe="XX", confiance=80, session="london"))
    assert (tp, sl) == (12.0, 15.0)  # FALLBACK_KEY (M1, NORMAL)


def test_calibrate_missing_db_returns_current_table(tmp_path):
    """DB absente → calibrate retourne la table courante inchangée (R6)."""
    r = PaperTradeResolver(db_path=str(tmp_path / "nope.db"))
    assert r.calibrate_from_history(30) == r.get_table()


# ── Helper : DB factice `decisions` ────────────────────────────────

def _seed_decisions(db_path, rows):
    """rows = list[(timeframe, regime_type, resolution_pips)]. resolved_at=now."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE decisions (
            timeframe TEXT, regime_type TEXT,
            resolution_pips REAL, resolved_at TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO decisions (timeframe, regime_type, resolution_pips, resolved_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        rows,
    )
    conn.commit()
    conn.close()
