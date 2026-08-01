"""v9_kiss_audit.py — Phase 79 motion CEO 48H (P3.2 audit Perplexity).

KISS/DRY audit : identifie les modules consideres comme 'morts' selon l'audit
Perplexity etablit le 31/07/2026.

Modules marques deprecated (mais conserves pour ne pas casser les imports) :
- v9_bear_perception.py : kill switch OFF permanent (shadow only)
- v9_human_mirror.py : DB vide en production, score 0.5
- principle_cascade_engine.py : boost cascade applique apres gate confiance
- market_regime_global.py : kill switch OFF defaut

L'API publique reste fonctionnelle (deprecation warning) pour permettre
la suppression progressive apres validation.

Auteur : Hermes (Phase 79 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("v9.kiss_audit")

ROOT = Path(__file__).resolve().parent.parent

# Liste des modules consideres comme morts selon audit Perplexity 31/07
DEPRECATED_MODULES = [
    {
        "path": "core/v9/v9_bear_perception.py",
        "loc": 830,  # approx
        "reason": "Kill switch OFF permanent, shadow only, jamais active",
        "fallback": "NO_BAISSIERE kill switch global (plus efficace)",
    },
    {
        "path": "core/v9/v9_human_mirror.py",
        "loc": 239,
        "reason": "DB v9_human_trades vide en production, score=0.5",
        "fallback": "Mirror BLOCKING via V9_HUMAN_MIRROR_BLOCKING=0 par defaut",
    },
    {
        "path": "core/v9/principle_cascade_engine.py",
        "loc": 380,
        "reason": "Boost cascade applique apres MIN_CONFIDENCE_GATE (bug P1.4)",
        "fallback": "Boost cascade correctement ordonne (FIXED P1.4 31/07)",
    },
    {
        "path": "core/v9/market_regime_global.py",
        "loc": 200,
        "reason": "Kill switch OFF defaut (R2 : DRM APPLY reste inchange)",
        "fallback": "DRM existant + market_regime_engine.py si besoin",
    },
]


def scan_deprecated_modules() -> list[dict[str, Any]]:
    """Verifie l'existence des modules deprecated."""
    results = []
    for mod in DEPRECATED_MODULES:
        path = ROOT / mod["path"]
        exists = path.exists()
        loc_actual = 0
        if exists:
            try:
                with open(path) as f:
                    loc_actual = sum(1 for _ in f)
            except Exception:
                pass
        results.append({
            **mod,
            "exists": exists,
            "loc_actual": loc_actual,
        })
    return results


def count_total_dead_loc() -> int:
    """Compte les LOC total des modules morts."""
    return sum(m.get("loc_actual", m["loc"]) for m in scan_deprecated_modules())


def recommend_suppression(conservative: bool = True) -> list[str]:
    """Recommandations de suppression selon mode.

    conservative (defaut) : marquer deprecated, conserver pour stabilite
    aggressive : supprimer completement (risque de casser imports)
    """
    if conservative:
        return [
            "Mode conservateur recommande :",
            "1. Ajouter _DEPRECATED = True dans chaque module",
            "2. Ajouter DeprecationWarning a l'import",
            "3. Mettre a jour la doc (USER_GUIDE.md) avec note deprecated",
            "4. Planifier suppression en V10 (apres validation 30j)",
        ]
    return [
        "Mode agressif :",
        "1. Supprimer les fichiers",
        "2. Supprimer tous les imports associes (recherche grep)",
        "3. Re-lancer la suite complete de tests",
        "4. Commit avec note de suppression KISS/DRY",
    ]


def main(argv=None) -> int:
    """Affiche le rapport KISS/DRY."""
    print("=" * 70)
    print("V9 KISS/DRY AUDIT (Phase 79)")
    print("=" * 70)
    results = scan_deprecated_modules()
    total_loc = 0
    for mod in results:
        marker = "DEPRECATED" if mod["exists"] else "MISSING"
        loc = mod.get("loc_actual", mod["loc"])
        total_loc += loc
        print(f"\n[{marker}] {mod['path']} ({loc} LOC)")
        print(f"  Reason : {mod['reason']}")
        print(f"  Fallback : {mod['fallback']}")
    print()
    print(f"Total LOC deprecated : {total_loc}")
    print(f"Reduction potentielle : ~{total_loc / 91000 * 100:.1f}% du core")
    print()
    print("Recommandations (mode conservateur) :")
    for line in recommend_suppression(conservative=True):
        print(f"  {line}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())