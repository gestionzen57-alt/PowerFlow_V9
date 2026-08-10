"""V10 Coherence Audit — auto-détection des modules orphelins (Phase 4, Cognitive Continuum).

Le levier de l'amélioration perpétuelle AUTOMATIQUE : le système se détecte
lui-même quand un module de lecture des comportements n'est pas branché dans
le cœur de décision.

Principe directeur (auto-cohérence) :
  > Tout module de lecture testé doit être NATURELLEMENT branché dans le cœur
  > de décision. Si un module est orphelin (importé seulement par `__init__.py`),
  > c'est un bug d'architecture, pas un choix.

`audit_orphans()` scanne `core/v10/` + `scripts/` et détecte les modules de
lecture qui ne sont consommés par AUCUN chemin de décision (seulement
`__init__.py`). Retourne la liste des orphelins + un verdict.

R6 fail-open. R9 : chaque module tracé. R10 : compute only.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]  # C:\projet\V9

# Modules de lecture des comportements (le vocabulaire riche)
READING_MODULES = [
    "v10_structure", "v10_market_context_global", "v10_smc", "v10_ict_ote",
    "v10_delta_flow", "v10_liquidity_map", "v10_currency_behavior",
    "v10_regime_hmm", "v10_compression_extension", "v10_vsa",
    "v10_fatman_bible_signals", "v10_memory_bridge", "v10_behavior_registry",
    "v10_cortex", "v10_grammar_v9",
]


def _scan_imports() -> Dict[str, List[str]]:
    """Carte module → fichiers qui l'importent (hors __init__)."""
    consumers: Dict[str, List[str]] = {m: [] for m in READING_MODULES}
    # Fichiers à scanner : core/v10/*.py (hors __init__) + scripts/*.py
    files = list((ROOT / "core" / "v10").glob("*.py")) + \
            list((ROOT / "scripts").glob("*.py"))
    for f in files:
        if f.name == "__init__.py":
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for mod in READING_MODULES:
            # import de <mod> ou from <mod> import
            if re.search(rf"(import|from)\s+.*{mod}", text):
                consumers[mod].append(str(f.relative_to(ROOT)))
    return consumers


def audit_orphans() -> Dict:
    """Détecte les modules de lecture orphelins (consommés seulement par __init__).

    Returns
    -------
    dict : {orphans: [...], n_orphans, n_connected, verdict}
    """
    consumers = _scan_imports()
    orphans = []
    connected = []
    for mod, cons in consumers.items():
        # Un module est connecté s'il est importé par au moins un fichier
        # autre que __init__.py (qui n'est pas dans la liste car skip).
        if cons:
            connected.append({"module": mod, "consumers": cons})
        else:
            orphans.append(mod)

    verdict = "COHERENT" if not orphans else "ORPHANS_DETECTED"
    return {
        "orphans": orphans,
        "n_orphans": len(orphans),
        "n_connected": len(connected),
        "connected": connected,
        "verdict": verdict,
        "audit": {"r10": "compute only"},
    }


__all__ = ["audit_orphans", "READING_MODULES"]
