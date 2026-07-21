# PROMPT OPUS — Vrai chantier Phase E (V2 — post NO-GO 2026-07-21)

**Verdict NO-GO V1** : le brief `PROMPT_OPUS_PRINCIPLE_SCORES_STRATEGY_MIGRATION.md` est fondé sur une fausse prémisse (le meta optimizer ne query pas de colonne `strategy`). NE PAS utiliser V1.

**V2 mission** : faire en sorte que `v9_meta_strategy_optimizer.select_strategy()` puisse vraiment diverger du legacy. Trois chemins possibles, par ordre d'effort :

---

## Chemin A — Réécrire la simulation pour mesurer honnêtement (1h)

**Problème identifié Opus** : `v9_meta_strategy_simulation.py L250-252` calcule `legacy_results` et `meta_results` avec **les mêmes pips historiques** (outcome figé). ΔWR ≡ 0 par construction.

**Correctif** : changer le modèle pour que **meta_strategy ait son propre outcome simulé**.

### Logique correcte (honnête)
Pour chaque décision historique, on sait :
- `meta_strategy` = ce que le meta optimizer aurait recommandé pour ce contexte
- `pips` legacy = outcome historique (résolu par une stratégie effective)
- `pips` meta = ??? (on ne sait pas, il n'a pas vraiment été exécuté)

**Approche 1 — attribution par décision.resolution_strategy** :
- `pips_meta = decision.resolution_pips SI decision.resolution_strategy == meta_strategy, sinon 0`
- Logique : si la strat effectivement utilisée = meta, alors meta l'aurait fait ; sinon meta n'aurait pas fait ce trade (skip)

**Approche 2 — simulation contrefactuelle via principle_scores** :
- Pour chaque trade historique, identifier dans `principle_scores` la ligne (principle, combination) matchant
- Récupérer `avg_pips` pour la stratégie considérée
- Approximation grossière mais mesurable

**Approche 3 — abandon de la simulation, faire confiance au shadow live** :
- Activer `V9_META_STRATEGY_SHADOW_ENABLED=1` 48h, puis `v9_meta_strategy_report.py`
- Comparer sur données live, pas simulation
- Plus long mais plus honnête

### Périmètre chemin A
1. Modifier `_wr_pf()` ou le calcul de `meta_results` pour utiliser une des 3 approches
2. Tests : verdict factuel change après modification
3. Validation live : WR/PF différents entre legacy et meta (sinon le fix n'a rien fait)

### Garde-fous chemin A
- R2 additif, R6 défensif, R18 code pur
- Lecture seule DB
- Pas de push sans motion CEO « go r28 »

---

## Chemin B — Brancher meta_optimizer sur decisions.resolution_strategy (2-3h)

**Constat Opus** : `decisions.resolution_strategy` (8690 DYNAMIC + 330 SKIPPED) est la donnée source des stratégies effectives, mais le meta optimizer ne la lit pas.

**Modification ciblée** :
1. Ajouter lecture de `decisions.resolution_strategy` + `signals.exit_strategy_recommended` dans `_score_candidate_strategies()`
2. Pour chaque décision historique du même (symbol, timeframe, regime, phase), calculer WR/PF/n par `resolution_strategy`
3. Réutiliser ces stats comme input du scoring composite

### Périmètre chemin B
1. Modifier `core/v9/v9_meta_strategy_optimizer.py` L246-251 pour intégrer `resolution_strategy` (lecture, pas écriture)
2. Nouvelle requête SQL : 
   ```sql
   SELECT resolution_strategy, COUNT(*) AS n,
          AVG(CASE WHEN is_win=1 THEN 1.0 ELSE 0.0 END) AS wr,
          SUM(resolution_pips) / MAX(1, SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END)) AS pf
   FROM decisions
   WHERE symbol=? AND timeframe=? AND regime_type=?
     AND resolution_strategy IS NOT NULL AND is_win IS NOT NULL
   GROUP BY resolution_strategy
   ```
3. Tests : `test_v9_meta_strategy_optimizer.py` étendu pour vérifier la nouvelle source de scoring

### Garde-fous chemin B
- **R25' strict** : modifier le optimizer = changer ce qui sera exécuté. C'est un changement runtime = motion CEO distincte requise
- Backup R8 obligatoire avant modif
- Tests verts obligatoires
- Pas d'auto-promotion runtime

---

## Chemin C — Activer le shadow live 48h (5 min de code, 48h d'attente)

**Action** : 
1. `V9_META_STRATEGY_SHADOW_ENABLED=1` dans `config/v9_kill_switches.env`
2. Le pipeline live enregistre les comparaisons legacy vs meta en continu
3. Après 48h : `python scripts/v9_meta_strategy_report.py --since 48h`
4. Verdict réel, pas simulation

### Garde-fous chemin C
- Kill switch ON = log live, pas d'impact runtime (R25' strict)
- Aucun risque de régression
- Le plus factuel des 3 chemins

---

## Recommandation

**Court terme (aujourd'hui)** : Chemin C (5 min, 0 risque, données réelles).
**Moyen terme (semaine prochaine)** : Chemin A (1h, simulation honnête, re-validable).
**Long terme (si shadow live confirme uplift)** : Chemin B (motion CEO distincte requise).

---

## Référence

- Verdict NO-GO V1 : `PROMPT_OPUS_PRINCIPLE_SCORES_STRATEGY_MIGRATION.md` (bandeau NO-GO)
- DECISIONS_LOG §2026-07-21 04h57 UTC
- Code source à modifier : `core/v9/v9_meta_strategy_optimizer.py` L246-251
- Code source à corriger : `scripts/v9_meta_strategy_simulation.py` L250-252
- Kill switch : `V9_META_STRATEGY_SHADOW_ENABLED` dans `config/v9_kill_switches.env`
- Tables DB : `decisions.resolution_strategy` (8690 lignes), `signals.exit_strategy_recommended`

---

**Pas d'arrêt. AUTO-PILOTE Phase E vrai chantier.**

— Søn CEO, post NO-GO V1, 2026-07-21 04h57 UTC