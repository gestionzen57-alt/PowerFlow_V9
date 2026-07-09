# V9 Infra Optimization — Framework OPT-N

> Skill compact. Voir `powerflow-v9-infra-optimization` pour l'intégral.

## 3 axes validés

| Axe | Action | Effet |
|-----|--------|-------|
| **OPT-2 Cache** | Décorateur `@_cached(key, ttl=30)` sur 6 fonctions hot | SELECT -50% |
| **OPT-3 Vue SQL** | Vue `v_dashboard_snapshot` 11 colonnes | 1 SELECT au lieu de 10+ |
| **OPT-5 System prompt** | Charger V9_FONCTIONNEMENT.md, lier le reste | Context < 50 KB |

## Pattern commun

- 0 dépendance externe (pas Redis, pas MCP, pas ngrok)
- 1 commit par OPT
- Tests pour chaque OPT
- Mesurable avant/après

## Anti-patterns

- ❌ Monolith MCP V8-style
- ❌ Redis pour cache Python (dict + TTL suffit)
- ❌ N vues SQL (1 vue agrégée suffit)
- ❌ ngrok (Tailscale remplace)
- ❌ Plusieurs commits pour 1 OPT
