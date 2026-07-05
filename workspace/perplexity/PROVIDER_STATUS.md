# PROVIDER_STATUS — rôles opérationnels V9

Reprend et détaille `docs/PERPLEXITY.md` §« Rôles opérationnels » et
`docs/CACHE_BOARD.md`. Ce tableau ne redéfinit pas la doctrine, il en donne une vue
opérationnelle (qui fait quoi, quand basculer).

## Tableau des providers

| Provider | Rôle | Disponibilité | Usage recommandé | Fallback |
|---|---|---|---|---|
| **Perplexity** | Doctrine, orchestration, structure, checkpoints, continuité entre sessions. Ne code pas. | Continu, entre les sessions de code | Arbitrage doctrine, rédaction de checkpoints, maintien de `BOARD.md`/`STATE.md`/`ROADMAP.md`, brief avant implémentation | Aucun — rôle non substituable par un autre provider sans reconstruire la continuité manuellement |
| **Claude Code** | Implémentation structurée du code métier (`core/v9/`, `scripts/`, `ea/`, tests). | Session par session, sur demande | Toute implémentation structurante ancrée dans un document de doctrine existant | — |
| **Hermes free** | Support ciblé, itérations légères, expérimentations encadrées. | Ponctuel | Petites itérations, tests exploratoires n'engageant pas la doctrine ou la structure | Ne jamais l'utiliser pour une décision de doctrine ou de structure — remonter à Perplexity |

## Notes
- **Aucun de ces providers ne doit lancer la Phase 10** (fédération d'agents) ni ouvrir
  de chantier d'architecture agentique globale avant stabilisation live de la Phase 9
  (`docs/ROADMAP.md` §« Chantiers futurs distincts »).
- Perplexity arbitre les conflits de doctrine **avant** qu'ils n'atteignent
  l'implémentation — si Claude Code détecte une ambiguïté de doctrine en cours de code,
  il doit remonter à Perplexity plutôt que trancher seul.
- Aucune dépendance bloquante à un LLM/provider spécifique pour le cœur métier
  (règle doctrine, voir `docs/DOCTRINE.md`) — ce tableau documente une répartition de
  rôles de continuité, pas une dépendance technique du code `core/v9/`.
- En cas d'absence prolongée d'un provider (ex. Perplexity indisponible), utiliser
  `REPRISE_TEMPLATE.md` avec n'importe quel autre assistant pour reconstruire le contexte
  à partir des fichiers de reprise — jamais depuis une mémoire supposée.
