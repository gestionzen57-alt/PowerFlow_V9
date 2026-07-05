# SKILLS_BACKLOG — idées skills, non ouvertes

**Backlog de notes, pas un chantier.** La génération automatique de skills/agents est
explicitement la plus tardive des trois initiatives gelées de `docs/ROADMAP.md`
§« Chantiers futurs distincts » — elle dépend d'un socle Phases 9-10 canonisé et
calibré en live. Ne rien démarrer ici avant ce déblocage.

## Statut
🔒 Gelé — dépend du déblocage de `AGENT_BACKLOG.md`, lui-même postérieur à la Phase 10.

## Squelette déjà existant dans le repo (README-only)
`skills/` contient déjà des dossiers placeholders, sans logique active :
- `skills/scene-reader/`
- `skills/behavior-reader/`
- `skills/window-evaluator/`
- `skills/replay-confronter/`
- `skills/doctrine-keeper/`

Vérifier leur contenu réel avant toute supposition — ce sont des points d'ancrage
documentaires posés en amont, pas un début d'implémentation.

## Idées collectées (à ré-évaluer seulement après déblocage)
- `scene-reader` : lecture/synthèse des scènes pour un humain ou un agent en aval.
- `behavior-reader` : synthèse lisible des comportements qualifiés.
- `window-evaluator` : aide à l'évaluation d'une fenêtre avant décision HITL.
- `replay-confronter` : confrontation systématique replay vs cas connus, en appui de
  `scripts/v9_replay.py --compare`.
- `doctrine-keeper` : garde-fou automatisé de cohérence doctrine (écho du rôle que
  Perplexity tient manuellement aujourd'hui).

## Règle de sortie du gel
Ne retirer une idée de ce backlog vers un vrai chantier que sur décision explicite
consignée dans `memory/DECISIONS_LOG.md`, jamais par extension implicite d'un travail
en cours sur `core/v9/`.
