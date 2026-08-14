# BRIEF DE DÉLÉGATION HERMES — Session post-audit VSA

**Date** : 2026-08-14  
**Émetteur** : Perplexity (architecte externe)  
**Destinataire** : Hermes (agent exécutant)  
**Priorité** : P0 — bloquant pour promotion live  
**Branche de travail** : `feat/v9-foundation-clean`

---

## CONTEXTE CRITIQUE À LIRE EN PREMIER

Avant toute action de code, Hermes DOIT lire dans cet ordre :
1. `docs/HAWKEYE_VSA_DOCTRINE.md` — doctrine Hawkeye/Fatman officielle
2. `docs/V10/SON_INTERPRETATION.md` — interprétation propriétaire Søn (**NON Williams**)
3. `docs/V10/AUDIT_VSA_INTEGRATION_PLAN.md` — plan d'intégration sélectif
4. `docs/V10/AUDIT_VSA_RAPPORT_COMPLET_2026-08-14.md` (branche `feat/zcode-night`) — ton propre rapport

**Règle absolue** : Tu implémentes `SON_INTERPRETATION.md`, pas Tom Williams.  
Si tu doutes, tu demandes à Perplexity avant de coder.

---

## MISSION 1 — Cherry-pick patches universels (P1/P2/P3/P5/P15)

**Objectif** : Intégrer les corrections structurelles de `feat/zcode-night` vers `feat/v9-foundation-clean`

```bash
git checkout feat/v9-foundation-clean
git cherry-pick 5e78531  # P1 close_location + P5 end-of-bar
git cherry-pick 6269498  # P2 Fatman = filtre contexte
git cherry-pick c355f12  # P3 sigma-bands spread
git cherry-pick cb0a31e  # P15 gap detection
```

**Gate de validation** :
- `python -m pytest tests/test_v10_vsa.py -v` → 100% vert
- `python -m pytest tests/test_v10_filter_compositor.py -v` → 100% vert
- Total cumulé ≥ 1460 tests verts
- Commit message : `fix(v10): cherry-pick P1/P2/P3/P5/P15 depuis feat/zcode-night [audit VSA 14/08]`

---

## MISSION 2 — Corriger le routage runner OVERLAP (blocage P4/P6/P7/P10)

**Problème diagnostiqué** : Le runner edge OVERLAP ne passe PAS par `decide_entry()` dans `v10_decision_pipeline.py`.  
Conséquence : P4 (gate triple), P6 (Effort/Résultat), P7 (gate SGL), P10 (force_boost) sont du code mort.

**Objectif** : Identifier le runner OVERLAP, le tracer, et vérifier s'il contourne `decide_entry()`.

**Steps** :
1. Trouver le runner : `grep -r "OVERLAP" core/v10/ --include="*.py" -l`
2. Tracer le chemin : depuis la sélection de paire jusqu'au déclenchement d'ordre
3. Identifier le point où `decide_entry()` devrait être appelé mais ne l'est pas
4. Brancher proprement (additif pur, R2 — ne pas casser le chemin existant)
5. Tester avec replay 1 jour avant de pousser

**Commit message** : `fix(v10): brancher runner OVERLAP sur decide_entry() — débloquer P4/P6/P7/P10`

---

## MISSION 3 — Implémenter séquences comportementales Søn

**Fichier cible** : `core/v10/v10_vsa.py` — nouvelle fonction `detect_behavioral_sequence()`

**Séquences canoniques à implémenter** (depuis `docs/V10/SON_INTERPRETATION.md`) :

```python
def detect_behavioral_sequence(bars_history: list[dict]) -> dict:
    """
    Analyse la séquence comportementale des 5 dernières barres.
    Retourne le pattern détecté et son niveau de confiance.
    
    Patterns Søn :
    - ACCUMULATION x2 → MARKUP = entrée longue (confiance: HAUTE)
    - MARKUP x3+ → DISTRIBUTION = sortie/short setup (confiance: HAUTE)
    - NEUTRAL x3+ → MARKUP fort = breakout institutionnel (confiance: MOYENNE)
    - UPTHRUST → MARKDOWN = piège confirmé (confiance: HAUTE)
    """
    # NON CODÉ — à implémenter selon élicitation Søn
    pass
```

**Note** : Si les séquences exactes ne sont pas claires, ne PAS inventer. Créer la structure vide avec les tests unitaires correspondants, documenter les patterns attendus, et attendre validation Søn.

---

## MISSION 4 — Brancher v10_cinematics.py sur la gate d'entrée

**Problème** : `v10_cinematics.py` produit `exhaustion_flag` et `divergence_flag` mais ils ne sont pas branchés sur `decide_entry()`.

**Modification dans `v10_decision_pipeline.py`** :
```python
# À ajouter dans decide_entry() après gate triple P4
cinematic_state = cinematics.get_cinematic_state(bars_history)
if cinematic_state.get("exhaustion_flag"):
    dec.action = "WAIT"
    dec.audit["blocked_by"] = "cinematic_exhaustion"
    return dec
if cinematic_state.get("divergence_flag"):
    dec.action = "WAIT"
    dec.audit["blocked_by"] = "cinematic_divergence"
    return dec
```

**Gate** : test unitaire `test_exhaustion_blocks_entry` + `test_divergence_blocks_entry`

---

## MISSION 5 — Replay 20j post-corrections

Une fois Missions 1-4 complètes :

```bash
# Runner replay élargi
python scripts/v10_replay_engine.py \
  --window 20d \
  --pairs EURUSD,AUDUSD \
  --tf M15 \
  --overlap-start 12 --overlap-end 13 \
  --delta-min 25 --delta-max 40 \
  --report docs/V10/replay_20d_post_audit.json
```

**Gate de promotion** :
- WR ≥ 45% sur 20j
- PnL > 0
- DD max < 35 pips
- Sharpe ≥ 0.5

Si toutes les gates passent → ouvrir PR vers `feat/v9-foundation-clean` avec tag `[PROMO-READY]`.

---

## RÈGLES DE COMPORTEMENT HERMES POUR CETTE SESSION

1. **R1-AGIR** : Exécute. Ne demande pas de permission pour ce qui est dans ce brief.
2. **R2-ADDITIF** : Ne supprime aucune fonctionnalité existante.
3. **R6-FAIL-OPEN** : En cas de doute sur une gate VSA, laisser passer (fail-open) et logger.
4. **R9-HONNÊTE** : Rapport réel. WR réel. Pas de fabrication.
5. **R10-CAPITAL** : Aucun patch live sans validation replay. Jamais.
6. **DOCTRINE SØN** : Si Williams et Søn divergent, Søn gagne. Toujours.

---

## LIVRABLES ATTENDUS

| Livrable | Type | Branche |
|---|---|---|
| Cherry-pick P1/P2/P3/P5/P15 intégrés | Code + tests | `feat/v9-foundation-clean` |
| Runner OVERLAP branché sur `decide_entry()` | Code + tests | `feat/v9-foundation-clean` |
| `detect_behavioral_sequence()` structure vide + tests | Code | `feat/v9-foundation-clean` |
| `exhaustion_flag` / `divergence_flag` branchés | Code + tests | `feat/v9-foundation-clean` |
| Replay 20j → `replay_20d_post_audit.json` | Données | `feat/v9-foundation-clean` |
| PR `[PROMO-READY]` si gates passées | PR | → `feat/v9-foundation-clean` |

---

*Brief émis par Perplexity 2026-08-14. Hermes : lis `SON_INTERPRETATION.md` d'abord. Toujours.*
