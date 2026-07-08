# ORCHESTRATION_POLICY_V9.md

## But
Définir comment V9 orchestre agents, skills, validations et escalades.

## Principe cardinal
L'orchestration doit servir la perception, jamais la dominer.

## Rôles types

### Orchestrator
- lit l'état global
- choisit le bon sous-système
- empêche les raccourcis cognitifs
- décide s'il faut continuer ou escalader

### force-reader
- lit les forces multi-devises / multi-timeframes
- extrait les tensions structurantes

### scene-builder
- construit la scène du moment
- lie forces, zones, temporalité, coalition, antagonisme

### behavior-analyst
- qualifie la dynamique de la scène
- lit la cinématique et la transformation dans le temps

### replay-confronter
- compare à des scènes / comportements passés
- détecte ressemblances, divergences, singularités

### window-gate
- qualifie l'ouverture / fermeture de fenêtre

### reviewer
- contrôle cohérence / contradiction / manque de preuve

## Règles d'appel
- Un agent d'aval ne peut pas invalider seul une couche amont sans reviewer.
- Toute décision ambiguë revient vers orchestrator.
- Toute nouvelle catégorie de comportement passe par replay + validation humaine.

## HITL obligatoire si
- ambiguïté
- conflit entre agents
- nouvelle lecture non classée
- décision sensible
- fenêtre potentiellement exploitable mais mal prouvée

## Règles anti-dérive
- Pas d'agent "omniscient".
- Pas d'exécution sans gate.
- Pas de scoring qui remplace la lecture.
- Pas de solution technique non localisée dans la chaîne cognitive.

## Critère de succès
L'orchestration est bonne si elle rend la perception plus claire, plus traçable et plus stable.

## Mode A borné (Phase 9.10) — implémentation réelle

Réalignement 2026-07-08 (Phase 9.8 Phase B, livrable B7) : les 7 rôles canoniques ci-dessus
sont une doctrine de rôles, pas des noms de code. L'implémentation réelle
(`agents/REGISTRY.py`, sprint Søn 2026-07-07) est le **Mode A borné** : 5 agents chauds +
1 supervisor + 1 reviewer = 7 agents, en observation seule (0 auto-apply, télémétrie
`core/v9/agent_telemetry.py`).

### Mapping rôles canoniques ↔ agents Mode A

| Rôle canonique | Agent Mode A | Écart |
|---|---|---|
| force-reader | `force_reader` | aucun — correspondance directe |
| scene-builder | `scene_builder` | aucun — correspondance directe |
| behavior-analyst | `behavior_analyst` | aucun — correspondance directe |
| window-gate | `gatekeeper` | renommage seul, rôle identique (qualifie l'ouverture/fermeture de fenêtre) |
| reviewer | `reviewer` | aucun — correspondance directe |
| Orchestrator | `supervisor` | renommage seul, rôle identique (lit l'état global, empêche les raccourcis, décide d'escalader) |
| replay-confronter | *(aucun agent Mode A)* | voir note ci-dessous — pas un oubli, un report explicite |
| *(aucun rôle canonique)* | `decision_maker` | agent supplémentaire — voir justification ci-dessous |

### `decision_maker` — justification (résout friction F7)

`decision_maker` n'a pas d'équivalent dans les 7 rôles canoniques d'origine (2026-07-05) parce
que ces rôles décrivaient uniquement la **chaîne perceptuelle amont**. Depuis
[`docs/doctrine/CHARTE_COGNITIVE_V9.md`](CHARTE_COGNITIVE_V9.md) v0.2 (Phase 9.8 B1), la
**chaîne opérationnelle aval** documente explicitement une couche « Décision » (couche 8/10) —
`decision_maker` est l'agent qui l'implémente. Il est donc justifié par CHARTE Règle 4
(architecture avant code) : sa place dans la chaîne cognitive est maintenant écrite, ce qui
n'était pas le cas avant la v0.2 de la CHARTE.

### `replay-confronter` — agent futur Phase 13

`replay-confronter` (compare à des scènes/comportements passés, détecte ressemblances et
singularités) **n'a aucun agent Mode A dédié à ce jour**. Ce n'est pas un oubli d'implémentation
mais un report explicite : la confrontation replay dépend d'un historique suffisant de
décisions win/loss pour être utile (voir `docs/DOCTRINE.md` Règle 30 — seuil ≥ 50 déclenchements
pour la « Phase 13 complète », recalibrage arbiter zone-type × session). Tant que ce seuil n'est
pas atteint, un agent `replay-confronter` n'aurait aucune donnée à confronter. Il sera
implémenté au déblocage de la Phase 13 (voir `docs/ROADMAP.md`), pas avant.

### Exemption explicite de la Règle 19 pour le Mode A borné

`docs/DOCTRINE.md` Règle 19 (« Les chantiers agents/routing/skills auto-générés ne démarrent
pas avant canonisation live ») **ne s'applique pas** au Mode A borné décrit ci-dessus. Ceci
résout la friction F8 de `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.3 : le Mode A borné est
en observation stricte (0 auto-apply, 0 décision non supervisée), distinct de la
« Phase 10 — fédération d'agents » que la Règle 19 vise réellement et que
`docs/ROADMAP.md` documente comme gelée. L'exemption tient à 3 conditions cumulatives, toutes
vraies au 2026-07-08 :
1. Zéro auto-apply — chaque décision reste soumise à validation HITL en aval (Arbiter →
   RiskManager → PaperTradeLogger, jamais d'ordre réel).
2. Télémétrie complète — chaque appel d'agent est journalisé (`agent_telemetry.py`), donc
   auditable a posteriori, pas une boîte noire.
3. Portée bornée à 7 agents fixes (pas de génération dynamique de nouveaux rôles/skills).

Si l'une de ces 3 conditions cesse d'être vraie (auto-apply activé, télémétrie désactivée, ou
extension à des rôles/skills générés dynamiquement), l'exemption cesse et la Règle 19
s'applique de nouveau sans dérogation.