# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-06 14h44 CEST — ANTAGONIST_NODE débloqué (347 tests, bug fallback cross-TF corrigé)

## Fix ANTAGONIST_NODE (2026-07-06) — bug propagation cross-TF

Commit [`7466f01`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/7466f0186e9bcd8a78a32ee8e18d3fbc52bc1da7) | **347 tests verts** (+4).

### Cause racine
Bug d'écrasement silencieux introduit dans commit `046b285` (extension des fallbacks pour
`test_context_propagation.py`). Le bloc fallbacks initialisait :
```
context["h1_dir"] = None
context["h1_state"] = None
context["m5_dir"] = None
context["m5_state"] = None
```
**après** `context.update(cross_tf_context)` — écrasant les valeurs correctement calculées.
Résultat : ANTAGONIST_NODE condition 1 (`h1_state not_in [NEUTRAL, None]`) échouait toujours.
Aucune exception — erreur silencieuse détectée uniquement par diagnostic.

### Fix
Retrait des 4 fallbacks redondants. Le bloc cross-TF gère déjà tous les cas
(force_self non-vide/vide, tf_row=None/forces vide). Commentaire dans le code
documente le bug et justifie l'absence de fallback.

### Vérification post-fix (216 scènes H1 GBPUSD 2026-07-06)
- 215 scènes : h1_state='HAUSSIERE' / h1_dir='HAUSSIERE' / m5_state='HAUSSIERE' (**correctement propagés**)
- 4 scènes : h1_state='NEUTRAL' (max_force 40-60, attendu)
- 0 opposition cross-TF observée (marché uniformement haussier ce jour)
- **ANTAGONIST_NODE reste à 0 déclenchement — mais désormais pour la bonne raison :**
  pas de signal cross-TF réel, pas de bug de propagation.
  Techniquement débloqué : déclenchera dès qu'une opposition H1 vs M5 apparaitra.

### Tests (+4 dans test_principle_engine.py)
- `test_antagonist_node_cross_tf_fields_propagated` — régression guard permanent
- `test_antagonist_node_triggers_on_cross_tf_opposition` — aurait détecté le bug dès la session précédente
- `test_antagonist_node_does_not_trigger_when_h1_m5_aligned`
- `test_antagonist_node_fallback_when_h1_state_neutral`

### Leçon retenue
L'extension de fallbacks pour satisfaire un test peut écraser des valeurs calculées
en aval — **l'ordre des `context.update()` vs initialisation des fallbacks est critique**.
Tout ajout de fallback dans `_load_shared_context` doit vérifier qu'il n'écrase pas
une valeur déjà populée par un bloc antérieur.

---

## Session Calibration Live + Tuning YAML (2026-07-06)

**343 tests verts** (339 baseline + 4 nouveaux test_context_propagation).
3 commits : `046b285` / `35939aa` / `ecc056b`.

### Calibration live
- 2245 snapshots / 1708 scènes / **0 signaux** (pipeline actif, principes trop sélectifs ou marché haussier uniforme)
- Comportements fréquents : rotation_leadership=831, annulation=264, bascule=185
- `config.py` inchangé — COALITION_THRESHOLD reporté à n>5000 scènes + WIN/LOSS

### Tuning YAML (8 fichiers)
4 NODE_RULE ACTIVE enrichis (COALITION_NODE, NODE_BIRTH_FAST, RAW_NODE_BIRTH, GRAVITY_RESPRING_NODE).
4 GRAMMAR enrichis (bounds informatifs + notes).
27/27 YAML valides. Aucun SHADOW promu.

### Doctrine ajoutée
`docs/DOCTRINE.md` 19 → 27 règles (calibration-first, CONTEXT_CONTRACT, sessions, YAML,
livraison, promotions, fallbacks). Commit [`2a970cf`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/2a970cf98551c62f2506e20e6699b53d27432763).

---

## Session Coalition Intelligence (2026-07-06)
**339 tests verts**. 13 champs ajoutés dans `_load_shared_context`.
CONTEXT_CONTRACT.md créé. Gardien `test_context_propagation.py`.
Commits : cd50cd7 / 4ebf86a / 24c0653 / 4d6cf53 / 44c8ae4 / 6648d27

---

## Correctif Phase 9.5 (2026-07-06) — observabilité DST US
Correctif `market_status_warning()`. `core/v9/*` inchangé. 269 tests verts.

## Statut Phase 9
PHASE 9 TERMINÉE (2026-07-05). Chaîne cognitive complète :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision.
27 principes YAML (10 ACTIVE / 17 SHADOW). Latence 189ms/snapshot.

## PHASES 1→8 TERMINÉES
Voir `docs/checkpoints/`.

## Décisions actées
- V9 from scratch. GitHub = source de vérité. V8 = migration curée.
- Squelette cognitif : Forces → Décision (9 couches).
- CONTEXT_CONTRACT.md + test_context_propagation.py = gardien de propagation (2026-07-06).
- DOCTRINE.md 27 règles (2026-07-06).
- COALITION_THRESHOLD : reporté à n>5000 scènes + WIN/LOSS (2026-07-06).
- **Nouvelle (2026-07-06)** : tout ajout de fallback dans `_load_shared_context` doit vérifier
  qu'il n'écrase pas une valeur populée par un `context.update()` antérieur.

## Objectif immédiat
**Observer les premiers déclenchements en live** — ANTAGONIST_NODE débloqué,
tuning YAML actif, pipeline sain. Laisser tourner jusqu'à l'apparition
d'une opposition H1/M5 ou d'un signal issu des principes NODE_RULE ACTIVE.
Relancer `v9_calibration.py --principes` à n>500 scènes post-tuning (dans ~2h).

## Chantiers en file
1. **Observer premiers signaux** — `v9_dashboard.py --watch decisions`
2. **Calibration --principes** — relancer à ~500 scènes post-tuning YAML
3. **COALITION_THRESHOLD** — réévaluer à n>5000 scènes + WIN/LOSS
4. **Métriques DORMANT P2** — contexte_temporel.fenetre + declencheur + variante
5. **Promotion SHADOW→ACTIVE** — décision sur base hit_rate live (règle 25)
6. AGENT.md racine V9
7. Inventaire de migration V8 → V9

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code / Hermes / MiniMax : implémentation selon périmètre assigné

## Règle d'or
Aucune implémentation structurante sans ancrage explicite dans la doctrine V9.
Toute nouvelle métrique tracée dans CONTEXT_CONTRACT.md avant ou à la livraison.
Tout fallback dans `_load_shared_context` vérifié qu'il n'écrase pas un `context.update()` antérieur.
