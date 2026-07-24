# exchange.md — Mémoire de coordination inter-agents PowerFlow V9

> **Bus de coordination pour Hermes, ZCode, Claude CLI et futurs agents.**
> Chaque agent lit ce fichier au démarrage de session et y inscrit son statut.
> Git = source de vérité (R14). Pas de coordination hors Git.

## Demandes en attente CEO (Søn)

| # | Demande | Acteur | Date | Statut |
|---|---|---|---|---|
| 1 | Token Telegram : rotation BotFather (4 tokens expirés) | Søn | 18/07 | EN ATTENTE |
| 2 | CVD : recompilation EA + restart capture (fenêtre contrôlée) | Søn | FAIT (déjà déployé) | ✅ |

## Handoffs inter-agents

| De | Vers | Sujet | Date | Statut |
|---|---|---|---|---|
| Hermes | ZCode | Align PRINCIPLE_ACTIVE_IDS sur YAML | 23/07 | ✅ Fait |
| Hermes | Claude CLI | Câblage DRM dans resolver | 23/07 | ✅ Fait |
| Hermes | Claude CLI | Colonnes bayésiennes dans signals table | 23/07 | ✅ Fait |

## Statuts agents (dernier passage)

| Agent | Dernière session | HEAD | Périmètre |
|---|---|---|---|
| Hermes | 23-24/07 | 9f55a64 | 5 causes racines + boucle fermée + purge DB + sync docs |
| ZCode | 22-23/07 | 98f7e78 | Analyse comportementale (9 filtres + 8 boosts + principe) |
| Claude CLI | - | - | (pas de session récente) |

## Arbitrages CEO actifs

| # | Décision | Date | Détail |
|---|---|---|---|
| 1 | V9_NO_BAISSIERE=0 | 23/07 | 2 directions (haussier + baissier) |
| 2 | V9_GBPUSD_LONG_ONLY=0 | 23/07 | Plus de forçage haussier GBPUSD |
| 3 | DRM APPLY permanent | 20/07 | R32 fermée — TP/SL adaptatifs par phase |
| 4 | edge_threshold learn loop 0.55 | 23/07 | Boucle d'apprentissage fermée |
| 5 | Horizon resolver 8h | 23/07 | Plus de temps pour toucher TP |

## Règles multi-IA (R28)

- Chaque agent peut commit + push directement sur `feat/v9-foundation-clean`
- `git pull --rebase` avant tout push
- Tests verts avant push (R7)
- 1 commit atomique par livraison (R22)
- Entrée DECISIONS_LOG si changement structurant (R26)
- Montrer SHA + 1 ligne après push

## Procédure de handoff

1. Agent sortant : met à jour `memory/memory.md` + `memory/exchange.md` + `docs/STATE.md`
2. Agent entrant : lit `memory/exchange.md` (handoffs) → `docs/CACHE_BOARD.md` → `docs/STATE.md`
3. Agent entrant : `git pull` + tests verts avant toute action
4. Agent entrant : inscrit son statut dans exchange.md après première action