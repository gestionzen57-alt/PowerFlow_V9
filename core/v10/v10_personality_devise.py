"""v10_personality_devise.py — SQUELETTE Pilier 4 (personnalité de devise).

⚠️ MÉTHODOLOGIE (docs/V10/METHODOLOGIE_INJECTION.md) :
CE MODULE EST VIDE VOLONTAIREMENT. Les règles de lecture sont la propriété
de Søn (brainstorming en cours). Ne PAS injecter de règles mécaniques
avant validation complète du Pilier 4.

Blocs source : docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md (blocs 1.1-2.3)
  - 1.1 Tempo par devise (GBP rapide, AUD lent...)
  - 1.2 Véracité par devise (fiabilité force → mouvement réel)
  - 1.3 Comportement de session par devise (heures préférées)
  - 2.1 Force normalisée par session (Asie ≠ Overlap)
  - 2.2 Volatilité de session (ATR, amplitude)
  - 2.3 Tempo de session (accélération/ralentissement)

Statut : ⬜ EN ATTENTE du brainstorming complet.

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations


def tempo_devise(symbol: str) -> dict:
    """Tempo de la devise (à implémenter après validation Søn)."""
    raise NotImplementedError("Pilier 4 non validé — brainstorming en cours")


def veracite_devise(db_path: str, symbol: str) -> dict:
    """Score de véracité (à implémenter après validation Søn)."""
    raise NotImplementedError("Pilier 4 non validé — brainstorming en cours")


def session_devise(symbol: str, hour_utc: int) -> dict:
    """Comportement de session par devise (à implémenter après validation Søn)."""
    raise NotImplementedError("Pilier 4 non validé — brainstorming en cours")
