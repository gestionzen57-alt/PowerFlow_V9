# LEXIQUE — PowerFlow V9

## Statut
Index alphabétique de navigation. Les définitions complètes vivent dans
[docs/lexicon/LEXICON_V9.md](lexicon/LEXICON_V9.md) — c'est la seule source de vérité pour
le vocabulaire métier. Ce fichier ne fait que trier et pointer.

**Règle** : tout nouveau terme métier introduit dans le code doit être ajouté à
`docs/lexicon/LEXICON_V9.md` (définition complète) puis référencé ici (ligne d'index).

## Index alphabétique

| Terme | Définition courte | Détail |
|---|---|---|
| Antagonisme | Conflit de forces entre devises, horizons ou structures | [LEXICON_V9.md](lexicon/LEXICON_V9.md#antagonisme) |
| Cinématique | Lecture du mouvement des forces (angle, courbure, pliure, pente, rotation) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#cinématique) |
| Coalition | Alignement de plusieurs forces/devises/horizons vers une même dynamique | [LEXICON_V9.md](lexicon/LEXICON_V9.md#coalition) |
| Comportement | Évolution dynamique d'une scène dans le temps (lutte, bascule, maintien, compression...) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#comportement) |
| Décision | Signal + contexte complet + action recommandée (Phase 9, en cours) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#décision) |
| Exploitabilité | Jugement tardif de tradabilité, subordonné à la qualité de lecture amont | [LEXICON_V9.md](lexicon/LEXICON_V9.md#exploitabilité) |
| Fenêtre | Moment ou période où une dynamique devient exploitable, surveillable ou invalide | [LEXICON_V9.md](lexicon/LEXICON_V9.md#fenêtre) |
| Force | Variation structurée d'intensité, direction ou équilibre entre devises/timeframes | [LEXICON_V9.md](lexicon/LEXICON_V9.md#force) |
| Live | Données en temps réel du marché ouvert, par opposition à Replay | [LEXICON_V9.md](lexicon/LEXICON_V9.md#live) |
| Orchestrateur | Composant qui enchaîne automatiquement les couches cognitives après chaque snapshot | [LEXICON_V9.md](lexicon/LEXICON_V9.md#orchestrateur) |
| Orchestration | Organisation globale des relations entre forces, scènes, temporalités et devises | [LEXICON_V9.md](lexicon/LEXICON_V9.md#orchestration) |
| Pliure | Changement de direction (inversion de pente) d'une force | [LEXICON_V9.md](lexicon/LEXICON_V9.md#pliure) |
| Principe | Règle de trading évaluable (entrée → bool + confiance) — un détecteur, pas un signal (Phase 9, en cours) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#principe) |
| Régime | État global du marché (trend, range, breakout, compression) (Phase 9, en cours) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#régime) |
| Replay | Confrontation d'un cas actuel à des cas passés / rejeu de données historiques | [LEXICON_V9.md](lexicon/LEXICON_V9.md#replay) |
| Scène | Configuration locale du marché à un instant ou sur une fenêtre donnée | [LEXICON_V9.md](lexicon/LEXICON_V9.md#scène) |
| Signal | Agrégation de plusieurs principes → direction + confiance (Phase 9, en cours) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#signal) |
| Snapshot | Capture instantanée des 8 forces d'un symbole/timeframe à un `bar_time` donné | [LEXICON_V9.md](lexicon/LEXICON_V9.md#snapshot) |
| Stale | Donnée périmée (âge > seuil de fraîcheur par timeframe) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#stale) |
| Zone | Espace de prix ou de structure significatif pour la lecture | [LEXICON_V9.md](lexicon/LEXICON_V9.md#zone) |
| Zone extrême | Niveau HTF où les forces atteignent un extrême, source d'opportunité LTF (Phase 9, en cours) | [LEXICON_V9.md](lexicon/LEXICON_V9.md#zone-extrême) |

## Termes marqués « Phase 9, en cours »

Ces termes correspondent à du code présent dans l'arborescence mais non finalisé, développé
sur une session concurrente au moment de la rédaction (2026-07-05). Leur définition est
provisoire et doit être revalidée contre le code réel à la clôture de la Phase 9 — voir
[docs/phases/PHASE9_DECISION.md](phases/PHASE9_DECISION.md) et règle du
[DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) (« le code est la source de vérité »).
