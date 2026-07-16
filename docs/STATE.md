# STATE — PowerFlow V9

> **Source de vérité vivante.** La section AUTO ci-dessous est générée
> automatiquement par `scripts/v9_sync_state.py` depuis les sources réelles
> (DB, pytest, git, disque). Ne pas éditer manuellement.
>
> Pour l'historique complet des phases, voir [`JOURNAL_PHASES.md`](JOURNAL_PHASES.md).

## État courant — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-16 22:29 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `ec19d46 docs(v9): ouverture des yeux â€” corrige compteurs tests (1497â†’1501, +4)` | `git log --oneline -1` |
| Tests collectés | 1503 | `pytest --collect-only` |
| Tables DB | 23 | `sqlite3 data/v9_forces.db` |
| Index DB | 57 | `sqlite3` |
| Taille DB | 1.56 GB | `du -h` |
| Décisions | 68844 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 120203 | DB |
| Scènes | 68871 | DB |
| Principle evals | 704896 | DB |
| Régime snapshots | 550768 | DB |
| Paper trades | 59 | DB |
| Principle scores | 5 | DB |
| Principes YAML | 55 (44 ACTIVE + 11 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 8 | `ls mcp_servers/*.py` |
| Crons Ready | 12 | `Get-ScheduledTask (PowerShell)` |
| V9_TRADER_MINI_ENABLED | 1 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 1 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 1 | env |

<!-- /AUTO:STATE -->

## Phase actuelle

**Session Claude Code (Opus) 2026-07-17 — Fix vote-devise NZD (cause racine) + vérif multi-paires** :
Reprise post-reboot. Le biais NZD résiduel (~97 %/jour) avait une cause racine unique :
l'index UNIQUE `idx_pe_snapshot_principle (snapshot_id, principle_id)` — **sans `currency`** —
sur `principle_evaluations`. Avec `INSERT OR REPLACE`, les 8 évaluations par-devise d'un
principe collapsaient en une seule (la dernière du loop `DEVISES=[…,NZD]` → NZD écrasait tout).
Le moteur était correct (vérifié live : 44 ACTIVE/devise équilibré) ; seule la persistance
tronquait. **Fix** : index UNIQUE → `(snapshot_id, principle_id, currency)` (migration DB live
`scripts/fix_vote_devise_index_20260717.py` + schéma `principle_db.py`). Après fix : 8 devises
persistées/snapshot (12,5 % chacune vs ~97 % NZD), idempotence préservée. **Vérif multi-paires** :
les 5 paires (GBPUSD, USDJPY, USDCAD, USDCHF, EURUSD) sont pleinement lues par le pipeline
cognitif (scènes + évals fraîches). Vue NZD `v_principle_evaluations_clean` OK (Option A).
Backup R8 MD5 `715ec03d…`. Tests 1502 verts (+1 non-régression).
Rapport : `docs/reports/etat_pipeline_5paires_20260716.md`.

**Session Claude Code (Opus) 2026-07-16 — Ouverture des yeux : data-layer (volume, vélocité), vue NZD, études** :
Mission « le cerveau lit, mais ses yeux sont myopes ». Corrige plusieurs prémisses du brief
par la donnée réelle :
1. **Volume** — `tick_volume` capturé à **100%** mais lu par 0 principe. Dérivation d'un
   régime relatif (`volume_regime` HIGH/NORMAL/LOW + `volume_ratio` vs médiane 100 derniers,
   `principle_engine._load_shared_context`) + 1er principe consommateur `VOLUME_CONFIRMATION`
   (SHADOW). Additif R2/R6.
2. **Vélocité** — fix robustesse `forces_reader` (fallback capture-time si `bar_time` fige).
   Constat : vélocité **vivante à 91% sur M1**, ~1% candle car **force SDI constante
   intra-bar** (99,2% M15) — pas un bug. KPI « >50% » non atteignable par patch reader
   (borné par le modèle données). Next-step : brancher `velocite_moyenne` sur tick M1
   (calibration séparée).
3. **NZD** — 655 724/657 284 (99,76%) = artefact vote-devise pré-fix. Vue non-destructive
   `v_principle_evaluations_clean` (1587 lignes propres) + `scripts/purge_nzd_20260716.sql`
   (2 options). **DÉCISION SØN** : purge destructive vs vue. Vote-devise résiduel (~97%
   go-forward) remonté, non corrigé (hors périmètre, change la logique d'éval).
4. **Études** — `docs/reports/etude_multipaires_20260716.md` (corrélation 8 forces →
   **activer USDJPY en premier**, axe JPY le plus décorrélé), audit coalitions (8,7% des
   scènes, WR-par-coalition pas encore exploitable : échantillon résolu <30).
Catalogue : **55 principes (44 ACTIVE / 11 SHADOW)**. Tests **1501 passed +1 skip** (+4 : 2 vélocité +
2 volume). `order_executor.py`, `config.py`, Phase 12 non touchés. Détail :
`docs/reports/audit_donnees_ouverture_yeux_20260716.md`, `DECISIONS_LOG.md` §2026-07-16 Ouverture des yeux.

**Session ZCode 2026-07-16 — Mandat CEO boucle fermée : SHADOW→ACTIVE massif + auto-calibrateur writable + auto-optimizer** :
Motion CEO Søn : « enlève les interdits, active tout, boucle fermée ». Trois chantiers livrés :

1. **SHADOW→ACTIVE massif** : tous les SHADOW avec n_triggered ≥ 20 et confiance ≥ 60 promus ACTIVE. PRINCIPLE_ACTIVE_IDS passe de 25 à ~48. Strategy blocks ajoutés dans les YAML promus. La boucle d'auto-promotion est désormais automatique (R25'').

2. **Auto-calibrateur writable** : `auto_calibrator.py` ne propose plus — il APPLIQUE. Ajuste CONFIANCE_MIN, NB_PRINCIPES_MIN, scales DYNAMIC par session, et promeut/démet les principes automatiquement. Journalise dans `cognitive_journal` + notifie Telegram.

3. **Auto-optimizer** : nouveau module `core/v9/auto_optimizer.py`. Grid search 81 combinaisons TP×SL par principe tous les 100 trades. Applique le meilleur couple si delta > 1 pip. Overrides persistés dans `config/strategy_overrides.json`.

**Doctrine mise à jour** : R25' → R25'' (auto-promotion), R30 remplacée (boucle fermée, plus de seuils progressifs). SOUL.md révisé (vision → réalité opérationnelle). CONTEXT_CONTRACT.md mis à jour (22 champs DORMANT vérifiés consommés par ML, maintenus). ROADMAP.md : Phase 13 marquée TERMINÉE.

**Rapport alpha inchangé** : PRICE_LAG +5.721 pips/trade (n=8092), edge decay -18.9% surveillé par l'auto-optimizer. Détail : `DECISIONS_LOG.md` §2026-07-16 Mandat CEO boucle fermée.
Correctif du goulot identifié par la session précédente (0 CASSURE/EXTENSION
live sur H1/H4). Diagnostic affiné avant correction : sur les 8 devises,
6/8 produisent déjà CASSURE/EXTENSION en H1 avec les seuils par défaut —
seul GBP (la **seule** devise lue par `mtf_confirmation_engine` via
`base = symbol[:3]` sur GBPUSD) est resté plat sur cette fenêtre de 10 jours
(deux tendances soutenues sans palier propre). Cause racine confirmée :
H1/H4 ne reçoivent qu'**une seule évaluation par barre fermée** (pas
d'échantillonnage intra-barre comme M1-M30), donc la probabilité jointe
« 3 barres consécutives quasi-immobiles » (REGIME_N_MIN=3) pour ancrer un
palier ne se matérialise quasiment jamais sur les ~25-100 barres H1/H4
disponibles en 10 jours — alors que les distributions de pas de force sont
quasi identiques entre TF (percentiles vérifiés, pas un problème d'échelle).
Correctif : `REGIME_TIMEFRAME_OVERRIDES` (config.py) + `RegimeDetector.
_effective_thresholds()` (nouveau, respecte la config explicite du
constructeur — R2 additif) — H1 `n_min=2`, H4 `seuil_palier=0.7 + n_min=2`.
Backtest réel (GBP, 2026-07-06→16, une éval/barre) : H1 10.8%, H4 17.4% de
taux CASSURE+EXTENSION, alignés sur le taux sain M1-M30 (4.9%-14.6%) au même
grain. Validation bout-en-bout sur données live réelles : `regime_detector.
detect()` reclasse une barre H4 historique en CASSURE UP, `MTFConfirmationEngine.
evaluate()` produit `aligned=True, confidence_boost=25` — le boost MTF est
démontré fonctionnel. M1/M5/M15/M30/D1 non touchés (déjà sains). 3 tests
ajoutés (override H4, seuil H4 vs M5, priorité config explicite). Seuls
`core/v9/config.py` et `core/v9/regime_detector.py` modifiés (MTF engine,
signal_generator, YAML non touchés, conforme au périmètre gelé de session).
Tests : 1381 passed, 1 skip, 1 fail pré-existant inchangé
(`test_classify_insufficient_data`). Détail : `DECISIONS_LOG.md` §2026-07-16 bis.

**Session Claude Code 2026-07-16 — P0 annulé (diagnostic MTF corrigé) + rapport alpha** :
Vérification empirique du diagnostic MTF du 2026-07-15 avant d'implémenter le
P0 (« forcer capture H4 ») : **invalidé**. H4 est frais (1.5h) et capturé au
rythme normal des clôtures de bougie (pas de bug de cadence, pas de filtre
de fraîcheur dans le code). Le vrai goulot : les 13 seules occurrences
CASSURE/EXTENSION sur H4 (GBP) proviennent **toutes** du burst seed du
2026-07-05 (3 secondes d'écart) — en 10 jours de capture live, H4 et H1 n'ont
**jamais** produit CASSURE/EXTENSION (alors que M1/M5/M15/M30 en produisent
normalement). Le MTF boost reste câblé correctement mais structurellement
dormant côté `regime_detector`, pas côté capture. P0 annulé (0 fichier
core touché). Rapport alpha regénéré :
`docs/reports/alpha_report_post_fix_20260716.md` (bus `alpha_report`) —
PRICE_LAG +5.721 pips/trade (n=8092) intact, edge decay inchangé -18.9%,
ZONE_RETEST/POWER_ANGLE/GRAVITY positifs mais modestes (plus réalistes
post-fix vote NZD). Tests : 1378 passed, 1 skip, **1 fail pré-existant**
(`test_classify_insufficient_data`, date hardcodée 2026-07-08 expirée, hors
périmètre). Détail : `DECISIONS_LOG.md` §2026-07-16.

**Session Claude Code (Opus) 2026-07-15 — Phase 1 stabilisation post-fix vote NZD** :
WR recalibrés (workhorse PRICE_LAG_AT_NODE_BIRTH intact à 86.9% n=8092 ;
ZONE_RETEST 57.3%, POWER_ANGLE 54.4%, GRAVITY 51.9%). Baseline post-fix
persistée dans `principle_alpha_metrics` (76 lignes, était vide). 6 strategy
profiles ACTIVE ré-ajustés via `sizing = min(2.0, max(0.3, WR/0.50))`.
`learning_loop.propose_from_alpha_metrics()` ajouté (additif R2, propose-only) —
propositions par principe × session (ex. PRICE_LAG asie WR 96% → sizing ×1.90).
**Finding structurant** : le boost MTF (+25) est correctement wire mais
**structurellement dormant** — capture H4 trop clairsemée (200/223 seed, ~3-6/j
live) + thesis H4 occultée par un H4 NEUTRE plus récent (`_find_context_snapshot`
LIMIT 1) → 0 boost sur tout l'historique. Correctif capture-cadence H4 =
chantier pipeline hors périmètre code, à arbitrer Søn. Rapport alpha :
`docs/reports/alpha_report_post_fix_20260715.md` (bus `849d6862`). Anomalie
sessions `new_york`/`after` 0% WR sur tous principes (artefact data). Paper-trade
validé (haussiere 76.9% vs baissiere 40% = résidu biais pré-fix). Détail :
`DECISIONS_LOG.md` §2026-07-15 Phase 1.

**Session Claude Code 2026-07-15 — reprise ZCode, tests + strategy profiles** :
Reprise après commit ZCode `98119c4` (infra collaborative IA + trade engine
consolidé + SOUL.md). 8 tests désynchronisés corrigés (comptages ACTIVE/SHADOW
+ scénarios GRAMMAR_CONTEXTE migrés vers GRAMMAR_CONTEXTE_ADAPTIVE, DORMANT
n'étant plus audité). 18 strategy profiles ajoutés aux principes ACTIVE
restants (7 avec données réelles, 11 conservateurs). 1339 verts + 1 skip +
0 fail. Détail : `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-15.

**Catalogue principes** : 25 ACTIVE (27→25 : 5 mis DORMANT — COALITION_NODE,
NODE_BIRTH_FAST, RAW_NODE_BIRTH, ELASTIC_BREATH, GRAMMAR_CONTEXTE — + 3
`*_ADAPTIVE` promus ACTIVE — GRAMMAR_CONTEXTE_ADAPTIVE 79.5%,
POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE 75.0%, ZONE_RETEST_ADAPTIVE 66.7%).
23 SHADOW YAML restants, 5 DORMANT. Sessions tradables : asie + london
uniquement (overlap blacklisté, expectancy -2.26 pips/trade). zone_diagnostics
réactivé (14 SHADOW débloquées). trade_engine : hook orchestrator actif.
PrincipleStrategyEngine : tous les principes ACTIVE ont désormais un champ
`strategy`.

P3-CONSUME-EXTEND **CLOSED** §2.2 (bilan, baseline 1307 verts, tous YAML `*_ADAPTIVE`
SHADOW R25' strict). Promotion ACTIVE = motion CEO distincte ultérieure.

WIRE activé 14/07 commit `ac26c3a` (motion CEO priorité 3). Les `*_ADAPTIVE.yaml`
SHADOW consomment désormais les seuils adaptatifs runtime.

TP_SL P3-D1 **CLOSED-OBSOLETE** §2.3 — 0 cas TP_SL depuis P1-RESOLVE 14/07, neutralisée
par doctrine (DYNAMIC default 8131 cas, 88.65% WR).

**Série Q1→Q5 clôturée** (2026-07-12/13) : trader-mini baseline, auto-calibrateur,
dashboard HITL, multi-paires, order_executor (double-verrou, Phase 12 gelée).
Kill switches `V9_TRADER_MINI_ENABLED=1` et `V9_AUTO_CALIBRATOR_ENABLED=1` activés
par motion CEO 2026-07-14.

**Fable hors service** (pas de crédit). ZCode et Hermes continuent en parallèle
sur `feat/v9-foundation-clean`.

## Dernier commit

Voir `git log --oneline -1` (git gagne toujours — ce champ dérive vite).

## Règles pour toute IA prenant la relève

```
1. Lire docs/CACHE_BOARD.md (2 min) AVANT toute action
2. Lire docs/STATE.md (ce document) — état exécutif complet
3. git pull + pytest tests/ -q + python scripts/v9_guards.py all → confirmer base saine
4. R20' : si marché ouvert → v9_calibration --analyze OBLIGATOIRE
5. R7 : zéro régression non justifiée (assoupli 2026-07-14, DOCTRINE.md)
6. R8 : backup MD5 avant toute modif core/v9/
7. R18 : zéro LLM dans le cœur cognitif
8. R22 : un périmètre = une livraison complète (assoupli 2026-07-14)
9. R26 : 1 commit + 1 DECISIONS_LOG + STATE.md à jour
10. R28 : Hermes = opérateur git unique (assoupli 2026-07-14)
```

## Références pivots

| Document | Rôle |
|---|---|
| `docs/CACHE_BOARD.md` | Tableau de bord compact (2 min) |
| `docs/STATE.md` | **CE DOCUMENT** — état exécutif |
| `docs/JOURNAL_PHASES.md` | Journal historique des phases (archive) |
| `docs/DOCTRINE.md` | 30 règles immuables |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Journal des décisions |
| `workspace/perplexity/BOARD.md` | Board de coordination |
| `workspace/perplexity/ACTIVE_TASKS.md` | Tâches actives |
| `scripts/v9_guards.py` | Gardiens de cohérence automatisés |
| `scripts/v9_sync_state.py` | Régénérateur automatique de l'état |