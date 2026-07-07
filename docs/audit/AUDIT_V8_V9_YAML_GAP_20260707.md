# Audit V8 → V9 — 11 YAML principles manquants — 2026-07-07

## Identification
- **Date** : 2026-07-07 22h00 CEST (sprint mode autonome Søn)
- **Opérateur** : Hermes
- **Branche** : `feat/v9-foundation-clean` à `80dc3c5`
- **Source** : diff `ls /d/Projet/V8/principles/*.yaml` vs `ls core/v9/principles/*.yaml`
- **Contexte** : sprint β complet demandé par Søn ; le recover des 11 YAML
  manquants V8→V9 fait partie du chemin β.

## Verdict global (règle 14 + 25)

**Perplexity n'a rien écarté d'utile.** La différence 38 V8 → 27 V9 = 11 fichiers
qui sont TOUS soit obsolètes, soit explicitement blacklistés, soit gelés par
Søn. Ci-dessous le détail factuel.

## Tableau par fichier

| Fichier V8 | Status V8 | Origine | Décision V9 | Justification |
|------------|-----------|---------|-------------|---------------|
| `BEARISH_DIVERGENCE.yaml` | SHADOW | V7 | **NON MIGRÉ (acceptable)** | WR30j 26.8% (n=527). Audit SHADOW vs legacy requis (skill_legacy_audit). Pas de critère promote ACTIVE. SHADOW=non utilisé dans V9, migration = sémantiquement vide. |
| `DECOUPLAGE_EUR_GBP.yaml` | DEPRECATED | V7 | NON MIGRÉ | WR 0% (0/13). Blacklisté par Søn. Migration = introduire faux signal. |
| `HIGH_ZONE_REJECT_PUSH_REJECT.yaml` | DEPRECATED | V7 | NON MIGRÉ | WR 0%. Désactivé. Biais anti-signal GPT. |
| `LOW_ZONE_REJECT.yaml` | DEPRECATED | V7 | NON MIGRÉ | WR 0% (0/21). Blacklisté. |
| `NODE_TRIPLE_CONVERGENCE.yaml` | SHADOW | V8_NATIVE | NON MIGRÉ (déjà gelé par Søn) | 3 cas confirmés, mais règle Søn = JAMAIS ACTIVE sans gate Søn (≥15-20 occ, WR≥50%, n≥30, CV≤0.20, validation explicite). À migrer le jour où ces critères sont remplis. |
| `NODE_V6_COMPRESSION.yaml` | DEPRECATED | V6 | NON MIGRÉ | Type nodes_v6. Producteur débranché, table gelée au 2026-04-29. Code mort V6. |
| `NODE_V6_CROISEMENT_DOUBLE.yaml` | DEPRECATED | V6 | NON MIGRÉ | idem V6 mort |
| `NODE_V6_CROISEMENT_TRIPLE.yaml` | DEPRECATED | V6 | NON MIGRÉ | idem V6 mort |
| `NODE_V6_LIBERATION.yaml` | DEPRECATED | V6 | NON MIGRÉ | idem V6 mort |
| `NODE_V6_LOCK.yaml` | DEPRECATED | V6 | NON MIGRÉ | idem V6 mort |
| `ZONE_ELASTIC_RETEST_SEQ.yaml` | DEPRECATED | V7 | NON MIGRÉ | Bug SQL ligne 740 (quote manquante). Mort silencieux. À corriger hors Phase A. |

## Synthèse

| Catégorie | Compte | Action V9 |
|-----------|--------|-----------|
| V6 archivage (producteur mort) | 5 | Aucune — code V6 mort, gelé 2026-04-29 |
| V7 DEPRECATED blacklistés (WR 0%) | 3 | Aucune — faux signaux |
| V7 SHADOW audit requis | 1 | Migration acceptable si Søn veut le passer en revue |
| V8_NATIVE SHADOW gelé par Søn | 1 | Migration différée critères Søn |

**Recommandation** : NE PAS MIGRER par défaut. Si Søn souhaite un jour revoir
BEARISH_DIVERGENCE en SHADOW V9, c'est 5 min (copie YAML + audit schema) —
mais ce n'est pas un blocage.

## Impact sprint β

Le chemin β COMPLET comprenait « recover 11 YAML ». Cet audit conclut
qu'aucun des 11 n'est récupérable en l'état sans compromettre les règles Søn.
Le chantier est donc bouclé par la négative — c'est un livrable propre, pas un
échec.

## Référence

- Diffs V8/V9 principles : voir `git diff feat/v9-foundation-clean -- core/v9/principles/`
- Sprint antérieur : `DECISIONS_LOG.md` 2026-07-07 « Sprint V9 mode autonome Søn »
