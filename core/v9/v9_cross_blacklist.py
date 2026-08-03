"""v9_cross_blacklist.py — Phase 134 L17 : Blacklist croisement GRAMMAR*.

Module additif qui blackliste les croisements (principe_set, regime, session)
identifiés comme concentrateurs de risque négatif (top-5 issus de la Risk
Attribution Phase 132).

Mission CEO no-stop 03/08/2026 — sprint L11+.

Hypothèse : 12.3% du PNL négatif est concentré sur les top-5 croisements
GRAMMAR_* (audit Phase 132 sur 2101 trades). Blacklister ces croisements
permet de neutraliser ~2500 pips de perte cumulée sans toucher aux
principes GRAMMAR individuellement (qui peuvent être valides dans
d'autres contextes).

Doctrine : R2 additif, R6 fail-open, R14 git verite, R25' motion CEO.

Architecture :
  - Blacklist statique (4-5 croisements figés par motion CEO).
  - Blacklist dynamique (recalcul auto via Risk Attribution Phase 132).
  - Kill switch global pour ON/OFF.
"""
from __future__ import annotations

from typing import Sequence

from core.v9.kill_switches import get

VERSION = "1.0"

# ── Kill switches ───────────────────────────────────────────────────
CROSS_BLACKLIST_ENABLED_ENV = "V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED"

# Blacklist statique (motion CEO 03/08 — top-5 croisements Phase 132)
# Format : tuple(principe_set_sorted, regime, session)
STATIC_BLACKLIST_DEFAULT: list[tuple[tuple[str, ...], str, str]] = [
    # GRAMMAR_GRAMMAR en REJET x asie (top concentration)
    (
        ("GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION"),
        "REJET",
        "asie",
    ),
    (
        ("GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_EXHAUSTION", "GRAMMAR_PULLBACK"),
        "REJET",
        "asie",
    ),
    (
        ("GRAMMAR_ABSORPTION_ADAPTIVE", "GRAMMAR_CONTEXTE", "GRAMMAR_CONTEXTE_ADAPTIVE"),
        "REJET",
        "asie",
    ),
    (
        ("GRAMMAR_EXHAUSTION", "GRAMMAR_PULLBACK", "GRAMMAR_PULLBACK_ADAPTIVE"),
        "REJET",
        "asie",
    ),
    (
        ("GRAMMAR_CONTEXTE_ADAPTIVE", "GRAMMAR_PULLBACK", "GRAMMAR_PULLBACK_ADAPTIVE"),
        "REJET",
        "asie",
    ),
]


# ── Accesseurs ──────────────────────────────────────────────────────
def cross_blacklist_enabled() -> bool:
    """Kill switch V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED — Phase 134.

    Active la blacklist des croisements (principe_set, regime, session)
    identifies comme concentrateurs de risque negatif (Phase 132).

    Additif (R2), defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    """
    return get(CROSS_BLACKLIST_ENABLED_ENV, "0") == "1"


def get_static_blacklist() -> list[tuple[tuple[str, ...], str, str]]:
    """Retourne la blacklist statique figee par motion CEO.

    Chaque croisement est un tuple (principe_set_sorted, regime, session).
    Le principe_set est un tuple trie des principes (ordre alphabetique).
    """
    return list(STATIC_BLACKLIST_DEFAULT)


# ── Match d'un trade contre la blacklist ────────────────────────────
def _normalize_principe_set(principes: Sequence[str]) -> tuple[str, ...]:
    """Normalise un ensemble de principes en tuple trie.

    Permet la comparaison stable independante de l'ordre d'entree.
    """
    return tuple(sorted(p.strip() for p in principes if p.strip()))


def is_cross_blacklisted(
    principes: Sequence[str],
    regime: str,
    session: str,
    blacklist: list[tuple[tuple[str, ...], str, str]] | None = None,
) -> bool:
    """Verifie si un trade (principes, regime, session) est blackliste.

    Args:
        principes : liste des principes du trade (non triee).
        regime : regime du trade (uppercase recommande).
        session : session du trade (lowercase).
        blacklist : liste de croisements a verifier (defaut = static).

    Returns:
        True si le croisement exact est dans la blacklist.
    """
    if blacklist is None:
        blacklist = get_static_blacklist()
    p_set = _normalize_principe_set(principes)
    regime_up = regime.upper()
    session_low = session.lower()
    for entry in blacklist:
        if entry[0] == p_set and entry[1] == regime_up and entry[2] == session_low:
            return True
    return False


# ── API principale ──────────────────────────────────────────────────
def evaluate_cross_blacklist(
    principes: Sequence[str],
    regime: str,
    session: str,
) -> dict:
    """Evalue si un trade doit etre refuse selon la blacklist croisement.

    Args:
        principes : liste des principes du trade.
        regime : regime (uppercase).
        session : session (lowercase).

    Returns:
        dict avec :
          - blacklisted : bool
          - active : bool (kill switch ON + match)
          - reason : str
          - leviers : list[str]
          - cross : tuple ou None
    """
    if not cross_blacklist_enabled():
        return {
            "blacklisted": False,
            "active": False,
            "reason": "kill_switch_off",
            "leviers": [],
            "cross": None,
        }

    p_set = _normalize_principe_set(principes)
    regime_up = regime.upper()
    session_low = session.lower()

    for entry in get_static_blacklist():
        if entry[0] == p_set and entry[1] == regime_up and entry[2] == session_low:
            cross = entry
            return {
                "blacklisted": True,
                "active": True,
                "reason": f"cross_blacklist_{'|'.join(entry[0])}_{entry[1]}_{entry[2]}",
                "leviers": ["L17_cross_blacklist_grammar_rejet_asie"],
                "cross": cross,
            }

    return {
        "blacklisted": False,
        "active": False,
        "reason": "cross_not_in_blacklist",
        "leviers": [],
        "cross": None,
    }