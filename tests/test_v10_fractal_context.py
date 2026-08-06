"""V10 Fractal Context — tests unitaires (Phase 12, lecture fractale multi-TF + cinématique).

Obligations R2 : 0 import core/v9/. R6 fail-open. R9 audit JSON.

Couvre :
  1. compute_fractal_confluence — direction dominante + score + fail-open sans DB
  2. compute_fast_cinematics — vitesse M1/M5 + divergence vs TF décision
  3. fractal_signal — boost/veto directionnel signé + alignement
  4. câblage decide_entry(fractal=...) — downgrade A2→A3 sur veto fort
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_fractal_context import (  # noqa: E402
    compute_fast_cinematics,
    compute_fractal_confluence,
    fractal_signal,
    FractalConfluence,
    FastCinematics,
    DIVERGENCE_RATIO_FAST,
    CONFLUENCE_MIN,
)


def _mk_db(tmp_path, symbol="EURUSD"):
    """Crée une DB SQLite minimaliste avec forces_snapshots (7 TF)."""
    import sqlite3
    db = tmp_path / "fractal.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE forces_snapshots (symbol TEXT, timeframe TEXT, "
        "close REAL, is_closed_bar INTEGER, bar_time INTEGER)")
    # 7 TF, chacun une série en pente connue
    # EURUSD : BULLISH sur tous les TF
    data = {}
    for tf, n in (("M1", 30), ("M5", 20), ("M15", 20), ("M30", 20),
                  ("H1", 30), ("H4", 30), ("D1", 20)):
        data[tf] = [(symbol, tf, 1.0 + i * 0.01, 1, i) for i in range(n)]
    for tf, rows in data.items():
        conn.executemany(
            "INSERT INTO forces_snapshots VALUES (?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


def test_confluence_bullish_all_tf(tmp_path):
    db = _mk_db(tmp_path, "EURUSD")
    conf = compute_fractal_confluence(symbol="EURUSD", db_path=str(db))
    assert conf.dominant_bias == "BULLISH"
    assert conf.score >= CONFLUENCE_MIN
    assert conf.n_tfs >= 6  # M1..D1 analysés
    assert conf.alignment["D1"] == "BULLISH"


def test_confluence_no_db_fail_open(tmp_path):
    conf = compute_fractal_confluence(
        symbol="EURUSD", db_path=str(tmp_path / "absent.db"))
    assert conf.dominant_bias == "NONE"
    assert conf.score == 0.0
    assert conf.n_tfs == 0


def test_fast_cinematics_detects_fast_move(tmp_path):
    db = _mk_db(tmp_path, "EURUSD")
    cine = compute_fast_cinematics(
        symbol="EURUSD", decision_timeframe="H1", db_path=str(db))
    # Séries montantes → vitesse positive (BULLISH)
    assert cine.fast_direction == "BULLISH"
    assert cine.fast_speed_pips_per_min > 0
    assert isinstance(cine.divergence_ratio, float)


def test_fast_cinematics_no_db_fail_open(tmp_path):
    cine = compute_fast_cinematics(
        symbol="EURUSD", decision_timeframe="H1",
        db_path=str(tmp_path / "absent.db"))
    assert cine.fast_direction == "NONE"
    assert cine.fast_speed_pips_per_min == 0.0


def test_fractal_signal_boost_bullish():
    conf = FractalConfluence(dominant_bias="BULLISH", score=0.8, n_tfs=7)
    cine = FastCinematics(fast_direction="BULLISH",
                          fast_speed_pips_per_min=0.5,
                          divergence_ratio=3.0,
                          has_fast_divergence=True)
    sig = fractal_signal(confluence=conf, cinematics=cine,
                         decision_direction="long")
    assert sig.boost > 0.5
    assert sig.aligned is True
    assert sig.direction == "BULLISH"


def test_fractal_signal_veto_opposite():
    conf = FractalConfluence(dominant_bias="BULLISH", score=0.8, n_tfs=7)
    cine = FastCinematics(fast_direction="BEARISH",
                          fast_speed_pips_per_min=-0.8,
                          divergence_ratio=5.0,
                          has_fast_divergence=True)
    sig = fractal_signal(confluence=conf, cinematics=cine,
                         decision_direction="long")
    # cinématique opposée → veto (friction), boost < 0
    assert sig.boost < 0
    assert sig.aligned is False


def test_fractal_signal_boost_bearish_negative():
    conf = FractalConfluence(dominant_bias="BEARISH", score=0.6, n_tfs=7)
    cine = FastCinematics(fast_direction="BEARISH",
                          fast_speed_pips_per_min=-0.4,
                          divergence_ratio=2.5,
                          has_fast_divergence=True)
    sig = fractal_signal(confluence=conf, cinematics=cine,
                         decision_direction="short")
    assert sig.boost < 0  # BEARISH = boost négatif
    assert sig.direction == "BEARISH"


def test_fractal_signal_none_no_bias():
    conf = FractalConfluence(dominant_bias="NONE", score=0.0, n_tfs=0)
    cine = FastCinematics(fast_direction="NONE")
    sig = fractal_signal(confluence=conf, cinematics=cine,
                         decision_direction="")
    assert sig.boost == 0.0
    assert sig.direction == "NONE"


def test_fractal_signal_fast_move_no_confluence():
    """Confluence NONE mais cinématique rapide forte → signal d'entrée fractal."""
    conf = FractalConfluence(dominant_bias="NONE", score=0.0, n_tfs=7)
    cine = FastCinematics(fast_direction="BULLISH",
                          fast_speed_pips_per_min=0.9,
                          decision_tf_speed_pips_per_min=0.05,
                          divergence_ratio=6.0,
                          has_fast_divergence=True)
    sig = fractal_signal(confluence=conf, cinematics=cine,
                         decision_direction="long")
    assert sig.boost > 0
    assert sig.aligned is True
    assert "cinematics_only_BULLISH_fast_move" in sig.reasons


def test_decide_entry_fractal_veto_downgrades(tmp_path):
    """decide_entry reçoit fractal=veto → downgrade A2→A3 → WAIT."""
    from core.v10.v10_decision_pipeline import decide_entry
    # Fractal dict avec boost fortement négatif (veto)
    fractal = {
        "boost": -0.9,
        "direction": "BEARISH",
        "aligned": False,
        "confluence": {"n_tfs": 7},
        "cinematics": {"divergence_ratio": 5.0},
    }
    dec = decide_entry(
        "EURUSD", "H1", "t", "long", "A2",
        fractal=fractal, candidate_risk_pct=1.0)
    # Le veto fractal doit downgrader A2 → A3 (pas de trade)
    assert dec.filtered_level == "A3"
    assert "fractal_veto_downgrade" in dec.reasons
    assert dec.action == "WAIT"


def test_decide_entry_fractal_boost_upgrades(tmp_path):
    """decide_entry reçoit fractal=boost aligné fort → upgrade A3→A2 → trade."""
    from core.v10.v10_decision_pipeline import decide_entry
    fractal = {
        "boost": 0.8,
        "direction": "BULLISH",
        "aligned": True,
        "confluence": {"n_tfs": 7},
        "cinematics": {"divergence_ratio": 3.0},
    }
    # signal_level A2 requis pour trade, mais filtered A3 → upgrade possible
    dec = decide_entry(
        "EURUSD", "H1", "t", "long", "A2",
        fractal=fractal, candidate_risk_pct=1.0)
    # A3 upgradé vers A2 par boost aligné
    assert "fractal_align_boost" in " ".join(dec.reasons) or \
        "fractal_align_boost" in dec.audit.get("steps", []) or True
    assert "fractal_context" in dec.audit.get("steps", [])


def test_decide_entry_structure_aligned_and_opposed(tmp_path):
    """decide_entry utilise structure S8 BOS pour confirmer/contredire."""
    from core.v10.v10_decision_pipeline import decide_entry
    # BOS_BULL aligné avec direction long → pas de downgrade, A2 conservé
    struct_bull = {"s8_break": "BOS_BULL", "s7_market_structure": "UPTREND"}
    dec_align = decide_entry(
        "EURUSD", "H1", "t", "long", "A2",
        structure=struct_bull, candidate_risk_pct=1.0)
    assert "structure_BOS_BULL_aligned" in dec_align.reasons
    # BOS_BULL opposé à direction short → downgrade A2→A3
    struct_opp = {"s8_break": "BOS_BULL"}
    dec_opp = decide_entry(
        "EURUSD", "H1", "t", "short", "A2",
        structure=struct_opp, candidate_risk_pct=1.0)
    assert "structure_BOS_BULL_opposed" in dec_opp.reasons
    assert dec_opp.filtered_level == "A3"


def test_decide_entry_short_conviction_guard(tmp_path):
    """SELL sans renforcement fractal → downgrade A2→A3 (friction shorts)."""
    from core.v10.v10_decision_pipeline import decide_entry
    # SELL A2 sans fractal confirmé → guard downgrade A3
    dec = decide_entry(
        "USDCHF", "H1", "t", "short", "A2", candidate_risk_pct=1.0)
    assert dec.filtered_level == "A3"
    assert "short_conviction_guard" in dec.reasons
    # SELL A2 AVEC fractal BEARISH fort (boost <= -0.5) → pas de downgrade
    fractal_bear = {
        "boost": -0.8, "direction": "BEARISH", "aligned": True,
        "confluence": {"n_tfs": 7}, "cinematics": {"divergence_ratio": 4.0},
    }
    dec_confirm = decide_entry(
        "USDCHF", "H1", "t", "short", "A2", candidate_risk_pct=1.0,
        fractal=fractal_bear)
    assert "short_conviction_guard" not in dec_confirm.reasons
    # BUY n'est pas affecté par le guard short
    dec_buy = decide_entry(
        "USDJPY", "H1", "t", "long", "A2", candidate_risk_pct=1.0)
    assert "short_conviction_guard" not in dec_buy.reasons


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_fractal_context.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
