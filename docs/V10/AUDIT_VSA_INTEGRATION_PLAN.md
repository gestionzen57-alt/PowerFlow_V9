# PLAN D'INTÉGRATION AUDIT VSA — Hermes 2026-08-14

**Statut** : Plan actif — à exécuter par ZCode/Claude Code  
**Source** : `docs/V10/AUDIT_VSA_RAPPORT_COMPLET_2026-08-14.md` (branche `feat/zcode-night`)  
**Auteur plan** : Perplexity CEO 2026-08-14 17:43 CEST  
**Branche cible** : `feat/v9-foundation-clean`

---

## CONTEXTE

Hermes a livré 11 patches atomiques (P1-P15) sur `feat/zcode-night` le 2026-08-14.  
Analyse senior Perplexity : **les patches sont techniquement corrects mais partiellement biaisés** — Hermes a appliqué la doctrine Williams/AnnieMQ pure, pas l'interprétation propriétaire Søn.  

**Décision CEO** : Cherry-pick sélectif. Pas de merge brut de `feat/zcode-night`.

---

## PATCHES À INTÉGRER IMMÉDIATEMENT (universels, non-doctrinaux)

Ces patches corrigent des bugs structurels indépendants de toute doctrine.

| Patch | Commit | Fichier | Correction | Risque |
|---|---|---|---|---|
| **P1** | `5e78531` | `v10_vsa.py` | `close_location` gate MARKUP/MARKDOWN + UPTHRUST detection | 🟢 Zéro |
| **P2** | `6269498` | `v10_filter_compositor.py` | Fatman = filtre contexte, jamais trigger | 🟢 Zéro |
| **P3** | `c355f12` | `v10_vsa.py` | σ-bands spread (ATR/20) au lieu de ratio SMA brut | 🟢 Faible |
| **P5** | `5e78531` | `v10_vsa.py` | End-of-bar enforcement (`is_closed_bar` gate) | 🟢 Zéro |
| **P15** | `cb0a31e` | `v10_vsa.py` | Gap detection open vs close précédent (session asiatique) | 🟢 Faible |

**Action ZCode** :
```bash
git checkout feat/v9-foundation-clean
git cherry-pick 5e78531  # P1 + P5
git cherry-pick 6269498  # P2
git cherry-pick c355f12  # P3
git cherry-pick cb0a31e  # P15
# Vérifier : python -m pytest tests/test_v10_vsa.py tests/test_v10_filter_compositor.py -v
```

---

## PATCHES EN ATTENTE — NON EXERCÉS EN REPLAY (code mort)

Ces patches sont logiquement corrects mais le chemin live ne les atteint pas.  
**Problème** : le runner edge OVERLAP ne passe pas par `decide_entry()` ni `decide_signal_level()`.  
**Action requise** : corriger le routage d'abord, puis valider les patches en replay.

| Patch | Commit | Fichier | Problème | Action requise |
|---|---|---|---|---|
| **P4** | `66771d1` | `v10_decision_pipeline.py` | Gate triple non exercée — runner OVERLAP contourne `decide_entry()` | Brancher runner sur `decide_entry()` |
| **P6** | `96df28f` | `v10_replay_engine.py` | `replay_engine` non appelé par chemin edge | Vérifier routage replay |
| **P7** | `96df28f` | `v10_signal_generator_live.py` | `decide_signal_level` non appelé | Vérifier routage live |
| **P10** | `99c38cc` | `v10_force_native.py` | `force_native` non appelé par chemin edge | Vérifier routage force |

**Brief Hermes pour cette correction** : voir `docs/V10/HERMES_DELEGATION_BRIEF.md`

---

## CALIBRATION OVERLAP (action code + config)

Basée sur replay empirique 2026-08-14 (55 trades, 5 jours) :

```python
# CONFIG ACTUELLE (à modifier)
OVERLAP_START_UTC = 12  # inchangé
OVERLAP_END_UTC   = 16  # RESTREINDRE à 13 (12h UTC = WR 93%, 13-15h = 22-40%)
DELTA_FORCE_MIN   = 25  # inchangé
DELTA_FORCE_MAX   = 40  # AJOUTER — delta > 40 = méfiance (WR 29% sur delta 50+)
PAIRES_ACTIVES    = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"]
PAIRES_SUSPENDUES = ["USDCHF"]  # AJOUTER — Sharpe -1.92 sur 5j
```

**Note** : Ces calibrations sont basées sur 5 jours (55 trades). Valider sur 20j minimum avant de rendre permanentes.

---

## TESTS À RÉCUPÉRER DE feat/zcode-night

Indépendamment des patches, les tests Hermes sont valides et enrichissent la couverture.

```bash
# Récupérer uniquement les fichiers de tests
git checkout feat/zcode-night -- tests/test_v10_vsa.py
git checkout feat/zcode-night -- tests/test_v10_audit_p6_p10.py
git checkout feat/zcode-night -- tests/test_v10_filter_compositor.py
git checkout feat/zcode-night -- tests/test_v10_decision_pipeline.py
# Merger manuellement si conflit avec tests existants
```

---

## ORDRE D'EXÉCUTION RECOMMANDÉ

```
1. Cherry-pick P1/P2/P3/P5/P15 → tests verts → commit
2. Récupérer nouveaux tests → vérifier ≥1460 verts → commit
3. Corriger routage runner OVERLAP → commit
4. Cherry-pick P4/P6/P7/P10 → re-replay 5j → valider WR > 45%
5. Replay 20j → décision promotion
```

---

*Plan créé par Perplexity 2026-08-14. Exécution déléguée à ZCode/Hermes.*
