"""V10 Currency Pairs — constantes pures de mapping devises ↔ paires.

Le Fatman Hawkeye lit le marché en DEVISES (pas en paires). Pour chaque paire,
chaque devise a un signe d'inversion :
- devise BASE   → signe +1 (elle monte quand la paire monte)
- devise QUOTE  → signe −1 (elle monte quand la paire descend)

Le moteur d'agrégation (v10_currency_strength) utilise INVERSION_MAP
pour pondérer correctement le momentum de chaque cross dans le score
par devise.

Doctrine : R2 additif pur (pas d'import core/v9/), R6 fail-open,
R9 audit (constantes versionnées, reproductibles).
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple

# 6 paires USD autorisées (Fatman Hawkeye compatible — broker Tickmill MT5)
PAIRS_USD: Tuple[str, ...] = (
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
)

# 7 devises agrégées (NZD absent au démarrage — serait GBP/NZD, EUR/NZD, AUD/NZD)
CURRENCIES: Tuple[str, ...] = (
    "EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD",
)

# Mapping devise → liste des paires qui la contiennent.
# Sert à itérer sur les crosses d'une devise dans le moteur strength.
PAIRS_BY_CURRENCY: Dict[str, Tuple[str, ...]] = {
    "EUR": ("EURUSD",),
    "GBP": ("GBPUSD",),
    "USD": ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"),
    "JPY": ("USDJPY",),
    "CHF": ("USDCHF",),
    "AUD": ("AUDUSD",),
    "CAD": ("USDCAD",),
}

# Signe d'inversion devise par paire.
# +1 si la devise est BASE (EUR dans EURUSD), −1 si QUOTE (USD dans EURUSD).
# Insensible aux majuscules.
def _build_inversion_map() -> Dict[str, Dict[str, int]]:
    """Construit INVERSION_MAP à partir d'une table de paires parsées.

    Format table :
        "EURUSD" → base=EUR, quote=USD
    Règle : devise base = +1, devise quote = −1.
    """
    raw = {
        "EURUSD": ("EUR", "USD"),
        "GBPUSD": ("GBP", "USD"),
        "USDJPY": ("USD", "JPY"),
        "USDCHF": ("USD", "CHF"),
        "AUDUSD": ("AUD", "USD"),
        "USDCAD": ("USD", "CAD"),
    }
    out: Dict[str, Dict[str, int]] = {}
    for pair, (base, quote) in raw.items():
        out[pair] = {base: 1, quote: -1}
    return out


INVERSION_MAP: Dict[str, Dict[str, int]] = _build_inversion_map()


def sign(pair: str, currency: str) -> int:
    """Retourne le signe d'inversion d'une devise dans une paire.

    Lève ValueError si la devise n'est pas dans la paire — l'appelant
    doit avoir filtré via PAIRS_BY_CURRENCY.

    >>> sign("EURUSD", "EUR")
    1
    >>> sign("EURUSD", "USD")
    -1
    >>> sign("USDJPY", "JPY")
    -1
    """
    m = INVERSION_MAP[pair]
    if currency not in m:
        raise ValueError(f"Currency '{currency}' not in pair '{pair}'")
    return m[currency]


def pairs_for(currency: str) -> Tuple[str, ...]:
    """Retourne la liste figée des paires contenant `currency`.

    Doctrine fail-open R6 : si devise inconnue → tuple vide (pas d'erreur).
    L'appelant teste len() == 0 pour skip l'agrégation (cas NZD au démarrage).
    """
    return PAIRS_BY_CURRENCY.get(currency.upper(), ())


def all_supported_pairs() -> FrozenSet[str]:
    """Ensemble figé de toutes les paires USD supportées (debug + sanity check)."""
    return frozenset(PAIRS_USD)


def all_supported_currencies() -> FrozenSet[str]:
    """Ensemble figé de toutes les devises agrégées."""
    return frozenset(CURRENCIES)


__all__ = [
    "PAIRS_USD",
    "CURRENCIES",
    "PAIRS_BY_CURRENCY",
    "INVERSION_MAP",
    "sign",
    "pairs_for",
    "all_supported_pairs",
    "all_supported_currencies",
]
