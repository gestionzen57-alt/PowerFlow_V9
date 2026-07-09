# V9 Zone Detector — zone_diagnostics

> Skill compact. Voir `powerflow-v9-zone-detector` pour l'intégral.

## Rôle

Alimente la table `zone_diagnostics` (30 colonnes) à chaque snapshot.
Débloque 7/9 principes `node_rule` ACTIVE.

## Architecture

```
regime_detector → zone_detector → principle_engine
```

## Machine à états (5 états)

| État | Condition |
|------|-----------|
| NEUTRAL | \|z\| < 1.0 |
| EARLY_EXTREME | \|z\| >= 1.0, pas d'extrême antérieur |
| ACCUMULATING | \|z\| >= 1.0, même direction que snapshot précédent |
| LEAKING | \|z\| >= 1.0, direction opposée |
| RUPTURE | \|z\| >= 2.0 |

## Seuils (provisoires)

| Seuil | Valeur |
|-------|--------|
| Z_SCORE_THRESHOLD_EXTREME | 1.0 |
| Z_SCORE_THRESHOLD_RUPTURE | 2.0 |
| TENSION_SCORE_MIN | 0.5 |
| PULLBACK_LOOKBACK | 5 |

## Pitfalls

- ❌ `PRAGMA table_info` utilise `d[1]` pour les noms de colonnes (pas `d[0]`)
- ❌ Ne pas confondre "zone_diagnostics populé" avec "grammaire complète"
- ❌ Les 2 principes restants (ANTAGONIST_NODE, COALITION_NODE) ont été débloqués par enrichissement du contexte, pas par zone_diagnostics
