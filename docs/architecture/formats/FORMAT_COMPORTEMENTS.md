# FORMAT_COMPORTEMENTS.md

## Rôle

Spécifie le format de sortie de la couche **Comportements** dans la chaîne
cognitive officielle de PowerFlow V9 :

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle
```

La couche Comportements ne lit jamais les forces directement. Elle lit une
**scène** (couche amont immédiate) et qualifie sa dynamique dans le temps.
Un objet Comportement référence donc toujours une scène source — jamais un
signal, jamais une intention de trade (Règle 2 de la charte : séparation
perception / exploitabilité).

## Position dans la chaîne cognitive

- **Couche amont** : Scène (`scene_source`)
- **Couche aval** : Fenêtre (consomme `behavior_id` comme `behavior_source`)

## Principe directeur

Un comportement décrit une **dynamique observée**, pas une prédiction. Il doit
pouvoir être émis même s'il ne débouche sur aucune fenêtre. L'absence de
qualification franche est modélisée par `comportement.confiance_qualification`
bas plutôt que par l'omission du champ.

## Structure JSON

```
behavior_id                    string   — identifiant unique du comportement
schema_version                 string   — version du format (ex: "1.0")
timestamp                      string   — ISO 8601 UTC, instant d'émission

scene_source                   object   — référence à la couche amont (obligatoire)
  scene_id                     string   — identifiant de la scène analysée
  symbol                       string   — paire / instrument
  timeframe                    string   — timeframe de la scène (ex: "M5", "H1")
  window_start                 string   — ISO 8601 UTC, début de la scène
  window_end                   string   — ISO 8601 UTC, fin de la scène

comportement                   object   — qualification du comportement (obligatoire)
  qualification                enum     — voir "Enum comportement" ci-dessous
  intensite                    enum     — faible | moderee | forte | extreme
  phase                        enum     — initiation | developpement | culmination | resolution
  confiance_qualification      integer  — 0-100, confiance de la couche dans sa propre lecture
  description_courte           string   — résumé narratif court, langage natif V9

transitions                    object   — détection de changement de dynamique (obligatoire, peut être vide/nulle)
  comportement_precedent       string|null  — qualification du comportement précédent sur la même scène-mère
  point_de_rupture             object|null
    detecte                    boolean
    timestamp                  string|null  — ISO 8601 UTC
    declencheur                string|null  — description du déclencheur observé
  sens_transition               enum|null   — escalade | desescalade | inversion | neutre

comparaison_cas_connus         object   — confrontation replay (obligatoire, peut être vide)
  similarite_score              number|null  — 0.0-1.0, similarité au(x) cas le(s) plus proche(s)
  cas_references                 array   — liste d'objets { case_id, similarite }
  singularites_locales           array   — liste de chaînes décrivant des écarts locaux non catalogués
  variante_de_comportement_connu object
    est_variante                boolean
    comportement_reference       string|null  — comportement connu dont celui-ci serait une variante
    ecarts                       array        — liste de chaînes décrivant les écarts

meta                            object   — traçabilité (obligatoire)
  produit_par                   string   — module/agent émetteur
  version_lexique                string   — version du LEXICON_V9.md utilisée
```

## Enum comportement (`comportement.qualification`)

| Code JSON                          | Libellé natif V9                        |
|-------------------------------------|------------------------------------------|
| `maintien`                          | maintien                                  |
| `bascule`                            | bascule                                   |
| `lutte_forces`                       | lutte / combat de forces                  |
| `contraction`                        | contraction                               |
| `extension`                          | extension                                 |
| `tension`                            | tension                                   |
| `rupture`                            | rupture                                   |
| `reequilibrage`                      | rééquilibrage                             |
| `annulation`                         | annulation (recroisement)                 |
| `preparation_ouverture_fenetre`      | préparation d'ouverture de fenêtre        |
| `seconde_bosse`                      | seconde bosse                             |
| `rotation_leadership`                | rotation de leadership                    |

Aucune autre valeur n'est acceptée sans révision du lexique (`LEXICON_V9.md`).

## Règles explicites

1. **Un comportement référence toujours une scène.** `scene_source.scene_id`
   ne peut jamais être vide.
2. **Un comportement n'est pas un signal.** Ce format ne contient aucun champ
   de direction de trade, de taille de position ou d'exécution.
3. **La confiance basse est une réponse valide.** Un `confiance_qualification`
   faible n'empêche pas l'émission de l'objet ; il informe simplement la
   couche Fenêtres qu'aucune fenêtre ne doit s'ouvrir sur cette base
   (Règle 1 de la charte : primauté de la lecture).

## Exemple JSON complet

```json
{
  "behavior_id": "beh_20260705T143200Z_gbpusd_m5_0007",
  "schema_version": "1.0",
  "timestamp": "2026-07-05T14:32:00Z",
  "scene_source": {
    "scene_id": "scn_20260705T143000Z_gbpusd_m5_0042",
    "symbol": "GBPUSD",
    "timeframe": "M5",
    "window_start": "2026-07-05T14:30:00Z",
    "window_end": "2026-07-05T14:32:00Z"
  },
  "comportement": {
    "qualification": "bascule",
    "intensite": "forte",
    "phase": "developpement",
    "confiance_qualification": 74,
    "description_courte": "Bascule de leadership USD vers GBP après contraction de deux cycles M5, rupture de l'équilibre observée en clôture de scène."
  },
  "transitions": {
    "comportement_precedent": "contraction",
    "point_de_rupture": {
      "detecte": true,
      "timestamp": "2026-07-05T14:31:15Z",
      "declencheur": "franchissement de zone avec accélération de cinématique GBP"
    },
    "sens_transition": "inversion"
  },
  "comparaison_cas_connus": {
    "similarite_score": 0.82,
    "cas_references": [
      { "case_id": "beh_20260622T091500Z_gbpusd_m5_0011", "similarite": 0.82 },
      { "case_id": "beh_20260530T160000Z_gbpusd_m5_0033", "similarite": 0.77 }
    ],
    "singularites_locales": [
      "vitesse de bascule supérieure de 30% à la médiane des cas comparés"
    ],
    "variante_de_comportement_connu": {
      "est_variante": true,
      "comportement_reference": "bascule",
      "ecarts": [
        "absence de rééquilibrage intermédiaire avant la bascule finale"
      ]
    }
  },
  "meta": {
    "produit_par": "behavior-analyst",
    "version_lexique": "1.0"
  }
}
```
