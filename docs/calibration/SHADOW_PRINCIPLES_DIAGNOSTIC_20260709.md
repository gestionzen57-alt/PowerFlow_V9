# Diagnostic SHADOW Principles — 0% Hit Rate

**Date** : 2026-07-09
**Source** : `data/v9_forces.db` + `core/v9/principle_engine.py` + YAML `core/v9/principles/`

---

## Résumé

| Principe | Évals | Triggers | Hit Rate | Cause Racine | Priorité |
|---|---|---|---|---|---|
| **ANTAGONIST_NODE** | 265 | 0 | **0.0%** | INERT — H1 et M5 corrélés sur la période | 🟡 Surveiller |
| **GRAMMAR_REGIME** | 66 706 | 0 | **0.0%** | BUG (historique) + INERT (actuel) | 🔴 Corriger |
| **ELASTIC_BREATH** | 65 791 | 8 | **0.01%** | INERT — conditions rares par conception | 🟢 OK |
| **COALITION_NODE** | 65 791 | 56 | **0.1%** | INERT — confluence rare de 5 conditions | 🟢 OK |

---

## 1. ANTAGONIST_NODE — INERT

### Conditions YAML (5 conditions)
```yaml
- field: h1_state       op: not_in  value: [NEUTRAL, null]
- field: m5_state       op: not_in  value: [NEUTRAL, null]
- field: h1_dir         op: !=      value: NONE
- field: m5_dir         op: !=      value: NONE
- field: h1_dir         op: !=      value_field: m5_dir   # ← divergence cross-TF
```

### Répartition des échecs (DB)
| Raison | Count | % |
|---|---|---|
| `condition_non_remplie:h1_state` | 204 | 77% |
| `condition_non_remplie:h1_dir` | 60 | 23% |
| `condition_non_remplie:m5_state` | 1 | <1% |

### Analyse

**Les champs sont correctement alimentés.** `_load_shared_context()` (lignes 350-431) charge les snapshots H1 et M5, dérive `h1_state`/`h1_dir`/`m5_state`/`m5_dir` depuis les forces. Le bug du commit 046b285 (fallback écrasant les valeurs cross-TF) est corrigé.

**Problème :** Sur la période évaluée (265 snapshots), H1 et M5 sont fortement corrélés :
- 77% du temps, H1 est en état NEUTRAL → `h1_state not_in [NEUTRAL, null]` échoue
- Quand H1 n'est pas NEUTRAL, `h1_dir` est souvent `NONE` (23%)
- La divergence `h1_dir != m5_dir` n'est **jamais** atteinte

**Diagnostic : INERT** — pas de bug, pas de champ manquant. Le principe exige une divergence H1≠M5 qui ne s'est pas produite sur la période d'échantillonnage. C'est attendu sur un marché calme/range.

### Recommandation
- 🟡 **Surveiller** sur une période plus longue (30+ jours) incluant des NEWS_SHOCK
- Ne pas modifier les conditions — elles sont correctes par conception
- Vérifier après un événement macro (NFP, FOMC, CPI) qui crée naturellement la divergence H1/M5

---

## 2. GRAMMAR_REGIME — BUG (historique) + INERT (actuel)

### Conditions YAML (4 conditions, ajoutées Phase 9.8 Phase B)
```yaml
- field: risk_sentiment           op: in     value: [RISK_ON, RISK_OFF, MIXTE]
- field: coalition_mtf_score      op: >=    value: 2
- field: persistance_confirmee     op: ==    value: true
- field: contexte_temporel_fenetre op: is_not_null
```

### Répartition des échecs (DB)
| Raison | Count | % |
|---|---|---|
| `entree_documentaire_non_emettrice` | 60 882 | **91.3%** |
| `condition_non_remplie:risk_sentiment` | 5 787 | 8.7% |
| `condition_non_remplie:persistance_confirmee` | 53 | 0.08% |

### Analyse — Deux régimes distincts

**Phase 1 — BUG (91.3% des évals) :** Avant le correctif Phase 9.8 Phase B (2026-07-08), `GRAMMAR_REGIME.yaml` avait `conditions: []`. `evaluate_principle()` retournait `entree_documentaire_non_emettrice` inconditionnellement. Le principe était classé ACTIVE dans `config.py` mais structurellement incapable d'émettre. C'est le **F1** documenté dans `AUDIT_DOCTRINE_REPORT.md`.

**Phase 2 — INERT (8.7% des évals, post-fix) :** Depuis le correctif, les conditions sont évaluées mais :
- `risk_sentiment` est presque toujours `"NEUTRE"` (valeur par défaut du fallback dans `_load_shared_context`, ligne 478). La condition `risk_sentiment IN [RISK_ON, RISK_OFF, MIXTE]` échoue donc massivement.
- Même quand `risk_sentiment` passe, `persistance_confirmee` est rarement `true` (seulement 53 échecs, mais c'est parce que très peu arrivent jusqu'à cette condition).

**Diagnostic : BUG (F1, résolu dans le YAML mais les données DB reflètent encore l'ancien état) + INERT (les conditions réelles sont trop restrictives pour le marché actuel).**

### Recommandation
- 🔴 **Rejouer le diagnostic** après un cycle complet de capture post-fix pour avoir des stats propres (le YAML a été corrigé le 2026-07-08, mais 91% des évals DB sont pré-fix)
- 🔴 **Vérifier le pipeline RiskMeter** : pourquoi `risk_sentiment` est toujours `NEUTRE` ? Soit le RiskMeter ne détecte jamais de sentiment clair, soit le fallback écrase la valeur réelle
- 🟡 **Assouplir** la condition `risk_sentiment` si le RiskMeter est trop conservateur (ex. accepter aussi `NEUTRE` avec `coalition_mtf_score >= 3` comme compensation)

---

## 3. ELASTIC_BREATH — INERT (OK)

### Conditions YAML (2 conditions)
```yaml
- field: state              op: ==    value: ACCUMULATING
- field: absorbed_pullbacks op: >=    value: 1
```

### Répartition des échecs (DB)
| Raison | Count | % |
|---|---|---|
| `condition_non_remplie:state` | 53 374 | 81% |
| `condition_non_remplie:absorbed_pullbacks` | 12 425 | 19% |
| `conditions_remplies` | 8 | 0.01% |

### Analyse
- 81% des snapshots n'ont pas `state == ACCUMULATING` → normal
- 19% ont le bon état mais pas assez de pullbacks absorbés → normal
- 8 déclenchements sur 65K → hit rate 0.01%, cohérent avec un pattern niche

**Diagnostic : INERT** — comportement correct. Les champs `state` et `absorbed_pullbacks` sont bien propagés depuis `zone_diagnostics` (lignes 838-847). Le principe capture un pattern rare par conception.

### Recommandation
- 🟢 **Aucune action** — hit rate attendu pour ce pattern

---

## 4. COALITION_NODE — INERT (OK)

### Conditions YAML (5 conditions)
```yaml
- field: state                op: in     value: [ACCUMULATING, LEAKING]
- field: coalition_strength   op: >=    value: 0.5
- field: coalition_mtf_score  op: >=    value: 3
- field: risk_sentiment       op: not_in value: [MIXTE]
- field: coalition_news_allow op: ==    value: true
```

### Répartition des échecs (DB)
| Raison | Count | % |
|---|---|---|
| `condition_non_remplie:state` | 53 341 | 81% |
| `condition_non_remplie:coalition_strength` | 12 399 | 19% |
| `conditions_remplies` | 56 | 0.1% |
| `condition_non_remplie:risk_sentiment` | 8 | <0.1% |
| `condition_non_remplie:coalition_mtf_score` | 3 | <0.1% |

### Analyse
- 81% échouent sur `state` (pas en ACCUMULATING/LEAKING) → normal
- 19% passent state mais échouent sur `coalition_strength >= 0.5` → la coalition est rarement assez forte
- 56 déclenchements sur 65K → hit rate 0.1%, cohérent
- Tous les champs sont correctement propagés : `state` depuis `zone_diagnostics`, `coalition_strength` depuis `coalitions_json` (ligne 540), `coalition_mtf_score` depuis `confluences_mtf_json` (ligne 599), `risk_sentiment` depuis `risk_assessment_json` (ligne 572), `coalition_news_allow` calculé ligne 775

**Diagnostic : INERT** — comportement correct. La confluence de 5 conditions est rare par conception.

### Recommandation
- 🟢 **Aucune action** — hit rate cohérent avec un principe multi-condition

---

## Synthèse des causes racines

| Cause | Définition | Principes concernés |
|---|---|---|
| **BOTTLE_NECK** | Champ manquant dans `_load_shared_context()` | Aucun (tous les champs sont propagés) |
| **INERT** | Conditions correctes mais rarement remplies par le marché | ANTAGONIST_NODE, GRAMMAR_REGIME (post-fix), ELASTIC_BREATH, COALITION_NODE |
| **BUG** | Try/except qui cache, fallback qui écrase, conditions vides | GRAMMAR_REGIME (F1 historique, résolu) |

## Vérification des champs référencés vs propagés

| Champ | Référencé par | Présent dans `_load_shared_context()` | Statut |
|---|---|---|---|
| `h1_state` | ANTAGONIST_NODE | ✅ Lignes 358-431 (cross-TF) | OK |
| `m5_state` | ANTAGONIST_NODE | ✅ Lignes 358-431 (cross-TF) | OK |
| `h1_dir` | ANTAGONIST_NODE | ✅ Lignes 358-431 (cross-TF) | OK |
| `m5_dir` | ANTAGONIST_NODE | ✅ Lignes 358-431 (cross-TF) | OK |
| `state` | ELASTIC_BREATH, COALITION_NODE | ✅ Lignes 822/840 (zone_diagnostics) | OK |
| `absorbed_pullbacks` | ELASTIC_BREATH | ✅ Ligne 829/847 (zone_diagnostics) | OK |
| `coalition_strength` | COALITION_NODE | ✅ Ligne 540 (coalitions_json) | OK |
| `coalition_mtf_score` | COALITION_NODE, GRAMMAR_REGIME | ✅ Ligne 599 (confluences_mtf_json) | OK |
| `risk_sentiment` | COALITION_NODE, GRAMMAR_REGIME | ✅ Ligne 572 (risk_assessment_json) | OK |
| `persistance_confirmee` | GRAMMAR_REGIME | ✅ Ligne 583 (risk_assessment_json) | OK |
| `contexte_temporel_fenetre` | GRAMMAR_REGIME | ✅ Ligne 667 (contexte_temporel_json) | OK |
| `coalition_news_allow` | COALITION_NODE | ✅ Ligne 775 (calculé) | OK |

**Aucun BOTTLE_NECK détecté.** Tous les champs référencés par les conditions YAML sont correctement propagés dans `_load_shared_context()`.

## Recommandations finales

1. **GRAMMAR_REGIME (🔴 Prioritaire)** : Rejouer le diagnostic après un cycle complet de capture post-fix. Vérifier pourquoi `risk_sentiment` est toujours `NEUTRE` — soit le RiskMeter est trop conservateur, soit le fallback écrase la valeur. Envisager d'assouplir la condition `risk_sentiment` si le détecteur de sentiment est calibré trop strict.

2. **ANTAGONIST_NODE (🟡 Surveiller)** : Ne rien modifier. Le principe est correct, les champs sont propagés. Attendre une période de marché avec divergence H1/M5 (NEWS_SHOCK) pour valider le déclenchement.

3. **ELASTIC_BREATH / COALITION_NODE (🟢 OK)** : Comportement nominal. Hit rate bas mais cohérent avec la rareté des patterns.
