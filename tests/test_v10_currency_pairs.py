"""Tests v10_currency_pairs — constantes pures de mapping devises.

4 tests verts exigés (doctrine R7 tests verts).
Couvre : signe d'inversion correct pour BASE/QUOTE, fail-open devise
inconnue, complétude des 7 devises, 6 paires USD toutes présentes.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permet l'import direct quand pytest est lancé depuis la racine
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10.v10_currency_pairs import (  # noqa: E402
    PAIRS_USD,
    CURRENCIES,
    PAIRS_BY_CURRENCY,
    INVERSION_MAP,
    sign,
    pairs_for,
    all_supported_pairs,
    all_supported_currencies,
)


def test_inversion_map_signs_correct():
    """EURUSD : EUR=+1 (base), USD=-1 (quote). 6 paires × 2 devises = 12 asserts."""
    expected = {
        ("EURUSD", "EUR"): 1,   ("EURUSD", "USD"): -1,
        ("GBPUSD", "GBP"): 1,   ("GBPUSD", "USD"): -1,
        ("USDJPY", "USD"): 1,   ("USDJPY", "JPY"): -1,
        ("USDCHF", "USD"): 1,   ("USDCHF", "CHF"): -1,
        ("AUDUSD", "AUD"): 1,   ("AUDUSD", "USD"): -1,
        ("USDCAD", "USD"): 1,   ("USDCAD", "CAD"): -1,
    }
    for (pair, cur), want in expected.items():
        assert sign(pair, cur) == want, f"{pair} {cur}: want {want}, got {sign(pair, cur)}"


def test_pairs_for_known_and_unknown_currency():
    """pairs_for() : devise connue → tuple non vide, devise inconnue → tuple vide (R6 fail-open)."""
    assert len(pairs_for("EUR")) >= 1
    assert "EURUSD" in pairs_for("EUR")
    assert pairs_for("NZD") == ()  # NZD non supporté au démarrage → vide
    assert pairs_for("BTC") == ()  # crypto non supportée → vide (fail-open)


def test_sign_raises_on_invalid_pair_or_currency():
    """sign() : devise non dans la paire → ValueError explicite."""
    try:
        sign("EURUSD", "JPY")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError when currency not in pair")


def test_constants_completeness():
    """7 devises agrégées, 6 paires USD, mapping complet, helpers cohérents."""
    assert len(CURRENCIES) == 7
    assert len(set(CURRENCIES)) == 7  # pas de doublon
    assert len(PAIRS_USD) == 6
    assert len(set(PAIRS_USD)) == 6
    assert all_supported_pairs() == frozenset(PAIRS_USD)
    assert all_supported_currencies() == frozenset(CURRENCIES)

    # Chaque paire USD est dans INVERSION_MAP avec 2 entrées
    for pair in PAIRS_USD:
        assert pair in INVERSION_MAP
        assert len(INVERSION_MAP[pair]) == 2
        assert sum(INVERSION_MAP[pair].values()) == 0  # base +1, quote -1 → somme nulle

    # Chaque devise a au moins 1 paire (sauf contrôle fail-open)
    for cur in CURRENCIES:
        assert cur in PAIRS_BY_CURRENCY
