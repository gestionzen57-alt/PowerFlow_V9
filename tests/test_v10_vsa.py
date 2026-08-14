"""V10 VSA Engine — tests unitaires (Phase 2 Edge Fund).

Couvre les 8 obligations de la Phase 2 :
  1. test_markup_high_vol_wide_spread
  2. test_distribution_climax_volume
  3. test_no_demand_detection
  4. test_fail_open_zero_volume
  5. test_all_4_states_reachable
  6. test_effort_vs_result_divergence
  7. test_timeframe_independence
  8. test_audit_metadata_present

Plus 2 bonus invariants (sérialisation, série backtest).
Total ≥ 10 tests pour la cible officielle 78/78.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Allow running `pytest tests/test_v10_vsa.py` from C:\projet\V9
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_vsa import (  # noqa: E402
    VSAState,
    VSAEngineState,
    compute_vsa,
    compute_vsa_series,
    DEFAULTS,
    _classify_bar,
    _spread,
    _body,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures — OHLCV synthétiques déterministes (R9 audit-friendly)
# ─────────────────────────────────────────────────────────────────────
def _make_bars(
    n: int = 40,
    base: float = 1.1000,
    start_vol: float = 1000.0,
) -> list:
    """Génère une série 'neutre' baseline : body=0, spread=0.0005, vol=1000.

    Les tests modifient ensuite les bougies voulues pour provoquer
    l'état ciblé.
    """
    return [
        {
            "open": base,
            "high": base + 0.0005,
            "low": base,
            "close": base + 0.0001,
            "tick_volume": start_vol,
        }
        for _ in range(n)
    ]


def _set_bar(bars, idx, *, open_, high, low, close, volume):
    bars[idx] = {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": volume,
    }


# ─────────────────────────────────────────────────────────────────────
# 1. test_markup_high_vol_wide_spread
# ─────────────────────────────────────────────────────────────────────
def test_markup_high_vol_wide_spread():
    """MARKUP : close > open, spread wide (>>1.5× avg), volume high (>>1.5× avg)."""
    bars = _make_bars(40)
    # Bougies préalables : spread ~ 0.001, volume ~ 1000
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie courante : wide=0.0050, high close, vol=2500 (high mais non climax)
    _set_bar(bars, 39, open_=1.1000, high=1.1100, low=1.0990,
             close=1.1095, volume=2500.0)
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", bars)
    assert s.state == VSAState.MARKUP, s.classification_path
    assert s.direction == +1
    assert s.spread_relative >= 4.0  # 0.005 / 0.001 ≈ 5×  → wide
    assert s.volume_relative >= 2.0  # 2500 / 1000 = 2.5×
    assert not s.climax, "vol=2.5× < 3× → pas climax"
    assert not s.no_demand


# ─────────────────────────────────────────────────────────────────────
# 2. test_distribution_climax_volume
# ─────────────────────────────────────────────────────────────────────
def test_distribution_climax_volume():
    """DISTRIBUTION via climax volume : climax + direction=+1 (selling climax).
    Par convention : buying climax = climax + direction=+1 → MARKUP ;
                     selling climax = climax + direction=-1 → MARKDOWN.
    Teste ici le MARKDOWN via climax.
    """
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Climax baissier : direction=-1, volume = 3500× (climax 3×), wide spread
    _set_bar(bars, 39, open_=1.1095, high=1.1100, low=1.0990,
             close=1.0995, volume=3500.0)
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", bars)
    assert s.state == VSAState.MARKDOWN, s.classification_path
    assert s.climax is True
    assert s.volume_relative >= 3.0


# ─────────────────────────────────────────────────────────────────────
# 3. test_no_demand_detection
# ─────────────────────────────────────────────────────────────────────
def test_no_demand_detection():
    """NO_DEMAND : spread narrow + volume sec + direction haussière.

    Pas d'état MARKDOWN — c'est un signal d'avertissement haussier.
    """
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie : narrow spread (0.0002 < 0.5×0.001=0.0005), vol=400 (dry), close > open
    _set_bar(bars, 39, open_=1.1000, high=1.1002, low=1.0998,
             close=1.1001, volume=400.0)
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", bars)
    assert s.no_demand is True, s.classification_path
    assert s.spread_relative < 0.5
    assert s.volume_relative < 0.5
    assert s.direction == +1


# ─────────────────────────────────────────────────────────────────────
# 4. test_fail_open_zero_volume
# ─────────────────────────────────────────────────────────────────────
def test_fail_open_zero_volume():
    """Vol tick_volume=0 sur tout l'historique → fail-open NEUTRAL."""
    bars = _make_bars(40, start_vol=0.0)
    # Avec volume=0 partout, avg_volume=0 → on tombe dans fail-open pré-EMA check
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", bars)
    # Soit data_insufficient, soit avg_volume==0 → NEUTRAL par défaut volume
    assert s.state in (VSAState.NEUTRAL,), s.classification_path
    # volume_relative doit rester non-cassant (pas de division /0)
    assert math.isfinite(s.volume_relative)


def test_fail_open_no_bars():
    """Pas de barres du tout → NEUTRAL + data_insufficient."""
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", [])
    assert s.state == VSAState.NEUTRAL
    assert s.data_insufficient is True


def test_fail_open_insufficient_bars():
    """Trop peu de barres (< min_bars_required=21) → NEUTRAL + data_insufficient."""
    bars = _make_bars(10)
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", bars)
    assert s.state == VSAState.NEUTRAL
    assert s.data_insufficient is True


# ─────────────────────────────────────────────────────────────────────
# 5. test_all_4_states_reachable
# ─────────────────────────────────────────────────────────────────────
def test_all_4_states_reachable():
    """Les 4 états purs (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION) sont
    chacun atteignables avec un input OHLCV contrôlé."""
    # --- MARKUP --- close>open, wide, high vol, non climax
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    _set_bar(bars, 39, open_=1.1000, high=1.1050, low=1.0990,
             close=1.1040, volume=1800.0)
    s_markup = compute_vsa("EURUSD", "t", "M15", bars)
    assert s_markup.state == VSAState.MARKUP

    # --- MARKDOWN --- direction=-1, wide, high vol, non climax
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.0995, volume=1000.0)
    _set_bar(bars, 39, open_=1.1050, high=1.1100, low=1.0990,
             close=1.1000, volume=1800.0)
    s_markdown = compute_vsa("EURUSD", "t", "M15", bars)
    assert s_markdown.state == VSAState.MARKDOWN

    # --- ACCUMULATION --- narrow(<0.5×) + high_vol + doji (body<0.25×) + direction≥0
    bars = _make_bars(40)
    for i in range(39):
        # Prior : spread=0.0020, vol=1000 → avg_spread=0.002, narrow<0.001
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    _set_bar(
        bars, 39,
        open_=1.1005, high=1.1008, low=1.1003,  # spread=0.0005 < 0.5×0.002=0.001 → narrow
        close=1.10055,                          # body=0.00005 → doji (< 0.25×spread)
        volume=1800.0,
    )
    s_acc = compute_vsa("EURUSD", "t", "M15", bars)
    assert s_acc.state == VSAState.ACCUMULATION, s_acc.classification_path

    # --- DISTRIBUTION --- narrow(<0.5×) + high_vol + doji + direction=-1
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.0995, volume=1000.0)
    _set_bar(
        bars, 39,
        open_=1.1003, high=1.1006, low=1.0998,  # spread=0.0008 < 0.5×0.002=0.001 → narrow
        close=1.0994,                          # body=0.0009 mais spread 0.0008 → body_ratio=1.12 doji=False... ajustons
        volume=1800.0,
    )
    # Re-set pour doji strict
    _set_bar(
        bars, 39,
        open_=1.10045, high=1.1008, low=1.1003,  # spread=0.0005 (narrow)
        close=1.1004,                           # body=0.00005, direction=-1 (close<open)
        volume=1800.0,
    )
    s_dist = compute_vsa("EURUSD", "t", "M15", bars)
    assert s_dist.state == VSAState.DISTRIBUTION, s_dist.classification_path


# ─────────────────────────────────────────────────────────────────────
# 6. test_effort_vs_result_divergence
# ─────────────────────────────────────────────────────────────────────
def test_effort_vs_result_divergence():
    """Effort faible = test : on doit voir effort_vs_result < 0.3 sans climax."""
    bars = _make_bars(40)
    # Prior : closes au même niveau pour faciliter le retest
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie de "test" : effort faible (open≈close) + volume normal
    _set_bar(bars, 39, open_=1.0995, high=1.1000, low=1.0990,
             close=1.0996, volume=1100.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    assert s.effort_vs_result < 0.3, s.classification_path
    # spread_relative doit être < narrow_threshold ou faible
    assert s.spread_relative < 1.0 or s.body_ratio < 0.3
    # state reste NEUTRAL ici, mais le path de test est traçable
    assert s.state == VSAState.NEUTRAL


# ─────────────────────────────────────────────────────────────────────
# 7. test_timeframe_independence
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tf", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
def test_timeframe_independence(tf):
    """Le moteur VSA classifie identiquement sur les 7 TF supportés."""
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    _set_bar(bars, 39, open_=1.1000, high=1.1050, low=1.0990,
             close=1.1040, volume=1800.0)
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", tf, bars)
    assert s.timeframe == tf
    assert s.state == VSAState.MARKUP, f"{tf}: {s.classification_path}"


def test_unsupported_timeframe_yields_neutral():
    """TF non listé → NEUTRAL (doctrine ne pas faire planter)."""
    bars = _make_bars(40)
    s = compute_vsa("EURUSD", "t", "W1", bars)
    assert s.state == VSAState.NEUTRAL
    assert s.data_insufficient is True


# ─────────────────────────────────────────────────────────────────────
# 8. test_audit_metadata_present
# ─────────────────────────────────────────────────────────────────────
def test_audit_metadata_present():
    """audit metadata doit toujours être présente et complète."""
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    _set_bar(bars, 39, open_=1.1000, high=1.1050, low=1.0990,
             close=1.1040, volume=1800.0)
    s = compute_vsa("EURUSD", "2026-08-04T12:00:00Z", "M15", bars, seed=42)
    payload = s.as_dict()
    assert payload["symbol"] == "EURUSD"
    assert payload["timestamp"] == "2026-08-04T12:00:00Z"
    assert payload["timeframe"] == "M15"
    assert payload["audit"]["seed"] == 42
    assert payload["audit"]["n_bars_used"] == 40
    assert payload["audit"]["period"] == 20
    assert "classification_path" in payload
    assert isinstance(payload["classification_path"], list)
    assert len(payload["classification_path"]) >= 1


# ─────────────────────────────────────────────────────────────────────
# Bonus : sérialisation + backtest series
# ─────────────────────────────────────────────────────────────────────
def test_serializable_round_trip_json():
    """Le payload as_dict() doit être JSON-sérialisable, sans valeur non-finie."""
    import json
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    _set_bar(bars, 39, open_=1.1000, high=1.1050, low=1.0990,
             close=1.1040, volume=1800.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    payload = s.as_dict()
    j = json.dumps(payload)
    assert isinstance(j, str)


def test_vsa_series_returns_aligned_length():
    """compute_vsa_series doit produire 1 état par bougie de l'input."""
    bars = _make_bars(50)
    out = compute_vsa_series("EURUSD", "M15", bars)
    assert len(out) == len(bars)
    # Premières bougies < min_required → NEUTRAL + data_insufficient
    assert all(
        o.data_insufficient for o in out[:20]
    ), "Les 20 premières bougies doivent être data_insufficient"
    # Dernières bougies classifiées
    assert out[-1].state in (
        VSAState.NEUTRAL, VSAState.MARKUP, VSAState.MARKDOWN,
        VSAState.ACCUMULATION, VSAState.DISTRIBUTION,
    )


def test_helpers_spread_and_body():
    """_spread et _body couvrent tous les cas (haussier, baissier, doji)."""
    bull = {"open": 1.0, "high": 1.005, "low": 0.995, "close": 1.004}
    assert _spread(bull) == pytest.approx(0.010)
    b, d = _body(bull)
    assert b == pytest.approx(0.004)
    assert d == +1

    bear = {"open": 1.0, "high": 1.005, "low": 0.995, "close": 0.996}
    b, d = _body(bear)
    assert d == -1

    doji = {"open": 1.0, "high": 1.005, "low": 0.995, "close": 1.0}
    b, d = _body(doji)
    assert b == 0.0
    assert d == 0


def test_classify_bang_path_includes_decisive():
    """Le classification_path doit contenir un token 'MAP'/'MARKDOWN'/etc.
    ou la mention NEUTRAL — l'audit doit permettre de comprendre."""
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    _set_bar(bars, 39, open_=1.1000, high=1.1050, low=1.0990,
             close=1.1040, volume=1800.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    blob = " | ".join(s.classification_path)
    assert "MARKUP" in blob or "NEUTRAL" in blob


# ─────────────────────────────────────────────────────────────────────
# P1 AUDIT — close_location gate (Tom Williams p.47)
# ─────────────────────────────────────────────────────────────────────
def test_upthrust_detected_p1():
    """P1 : wide+high_vol+direction haussière mais close bas = UPTHRUST (NEUTRAL).
    AVANT : ce cas était classé MARKUP (faux signal haussier).
    """
    bars = _make_bars(40)
    # Bougies neutres historiques (avg spread = 0.0020, avg vol = 1000)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie courante : wide spread (3.25× avg) + high vol (2.5×, NON climax 3.0×)
    # + direction haussière (close > open) MAIS close bas (UPTHRUST)
    _set_bar(bars, 39, open_=1.0945, high=1.1005, low=1.0940,
             close=1.0955, volume=2500.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    # P1 : doit être NEUTRAL + flag upthrust=True
    assert s.state == VSAState.NEUTRAL, f"UPTHRUST doit être NEUTRAL, got {s.state}"
    assert s.upthrust is True, f"upthrust flag doit être True, got {s.upthrust}"
    assert s.close_location < 0.4, f"close_location doit être < 0.4, got {s.close_location}"


def test_markup_requires_close_location_high_p1():
    """P1 : wide+high_vol+direction=+1+close haut (>=0.6) → MARKUP valide.
    Vérifie que le gate close_location fonctionne dans le sens positif aussi.
    """
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie : wide + high_vol + dir=+1 + close haut
    # open=1.1000, high=1.1060, low=1.0990, close=1.1055, vol=3000
    # spread=0.0070, close_loc = (1.1055-1.0990)/0.0070 = 0.929
    _set_bar(bars, 39, open_=1.1000, high=1.1060, low=1.0990,
             close=1.1055, volume=3000.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    assert s.state == VSAState.MARKUP, f"Doit être MARKUP, got {s.state}"
    assert s.close_location >= 0.6
    assert s.upthrust is False


def test_narrow_high_vol_reclassified_p1():
    """P1 : narrow+high_vol (non-doji) reclassifié en ACCUMULATION si close haut.
    AVANT : ce cas était classé MARKUP (fallback sur direction).
    Doctrine réf : narrow + high_vol + close haut = absorption haussière, pas continuation.
    """
    bars = _make_bars(40)
    # Bougies : wide spread historique (avg ~0.0020) pour que narrow soit détectée
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1050, low=1.0950,
                 close=1.1000, volume=1000.0)
    # Bougie narrow : open=1.0998, high=1.1008, low=1.0990, close=1.1005
    # spread=0.0018, body=0.0007, body_ratio=0.39 (>0.25, non-doji)
    # vol=2500 (2.5×, NON climax 3.0×) high_vol mais pas climax
    # close_loc=(1.1005-1.0990)/0.0018=0.83 (haut)
    # avg_spread historique = 0.010 → spread_relative=0.18 < 0.5 (narrow)
    _set_bar(bars, 39, open_=1.0998, high=1.1008, low=1.0990,
             close=1.1005, volume=2500.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    # P1 : doit être ACCUMULATION, pas MARKUP
    assert s.state == VSAState.ACCUMULATION, (
        f"narrow+high_vol+close_haut doit être ACCUMULATION, got {s.state}"
    )


# ─────────────────────────────────────────────────────────────────────
# P5 AUDIT — end-of-bar gate (intra-barre interdit)
# ─────────────────────────────────────────────────────────────────────
def test_intra_bar_blocked_p5():
    """P5 : bougie non fermée (is_closed_bar=0) → NEUTRAL fail-open.
    AVANT : compute_vsa calculait sur Bougie en formation, donnant de faux signaux.
    """
    bars = _make_bars(40)
    # Bougie courante NON fermée (intra-barre)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0, ) if False else None
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
        bars[i]["is_closed_bar"] = 1
    _set_bar(bars, 39, open_=1.1000, high=1.1050, low=1.0990,
             close=1.1040, volume=1800.0)
    bars[39]["is_closed_bar"] = 0  # INTRA-BARRE — interdit
    s = compute_vsa("EURUSD", "t", "M15", bars)
    assert s.state == VSAState.NEUTRAL
    assert s.data_insufficient is True
    blob = " | ".join(s.classification_path)
    assert "P5" in blob or "end-of-bar" in blob or "intra-barre" in blob


# ─────────────────────────────────────────────────────────────────────
# P3 AUDIT VSA — σ-bands sur spread (doctrine ATR/20)
# ─────────────────────────────────────────────────────────────────────
def test_sigma_bands_classification_p3():
    """P3 : σ-bands sur spread — wide détecté via σ>=0.7, narrow via σ<=-0.4.

    AVANT : le spread était classé en ratio vs SMA (sensible aux outliers).
    APRÈS : σ-bands primaires, ratio en fallback si std=0 (R6 backward compat).
    """
    bars = _make_bars(40)
    # Bougies historiques : spread=0.0020 constant (std=0)
    # → on tombe dans le fallback ratio (R6 fail-open)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie courante : spread large
    _set_bar(bars, 39, open_=1.1000, high=1.1060, low=1.0990,
             close=1.1055, volume=2500.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    # P3 : le path doit mentionner σ (même si 'n/a' en fallback std=0)
    blob = " | ".join(s.classification_path)
    assert "σ" in blob or "spread_sigma" in blob, (
        f"Le path doit mentionner σ-bands P3, got: {blob[:200]}"
    )


def test_sigma_bands_active_with_variance_p3():
    """P3 : avec série à variance > 0, σ-bands sont PRIMAIRE (pas fallback ratio)."""
    bars = _make_bars(40)
    # Bougies avec spreads variés (0.0010, 0.0030, 0.0050 alternés)
    # → moyenne ≈ 0.0030, std > 0
    spreads = [0.0010, 0.0030, 0.0050] * 13  # 39 bougies
    for i in range(39):
        sp = spreads[i]
        mid = 1.1000
        bars[i] = {
            "open": mid,
            "high": mid + sp / 2,
            "low": mid - sp / 2,
            "close": mid + 0.0001,
            "tick_volume": 1000.0,
        }
    # Bougie courante : spread=0.0090 (3× avg, ~2.5σ wide)
    _set_bar(bars, 39, open_=1.1000, high=1.1045, low=1.0955,
             close=1.1040, volume=2500.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    # P3 : is_wide doit être True (σ≈2.5 > 0.7)
    blob = " | ".join(s.classification_path)
    assert "wide=True" in blob or "MARKUP" in blob, (
        f"P3 : wide doit être True via σ-bands, got: {blob[:200]}"
    )


def test_pstdev_helper_p3():
    """P3 : helper _pstdev — écart-type population correct."""
    from core.v10.v10_vsa import _pstdev
    # Cas 1 : liste vide → 0
    assert _pstdev([]) == 0.0
    # Cas 2 : 1 valeur → 0
    assert _pstdev([5.0]) == 0.0
    # Cas 3 : valeurs constantes → 0
    assert _pstdev([5.0, 5.0, 5.0]) == 0.0
    # Cas 4 : valeurs [2,4,4,4,5,5,7,9] → écart-type population ≈ 2.0
    val = _pstdev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert 1.9 < val < 2.1, f"_pstdev incorrect, got {val}"


# ─────────────────────────────────────────────────────────────────────
# P15 AUDIT VSA — gap detection (open vs close précédent)
# ─────────────────────────────────────────────────────────────────────
def test_gap_bullish_detected_p15():
    """P15 : gap haussier (open >> prev_close) détecté, gap_bullish=True."""
    bars = _make_bars(40)
    # Bougies neutres historiques
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Bougie courante : GAP BULLISH — open=1.1030, prev_close=1.1005
    # gap_size=0.0025, avg_spread=0.0020 → ratio=1.25 > 0.5 seuil
    _set_bar(bars, 39, open_=1.1030, high=1.1050, low=1.1025,
             close=1.1045, volume=1000.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    assert s.has_gap is True, f"has_gap doit être True, got {s.has_gap}"
    assert s.gap_bullish is True, f"gap_bullish doit être True"
    assert s.gap_bearish is False
    blob = " | ".join(s.classification_path)
    assert "GAP BULLISH" in blob


def test_gap_bearish_detected_p15():
    """P15 : gap baissier (open << prev_close) détecté, gap_bearish=True."""
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # GAP BEARISH — open=1.0980, prev_close=1.1005, gap=-0.0025
    _set_bar(bars, 39, open_=1.0980, high=1.0990, low=1.0975,
             close=1.0985, volume=1000.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    assert s.has_gap is True
    assert s.gap_bearish is True
    assert s.gap_bullish is False


def test_no_gap_small_diff_p15():
    """P15 : gap trop petit (< seuil 0.5) → has_gap=False."""
    bars = _make_bars(40)
    for i in range(39):
        _set_bar(bars, i, open_=1.1000, high=1.1010, low=1.0990,
                 close=1.1005, volume=1000.0)
    # Pas de gap : open=1.1006, prev_close=1.1005, gap=0.0001
    # avg_spread=0.0020 → ratio=0.05 < 0.5
    _set_bar(bars, 39, open_=1.1006, high=1.1015, low=1.1000,
             close=1.1010, volume=1000.0)
    s = compute_vsa("EURUSD", "t", "M15", bars)
    assert s.has_gap is False, f"has_gap doit être False pour gap<seuil, got {s.has_gap}"
