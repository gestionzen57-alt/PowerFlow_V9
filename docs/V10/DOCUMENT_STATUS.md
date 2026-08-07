# V10 — Statut documentaire canonique

**Mis à jour :** 2026-08-07 15:45 CEST
**Git source de vérité :** `d213290b8cd3d21be2ec7266532476c217f6ef28` sur `feat/v9-foundation-clean`
**Validation :** `python -m pytest tests/test_v10_*.py -q` → **1310 passed**, 3 warnings `sklearn` attendus, 167.89 s.

## Hiérarchie de vérité

1. Le code et Git font foi pour l’implémentation et le SHA.
2. Les requêtes DB et rapports horodatés font foi pour l’état runtime et les métriques.
3. Ce document et `docs/V10/STATE.md` décrivent l’état opérationnel consolidé.
4. Les plans, audits et rapports datés sont des instantanés historiques ; ils ne doivent pas être lus comme l’état courant.

## Documents actifs

| Document | Rôle | Statut |
|---|---|---|
| `AGENTS.md` | doctrine opératoire et rituel de session | actif |
| `SOUL.md` | philosophie et vision | actif, avec historique conservé |
| `docs/V10/STATE.md` | état V10 consolidé | actif |
| `docs/STATE.md` | pointeur exécutif racine | actif |
| `docs/V10/CACHE_BOARD.md` | tableau opérationnel compact | actif |
| `workspace/perplexity/BOARD.md` | board de chantier compact | actif |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | décisions structurantes | actif |

## État consolidé

- V10 reste additif : `core/v10/` n’importe pas `core/v9/`.
- Le système V10 est en décision/signal, paper et shadow ; aucun ordre réel V10 n’a été vérifié.
- Cognitive Continuum livré : mémoire V9 read-only, registre d’interprétation, Cortex, enrichissement, apprentissage et audit de cohérence.
- Audit de cohérence : 17 modules de lecture connectés, 0 orphelin documenté.
- Corrections R9 : stale gate, dénominateur WR limité aux outcomes résolus, filtrage de cohérence par TF de décision.
- **Phases 13-15 livrées** : Wyckoff gate (Phase 13), LiquidityMap (Phase 14), Behavior Context Gate (Phase 15).
- Les prochains travaux doivent être décidés sur données fraîches et non sur les compteurs historiques inclus dans les anciens rapports.

## Documents historiques

Les documents de planification datés, audits, checkpoints, comptes rendus, prompts, exports et répertoires `archive/`, `backups/` ou `docs/calibration/` décrivent leur date de production. Ils sont conservés pour l’audit et ne sont pas réécrits rétroactivement. Toute valeur historique contradictoire est supplantée par le présent document et l’état V10 actif.
