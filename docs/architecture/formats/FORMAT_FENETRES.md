# FORMAT_FENETRES.md

## Rôle

Spécifie le format de sortie de la couche **Fenêtres** dans la chaîne
cognitive officielle de PowerFlow V9 :

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle
```

Une fenêtre qualifie le **moment** où une dynamique comportementale devient
surveillable, potentiellement exploitable, fragile ou invalide. Elle ne
qualifie jamais la scène ou la force directement : elle référence toujours un
**comportement** (couche amont immédiate).

## Position dans la chaîne cognitive

- **Couche amont** : Comportement (`behavior_source`)
- **Couche aval** : Exploitabilité (consomme `window_id` comme `window_source`)

## Principe directeur

Une fenêtre n'existe que si un comportement a été qualifié avec une confiance
suffisante. Elle ne peut jamais court-circuiter la couche Comportements
(Règle « Aucune couche aval ne doit polluer ou court-circuiter une couche
amont », charte cognitive V9).

## Structure JSON

```
window_id                      string   — identifiant unique de la fenêtre
schema_version                 string   — version du format (ex: "1.0")
timestamp                      string   — ISO 8601 UTC, instant d'évaluation

behavior_source                object   — référence à la couche amont (obligatoire)
  behavior_id                  string   — identifiant du comportement analysé
  qualification                string   — qualification du comportement au moment de l'évaluation
  confiance_qualification      integer  — confiance du comportement source (0-100), reprise pour traçabilité

statut                         enum     — voir "Enum statut" ci-dessous (obligatoire)
type_fenetre                   string|null — nature de la fenêtre si applicable (ex: "continuation",
                                              "retournement", "rupture_range", "rebond"), null si statut=absente
niveau_confiance                integer  — 0-100, confiance globale dans la qualification de fenêtre

duree_de_vie                   object   — obligatoire
  timestamp_ouverture           string|null  — ISO 8601 UTC, null si jamais ouverte
  timestamp_fermeture           string|null  — ISO 8601 UTC, null si toujours ouverte ou jamais ouverte
  fragilite                     object
    detectee                    boolean
    raison                      string|null  — raison de la fragilité si detectee=true

conditions_invalidation         array    — liste d'objets { condition, description }, peut être vide

meta                             object  — traçabilité (obligatoire)
  produit_par                   string   — module/agent émetteur
```

## Enum statut

| Code JSON         | Libellé natif V9        | Signification                                                        |
|--------------------|--------------------------|-----------------------------------------------------------------------|
| `absente`          | absente                  | aucune fenêtre détectée ; réponse valide et attendue par défaut       |
| `en_preparation`    | en préparation           | dynamique en formation, pas encore ouverte                            |
| `ouverte`           | ouverte                  | fenêtre active, surveillable                                          |
| `fragile`           | fragile                  | ouverte mais avec signaux de fragilité détectés                       |
| `invalidee`         | invalidée                | fenêtre ouverte puis annulée par une condition d'invalidation          |
| `ambigue`           | ambiguë                  | lecture insuffisante pour trancher entre ouverte/absente/invalidée     |

## Règles explicites

1. **« Pas de fenêtre » est une réponse valide.** `statut = "absente"` est un
   résultat de première classe, pas une erreur ni une omission. Il doit être
   émis explicitement au même titre que `ouverte`.
2. **Pas de fausse fenêtre sans comportement confirmé.** Un objet Fenêtre ne
   peut avoir `statut` différent de `absente` ou `ambigue` que si
   `behavior_source.confiance_qualification` dépasse le seuil défini par la
   couche Comportements. Si ce seuil n'est pas atteint, la couche Fenêtres
   doit émettre `absente` ou `ambigue`, jamais `ouverte`, `fragile` ou
   `en_preparation`.
3. **Une fenêtre référence toujours un comportement.**
   `behavior_source.behavior_id` ne peut jamais être vide, même quand
   `statut = "absente"` (la fenêtre absente est évaluée par rapport à un
   comportement donné, pas dans le vide).
4. **`type_fenetre` est null quand `statut = "absente"`.** Une fenêtre
   inexistante n'a pas de nature.

## Exemple JSON complet

```json
{
  "window_id": "win_20260705T143200Z_gbpusd_m5_0007",
  "schema_version": "1.0",
  "timestamp": "2026-07-05T14:32:00Z",
  "behavior_source": {
    "behavior_id": "beh_20260705T143200Z_gbpusd_m5_0007",
    "qualification": "bascule",
    "confiance_qualification": 74
  },
  "statut": "ouverte",
  "type_fenetre": "retournement",
  "niveau_confiance": 68,
  "duree_de_vie": {
    "timestamp_ouverture": "2026-07-05T14:32:00Z",
    "timestamp_fermeture": null,
    "fragilite": {
      "detectee": false,
      "raison": null
    }
  },
  "conditions_invalidation": [
    {
      "condition": "retour_zone_origine",
      "description": "prix referme sous la zone de bascule GBP dans les 3 bougies M5 suivantes"
    },
    {
      "condition": "rotation_leadership_inverse",
      "description": "un nouveau comportement rotation_leadership contredit le sens de la bascule avant confirmation"
    }
  ],
  "meta": {
    "produit_par": "window-gate"
  }
}
```

### Exemple — fenêtre absente (réponse valide)

```json
{
  "window_id": "win_20260705T143500Z_gbpusd_m5_0008",
  "schema_version": "1.0",
  "timestamp": "2026-07-05T14:35:00Z",
  "behavior_source": {
    "behavior_id": "beh_20260705T143500Z_gbpusd_m5_0008",
    "qualification": "maintien",
    "confiance_qualification": 31
  },
  "statut": "absente",
  "type_fenetre": null,
  "niveau_confiance": 12,
  "duree_de_vie": {
    "timestamp_ouverture": null,
    "timestamp_fermeture": null,
    "fragilite": {
      "detectee": false,
      "raison": null
    }
  },
  "conditions_invalidation": [],
  "meta": {
    "produit_par": "window-gate"
  }
}
```
