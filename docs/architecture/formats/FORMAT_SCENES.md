# FORMAT_SCENES — Spécification de sortie de la couche Scènes

## Statut
Document de spécification. PowerFlow V9 — Phase 1 (Squelette cognitif).
Aucune logique de trading, aucune logique d'exécution.
Ce document ne dépend d'aucune couche aval (Comportements, Fenêtres, Exploitabilité, Exécution).

## Place dans la chaîne cognitive
La couche Scènes est la deuxième couche de l'ordre cognitif officiel :

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle
```

Elle ne consomme que la sortie de la couche Forces (voir `FORMAT_FORCES.md`). Elle ne lit jamais une couche aval. Elle produit le seul matériau que la couche Comportements est autorisée à consommer.

## Définition native (rappel LEXICON_V9)
**Scène** : configuration locale du marché dans une fenêtre donnée.
Une scène assemble forces, zone, temporalité, coalitions, antagonismes et cinématique en une lecture cohérente — sans jamais qualifier une dynamique dans le temps (ce rôle appartient à la couche Comportements) ni statuer sur une exploitabilité.

## Champs obligatoires

- `schema_version` (string) — Version du schéma JSON, actuellement 1.0. Permet le versioning et la migration future.

## Principes de format

- Une scène référence son snapshot de forces source (`forces_snapshot_ref`) — elle ne duplique jamais les données brutes de forces.
- Une scène est **datée** et **localisée** (zone), jamais un concept abstrait flottant.
- Les coalitions et antagonismes sont des **listes** : une scène peut contenir zéro, une ou plusieurs coalitions/antagonismes simultanément.
- La cinématique est **locale** à la scène : elle décrit le mouvement des forces au sein de cette configuration précise, pas une tendance générale.
- Les confluences multi-timeframes (MTF) décrivent l'emboîtement des lectures entre timeframes, pas une moyenne ou un consensus.
- Aucun champ ne représente une décision, un score d'exploitabilité ou une intention d'exécution.

## Structure JSON complète

```json
{
  "schema_version": "string — version du schéma JSON, actuellement 1.0. Permet le versioning et la migration future.",
  "scene_id": "string — identifiant unique de la scène (ex: uuid4)",
  "timestamp": "string — ISO8601 UTC, instant de constitution de la scène",
  "timeframes_concernes": "array[string] — sous-ensemble de M1, M5, M15, M30, H1, H4, D1 impliqués dans la scène",
  "forces_snapshot_ref": {
    "snapshot_id": "string — référence au snapshot_id de FORMAT_FORCES",
    "timestamp": "string — ISO8601 UTC, timestamp du snapshot référencé"
  },
  "zone": {
    "prix": {
      "niveau_reference": "number — prix pivot de la zone",
      "borne_basse": "number|null",
      "borne_haute": "number|null"
    },
    "structure": "string — description native de la structure (ex: zone de rejet, zone de rotation, zone de compression)",
    "niveau": "string — importance perçue de la zone (ex: mineure, intermediaire, majeure)"
  },
  "coalitions": [
    {
      "devises_alignees": "array[string] — devises impliquées dans la coalition",
      "intensite_alignement": "number — force de l'alignement",
      "leader": "string — devise identifiée comme meneuse de la coalition",
      "rotation_leadership": {
        "detectee": "boolean",
        "ancien_leader": "string|null",
        "nouveau_leader": "string|null"
      }
    }
  ],
  "antagonismes": [
    {
      "devises_en_conflit": "array[string] — devises impliquées dans l'antagonisme",
      "intensite_conflit": "number — force du conflit",
      "bascule_equilibre": {
        "detectee": "boolean",
        "sens": "string|null — devise vers laquelle l'équilibre bascule"
      }
    }
  ],
  "cinematique_locale": {
    "angle": "number — angle de la trajectoire de force locale",
    "courbure": "number — courbure de la trajectoire",
    "pente": "number — pente instantanée",
    "pliure": {
      "detectee": "boolean",
      "severite": "number|null — sévérité de la rupture de dynamique"
    },
    "acceleration_deceleration": "string — acceleration | deceleration | stable",
    "rotation_force": {
      "detectee": "boolean",
      "sens": "string|null — sens de la rotation (ex: horaire, antihoraire, ou description native)"
    },
    "compression_extension": {
      "etat": "string — compression | extension | neutre",
      "intensite": "number"
    }
  },
  "confluences_mtf": {
    "emboitement_detecte": "boolean — les lectures des timeframes concernés s'emboîtent-elles",
    "cascades_temporelles": [
      {
        "de_timeframe": "string",
        "vers_timeframe": "string",
        "description": "string — nature de la cascade observée"
      }
    ],
    "signatures_coherence": "array[string] — libellés natifs des signatures de cohérence détectées"
  },
  "contexte_temporel": {
    "session": "string — Sydney | Tokyo | Londres | New York | chevauchement",
    "fenetre": "string — description native de la fenêtre temporelle (ex: ouverture de session, mi-session, clôture)"
  }
}
```

## Exemple JSON complet et valide

```json
{
  "schema_version": "1.0",
  "scene_id": "scene-20260705-141500-001",
  "timestamp": "2026-07-05T14:15:00.000Z",
  "timeframes_concernes": ["M5", "M15", "H4"],
  "forces_snapshot_ref": {
    "snapshot_id": "forces-20260705-141500-001",
    "timestamp": "2026-07-05T14:15:00.000Z"
  },
  "zone": {
    "prix": {
      "niveau_reference": 1.0862,
      "borne_basse": 1.0850,
      "borne_haute": 1.0875
    },
    "structure": "zone de rotation autour d'un ancien niveau de rejet H4",
    "niveau": "majeure"
  },
  "coalitions": [
    {
      "devises_alignees": ["USD", "EUR"],
      "intensite_alignement": 71.2,
      "leader": "USD",
      "rotation_leadership": {
        "detectee": false,
        "ancien_leader": null,
        "nouveau_leader": null
      }
    },
    {
      "devises_alignees": ["AUD", "NZD"],
      "intensite_alignement": 64.5,
      "leader": "NZD",
      "rotation_leadership": {
        "detectee": true,
        "ancien_leader": "AUD",
        "nouveau_leader": "NZD"
      }
    }
  ],
  "antagonismes": [
    {
      "devises_en_conflit": ["USD", "GBP"],
      "intensite_conflit": 48.9,
      "bascule_equilibre": {
        "detectee": true,
        "sens": "USD"
      }
    }
  ],
  "cinematique_locale": {
    "angle": 34.5,
    "courbure": 0.18,
    "pente": 2.1,
    "pliure": {
      "detectee": true,
      "severite": 22.0
    },
    "acceleration_deceleration": "acceleration",
    "rotation_force": {
      "detectee": true,
      "sens": "antihoraire"
    },
    "compression_extension": {
      "etat": "extension",
      "intensite": 38.0
    }
  },
  "confluences_mtf": {
    "emboitement_detecte": true,
    "cascades_temporelles": [
      {
        "de_timeframe": "H4",
        "vers_timeframe": "M15",
        "description": "la coalition USD/EUR amorcée en H4 se retrouve en accélération sur M15"
      },
      {
        "de_timeframe": "M15",
        "vers_timeframe": "M5",
        "description": "confirmation de la bascule d'équilibre USD/GBP sur M5"
      }
    ],
    "signatures_coherence": [
      "alignement descendant H4 vers M5 confirmé",
      "rotation de leadership AUD/NZD isolée au timeframe M15"
    ]
  },
  "contexte_temporel": {
    "session": "Londres",
    "fenetre": "mi-session, avant chevauchement New York"
  }
}
```

## Ce que ce format ne fait jamais

- Il ne qualifie aucun comportement dans le temps (rôle de la couche Comportements).
- Il ne statue jamais sur une fenêtre ouverte, fragile ou invalidée.
- Il ne produit aucun score d'exploitabilité.
- Il ne duplique jamais les données de forces : il les référence via `forces_snapshot_ref`.
- Il ne compare jamais la scène courante à l'historique (rôle du replay, Phase 6).
