# AGENT_BACKLOG — idées agents, non ouvertes

**Ce fichier est un backlog de notes, pas un chantier.** Rien ici ne doit être démarré
avant que `docs/ROADMAP.md` §« Chantiers futurs distincts » ne lève explicitement le gel
de la Phase 10 (fédération d'agents) et de l'architecture globale agents/routing/mémoire
avancée. Le collecter ici sert uniquement à ne pas perdre les idées entre sessions.

## Statut
🔒 Gelé — voir `docs/ROADMAP.md` §Phase 10 et §« Chantiers futurs distincts ».
Ne démarre pas avant stabilisation live de la Phase 9 (calibration sur données réelles).

## Squelette déjà existant dans le repo (structure seulement, pas de logique fédérée)
`agents/` contient déjà des dossiers README-only, posés en amont sans logique active :
- `agents/orchestrator/`
- `agents/force-reader/`
- `agents/scene-builder/`
- `agents/behavior-analyst/`
- `agents/window-gate/`
- `agents/reviewer/`

Ces README ne doivent pas être interprétés comme un début d'implémentation de la
Phase 10 — vérifier leur contenu réel avant toute supposition (ils peuvent être de
simples placeholders).

## Idées collectées (à ré-évaluer seulement après déblocage Phase 10)
- Un agent par couche cognitive (scene agent, behavior agent, window agent,
  exploitability agent, regime/principle agent) — cf. `docs/ROADMAP.md` §Phase 10.
- Un agent arbitre consolidant les lectures inter-couches.
- Un agent risk manager filtrant les décisions avant toute action (paper-trading
  d'abord, jamais d'exécution réelle avant Phase 12).

## Règle de sortie du gel
Ne retirer une idée de ce backlog vers un vrai chantier que sur décision explicite
consignée dans `memory/DECISIONS_LOG.md`, avec référence à la calibration live de la
Phase 9 ayant justifié le déblocage.
