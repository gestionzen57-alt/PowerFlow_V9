# DOCTRINE — PowerFlow V9

> **Principe directeur CEO (2026-07-20)** : le système doit être autonome
> et évoluer sans règle bloquante. Toute règle gelant l'adaptation
> automatique doit être révisée ou supprimée. Objectif : zéro friction
> doctrinal.

## Statut
Document pivot de navigation. Ce fichier ne contient pas le détail des règles :
il les résume en une ligne et renvoie vers le document source qui fait foi.
**En cas de divergence, le document source (colonne « Détail ») l'emporte sur ce résumé.**

## Sources de la doctrine

| Document source | Contenu détaillé |
|---|---|
| [docs/doctrine/CHARTE_COGNITIVE_V9.md](doctrine/CHARTE_COGNITIVE_V9.md) | Mission, chaîne cognitive officielle, définitions natives, règles de gouvernance 1-5 |
| [docs/doctrine/MEMORY_POLICY_V9.md](doctrine/MEMORY_POLICY_V9.md) | Types de mémoire, cycle de vie, politique de reprise de session |
| [docs/doctrine/ORCHESTRATION_POLICY_V9.md](doctrine/ORCHESTRATION_POLICY_V9.md) | Rôles d'agents, règles d'appel, conditions HITL |
| [docs/doctrine/MIGRATION_POLICY_V9.md](doctrine/MIGRATION_POLICY_V9.md) | Classification A/B/C/D de tout élément candidat à la migration V8→V9 |
| [docs/architecture/audit_v8_v9_migration.md](architecture/audit_v8_v9_migration.md) | Application de la politique de migration à l'inventaire réel de V8 |
| [docs/architecture/CONTEXT_CONTRACT.md](architecture/CONTEXT_CONTRACT.md) | Contrat vivant de propagation des métriques entre couches (PROPAGÉ / DORMANT) |

## Les 30 règles immuables

Ces règles sont une synthèse opérationnelle des documents ci-dessus, plus des règles
d'ingénierie (tests, documentation, calibration, process de session) issues des retours live.

| # | Règle | Détail / preuve |
|---|---|---|
| 1 | Le code est la source de vérité, pas la doc | Règle de gouvernance (voir [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md)) |
| 2 | Chaque couche est additive et filtrante | [CHAINE_COGNITIVE.md](architecture/CHAINE_COGNITIVE.md) |
| 3 | Pas de signal si exploitabilité != exploitable | `core/v9/exploitability_evaluator.py` |
| 4 | Les données stale (seuils par TF, voir `config.py`) sont rejetées | `core/v9/stale_gate.py` |
| 5 | Anti-replay : une bougie fermée = un seul snapshot | `core/v9/db_schema.py` — UNIQUE INDEX `bar_time` |
| 6 | L'orchestrateur ne crash jamais (try/except par couche) | `core/v9/orchestrator.py` |
| 7 | Tests obligatoires avant commit — zéro régression **non justifiée** tolérée. Toute régression doit être accompagnée d'une entrée DECISIONS_LOG expliquant pourquoi le changement de comportement est un progrès (pas une régression silencieuse). | Convention depuis Phase 1 ; **663 verts / 3 xfailed / 1 xpassed au 2026-07-07 fin sprint Søn** ; assoupli 2026-07-14 (motion CEO Søn, DECISIONS_LOG §2026-07-14 — voir Reformulation R7 ci-dessous) |
| 8 | Documentation mise à jour à chaque livraison | [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) |
| 9 | Pas de dette technique héritée (V6/V7/V8 = legacy) | [MIGRATION_POLICY_V9.md](doctrine/MIGRATION_POLICY_V9.md) |
| 10 | MT4 (forces) dicte, MT4 (ticks) confirme | Phase 11 future — pas encore implémenté |
| 11 | Architecture 9+1 : 9 principes `kind: node_rule` (détecteurs de zone, données `zone_diagnostics`) + 1 principe `kind: grammar` (GRAMMAR_REGIME, classificateur de régime contextuel) sont ACTIVE — les deux `kind` restent des DÉTECTEURS, jamais des signaux de trading directs | `core/v9/principle_engine.py` (9 node_rule ACTIVE + 1 grammar ACTIVE / 15 grammar SHADOW ; 2 grammar archivés — `core/v9/principles/_archive/ARCHIVE_MANIFEST.md`) — reformulée 2026-07-08, Phase 9.8 Phase B (F1/F2, `docs/audit/AUDIT_DOCTRINE_REPORT.md`) |
| 12 | Replay et live sont marqués distinctement dans les décisions | Colonne `source_type` sur les 8 tables dérivées ; voir `CHECKPOINT_20260706_V9_SOURCE_TYPE.md` |
| 13 | Le système observe d'abord, agit ensuite (paper → réel) | [CHARTE_COGNITIVE_V9.md](doctrine/CHARTE_COGNITIVE_V9.md) |
| 14 | Le Git courant est la source de vérité, jamais une mémoire de conversation | [README.md](../README.md) « Rituel de lecture » |
| 15 | Une seule source de vérité par sujet — jamais duplication | [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) règle 8 |
| 16 | La migration métier précède toute agentification généralisée | [ROADMAP.md](ROADMAP.md) |
| 17 | L'autonomie ne progresse qu'après stabilité démontrée en live | [ROADMAP.md](ROADMAP.md) |
| 18 | Aucune dépendance bloquante à un provider LLM pour le cœur cognitif | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 19 | Les chantiers agents/routing/skills auto-générés ne démarrent pas avant canonisation live | [ROADMAP.md](ROADMAP.md) |
| **20'** | **Lecture-first : avant tout chantier de code sur marché ouvert, l'opérateur LIT d'abord l'état courant (`v9_calibration.py --analyze`, `v9_dashboard.py --once`) — pas comme un outillage de scoring qui déforme la perception, mais parce que la primauté de la lecture (CHARTE Règle 1) s'applique aussi au process d'ingénierie** | **Remplace R20 "Calibration-first"**, supprimée pour contradiction 🔴 avec CHARTE Interdit #4 (« introduire un outillage […] avant d'avoir localisé sa place dans la chaîne cognitive » — `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.1/§3.2). Décision actée `workspace/perplexity/memory/DECISIONS_LOG.md` 2026-07-08. Règle applicable dès que nb_snapshots >= 20. |
| **21** | **Toute métrique ajoutée dans une couche doit être tracée dans `CONTEXT_CONTRACT.md` (PROPAGÉ ou DORMANT justifié) avant ou au moment du commit** | [docs/architecture/CONTEXT_CONTRACT.md](architecture/CONTEXT_CONTRACT.md) ; `tests/test_context_propagation.py` est le gardien automatique |
| **22** | **Une session = un périmètre = une livraison complète, sauf pour les chantiers complexes explicitement découpés en sous-unités livrables autonomes. Jamais de chantier ouvert non livré en fin de session** | Retour session 2026-07-06 : tuning YAML reporté d'une session, laissant le contexte enrichi cognitivement muet. Un chantier commencé = terminé dans la même session ou explicitement découpé en unité livrable autonome. Exception : chantier complexe (e.g. P3-CONSUME 6-10h) peut être découpé en sous-unités (consommation YAML, puis consommation evaluate_condition) si chaque sous-unité est livrée + testée + commitée atomiquement. Assoupli 2026-07-14 (motion CEO Søn, DECISIONS_LOG §2026-07-14). |
| **23** | **Les principes YAML consommateurs d'un champ contexte doivent être mis à jour dans la même session que le champ** | Corollaire de la règle 22. Exception acceptée : champ DORMANT (P3) — il doit alors être explicitement marqué DORMANT dans CONTEXT_CONTRACT.md avec raison. |
| **24** | **CONTEXT_CONTRACT.md est mis à jour à la clôture de chaque phase, pas en rattrapage** | Retour Phase 9 : anomalies #3/#4 non détectées pendant 24h. Le CONTEXT_CONTRACT.md créé en fin de Phase 10 fait partie du livrable de la phase, au même titre que les tests. |
| **25''** | **Promotion SHADOW→ACTIVE automatique par l'auto-calibrateur : tout principe SHADOW avec n_triggered ≥ 20 et confiance_moyenne ≥ 60 est automatiquement promu ACTIVE au prochain cycle de calibration. Tout principe ACTIVE avec WR < 40% sur n ≥ 50 est automatiquement mis DORMANT. La boucle est fermée — plus d'attente Søn pour les décisions mathématiques. Søn garde un droit de veto via DECISIONS_LOG.** | **Remplace R25'** (assouplie 2026-07-14, motion CEO). Décision actée `workspace/perplexity/memory/DECISIONS_LOG.md` 2026-07-16 §« Mandat CEO — boucle fermée ». Les critères (n_triggered ≥ 20, confiance ≥ 60, WR < 40% sur n ≥ 50) sont des repères initiaux, révisables par Søn. L'auto-calibrateur journalise chaque promotion/démotion dans `cognitive_journal` + notifie Telegram. Søn peut à tout moment désactiver l'auto-promotion via `V9_AUTO_PROMOTION_ENABLED=0`. |
| **26** | **Chaque session de code produit : 1 commit par unité logique + 1 entrée DECISIONS_LOG + STATE.md à jour. Aucune session ne se ferme sans ces 3 livrables documentaires** | Retour ops 2026-07-06 : STATE.md mis à jour en rattrapage par Perplexity, pas par l'agent implémenteur. Ce retard craint un écart temporaire de source de vérité. |
| **27** | **Un champ DORMANT qui reste DORMANT plus de 2 phases est réévalué au checkpoint de phase : promu PROPAGÉ s'il a une couche consommatrice, sinon maintenu DORMANT avec justification écrite et datée dans `CONTEXT_CONTRACT.md`. Plus de suppression automatique — la suppression d'un champ DORMANT exige une décision explicite Søn tracée dans `DECISIONS_LOG.md`** | Reformulée 2026-07-08, Phase 9.8 Phase B : la suppression automatique contredisait 🔴 CHARTE Règle 3 (« la mémoire sert d'abord à conserver et confronter les lectures » — `docs/audit/AUDIT_DOCTRINE_REPORT.md` §3.1/§3.2). Évite toujours l'accumulation de champs calculés mais jamais consommés — la réévaluation reste obligatoire, seule l'issue par défaut change (justifier plutôt que purger). |
| **28** | **Tout agent IA (Hermes, Claude, ZCode, futur agent) peut commit + push directement sur `feat/v9-foundation-clean` — Søn ne gère pas le git lui-même** | Remplace la version "opérateur unique Hermes" (assouplie 2026-07-15, motion CEO Søn, DECISIONS_LOG §2026-07-15 §5). Søn reste novice git et ne tape jamais de commande git. Chaque agent qui pousse doit respecter, sans exception : (1) `git pull --rebase` avant tout push — jamais de push sans rebase préalable ; (2) tests verts avant push (R7 inchangée, non-négociable) ; (3) 1 commit atomique par livraison (R22 inchangée) ; (4) entrée `DECISIONS_LOG.md` si le changement est structurant (R26 inchangée) ; (5) toujours montrer le SHA + 1 ligne description après push. Pas de worktree obligatoire, pas de passage obligé par Hermes. Exceptions (re-ask autorisé auprès de Søn) : (a) credential/2FA demandé, (b) force-push destructif, (c) opération irréversible hors scope session (squash/merge/rebase d'historique partagé). |
| **29** | **Doctrine de lecture du marché : zone-type × multi-TF × non-HTF-first conditionnelle** | Lecture scène-complète multi-TF (§3.1+§3bis+§6+§8 V8, rapatrié 2026-07-07). 4 types de zone (naissance / 2e_jambe / continuation / respiration). HTF = biais interdit, pas alignement obligatoire. MTF = contexte, LTF = confirmation. 2 sens coexistent. Citation Søn : « chaque moment est unique ». Détail ci-après (Règle 29 développe). |
| **30** | **Boucle fermée d'auto-optimisation continue : l'auto-calibrateur ajuste automatiquement les TP/SL/sizing par principe tous les 100 trades. L'auto-optimizer simule 81 combinaisons TP×SL et applique la meilleure si delta > 1 pip. Plus de seuils progressifs — le système s'optimise en continu sans intervention humaine.** | **Remplace R30** (seuils 5/20/50/200 supprimés). Décision actée `workspace/perplexity/memory/DECISIONS_LOG.md` 2026-07-16 §« Mandat CEO — boucle fermée ». L'auto-optimizer est kill-switché par `V9_AUTO_OPTIMIZER_ENABLED`. Zéro LLM dans la boucle (règle 18 préservée). Les ajustements sont journalisés dans `cognitive_journal` + notifiés Telegram. Søn peut désactiver à tout moment. Détail ci-après. |


## Process de session — ordre obligatoire

Ce process s'applique à toute session de code sur `feat/v9-foundation-clean`.

```
┌──────────────────────────────────────────────────────────────────────┐
│ 0. git pull + pytest → confirmer base saine               │
│ 1. [marché ouvert?] OUI → v9_calibration --analyze OBLIGATOIRE   │
│    [marché ouvert?] NON → passer au 2                         │
│ 2. périmètre explicité : un chantier, une livraison complète   │
│ 3. implémentation                                              │
│ 4. tests verts (zéro régression)                              │
│ 5. CONTEXT_CONTRACT.md mis à jour si nouveau champ             │
│ 6. principes YAML consommateurs mis à jour (règle 23)          │
│ 7. commits atomiques (1 par unité logique)                     │
│ 8. DECISIONS_LOG.md — 1 entrée par décision structurante      │
│ 9. STATE.md à jour                                             │
│ 10. git push origin feat/v9-foundation-clean                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Cycle de promotion d'un principe

```
SHADOW ──[auto-calibrateur : n_triggered ≥ 20 ET confiance_moyenne ≥ 60]──► ACTIVE
ACTIVE ──[auto-calibrateur : WR < 40% sur n ≥ 50]──► DORMANT
DORMANT ──[auto-calibrateur : WR remonte > 50% sur n ≥ 30]──► SHADOW (réévaluable)
Toute promotion/démotion est journalisée dans cognitive_journal + notifiée Telegram.
Søn peut désactiver l'auto-promotion via V9_AUTO_PROMOTION_ENABLED=0.
Søn garde un droit de veto via DECISIONS_LOG.

## Cycle de vie d'un champ contexte

```
NOUVEAU CHAMP
  │
  ├── calculé + injecté dans _load_shared_context
  ├── tracé dans CONTEXT_CONTRACT.md (PROPAGÉ ou DORMANT P2/P3)
  ├── test_context_propagation.py mis à jour
  └── [si PROPAGÉ] → principes YAML consommateurs mis à jour (même session)
       [si DORMANT] → justification écrite dans CONTEXT_CONTRACT.md
                        réévaluation au prochain checkpoint de phase
```

## Règle de lecture

Pour toute tâche de code touchant une couche précise, se référer au **Niveau 2/3/4** du rituel
de démarrage décrit dans [README.md](../README.md), qui reste la procédure de référence.
Ce fichier DOCTRINE.md est un point d'entrée synthétique, pas un remplacement du rituel.

---

## Règle 29 — Doctrine de lecture du marché (zone-type, multi-lecture)

> **Origine** : §3.1 + §3bis + §6 + §8 de `DOCTRINE_LECTURE_MARCHE.md` V8, rapatrié dans
> [`workspace/perplexity/memory/DOCTRINE_LECTURE_MARCHE.md`](../workspace/perplexity/memory/DOCTRINE_LECTURE_MARCHE.md)
> le 2026-07-07 (792 lignes).
> **Adoption** : confirmée par Søn 2026-07-07 (Q1=oui, Q2=les 2, Q3=tous, Q4=non).

### Lecture d'une arrivée en zone — 6 dimensions (§3bis)

Une zone extrême (SDI <25 ou >75) ne se lit jamais comme un seuil. Toujours comme une **scène complète** :

1. **TRAJECTOIRE** — d'où vient-on ? (origine, vitesse, profil, temps en zone précédente)
2. **ALIGNEMENT MULTI-TF** — tous les TF racontent la même histoire ? (cohérence, premier arrivé, cascade)
3. **CARTE DES COALITIONS** — qui pousse ? (leader, largeur, opposition)
4. **HISTOIRE RÉCENTE** — qu'est-ce qui s'est passé avant ? (compression, patterns, tension accumulée)
5. **CONTEXTE MARCHÉ** — dans quel cadre ? (session, vol, texture, heure relative)
6. **SIGNATURE COMPORTEMENTALE** — que fait le prix maintenant ? (rejet, absorption, équilibre)

### 3 comportements en zone (§3.1)

| Comportement | Construction HTF | Action |
|--------------|------------------|--------|
| **REJET** | Clôture HTF en opposition (mèche, doji, pin bar) | Fenêtre retournement ouverte |
| **ABSORPTION** | Construction d'une base HTF | Surveiller rupture de la zone |
| **ÉQUILIBRE** | Rejet faible, aucun chantier HTF | Retour à l'attente |

**Règle** : seul REJET construit un vrai setup. ABSORPTION = alerte, ÉQUILIBRE = bruit.

### Mécanisme énergétique — phases en cascade (§6.1)

```
Stockage (H4/H1) → Croisement (TF porteur) → Attente (open) →
Casse (tous TFs) → Cascade (extrêmes absolus sur M1) → Épuisement (M5/M15)
```

Rôle par TF : **H4/D1 stockent**, **H1 confirme**, **M15/M5 transmettent**, **M1 fenêtre**.

### Règle hiérarchique (§8) — non-HTF-first conditionnelle

- HTF définit **un biais interdit** (ne pas trader contre H4 *quand H4 est extrême confirmé*)
- MTF identifie **le contexte** — SDI extrême = fenêtre d'intérêt ouverte
- LTF confirme — sans LTF, pas d'entrée même si MTF est parfait
- **Court terme et long terme coexistent** — un signal M5 peut être valide même si H4 diverge
- Le type de zone (naissance / 2e jambe / continuation / respiration) pondère chaque dimension différemment

### Anti-biais HTF-first

La cascade confirmée HTF→LTF est **un mode d'arrivée en zone parmi d'autres**, pas le seul.
*« La cascade fonctionne dans alignement, mais il y a pas que cela. Ce qui marche hier ne marche
pas aujourd'hui, car chaque moment est unique. »* (Søn, 2026-07-07)

Conséquences code (Phase 9.7 + post-Phase 13) :
- `principle_engine._load_shared_context` : ajout lecture `zone_type` parmi les 6 dimensions
- `window_gate` : assouplissement conditionnel pour fenêtres `naissance_isolee` (1-2 bougies)
  avec `validation_hitl_requise=true` renforcé
- `arbiter.consolidate` : pondération zone-type × session × inertie devise par pattern

### Seuils = repères de départ, pas absolus (§3.2)

Les seuils chiffrés (75/25, 80/20, COALITION_THRESHOLD=5.38, ANTAGONISM=31.39, PLIURE=1.7)
sont des **repères de calibrage**, pas des règles figées. Ils évolueront avec l'apprentissage
(Phase 13, WIN/LOSS ≥ 50). Ce qui est invariant, c'est le **comportement attendu dans chaque zone**.

## Règle 30 — Boucle fermée d'auto-optimisation continue

> **Origine** : Mandat CEO Søn 2026-07-16 — « enlève les interdits, active tout, boucle fermée ».
> Remplace R30 (seuils progressifs 5/20/50/200, supprimés).
> Décision actée `workspace/perplexity/memory/DECISIONS_LOG.md` 2026-07-16.

### Principe
Le système s'auto-optimise en continu sans intervention humaine. Toute décision
mathématiquement rentable avec garde-fous verts est appliquée automatiquement.

### Cycles d'optimisation

| Cycle | Déclencheur | Action | Kill switch |
|---|---|---|---|
| **Auto-calibrateur** | Tous les 100 trades | Ajuste CONFIANCE_MIN, NB_PRINCIPES_MIN, scales DYNAMIC par session | `V9_AUTO_CALIBRATOR_ENABLED` |
| **Auto-optimizer** | Tous les 100 trades | Grid search 81 combinaisons TP×SL par principe, applique si delta > 1 pip | `V9_AUTO_OPTIMIZER_ENABLED` |
| **Auto-promotion** | Tous les 100 trades | SHADOW→ACTIVE si n≥20 + conf≥60 ; ACTIVE→DORMANT si WR<40% sur n≥50 | `V9_AUTO_PROMOTION_ENABLED` |
| **Alpha refresh** | Tous les 100 trades | Recalcule WR/expectancy/edge decay par principe × session × regime | Toujours actif |

### Règles non-négociables
- Zéro LLM dans la boucle (règle 18 préservée).
- Toute modification est journalisée dans `cognitive_journal` + notifiée Telegram.
- Søn peut désactiver n'importe quel cycle via son kill switch.
- Søn garde un droit de veto via DECISIONS_LOG (peut annuler une optimisation).
- Les bornes de sécurité sont codées en dur (TP 5-20, SL 5-20, sizing 0.3-2.0).

### Anti-patterns
- ❌ Attendre Søn pour une promotion mathématiquement justifiée
- ❌ Laisser un principe à 0% hit rate consommer du CPU
- ❌ Avoir des TP/SL statiques alors que les données évoluent
- ❌ Demander la permission pour ce qui est calculable

## Règle 31 — Vérification vocabulaire/échelle avant promotion d'un principe

> **Origine** : DIVERSIFY Chantier A (Claude Opus 2026-07-16). Diagnostic :
> **4 des 6 principes à 0 % hit rate** échouaient parce que leurs conditions
> YAML référençaient une **valeur** ou une **échelle** que la couche cognitive
> amont **ne produit jamais**. Décision actée `DECISIONS_LOG.md` 2026-07-16.

### Principe
Une condition YAML n'est valide que si son champ ET sa valeur/échelle attendue
sont **effectivement produits** par `_load_shared_context` /
`_build_currency_context` sur données réelles. Un principe « vert en test » mais
à 0 % de déclenchement en prod est un **faux positif de couverture**, pas un
principe inactif par nature.

### Obligations
- Avant promotion SHADOW→ACTIVE (ou à la première écriture d'un YAML) :
  vérifier la **distribution réelle** du champ en DB (valeurs, casse, échelle).
- Les comparaisons `value_field` doivent porter sur des champs de **même
  échelle** (ex. ratio 0-1 vs ratio 0-1, jamais ratio 0-1 vs seuil brut).
- Le vocabulaire d'une valeur littérale (`==`, `in`) doit correspondre à la
  casse/valeur exacte de la source (ex. `"compression"` ≠ `"COMPRESSING"`,
  `window_statut="ouverte"` ≠ `"exploitable"`).
- Un principe à 0 % de déclenchement sur ≥ 500 évaluations est **suspect** :
  diagnostiquer la cause racine (champ produit ? valeur atteinte ?) avant de
  le laisser en catalogue.

### Anti-patterns
- ❌ Écrire une condition sur une valeur « plausible » sans la vérifier en DB
- ❌ Comparer deux champs d'échelles différentes via `value_field`
- ❌ Considérer un test unitaire vert comme preuve de productivité en prod

## Règle 32 — DRM APPLY permanent (motion CEO 2026-07-20, R32 fermée)

> **R32 — DRM APPLY PERMANENT (motion CEO 2026-07-20)**
> Le DynamicRiskManager opère en mode **APPLY** par défaut.
> Pas de retour SHADOW sans motion CEO explicite.
> Objectif : zéro friction doctrinal — le système évolue librement.
>
> **R32 est fermée** : la contrainte « SHADOW obligatoire » est levée. La
> gestion du risque adaptative aux cycles et phases est désormais le mode
> nominal du système.

> **Origine** : Mission « Risk Manager Dynamique » (ZCode / Claude Opus,
> 2026-07-17). Diagnostic : le système lit le marché en haute définition
> (5 paires, 8 devises, coalitions HTF, confirmation LTF, cycles/phases) mais
> tradait encore en basse définition (TP/SL statiques, identiques pour toutes
> les phases). Décision actée `DECISIONS_LOG.md` 2026-07-17. Activation APPLY
> permanente actée `DECISIONS_LOG.md` 2026-07-20 (motion CEO R32-CLOSE).

### Principe
La gestion du risque doit refléter la **phase du cycle de marché** lue par la
couche cognitive. Un breakout, un trend, un climax et un range n'ont pas la
même espérance ni la même volatilité — donc pas le même SL/TP/trailing/BE.

Cycle canonique :
`ACCUMULATION → CASSURE → TREND → DISTRIBUTION → CLIMAX → RETOUR → …`

### Détection (code pur, R18)
La phase est dérivée de signaux **déjà produits** par le pipeline (aucun
nouveau calcul de marché, aucun LLM) : `scene.cinematique_json` (vélocité,
accélération, compression), `scene.coalitions_json` (intensité, tendance,
âge), `scene.confluences_mtf_json` (profondeur HTF/LTF, emboîtement),
`regime.regime_type`, `behavior.phase`. Modules :
`core/v9/market_cycle_detector.py`, `core/v9/phase_classifier.py`,
`core/v9/dynamic_risk_manager.py`.

### Calibration
| Phase | Exit | Trailing | Break-even | Rationale |
|---|---|---|---|---|
| Accumulation | TP_SL | non | non | range serré, objectif modeste |
| Cassure | TRAILING | 50% TP | 30% TP | breakout peut pullback, laisser courir |
| Trend | TRAILING | 25% TP | 20% TP | tendance, trailing serré, BE rapide |
| Distribution | TP_SL | non | 50% TP | prendre le profit vite |
| Climax | TIME_BASED | non | non | **aucune nouvelle position** |
| Retour | TP_SL | non | non | mean reversion, objectif modeste |

Modulation coalition : HTF (D1/H4) TP×1.5 SL×1.2 ; LTF (M5/M15) ×0.8 ;
emboîtement multi-TF TP×1.3 ; coalition forte TP×1.2, faible ×0.7.

### Statut & garde-fous
- **APPLY par défaut (motion CEO R32-CLOSE, 2026-07-20)** : le module évalue,
  décrit (`result["dynamic_risk"]`) **et applique** — il propage
  tp_pips/sl_pips/exit_strategy issus de la décision dynamique et marque
  `result["drm_applied"] = True`. Le kill switch `V9_DYNAMIC_RISK_ENABLED`
  reste disponible (défaut ON) ; un retour SHADOW exige une **motion CEO
  explicite** (Søn).
- **R2** : le RiskManager statique reste le fallback (phase indéterminée /
  contexte absent → profil session `DYNAMIC_PROFILES`).
- **R6** : jamais bloquant — toute erreur ou signal manquant retombe sur le
  fallback.
- Bornes descriptives par phase : SL ∈ [6, 25], TP ∈ [4, 40]. Réconciliation
  avec les bornes R30 (TP 5-20, SL 5-20) suivie dans `DECISIONS_LOG.md`.

### Anti-patterns
- ❌ Un même TP/SL pour un climax et un range
- ❌ Ouvrir une nouvelle position en phase climax
- ❌ Repasser le DRM en SHADOW sans motion CEO explicite
