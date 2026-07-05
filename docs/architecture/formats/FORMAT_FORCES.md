# FORMAT_FORCES — Spécification de sortie de la couche Forces

## Statut
Document de spécification. PowerFlow V9 — Phase 1 (Squelette cognitif).
Aucune logique de trading, aucune logique d'exécution.
Ce document ne dépend d'aucune couche aval (Scènes, Comportements, Fenêtres, Exploitabilité, Exécution).

## Place dans la chaîne cognitive
La couche Forces est la première couche de l'ordre cognitif officiel :

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle
```

Elle ne lit rien en amont. Elle produit le seul matériau que la couche Scènes est autorisée à consommer.

## Définition native (rappel LEXICON_V9)
**Force** : variation structurée d'intensité, direction ou équilibre entre devises / timeframes.

## Principes de format

- Le format est un **snapshot** : une photographie datée de l'état des forces sur les 8 devises et les timeframes candle-close, plus un état séparé pour M1 (ticks/vélocité).
- Chaque entrée de force est **auto-porteuse** : elle contient sa propre fraîcheur (`freshness`), indépendamment du snapshot global.
- Le format est **plat et implémentable en Python** sous forme de liste de dictionnaires (facilement sérialisable en lignes de base de données).
- Aucun champ ne représente une décision, un score d'exploitabilité ou une intention d'exécution.

## Devises couvertes
`USD`, `GBP`, `EUR`, `JPY`, `CAD`, `CHF`, `AUD`, `NZD` — 8 devises fixes, aucune extension implicite.

## Timeframes couverts

### Candle-close (tableau `forces`)
`M5`, `M15`, `M30`, `H1`, `H4`, `D1`

### Tick / vélocité (tableau `m1`)
`M1` est **géré séparément**. Il n'est pas une bougie clôturée mais un flux de ticks avec vélocité instantanée. Il ne partage pas le schéma candle-close.

## STALE_GATE — règle de péremption

Chaque entrée porte un objet `freshness` qui permet à toute couche consommatrice de refuser une donnée périmée **sans avoir à interroger la source**.

| Timeframe | Seuil de péremption (`stale_threshold_ms`) |
|---|---|
| M1 (tick) | 5 000 ms |
| M5 | 30 000 ms |
| M15 | 90 000 ms |
| M30 | 180 000 ms |
| H1 | 300 000 ms |
| H4 | 900 000 ms |
| D1 | 3 600 000 ms |

Règle : `stale = (now - timestamp) > stale_threshold_ms`.
Si `stale = true`, l'entrée doit être traitée comme **absente** par toute couche aval — jamais comme une valeur dégradée utilisable. Le STALE_GATE est bloquant, pas informatif.

Le snapshot porte également une fraîcheur globale (`freshness` au niveau racine) qui reflète l'instant de capture toutes sources confondues.

## Structure JSON complète

```json
{
  "snapshot_id": "string — identifiant unique du snapshot (ex: uuid4)",
  "timestamp": "string — ISO8601 UTC, instant de constitution du snapshot",
  "source": "string — MT4_SDI | MT5_TICK",
  "freshness": {
    "captured_at": "string — ISO8601 UTC",
    "age_ms": "integer — âge du snapshot en millisecondes au moment de la lecture",
    "stale": "boolean",
    "stale_threshold_ms": "integer — seuil appliqué au snapshot global"
  },
  "forces": [
    {
      "devise": "string — USD | GBP | EUR | JPY | CAD | CHF | AUD | NZD",
      "timeframe": "string — M5 | M15 | M30 | H1 | H4 | D1",
      "intensite": "number — valeur brute de force (magnitude)",
      "direction": "string — haussiere | baissiere | neutre",
      "vitesse": "number — taux de changement de l'intensité entre deux clôtures",
      "croisement": {
        "detecte": "boolean",
        "devise_partenaire": "string|null — devise avec laquelle le croisement a lieu",
        "direction": "string|null — haussiere | baissiere"
      },
      "recroisement": {
        "detecte": "boolean",
        "contexte": "string|null — description courte du contexte de recroisement"
      },
      "rejet_repulsion": {
        "detecte": "boolean",
        "intensite": "number|null — intensité du rejet/repulsion si détecté"
      },
      "compression_extension": {
        "etat": "string — compression | extension | neutre",
        "intensite": "number — intensité de l'état"
      },
      "freshness": {
        "timestamp": "string — ISO8601 UTC, horodatage de la clôture source",
        "age_ms": "integer",
        "stale": "boolean",
        "stale_threshold_ms": "integer"
      }
    }
  ],
  "m1": [
    {
      "devise": "string — USD | GBP | EUR | JPY | CAD | CHF | AUD | NZD",
      "mode": "string — tick_velocity (constante, distingue M1 du candle-close)",
      "dernier_tick_timestamp": "string — ISO8601 UTC",
      "intensite_instantanee": "number — valeur brute de force au dernier tick",
      "direction": "string — haussiere | baissiere | neutre",
      "vitesse_tick": "number — taux de changement entre ticks",
      "nb_ticks_fenetre": "integer — nombre de ticks pris en compte",
      "fenetre_ms": "integer — largeur de la fenêtre de calcul en millisecondes",
      "freshness": {
        "timestamp": "string — ISO8601 UTC",
        "age_ms": "integer",
        "stale": "boolean",
        "stale_threshold_ms": "integer"
      }
    }
  ]
}
```

## Note sur l'exemple

L'exemple ci-dessous est syntaxiquement complet et valide. Pour rester lisible, il illustre **2 timeframes candle-close par devise** (`M5` et `H4`) au lieu des 6 timeframes possibles. En production, chaque devise expose une entrée par timeframe candle-close (`M5`, `M15`, `M30`, `H1`, `H4`, `D1`) dans le tableau `forces`, en plus de son entrée dans le tableau `m1`. Le schéma d'une entrée ne change pas selon le timeframe : seul le contenu varie.

## Exemple JSON complet et valide

```json
{
  "snapshot_id": "forces-20260705-141500-001",
  "timestamp": "2026-07-05T14:15:00.000Z",
  "source": "MT4_SDI",
  "freshness": {
    "captured_at": "2026-07-05T14:15:00.120Z",
    "age_ms": 120,
    "stale": false,
    "stale_threshold_ms": 30000
  },
  "forces": [
    {
      "devise": "USD",
      "timeframe": "M5",
      "intensite": 62.4,
      "direction": "haussiere",
      "vitesse": 3.1,
      "croisement": { "detecte": true, "devise_partenaire": "EUR", "direction": "haussiere" },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "extension", "intensite": 41.0 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "USD",
      "timeframe": "H4",
      "intensite": 58.9,
      "direction": "haussiere",
      "vitesse": 0.6,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 8.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "EUR",
      "timeframe": "M5",
      "intensite": 55.2,
      "direction": "haussiere",
      "vitesse": 2.4,
      "croisement": { "detecte": true, "devise_partenaire": "USD", "direction": "haussiere" },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "extension", "intensite": 33.5 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "EUR",
      "timeframe": "H4",
      "intensite": 51.0,
      "direction": "neutre",
      "vitesse": 0.1,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": true, "contexte": "retour sous la ligne de force après croisement H4 invalidé" },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "compression", "intensite": 12.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "GBP",
      "timeframe": "M5",
      "intensite": 40.1,
      "direction": "baissiere",
      "vitesse": -1.8,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": true, "intensite": 22.3 },
      "compression_extension": { "etat": "neutre", "intensite": 5.0 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "GBP",
      "timeframe": "H4",
      "intensite": 44.0,
      "direction": "baissiere",
      "vitesse": -0.3,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "compression", "intensite": 15.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "JPY",
      "timeframe": "M5",
      "intensite": 35.7,
      "direction": "baissiere",
      "vitesse": -0.9,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 6.5 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "JPY",
      "timeframe": "H4",
      "intensite": 33.2,
      "direction": "baissiere",
      "vitesse": -0.2,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 7.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "CAD",
      "timeframe": "M5",
      "intensite": 48.6,
      "direction": "neutre",
      "vitesse": 0.2,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "compression", "intensite": 18.4 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "CAD",
      "timeframe": "H4",
      "intensite": 47.9,
      "direction": "neutre",
      "vitesse": 0.0,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "compression", "intensite": 20.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "CHF",
      "timeframe": "M5",
      "intensite": 52.3,
      "direction": "haussiere",
      "vitesse": 1.1,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 9.8 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "CHF",
      "timeframe": "H4",
      "intensite": 50.5,
      "direction": "neutre",
      "vitesse": 0.1,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 10.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "AUD",
      "timeframe": "M5",
      "intensite": 39.4,
      "direction": "baissiere",
      "vitesse": -2.0,
      "croisement": { "detecte": true, "devise_partenaire": "NZD", "direction": "baissiere" },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "extension", "intensite": 28.0 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "AUD",
      "timeframe": "H4",
      "intensite": 41.0,
      "direction": "baissiere",
      "vitesse": -0.4,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 11.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    },
    {
      "devise": "NZD",
      "timeframe": "M5",
      "intensite": 37.8,
      "direction": "baissiere",
      "vitesse": -2.3,
      "croisement": { "detecte": true, "devise_partenaire": "AUD", "direction": "baissiere" },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "extension", "intensite": 30.1 },
      "freshness": { "timestamp": "2026-07-05T14:15:00.000Z", "age_ms": 120, "stale": false, "stale_threshold_ms": 30000 }
    },
    {
      "devise": "NZD",
      "timeframe": "H4",
      "intensite": 39.6,
      "direction": "baissiere",
      "vitesse": -0.3,
      "croisement": { "detecte": false, "devise_partenaire": null, "direction": null },
      "recroisement": { "detecte": false, "contexte": null },
      "rejet_repulsion": { "detecte": false, "intensite": null },
      "compression_extension": { "etat": "neutre", "intensite": 9.0 },
      "freshness": { "timestamp": "2026-07-05T12:00:00.000Z", "age_ms": 8100120, "stale": false, "stale_threshold_ms": 900000 }
    }
  ],
  "m1": [
    { "devise": "USD", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.870Z", "intensite_instantanee": 63.1, "direction": "haussiere", "vitesse_tick": 0.42, "nb_ticks_fenetre": 34, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.870Z", "age_ms": 250, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "EUR", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.910Z", "intensite_instantanee": 56.0, "direction": "haussiere", "vitesse_tick": 0.31, "nb_ticks_fenetre": 29, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.910Z", "age_ms": 210, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "GBP", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.800Z", "intensite_instantanee": 39.5, "direction": "baissiere", "vitesse_tick": -0.20, "nb_ticks_fenetre": 22, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.800Z", "age_ms": 320, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "JPY", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.750Z", "intensite_instantanee": 35.9, "direction": "baissiere", "vitesse_tick": -0.05, "nb_ticks_fenetre": 18, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.750Z", "age_ms": 370, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "CAD", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.900Z", "intensite_instantanee": 48.4, "direction": "neutre", "vitesse_tick": 0.01, "nb_ticks_fenetre": 20, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.900Z", "age_ms": 220, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "CHF", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.860Z", "intensite_instantanee": 52.6, "direction": "haussiere", "vitesse_tick": 0.09, "nb_ticks_fenetre": 21, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.860Z", "age_ms": 260, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "AUD", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.700Z", "intensite_instantanee": 38.9, "direction": "baissiere", "vitesse_tick": -0.28, "nb_ticks_fenetre": 25, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.700Z", "age_ms": 420, "stale": false, "stale_threshold_ms": 5000 } },
    { "devise": "NZD", "mode": "tick_velocity", "dernier_tick_timestamp": "2026-07-05T14:14:59.680Z", "intensite_instantanee": 37.2, "direction": "baissiere", "vitesse_tick": -0.31, "nb_ticks_fenetre": 24, "fenetre_ms": 5000, "freshness": { "timestamp": "2026-07-05T14:14:59.680Z", "age_ms": 440, "stale": false, "stale_threshold_ms": 5000 } }
  ]
}
```

## Ce que ce format ne fait jamais

- Il ne qualifie aucune scène, aucun comportement, aucune fenêtre.
- Il ne produit aucun score d'exploitabilité.
- Il ne suppose aucune paire de trading, aucun sens d'ordre.
- Il ne masque jamais une donnée périmée : `stale = true` doit être visible et respecté par la couche Scènes.
