"""v10_cycles_fatman.py — SQUELETTE Pilier 6 (cycles Fatman).

⚠️ MÉTHODOLOGIE (docs/V10/METHODOLOGIE_INJECTION.md) :
CE MODULE EST VIDE VOLONTAIREMENT. Les règles de lecture sont la propriété
de Søn (brainstorming en cours). Ne PAS injecter de règles mécaniques
avant validation complète du Pilier 6.

Blocs source :
  - docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md (blocs 4.1-4.3)
  - docs/V10/LECTURE_STRATEGIE_CHANGEMENT_PHASE.md (R1-R5)

Concepts à capturer (description Søn 13/08) :
  - Vagues Elliott adaptées à Fatman (impulsion/correction)
  - Phases du cycle : naissance → expansion → maturité → épuisement
  - Emboîtement H1→H4 (H1 croise avant, H4 confirme)
  - Croisement H4 = changement de phase (GBP haut→bas, USD bas→haut)
  - Antagonisme (2 forces extrêmes) = point de retournement possible
  - Propagation vs Répulsion après croisement
  - Confirmation du retournement par croisement sur TF <

Statut : ⬜ EN ATTENTE du brainstorming complet.

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations


def detecter_vagues(forces: list) -> dict:
    """Détecteur de vagues (impulsion/correction) — à implémenter."""
    raise NotImplementedError("Pilier 6 non validé — brainstorming en cours")


def phase_cycle(forces: list) -> dict:
    """Phase du cycle (naissance/expansion/maturité/épuisement) — à implémenter."""
    raise NotImplementedError("Pilier 6 non validé — brainstorming en cours")


def croisement_phase(db_path: str, symbol: str, tf: str) -> dict:
    """Croisement H4 = changement de phase — à implémenter."""
    raise NotImplementedError("Pilier 6 non validé — brainstorming en cours")


def antagonisme(db_path: str, symbol: str) -> dict:
    """Antagonisme (2 forces extrêmes) = retournement possible — à implémenter."""
    raise NotImplementedError("Pilier 6 non validé — brainstorming en cours")
