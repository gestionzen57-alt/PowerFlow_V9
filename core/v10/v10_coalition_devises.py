"""v10_coalition_devises.py — SQUELETTE Pilier 3 (coalition multidevise).

⚠️ MÉTHODOLOGIE (docs/V10/METHODOLOGIE_INJECTION.md) :
CE MODULE EST VIDE VOLONTAIREMENT. Les règles de lecture sont la propriété
de Søn (brainstorming en cours). Ne PAS injecter de règles mécaniques
avant validation complète du Pilier 3.

Blocs source : docs/V10/BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md
(blocs 3.1-3.4)
  - 3.1 Qui mène ? (GBP fort en absolu = leader, USD faible = follower)
  - 3.2 Rupture de coalition risk-on (GBP casse pendant que AUD continue)
  - 3.3 Safe haven (JPY/CHF montent → risk-off → GBPUSD chute)
  - 3.4 Cross-pair confirmation (EURGBP divergence vs GBPUSD)

Note : le module existant v10_market_context_global.py (CoalitionDetector)
est le point de départ — il faut le brancher ici après validation Søn.

Statut : ⬜ EN ATTENTE du brainstorming complet.

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations


def leader_follower(db_path: str, symbol: str) -> dict:
    """Qui mène ? (leader/follower) — à implémenter après validation Søn."""
    raise NotImplementedError("Pilier 3 non validé — brainstorming en cours")


def rupture_coalition(db_path: str, symbol: str) -> dict:
    """Rupture de coalition risk-on — à implémenter après validation Søn."""
    raise NotImplementedError("Pilier 3 non validé — brainstorming en cours")


def safe_haven_signal(db_path: str) -> dict:
    """Safe haven (JPY/CHF → risk-off) — à implémenter après validation Søn."""
    raise NotImplementedError("Pilier 3 non validé — brainstorming en cours")


def cross_pair_confirm(db_path: str, symbol: str) -> dict:
    """Cross-pair confirmation (EURGBP vs GBPUSD) — à implémenter."""
    raise NotImplementedError("Pilier 3 non validé — brainstorming en cours")
