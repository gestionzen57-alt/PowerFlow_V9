"""v10_fractalite_tf.py — SQUELETTE Pilier 5 (fractalité temporelle).

⚠️ MÉTHODOLOGIE (docs/V10/METHODOLOGIE_INJECTION.md) :
CE MODULE EST VIDE VOLONTAIREMENT. Les règles de lecture sont la propriété
de Søn (brainstorming en cours). Ne PAS injecter de règles mécaniques
avant validation complète du Pilier 5.

Blocs source : docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md (blocs 3.1-3.3, 5.1-5.3)
  - 3.1 Le 1min (scalp GBPUSD)
  - 3.2 L'emboîtement des TF (fractalité)
  - 3.3 TF de lisibilité par devise
  - 5.1 La lecture GBPUSD 1min (session de scalp)
  - 5.2 Ce qui rend GBPUSD lisible
  - 5.3 La transposition aux autres devises

Note : le score de confluence (v10_confluence_tf.py) est le début du
Pilier 2 — il manque le 1min et le TF de lisibilité par devise.

Statut : ⬜ EN ATTENTE du brainstorming complet.

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations


def couche_1min(db_path: str, symbol: str) -> dict:
    """Couche 1min (timing d'entrée scalp) — à implémenter après validation Søn."""
    raise NotImplementedError("Pilier 5 non validé — brainstorming en cours")


def tf_lisibilite(symbol: str) -> str:
    """TF de lisibilité par devise (GBPUSD→1min, EURUSD→5min...) — à implémenter."""
    raise NotImplementedError("Pilier 5 non validé — brainstorming en cours")


def lisibilite_devise(db_path: str, symbol: str) -> dict:
    """Score de lisibilité (clarté des pics, ratio signal/bruit) — à implémenter."""
    raise NotImplementedError("Pilier 5 non validé — brainstorming en cours")
