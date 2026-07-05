# MEMORY_CANON — éléments stables du contexte V9

Synthèse des éléments qui ne changent pas d'une session à l'autre. Renvoie vers les
documents pivots pour le détail — ne duplique jamais leur contenu complet
(`docs/DOC_GOVERNANCE.md` règle 8).

## Doctrine durable (index — détail dans `docs/DOCTRINE.md` et `docs/doctrine/*.md`)
- Git est la source de vérité, jamais une mémoire de conversation.
- Une seule source de vérité par sujet (pas de doctrine concurrente).
- La migration métier précède l'agentification.
- Autonomie progressive, seulement après stabilité live.
- Aucune dépendance bloquante à un LLM/provider spécifique pour le cœur métier.
- Architecture agents/skills gelée tant que la phase métier en cours n'est pas
  canonisée et stable en live.
- Le code est présumé correct avant la documentation en cas de divergence
  (`docs/DOC_GOVERNANCE.md` §« Règle absolue »).
- Aucune logique d'exécution d'ordre avant la Phase 12 (interdit fondateur).
- MT4 (forces) dicte, MT5 (ticks) confirme, jamais l'inverse (règle 10).

## Décision fondatrice du projet
V9 part d'un dossier vide. Aucune mémoire, skill, convention ou workflow hérité de
V8/Hermes n'est repris implicitement — toute reprise passe par un audit explicite
(voir `docs/architecture/audit_v8_v9_migration.md`).

## Squelette cognitif officiel
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → (Régime → Principes →
Signal → Décision, ajoutés Phase 9) → Exécution éventuelle (Phase 12, non ouverte).

## État d'avancement fondamental (au 2026-07-05)
- Phases 1 à 9 terminées et fusionnées sur `feat/v9-foundation-clean`.
- 218 tests, tous verts.
- Gouvernance documentaire canonisée (`docs/ARCHITECTURE.md`, `docs/DOCTRINE.md`,
  `docs/LEXIQUE.md`, `docs/NOMENCLATURE.md`, `docs/ROADMAP.md`, `docs/DOC_GOVERNANCE.md`,
  `docs/DOC_REGISTRY.yml`).
- Deux gaps connus non bloquants : `zone_diagnostics` non alimentée (9/27 principes en
  dégradation gracieuse), marquage replay vs live absent des `decisions`.
- Phases 10-13 planifiées mais non démarrées ; Phase 10 et tout chantier d'architecture
  agentique globale explicitement gelés jusqu'à stabilisation live de la Phase 9.

## Rôles opérationnels stables
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité — ne code pas.
- Claude Code : implémentation structurée, ancrée dans la doctrine existante.
- Hermes free : support ciblé, itérations légères, expérimentations encadrées — jamais
  de décision de doctrine ou de structure.

## Documents pivots à toujours consulter en premier
`docs/STATE.md`, `docs/CACHE_BOARD.md`, `docs/ROADMAP.md`, `docs/PERPLEXITY.md`,
`docs/DOCTRINE.md`, `docs/DOC_GOVERNANCE.md`.
