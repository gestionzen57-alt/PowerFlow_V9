# MEMORY_CONTRACT — Contrat de mémoire entre couches

## Statut
Document de spécification. PowerFlow V9 — Phase 1 (Squelette cognitif).
Aucune logique de trading, aucune logique d'exécution.
Ce document couvre les 5 couches de l'ordre cognitif officiel : Forces, Scènes (couches amont), et Comportements, Fenêtres, Exploitabilité (couches aval). Aucune couche ne dépend de la couche Exécution.

## Principe fondateur
Rappel de la Règle 3 de la CHARTE_COGNITIVE_V9 :

> La mémoire sert d'abord à conserver et confronter les lectures, scènes, comportements et fenêtres.

**La mémoire sert d'abord la perception, pas l'exécution.**
Aucune entrée de mémoire n'existe pour préparer, justifier ou accélérer une décision d'exécution. Une entrée de mémoire existe pour que le système puisse un jour se souvenir de ce qu'il a perçu, et confronter une perception présente à une perception passée (replay, Phase 6).

**On ne migre pas une mémoire, on migre des connaissances validées.**
Une mémoire brute (hypothèse, snapshot temporaire, observation non confrontée) ne traverse jamais telle quelle une frontière de couche, de version ou de projet. Seule une connaissance qui a été validée — confrontée, stable, reproductible — peut être portée plus loin. Ce principe s'applique aussi bien entre couches qu'entre V8 et V9 (Règle 5, migration curée).

## Ce que la couche Forces écrit en mémoire

- **Snapshots de forces validés** : un snapshot n'est écrit en mémoire durable que s'il a passé le STALE_GATE (voir `FORMAT_FORCES.md`) — un snapshot périmé n'est jamais persisté comme référence fiable.
- **Anomalies de lecture** : inversions suspectes, valeurs aberrantes, ruptures de continuité entre deux snapshots consécutifs. Ces anomalies sont des hypothèses, pas des faits établis.
- **Aucune interprétation** : la couche Forces n'écrit jamais de coalition, d'antagonisme ou de cinématique — ce travail appartient à la couche Scènes.

## Ce que la couche Scènes écrit en mémoire

- **Scènes construites**, référençant leur `forces_snapshot_ref` — jamais une scène qui duplique les données de forces.
- **Hypothèses de lecture** : une coalition, un antagonisme ou une signature de cohérence qui semble se dessiner mais n'a pas encore été confrontée à d'autres scènes.
- **Aucune qualification temporelle** : la couche Scènes n'écrit jamais un comportement, une transition ou une fenêtre — ce travail appartient aux couches aval.

## Ce que chaque couche lit en mémoire

| Couche | Lit |
|---|---|
| Forces | Ses propres derniers snapshots validés (pour calculer `vitesse`, détecter `croisement`/`recroisement`). Ne lit jamais les scènes. |
| Scènes | Les snapshots de forces validés référencés. L'historique de ses propres scènes récentes (pour détecter une rotation de leadership ou une bascule d'équilibre, qui nécessitent une comparaison dans le temps). Ne lit jamais un comportement, une fenêtre ou une exploitabilité. |

Chaque couche lit sa propre production passée et la production validée de la couche immédiatement amont. Aucune couche ne lit une couche aval : cela violerait la Règle 1 (primauté de la lecture) et l'ordre cognitif officiel.

## Couches aval

### Couche Comportements

- **ÉCRIT** :
  - Comportements qualifiés (`behavior_id`, qualification, intensité, phase, confiance_qualification).
  - Transitions détectées (comportement précédent → actuel, point de rupture, sens).
  - Comparaisons aux cas connus (similarité_score, cas référencés).
- **LIT** :
  - Scènes validées en mémoire (pour qualifier les comportements).
  - Comportements passés qualifiés (pour comparaison et replay).
- **Cycle de vie** : identique (hypothèse → validation → archive).

### Couche Fenêtres

- **ÉCRIT** :
  - Fenêtres ouvertes (`window_id`, statut, type, niveau_confiance).
  - Fenêtres fermées (timestamp_fermeture, raison).
  - Fragilités détectées (booléen + raison).
  - Conditions d'invalidation (liste).
- **LIT** :
  - Comportements qualifiés (pour ouvrir/fermer fenêtres).
  - Fenêtres passées (pour replay et comparaison).
- **Cycle de vie** : identique (hypothèse → validation → archive).

### Couche Exploitabilité

- **ÉCRIT** :
  - Évaluations d'exploitabilité (statut, niveau_confiance_global).
  - Raisons de refus (enum documenté).
  - Demandes de validation HITL (booléen + raison).
  - `replay_context` (cas comparés, synthèse).
- **LIT** :
  - Fenêtres ouvertes/fermées (pour évaluer exploitabilité).
  - Évaluations passées (pour calibration du seuil de confiance).
- **Cycle de vie** : identique (hypothèse → validation → archive).

## Cycle de vie des entrées mémoire

```
hypothèse ──────────────► memory_temp.md
                               │
                validation ────┼──── rejet
                               │           │
                               ▼           ▼
                          memory.md     archive
```

1. **Hypothèse** : toute observation nouvelle (anomalie de forces, coalition naissante, signature de cohérence) est d'abord écrite dans `memory_temp.md`. Elle n'a aucune autorité tant qu'elle n'est pas confrontée.
2. **Validation** : une hypothèse confirmée par confrontation (répétition, cohérence avec d'autres lectures, stabilité dans le temps) est promue vers `memory.md`. Elle devient une connaissance de référence pour les couches qui lisent en amont.
3. **Rejet** : une hypothèse infirmée, contredite ou devenue non pertinente est déplacée vers l'archive. Elle n'est pas supprimée — elle reste traçable pour éviter de reproduire la même hypothèse sans apprentissage.

Aucune entrée ne saute d'étape. Une hypothèse ne devient jamais directement une connaissance archivée sans passer par une tentative de validation, et ne devient jamais une connaissance de référence sans passer par l'état hypothèse.

## Champs obligatoires

- `schema_version` (string) — Version du schéma JSON, actuellement 1.0. Permet le versioning et la migration future.

## Format des entrées mémoire

```json
{
  "schema_version": "string — version du schéma JSON, actuellement 1.0. Permet le versioning et la migration future.",
  "entry_id": "string — identifiant unique de l'entrée",
  "type": "string — snapshot_forces | anomalie_forces | scene | hypothese_coalition | hypothese_antagonisme | signature_coherence",
  "statut": "string — hypothese | valide | rejete",
  "couche_origine": "string — forces | scenes",
  "created_at": "string — ISO8601 UTC, date de création de l'hypothèse",
  "resolved_at": "string|null — ISO8601 UTC, date de validation ou de rejet",
  "reference": {
    "id": "string — identifiant de l'objet référencé (snapshot_id ou scene_id)",
    "timestamp": "string — ISO8601 UTC"
  },
  "contenu": "object — payload natif de l'entrée (structure libre selon le type, alignée sur FORMAT_FORCES ou FORMAT_SCENES)",
  "justification": "string — raison de la validation ou du rejet, obligatoire si statut != hypothese"
}
```

### Exemple — hypothèse en attente (`memory_temp.md`)

```json
{
  "schema_version": "1.0",
  "entry_id": "mem-20260705-141502-014",
  "type": "hypothese_coalition",
  "statut": "hypothese",
  "couche_origine": "scenes",
  "created_at": "2026-07-05T14:15:02.000Z",
  "resolved_at": null,
  "reference": {
    "id": "scene-20260705-141500-001",
    "timestamp": "2026-07-05T14:15:00.000Z"
  },
  "contenu": {
    "devises_alignees": ["AUD", "NZD"],
    "intensite_alignement": 64.5,
    "leader": "NZD"
  },
  "justification": ""
}
```

### Exemple — connaissance validée (`memory.md`)

```json
{
  "schema_version": "1.0",
  "entry_id": "mem-20260705-093000-002",
  "type": "signature_coherence",
  "statut": "valide",
  "couche_origine": "scenes",
  "created_at": "2026-07-05T09:00:00.000Z",
  "resolved_at": "2026-07-05T09:45:00.000Z",
  "reference": {
    "id": "scene-20260705-090000-014",
    "timestamp": "2026-07-05T09:00:00.000Z"
  },
  "contenu": {
    "libelle": "alignement descendant H4 vers M5 confirmé",
    "occurrences_confrontees": 6
  },
  "justification": "Répétée sur 6 scènes consécutives sur 45 minutes avec cohérence de sens à chaque timeframe, sans invalidation."
}
```

### Exemple — hypothèse rejetée (archive)

```json
{
  "schema_version": "1.0",
  "entry_id": "mem-20260705-081500-007",
  "type": "anomalie_forces",
  "statut": "rejete",
  "couche_origine": "forces",
  "created_at": "2026-07-05T08:15:00.000Z",
  "resolved_at": "2026-07-05T08:20:00.000Z",
  "reference": {
    "id": "forces-20260705-081500-330",
    "timestamp": "2026-07-05T08:15:00.000Z"
  },
  "contenu": {
    "devise": "AUD",
    "timeframe": "M5",
    "observation": "saut d'intensité de 12 à 58 entre deux clôtures consécutives"
  },
  "justification": "Confirmé comme artefact de reconnexion de flux MT4/SDI, pas une variation réelle de force. Ne pas retenir comme signal de rupture."
}
```

## Règles de gouvernance de ce contrat

### Règle A — La mémoire sert la perception, pas l'exécution
Aucune entrée mémoire n'est structurée en fonction d'un besoin d'exécution futur. Le contenu d'une entrée reste descriptif, jamais prescriptif.

### Règle B — On migre des connaissances, pas des mémoires
Seules les entrées au statut `valide` peuvent être portées vers une couche aval, une nouvelle version du système, ou un module de replay. Les hypothèses et les entrées rejetées restent internes à la couche qui les a produites.

### Règle C — Traçabilité totale
Aucune entrée n'est supprimée. Le passage `hypothese → valide` ou `hypothese → rejete` est toujours accompagné d'une `justification`. L'archive est une mémoire à part entière, pas une corbeille.

### Règle D — Aucune lecture aval
Aucune couche ne lit une entrée mémoire produite par une couche qui se situe plus loin qu'elle dans l'ordre cognitif officiel. Une entrée produite par la couche Scènes ne peut jamais influencer une lecture de la couche Forces.

### Règle E — Écriture aval conditionnée à la cohérence interne
Toute couche aval ne peut écrire en mémoire que des productions validées par sa propre cohérence interne. Les hypothèses restent en `memory_temp.md` jusqu'à validation.
