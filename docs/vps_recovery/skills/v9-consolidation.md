# V9 Consolidation — Playbook anti-V8

> Skill compact. Voir `powerflow-v9-consolidation` pour l'intégral.

## Principe

V8 a échoué par expansion avant stabilisation. V9 = consolidation d'abord.

## Pre-expansion ritual

Avant toute Phase 11+, exécuter :

| # | Chantier | Effort |
|---|----------|--------|
| C-1 | Sync CONTEXT_CONTRACT.md avec le code | 1 patch |
| C-2 | Compléter `init_all_dbs()` canonique | ~50 LOC + tests |
| C-3 | Gitignorer artefacts runtime | 5 lignes .gitignore |
| C-4 | Créer/mettre à jour mode d'emploi global | 1 fichier |

## Règle d'engagement

Aucune expansion tant que C-1→C-4 ne sont pas livrés ET `pytest -q` = 0 rouge.

## Anti-patterns V8

- Monolith MCP (1 serveur qui wrappe 6 services)
- Redis pour cache Python (dict + TTL suffit)
- N vues SQL (1 vue agrégée suffit)
- ngrok (Tailscale remplace)
