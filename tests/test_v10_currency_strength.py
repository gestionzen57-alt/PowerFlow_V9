"""Tests v10_currency_strength — moteur Fatman Hawkeye par devise.

12 tests verts exigés (doctrine R7 tests verts).
Couvre :
  1. Import + constants sanity
  2. Marché neutre (history=None) → scores=50 (fallback neutre)
  3. USD fort directionnel (avec history) → USD > tous
  4. EUR faible (EURUSD baissier) → EUR < USD
  5. Percentile rank monotique (fenêtre 50)
  6. Velocity cohérente avec history windowed
  7. Fail-open : N<min_bars → score=50, dans insufficient
  8. ATR=0 → momentum_normalized retourne (0, 0)
  9. 7 TF supportés
 10. Audit metadata : seed + reproductibilité
 11. Cas manuel ordering faible/fort (GBP faible vs EUR)
 12. Paire manquante (USDCAD) → CAD neutre, USD continue
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10.v10_currency_strength import (  # noqa: E402
    CurrencyStrength,
    compute_currency_strength,
    _ema, _sma, _atr, _percentile_rank, _momentum_normalized, _aggregate_currency,
    DEFAULTS, WINDOW_BARS_BY_TF,
)
from core.v10.v10_currency_pairs import (  # noqa: E402
    PAIRS_USD, CURRENCIES, PAIRS_BY_CURRENCY,
)


# ─────────────────────────────────────────────────────────────────────
# Builders de bars OHLCV synthétiques
# ─────────────────────────────────────────────────────────────────────
def _flat_bars(n: int, price: float = 1.1000, volume: float = 100.0) -> list:
    out = []
    for i in range(n):
        out.append({
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "tick_volume": volume,
            "spread_points": 1.0,
        })
    return out


def _rising_bars(n: int, start: float = 1.1000, step: float = 0.0010, volume: float = 100.0):
    out = []
    for i in range(n):
        c = start + i * step
        out.append({
            "open": c - step / 2,
            "high": c + step / 2,
            "low": c - step / 2,
            "close": c,
            "tick_volume": volume,
            "spread_points": 1.0,
        })
    return out


def _falling_bars(n: int, start: float = 1.2000, step: float = 0.0010, volume: float = 100.0):
    out = []
    for i in range(n):
        c = start - i * step
        out.append({
            "open": c + step / 2,
            "high": c + step / 2,
            "low": c - step / 2,
            "close": c,
            "tick_volume": volume,
            "spread_points": 1.0,
        })
    return out


def _build_usd_strong_fixture(n: int = 100) -> dict:
    """USD fort : paires où USD base montent, où USD quote descendent."""
    return {
        "EURUSD": _falling_bars(n),
        "GBPUSD": _falling_bars(n),
        "USDJPY": _rising_bars(n),
        "USDCHF": _rising_bars(n),
        "AUDUSD": _falling_bars(n),
        "USDCAD": _rising_bars(n),
    }


def _build_neutral_fixture(n: int = 100) -> dict:
    return {p: _flat_bars(n, price=1.0 if p != "USDJPY" else 150.0) for p in PAIRS_USD}


def _build_history_window(seed: int = 0, base: float = 0.0, step: float = 0.001):
    """Helper : history 50 bougies monotone, déterministe."""
    rng = random.Random(seed)
    return {c: [base + step * i + rng.uniform(-0.0005, 0.0005) for i in range(50)] for c in CURRENCIES}


# ─────────────────────────────────────────────────────────────────────
# TESTS
# ─────────────────────────────────────────────────────────────────────
def test_imports_and_constants():
    """Sanity : module importable + dataclass présente + 7 devises trackées."""
    assert CurrencyStrength is not None
    assert callable(compute_currency_strength)
    assert len(CURRENCIES) == 7
    assert DEFAULTS["rank_window"] == 50
    assert DEFAULTS["min_bars"] == 30
    assert WINDOW_BARS_BY_TF["M1"] == 200
    assert WINDOW_BARS_BY_TF["D1"] == 50


def test_zero_market_neutral_score_50():
    """Marché plat SANS history → score=50 (fallback fail-open)."""
    pairs_bars = _build_neutral_fixture(n=100)
    res = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
        history=None,
    )
    assert res.timeframe == "H1"
    assert set(res.scores.keys()) == set(CURRENCIES)
    for cur, score in res.scores.items():
        assert score == 50.0, f"{cur}={score} attendu 50"
    assert res.spread_score == 0.0


def test_usd_strong_dxy_like():
    """USD fort (DXY haussier) + history windowed → USD top score."""
    pairs_bars = _build_usd_strong_fixture(n=100)
    history = _build_history_window(seed=42, base=0.0, step=0.001)
    res = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
        history=history,
    )
    # USD doit être LE top ou parmi le top2
    for cur in CURRENCIES:
        if cur == "USD":
            continue
        assert res.scores["USD"] >= res.scores[cur], \
            f"USD={res.scores['USD']} devrait être >= {cur}={res.scores[cur]}"
    assert res.ranks["USD"] <= 2, f"USD rank={res.ranks['USD']}, attendu top"


def test_eur_weak_dxy_like():
    """EURUSD baissier → EUR < USD."""
    neutral = {p: _flat_bars(100, price=1.0 if p != "USDJPY" else 150.0) for p in PAIRS_USD}
    neutral["EURUSD"] = _falling_bars(100, start=1.2000, step=0.0020)
    history = _build_history_window(seed=42, base=0.0, step=0.001)
    res = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=neutral,
        history=history,
    )
    assert res.scores["EUR"] <= res.scores["USD"], \
        f"EUR={res.scores['EUR']} devrait être <= USD={res.scores['USD']}"


def test_percentile_rank_monotonic():
    """Fenêtre 50 valeurs croissantes : p[0]=0 (exclusif), p[max]=98%, p[>max]=100."""
    window = [i * 1.0 for i in range(50)]
    p0 = _percentile_rank(0.0, window)
    p49 = _percentile_rank(49.0, window)
    p25 = _percentile_rank(25.0, window)
    assert p0 == 0.0, f"p0={p0}"
    assert p49 == 98.0, f"p49={p49} (49 strict < 49.0 sur 50)"
    assert math.isclose(p25, 50.0, abs_tol=1.0), f"p25={p25}"
    # Valeur > max → 100%
    assert _percentile_rank(999.0, window) == 100.0
    # Empty → 50
    assert _percentile_rank(5.0, []) == 50.0


def test_velocity_consistent_with_history():
    """History windowed 50 valeurs monotones → scores attribués + ordering cohérent."""
    history = _build_history_window(seed=42, base=0.0, step=0.001)
    pairs_bars_1 = _build_usd_strong_fixture(n=100)
    res = compute_currency_strength(
        timestamp="2026-08-04T10:00:00Z",
        timeframe="M15",
        pairs_bars=pairs_bars_1,
        history=history,
    )
    # USD fort dans ce scénario
    assert res.scores["USD"] > 50.0, f"USD={res.scores['USD']} devrait être > 50"
    # Scores sont bornés [5..95] (doctrine)
    for cur, score in res.scores.items():
        assert 5.0 <= score <= 95.0, f"{cur}={score} hors bornes"


def test_insufficient_data_returns_neutral_50():
    """N < min_bars → toutes devises dans insufficient_data + score=50."""
    pairs_bars = {p: _rising_bars(10) for p in PAIRS_USD}  # 10 < 30
    res = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
    )
    assert len(res.insufficient_data_currencies) == len(CURRENCIES)
    for ins in res.insufficient_data_currencies:
        assert res.scores[ins] == 50.0


def test_atr_zero_safe_no_division_error():
    """ATR=0 (bougies plates) → momentum_normalized=(0,0) sans crash."""
    bars = _flat_bars(60)  # range=0 → ATR=0
    mom, atr = _momentum_normalized(bars, ema_s=8, ema_l=34, atr_p=14)
    assert mom == 0.0
    assert atr == 0.0


def test_all_7_timeframes_supported():
    """M1/M5/M15/M30/H1/H4/D1 → 7 CurrencyStrength distincts (avec history)."""
    pairs_bars = _build_usd_strong_fixture(n=100)
    history = _build_history_window(seed=42)
    tfs = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
    results = []
    for tf in tfs:
        r = compute_currency_strength(
            timestamp="2026-08-04T12:00:00Z",
            timeframe=tf,
            pairs_bars={p: bars[-50:] if tf == "D1" else bars for p, bars in pairs_bars.items()},
            history=history,
        )
        results.append(r)
    assert len(results) == 7
    for r in results:
        assert len(r.scores) == 7
        assert r.timeframe in tfs
        # history complet → aucune devise insuffisante
        assert len(r.insufficient_data_currencies) == 0, \
            f"{r.timeframe} : insuffisants = {r.insufficient_data_currencies}"


def test_audit_metadata_seed_reproducible():
    """seed=42 → scores identiques sur même input. Métadonnées audit présentes."""
    pairs_bars = _build_usd_strong_fixture(n=100)
    history = _build_history_window(seed=42)
    res1 = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
        history=history,
        seed=42,
    )
    res2 = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
        history=history,
        seed=42,
    )
    assert res1.scores == res2.scores, "Seed devrait rendre les scores identiques"
    assert res1.seed == 42
    assert res1.invert_sign is True
    assert len(res1.pairs_used) == 6
    for pair in PAIRS_USD:
        assert pair in res1.pairs_used, f"{pair} manquant dans pairs_used"

    # as_dict serializable
    d = res1.as_dict()
    assert d["audit"]["seed"] == 42
    assert d["audit"]["n_bars_used"] >= 0
    assert "scores" in d and "ranks" in d and "strongest" in d


def test_known_scenario_strongest_weakest_ordering():
    """Scénario contrôlé : GBP chute fortement (1 cross), tout reste stable → GBP faible."""
    pairs_bars = {p: _flat_bars(100, price=1.0 if p != "USDJPY" else 150.0) for p in PAIRS_USD}
    pairs_bars["GBPUSD"] = _falling_bars(100, start=1.4000, step=0.0030)
    history = _build_history_window(seed=7, base=-0.002, step=0.0001)
    res = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
        history=history,
    )
    # GBP (1 cross, baissier) doit être classé plus faiblement que USD (6 crosses stables)
    assert res.ranks["GBP"] > res.ranks["USD"], \
        f"GBP rank {res.ranks['GBP']} devrait être > USD rank {res.ranks['USD']}"
    # Scores bornés [5..95]
    for cur, score in res.scores.items():
        assert 5.0 <= score <= 95.0, f"{cur}={score} hors bornes"


def test_missing_pair_partial_aggregation():
    """1 paire absente (USDCAD) → CAD neutre insufficient, USD reste trackée via 5 autres."""
    pairs_bars = {p: _rising_bars(100) for p in PAIRS_USD}
    del pairs_bars["USDCAD"]
    history = _build_history_window(seed=42)
    res = compute_currency_strength(
        timestamp="2026-08-04T12:00:00Z",
        timeframe="H1",
        pairs_bars=pairs_bars,
        history=history,
    )
    assert "CAD" in res.insufficient_data_currencies
    assert res.scores["CAD"] == 50.0
    assert "USD" not in res.insufficient_data_currencies
    assert "USDCAD" not in res.pairs_used
    assert "EURUSD" in res.pairs_used
    assert len(res.pairs_used) == 5  # USD + 4 autres crosses trackées
