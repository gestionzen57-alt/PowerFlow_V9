#!/usr/bin/env python3
"""mcp-v9-doctrine — MCP server ciblé pour interrogation doctrine V9 (2026-07-14).

État courant (post-assouplissement motion CEO Søn 2026-07-14) :
- R7 assoupli : « zéro régression NON justifiée tolérée »
- R22 assoupli : « 1 session = 1 périmètre, sauf chantier complexe »
- R25' assoupli : « promotion SHADOW→ACTIVE, sauf mandat CEO explicite »
- R28 assoupli : « Hermes opérateur git unique, sauf instruction Søn »

Tools exposés (stdin/stdout JSON-RPC simplifié, transport subprocess Hermes) :
- rules() → list[dict]                       (les 30 règles + statut assouplissement)
- get_rule(n: int) → dict                    (détail d'une règle)
- motion_log(limit: int) → list[dict]        (entrées DECISIONS_LOG contenant
                                              « assoupli 2026-07-14 »)
- assouplissement_summary() → dict           (résumé motion CEO 2026-07-14)

Doctrine : R6 strict, lecture seule du DOCTRINE.md + DECISIONS_LOG.md.
Aucun write, aucune modif. Read-only.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DOCTRINE_PATH = ROOT_DIR / "docs" / "DOCTRINE.md"
DECISIONS_LOG_PATH = ROOT_DIR / "workspace" / "perplexity" / "memory" / "DECISIONS_LOG.md"


# Snapshot 2026-07-14 de l'état doctrinal (extrait de DOCTRINE.md).
# Mis à jour manuellement à chaque motion CEO. Pas de parsing dynamique
# pour rester traçable (R6 strict).
RULES_2026_07_14 = {
    1: {"name": "Code = source de vérité, pas la doc", "statut": "intacte"},
    2: {"name": "Couches additives et filtrantes", "statut": "intacte"},
    3: {"name": "Pas de signal si exploitabilité != exploitable", "statut": "intacte"},
    4: {"name": "Données stale rejetées", "statut": "intacte"},
    5: {"name": "Anti-replay : 1 bougie fermée = 1 snapshot", "statut": "intacte"},
    6: {"name": "Orchestrateur ne crash jamais (try/except par couche)", "statut": "intacte"},
    7: {"name": "Tests obligatoires avant commit — zéro régression NON justifiée",
         "statut": "assoupli 2026-07-14",
         "motion": "R7 nouvelle formulation : toute régression doit être accompagnée "
                   "d'une entrée DECISIONS_LOG expliquant le progrès. (DECISIONS_LOG §2026-07-14)"},
    8: {"name": "Documentation mise à jour à chaque livraison", "statut": "intacte"},
    9: {"name": "Pas de dette technique héritée (V6/V7/V8 = legacy)", "statut": "intacte"},
    10: {"name": "MT4 dicte, MT5 confirme (Phase 11 future)", "statut": "intacte"},
    11: {"name": "Architecture 9+1 (9 node_rule + 1 grammar ACTIVE)", "statut": "intacte"},
    12: {"name": "Replay et live marqués distinctement (source_type)", "statut": "intacte"},
    13: {"name": "Observer d'abord, agir ensuite (paper → réel)", "statut": "intacte"},
    14: {"name": "Git = source de vérité, pas mémoire de conversation", "statut": "intacte"},
    15: {"name": "Une seule source de vérité par sujet", "statut": "intacte"},
    16: {"name": "Migration métier précède agentification généralisée", "statut": "intacte"},
    17: {"name": "Autonomie après stabilité démontrée en live", "statut": "intacte"},
    18: {"name": "Aucune dépendance LLM pour le cœur cognitif", "statut": "intacte"},
    19: {"name": "Chantiers agents/routing/skills auto-générés pas avant canonisation",
         "statut": "intacte"},
    "20'": {"name": "Lecture-first sur marché ouvert (v9_calibration --analyze)",
             "statut": "intacte"},
    21: {"name": "Toute métrique ajoutée → CONTEXT_CONTRACT.md", "statut": "intacte"},
    22: {"name": "Une session = un périmètre = une livraison complète, sauf chantier complexe",
         "statut": "assoupli 2026-07-14",
         "motion": "R22 nouvelle formulation : un chantier complexe peut être découpé en "
                   "sous-unités livrables autonomes. (DECISIONS_LOG §2026-07-14)"},
    23: {"name": "Principes YAML consommateurs mis à jour même session que le champ",
         "statut": "intacte"},
    24: {"name": "CONTEXT_CONTRACT.md à jour à clôture de phase", "statut": "intacte"},
    "25'": {"name": "Vocabulaire descriptif : promotion SHADOW→ACTIVE conditionnée, sauf mandat CEO",
            "statut": "assoupli 2026-07-14",
            "motion": "R25' nouvelle formulation : les motions CEO « go global » "
                      "(« go activer tous », « go r28 », « go la suite ») constituent "
                      "des mandats explicites couvrant un périmètre autorisé de promotions. "
                      "(DECISIONS_LOG §2026-07-14)"},
    26: {"name": "1 commit par unité logique + 1 DECISIONS_LOG + STATE.md par session",
         "statut": "intacte"},
    27: {"name": "Champ DORMANT > 2 phases = réévaluation (PROMU/SUPPRIMÉ)",
         "statut": "intacte"},
    28: {"name": "Hermes opérateur git unique de V9, sauf instruction directe Søn",
         "statut": "assoupli 2026-07-14",
         "motion": "R28 nouvelle formulation : la motion CEO « go r28 » du 2026-07-14 "
                   "= délégation explicite du push à Hermes, conformément à la nouvelle "
                   "clause. (DECISIONS_LOG §2026-07-14)"},
    29: {"name": "Doctrine de lecture du marché : zone-type × multi-TF", "statut": "intacte"},
    30: {"name": "Apprentissage conditionnel WIN/LOSS — seuils 5/20/50/200",
         "statut": "intacte"},
}


def handle_rules(args: dict) -> dict:
    """Liste les 30 règles avec leur statut (intacte / assoupli)."""
    return {
        "total": len(RULES_2026_07_14),
        "assouplies_2026_07_14": [n for n, v in RULES_2026_07_14.items()
                                  if v["statut"].startswith("assoupli")],
        "rules": [{"n": str(n), **v} for n, v in RULES_2026_07_14.items()],
        "source": "DOCTRINE.md (c560506) — état 2026-07-14",
    }


def handle_get_rule(args: dict) -> dict:
    """Détail d'une règle par son numéro."""
    n = args.get("n")
    if n is None:
        return {"error": "n (numéro de règle) manquant"}
    # Convert to str/int pour matching
    key = n if isinstance(n, int) else str(n)
    rule = RULES_2026_07_14.get(key)
    if not rule:
        return {"error": f"règle {n} inconnue (30 règles : 1-30 + 20' + 25')"}
    return {"n": str(key), **rule}


def handle_motion_log(args: dict) -> dict:
    """Extrait les entrées DECISIONS_LOG contenant « assoupli 2026-07-14 »."""
    limit = args.get("limit", 20)
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        return {"error": "limit doit être un entier entre 1 et 100"}
    if not DECISIONS_LOG_PATH.exists():
        return {"error": f"DECISIONS_LOG introuvable: {DECISIONS_LOG_PATH}"}
    try:
        text = DECISIONS_LOG_PATH.read_text(encoding="utf-8", errors="replace")
        # Sections qui contiennent le marqueur
        pattern = re.compile(
            r"(## 2026-07-14[^\n]*\n.*?)(?=\n## |\Z)", re.DOTALL
        )
        sections = pattern.findall(text)
        assoupli_sections = [s for s in sections
                             if "assoupli" in s.lower() or "motion CEO" in s]
        truncated = assoupli_sections[:limit]
        return {
            "count": len(truncated),
            "total_assoupli_sections": len(assoupli_sections),
            "sections": [
                {
                    "header": s.split("\n", 1)[0].strip(),
                    "excerpt": s[:500] + ("..." if len(s) > 500 else ""),
                    "length_chars": len(s),
                }
                for s in truncated
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def handle_assouplissement_summary(args: dict) -> dict:
    """Résumé factuel de la motion CEO d'assouplissement 2026-07-14."""
    rules_assouplies = [n for n, v in RULES_2026_07_14.items()
                        if v["statut"].startswith("assoupli")]
    return {
        "motion_ceo_date": "2026-07-14",
        "rules_assouplies": rules_assouplies,
        "rules_intactes_count": len(RULES_2026_07_14) - len(rules_assouplies),
        "rules_total": len(RULES_2026_07_14),
        "commits_lies": [
            {"sha": "c560506", "what": "DOCTRINE.md assoupli 4 règles"},
            {"sha": "fd0a4fc", "what": "Propagation 8 docs Hermes"},
            {"sha": "e503e9c", "what": "Propagation résiduelle R22/R28 (Fable)"},
        ],
        "source": "DOCTRINE.md + DECISIONS_LOG.md (R6 strict, lecture seule)",
    }


HANDLERS = {
    "rules": handle_rules,
    "get_rule": handle_get_rule,
    "motion_log": handle_motion_log,
    "assouplissement_summary": handle_assouplissement_summary,
}


def main() -> None:
    from stdio_runtime import serve

    serve(HANDLERS, "v9-doctrine")


if __name__ == "__main__":
    main()
