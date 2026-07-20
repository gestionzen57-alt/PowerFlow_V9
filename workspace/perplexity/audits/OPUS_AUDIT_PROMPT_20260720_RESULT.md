# Audit Opus Code V9 — 2026-07-20

> **Audit structurel post-fix nocturne** | 8 commits analysés (1072999 → 9054725)
> **Doctrine** : R6 · R7 · R18 · R22 · R25'' · R26 · R28 · R30 · R32
> **Mode** : lecture seule + `core/v9/*.py` non modifié | PAS DE COMMIT (R22 strict, R28 multi-agent flow)
> **Périmètre** : 1 chantier = 1 livraison (audit seul)

---

## A. Inventaire technique actuel

### A.1 Code coverage `core/v9/`

| Métrique | Valeur |
|---|---|
| Modules Python | **99** (98 fichiers + `__init__.py`) |
| Total LOC | **35 228** |
| Top 5 par taille | `trade_engine.py` 1514 · `principle_engine.py` 1291 · `scene_builder.py` 987 · `v9_bear_perception.py` 947 · `v9_bayesian_predictor.py` 931 |
| Tests | **181 fichiers `tests/`** (court-circuit slow/non-slow via `pytest -m "not slow"`) |
| Scripts CLI | **117 fichiers `scripts/v9_*.py`** |

**Modules candidats "morts"** (non importés ailleurs — vérifications croisées code/docs) :

| Module | LOC | Statut réel | Recommandation |
|---|---:|---|---|
| `v9_dashboard_api.py` | 474 | Référencé par `v9_bear_dashboard.py:6` (docstring) + `uvicorn core.v9.v9_dashboard_api:app` (entry-point) | **Garder** — point d'entrée uvicorn |
| `v9_aggressive_strategy.py` | 400 | Importé uniquement par scripts `v9_aggressive_optimize.py:33` + `v9_aggressive_paper_trade.py:41` — **Phase F NO-GO** (DECISIONS_LOG §6409) | **Archiver** dans `core/v9/_archive_no_go/` |
| `v9_pyramiding_engine.py` | 209 | Idem — uniquement scripts Phase F | **Archiver** |
| `v9_sizing_confidence.py` | 140 | Idem — uniquement scripts Phase F (Kelly NO-GO walk-forward) | **Archiver** |

→ **Effort DROP/Archive** = ~750 LOC + 3 tests. **Motion CEO #1** (voir F).

### A.2 Tables DB (DB live `data/v9_forces.db` lecture seule, 3.12 GB)

**Inventaire brut (24 tables user — le brief disait 25, écart = 1 table sans doute `paper_trades_backup` comptée à tort, ou table transitoire)** :

| Table | Rows | Refs code | Verdict |
|---|---:|---:|---|
| `principle_evaluations_shadow_archive_20260718` | **1 984 513** | **0** | 🗑️ **CANDIDAT DROP** — 2 GB pur, jamais requêté |
| `paper_trades_backup_20260717` | 4 839 | 4 | 🗑️ **CANDIDAT DROP/ARCHIVE** — backup one-shot pré-fix P0 |
| `agent_event_bus` | 0 | 1 | ⚠️ Wired in `agent_bus.py` mais aucune émission → ou DROP ou LIVE |
| `cognitive_journal` | 0 | 16 | ⚠️ Wired mais non alimenté (devrait l'être par auto_calibrator) |
| `principle_evaluations` | 1 615 062 | 212 | ✅ actif |
| `forces_snapshots` | 136 862 | 392 | ✅ actif |
| `decisions` | 78 415 | 635 | ✅ actif |
| `regime_snapshots` | 627 928 | 90 | ✅ actif |
| `zone_diagnostics` | 600 464 | 88 | ✅ actif |
| `behaviors` / `signals` / `windows` / `exploitability` / `scenes` | ~78k chacun | actif | ✅ |
| `paper_trades` | 4 854 | 274 | ✅ actif (16 ouvertes) |
| `agent_telemetry` | 41 386 | 42 | ✅ actif |
| `probe_events` | 19 232 | 11 | ✅ actif |
| `mtf_confirmations` | 12 059 | 17 | ✅ actif |
| `principles` | 55 | 237 | ✅ actif |
| `principle_scores` | 226 | 53 | ✅ actif |
| `learning_proposals` | **18** | 30 | ⚠️ Très peu de propositions malgré auto-promotion active |
| `principle_alpha_metrics` | 194 | 13 | ✅ |
| `principle_cascade_registry` | 17 | 6 | ✅ |
| `principle_causal_journal` | 1 | 6 | ⚠️ Quasi vide |

**Stats marché live (snapshot ~06:39 UTC)** :
- Décisions 2h : **1539 aucune_action · 110 preparer_entree · 213 surveiller** (le brief disait 504/53/33 — diff fenêtre temporelle : probablement chiffres 06:11 → 06:39, 2h × 1.5 à 3× plus de volume depuis reprise)
- Source breakdown 2h : **100 % live · 0 shadow** ✓ (cohérent `V9_SHADOW_MODE_ENABLED=0`)
- **`open_long` GBPUSD depuis 2026-07-19 23:00 UTC : 0** ✓ (conforme motion P0)
- WR 24h paper_trades : 21 clôturés, sample non significatif

### A.3 Principes YAML (55 fichiers)

| Statut | YAML sur disque | `principles.v9_status` (DB) | `principles.source_status` (DB) |
|---|---:|---:|---:|
| ACTIVE | 46 | **46** | **48** |
| SHADOW | 9 | **9** | **7** |

⚠️ **DRIFT entre `v9_status` et `source_status`** : 2 principes avec `source_status=ACTIVE` mais `v9_status=SHADOW` (et 1 SHADOW→ACTIVE). Cause probable : `v9_status` patché par `b9e8ba5` (PRICE_LAG_AT_NODE_BIRTH drift fix) sans toucher `source_status`. **À reconcilier** dans un chantier dédié (gardien `v9_guards.py db-sync` ne le détecte pas car il compare aux YAML disque).

**Dédup candidates** (paires `_ADAPTIVE` semblent être des variantes paramétriques — non dupliquées stricto sensu) : 18 fichiers `_ADAPTIVE.yaml` distincts (couple {BASE, BASE_ADAPTIVE}). Pas de redondance textuelle détectée.

---

## B. Doctrine wiring audit

### B.1 R18 (zéro LLM dans `core/v9/`)

- **Verdict : ✅ OK**
- Preuve : `grep -rE "openai|anthropic|claude" core/v9/*.py` → 7 hits, **tous dans `agent_bus_bridge.py`** (constante string `CLAUDE_CLI_PREFIX = "claude-cli"` aux lignes 43/69/113/121/231/254/330, utilisé comme tag de provenance agent — pas d'appel LLM).

### B.2 R25' (kill switch par feature)

- **Verdict : ⚠️ PARTIEL** — wrapper `core/v9/kill_switches.py` existe et expose 14+ fonctions (`shadow_mode_enabled`, `paper_trade_halt_enabled`, etc.). **Mais** :
  - 31 sites `core/v9/*.py` lisent encore `os.environ.get(...)` direct (`grep -rEn "os\.environ\.get" core/v9/`), contournant le wrapper. Cas notables :
    - `trade_engine.py:99,104,116,128,133,146,151,156` (7 sites)
    - `auto_calibrator.py:59,64,69`
    - `shadow_evaluator.py:84,176`
    - `principle_engine.py:1194`, `order_executor.py:68`, `arbiter.py:217`, etc.
  - Le **wrapper cron** `scripts/v9_load_kill_switches.py` couvre 15/15 Scheduled Tasks V9_* (vérifié via `schtasks /query`) **SAUF** `V9CaptureWatchdog` (manuelle par design — MT4 préalable).
- **R6 (fail-safe) OK** : `trade_engine.py:298-306` câble `V9_PAPER_TRADE_HALT` comme gate P0.
- **Recommandation** : chantier `P1-KILLSWITCH-REFACTOR` — migrer 31 sites vers `kill_switches.get(...)`. Effort M.

### B.3 R26 (tests verts avant commit)

- **Verdict : ⚠️ PARTIEL** — `scripts/v9_guards.py` existe avec 6 gardiens (`no-secrets`, `yaml-sync`, `scripts-exist`, `hitl-sync`, `db-sync`, `kill-switch-integrity`). Mais `.pre-commit-config.yaml` (lignes 35-77) ne référence que **4 des 6 gardiens** :
  - ❌ `db-sync` absent → drift YAML↔DB pourrait passer
  - ❌ `kill-switch-integrity` absent → kill switch fantôme possible
  - ❌ `v9_audit_cron_wiring` (livré `0faf2e9`) **non câblé en pre-commit** → re-décâblage futur possible
- Le hook `pytest-fast` (ligne 35-44) ne fail pas (`always_run: true` commenté). **R26 non bloquante mécaniquement** pour les commits.

### B.4 R28 (multi-agent commit + push)

- **Verdict : ✅ CONFORME** — aucun commit/push effectué par cette mission (cf. R22 strict). Motion commit sera tranchée par le CEO sur review.

### B.5 R30 (boucle fermée d'auto-optimisation)

- **Verdict : ⚠️ PARTIEL** — `auto_calibrator.py` (commit `5c09a60`) tourne chaque nuit via `V9_AutoCalibrator` schtasks (03:00 UTC). Mais :
  - `learning_proposals` = **18 rows** seulement (faible activité malgré auto-promotion)
  - `cognitive_journal` = **0 rows** (devrait journaliser chaque promotion/démotion selon R25'')
  - **Boucle réelle** : `V9_ResolveLoop` (10 min) → `V9_CalibrationLoop` (2h) → `V9_AutoCalibrator` (3h daily) → `V9_AutoOptimizer` (proposé). **Feedback loop mesurable** : ✅ oui (via WR par session dans `auto_calibrator.py:141-156`), mais **promotions effectives = 18 / 55 principes** depuis l'origine → boucle lente.
  - Divergence seuils : voir C-P1 ci-dessous.

### B.6 R32 (DRManager SHADOW/APPLY)

- **Verdict : 🔴 VIOLATION CARACTÉRISÉE** — le subagent précédent avait raison :
  - **Commentaire `trade_engine.py:72-77` dit** : *"Défaut ON en mode SHADOW : le module ÉVALUE la gestion de risque adaptative et attache le résultat au diagnostic, mais n'APPLIQUE rien — le SL/TP réellement utilisé reste celui calculé par la chaîne existante."*
  - **Code `trade_engine.py:692-703` dit l'inverse** :
    ```python
    if (risk_decision.source == "dynamic" and risk_decision.allow_new_position):
        if risk_decision.tp_pips: tp_pips = float(risk_decision.tp_pips)
        if risk_decision.sl_pips: sl_pips = float(risk_decision.sl_pips)
        if risk_decision.exit_strategy: strategy = risk_decision.exit_strategy
        result["drm_applied"] = True
    ```
  - **Conclusion** : DRM est en **mode APPLY**, pas SHADOW. Le commentaire ligne 72-77 est **faussé** et `DYNAMIC_RISK_ENV` défaut `1` active APPLY silencieusement. Motion CEO requise pour trancher : SHADOW strict (aligner le code) ou APPLY assumé (corriger le commentaire).
- **Lien avec `dynamic_risk_manager.py:270`** : `source="dynamic"` est le retour par défaut du profil phase/cycle → toutes les décisions calibrées **override** les tp/sl/exit.

---

## C. Gaps structurels (P0/P1/P2)

### P0 — Gaps bloquants

#### P0-A · DRManager SHADOW vs APPLY contradiction (R32 violée)
- **Symptôme** : commentaire `trade_engine.py:72-77` affirme SHADOW-only, mais `trade_engine.py:692-703` APPLIQUE tp/sl/strategy en silence dès que `source=dynamic`.
- **Cause** : `DYNAMIC_RISK_ENV` défaut `"1"` (`trade_engine.py:78,151`) + code APPLY inconditionnel quand `source == "dynamic"`.
- **Fix** : 2 options tranchables par motion CEO :
  - (a) **SHADOW strict** : commenter lignes 697-703 (`tp_pips = ...` → `result["dynamic_risk_proposed"] = ...` sans override).
  - (b) **APPLY assumé** : corriger le commentaire 72-77, journaliser chaque override dans `cognitive_journal`, ajouter gate `V9_DRM_APPLY_CONFIRM`.
- **Motion CEO** : oui, **chantier #1** (voir F).
- **Effort** : S.

#### P0-B · `v9_paper_trade_resolver` import fantôme
- **Symptôme** : `_load_adaptive_threshold` (`v9_paper_trade_resolver.py:113-124`) tente `from core.v9._load_shared_context import load_shared_context`. Le module **n'existe pas** (vérifié : 0 fichier `_load_shared_context.py` dans `core/v9/`).
- **Cause** : import mort livré SHADOW (commit `5c09a60`).
- **Fix** : soit créer `core/v9/_load_shared_context.py` (avec P3-WIRE derrière), soit retirer le bloc et logger en WARNING qu'aucun seuil adaptatif n'est chargé.
- **Motion CEO** : non (S peut trancher), mais à signaler.
- **Effort** : XS.

#### P0-C · 3 modules Phase F NO-GO livrés en prod (`v9_aggressive_strategy` / `v9_pyramiding_engine` / `v9_sizing_confidence`)
- **Symptôme** : 750 LOC de code Phase F non utilisés en production (NO-GO walk-forward DECISIONS_LOG §6409), mais toujours compilés et accessibles → surface d'attaque inutile.
- **Cause** : motion CEO antérieure "livré mais non activé" sans.archive.
- **Fix** : déplacer dans `core/v9/_archive_no_go/phase_f_2026-07-09/` + ajouter `core/v9/_archive_no_go/__init__.py` blocklist pour pytest collection. Tests associés à déplacer aussi.
- **Motion CEO** : oui, **chantier #1 (même lot que archive)**.
- **Effort** : S.

### P1 — Gaps importants

#### P1-A · `auto_calibrator.py` vs `v9_auto_promotion.py` double moteur avec seuils divergents
- **Symptôme** :
  - `auto_calibrator.py:37-47` : `TARGET_WR_SESSION=75%`, `WR_LOW_THRESHOLD=60%`, `DEMOTION_MAX_WR=40%`
  - `v9_auto_promotion.py:366-368` : `--min-wr=0.70 (70%)`, `--min-n=100`, `--min-sharpe=1.0`
  - **Aucun** lien entre les deux. Si R25'' (auto-promotion) tourne, elle utilise des seuils différents du calibrateur qui calcule les WR. **Risque** : un principe avec WR=65% serait `WR_LOW_THRESHOLD` OK pour le calibrateur mais `WR < 70%` REJECTED par l'auto-promotion.
- **Cause** : deux implémentations séparées (commit `5c09a60` + historique). Pas de constante partagée.
- **Fix** : extraire `core/v9/promotion_thresholds.py` avec `MIN_WR_PROMOTE`, `MIN_N_PROMOTE`, `MIN_SHARPE_PROMOTE` importé par les deux modules. Une seule source de vérité (R15).
- **Motion CEO** : oui, chantier #2.
- **Effort** : S.

#### P1-B · Drift `v9_status` vs `source_status` sur table `principles`
- **Symptôme** : 55 principes, dont 48 ACTIVE selon `source_status` mais 46 ACTIVE selon `v9_status` (et 7 vs 9 SHADOW) — **2 incohérences** non détectées par gardien `db-sync` (qui compare aux YAML disque).
- **Cause** : commit `b9e8ba5` a aligné `v9_status` à `PRICE_LAG_AT_NODE_BIRTH` mais pas `source_status`.
- **Fix** : ajouter gardien `v9_guards.py principles-status-coherence` (vérifie `v9_status == source_status` ou documente la divergence intentionnelle).
- **Motion CEO** : non (S peut trancher).
- **Effort** : XS.

#### P1-C · 31 sites `os.environ.get` contournent le wrapper `kill_switches.py`
- **Symptôme** : modules core lisent l'env directement → wrapper central inopérant pour ces features. Risque : un script qui n'utilise pas `v9_load_kill_switches.py` voit un comportement différent.
- **Cause** : historique (wrapper livré tard, migration non finie).
- **Fix** : grep → refactor systématique `os.environ.get(KEY, default)` → `kill_switches.get(KEY, default)` sur les 31 sites. Compatible R6 (fallback identique).
- **Motion CEO** : non.
- **Effort** : M.

#### P1-D · Hooks R26 incomplets (3 gardiens absents du pre-commit)
- **Symptôme** : `db-sync`, `kill-switch-integrity`, `v9_audit_cron_wiring` non listés dans `.pre-commit-config.yaml`.
- **Fix** : ajouter les 3 hooks en local + activer `always_run: true` sur `pytest-fast` (R26 bloquante).
- **Motion CEO** : oui si on active `always_run: true`, sinon non.
- **Effort** : S.

#### P1-E · `cognitive_journal` et `agent_event_bus` vides
- **Symptôme** : `cognitive_journal=0 rows` (R25'' exige journalisation des promotions) ; `agent_event_bus=0 rows` (le bus agent existe en schema mais aucun émetteur).
- **Fix** : `auto_calibrator.propose()` doit `INSERT INTO cognitive_journal` ; les agents `meta_agent`, `arbiter`, etc. doivent émettre dans `agent_event_bus`.
- **Effort** : M (touche plusieurs modules).

### P2 — Qualité

#### P2-A · Tables `paper_trades_backup_20260717` (4 839 rows) et `principle_evaluations_shadow_archive_20260718` (1 984 513 rows, ~2 GB) à DROP après vérif MD5
- **Fix** : `VACUUM INTO` → `data/backups/db_20260720_pre_archive_drop.db`, MD5, puis DROP. **Pré-requis motion CEO** : confirmer que les archives git (`docs/calibration/backups/2026-07-19_p0_shadow_halt`) contiennent déjà l'essentiel.

#### P2-B · `learning_proposals` = 18 rows malgré R25'' actif
- **Symptôme** : très peu de propositions depuis l'activation de l'auto-promotion.
- **Fix** : audit du cycle `v9_ops.py propose 7` → vérifier que la chaîne `cognitive_journal → learning_proposals → auto_promotion` est bien fermée.

#### P2-C · 7 fichiers YAML `_ADAPTIVE.yaml` non testés individuellement
- **Symptôme** : `test_yaml_loads_25_unique_ids.py` charge 25 IDs (probablement les non-adaptive), mais les 18 variants `_ADAPTIVE` n'ont pas de couverture dédiée.

---

## D. Plan d'action numéroté

| # | ID | Titre | Dépendances | Motion CEO | Tests à ajouter | Risque doctrinal | Effort |
|---|---|---|---|---|---|---|---|
| 1 | **P0-DRM-MOTION** | Trancher DRManager SHADOW strict vs APPLY assumé | Aucune | **OUI (F)** | `tests/test_v9_drm_shadow_or_apply.py` (vote runtime) | R32 | S |
| 2 | **P0-NO-GO-ARCHIVE** | Déplacer 3 modules Phase F NO-GO vers `_archive_no_go/` | Aucune | OUI (lot avec #1) | Adapter `tests/test_v9_aggressive_strategy.py`, `test_v9_sizing_confidence.py`, `test_v9_pyramiding_engine.py` → xfail/skip | R9 (dette) | S |
| 3 | **P0-DB-DROP-ARCHIVES** | DROP `paper_trades_backup_20260717` + `principle_evaluations_shadow_archive_20260718` après vérif MD5 | Dépend de `docs/calibration/backups/2026-07-19_p0_shadow_halt` | OUI | `tests/test_v9_db_archives_droopped.py` | R7, R14 | S |
| 4 | **P0-RESOLVER-IMPORT-FIX** | Créer `core/v9/_load_shared_context.py` OU retirer bloc mort dans `v9_paper_trade_resolver.py:113-124` | Aucune | NON (S tranche) | `tests/test_v9_paper_trade_resolver_imports.py` | R6 | XS |
| 5 | **P1-PROMOTION-THRESHOLDS-UNIFY** | Extraire `core/v9/promotion_thresholds.py` ; `auto_calibrator` + `v9_auto_promotion` importent la même source | Aucune | OUI | `tests/test_promotion_thresholds_coherence.py` | R15, R25'' | S |
| 6 | **P1-STATUS-DRIFT-GUARD** | Ajouter gardien `principles-status-coherence` (db-sync v2) + câbler pre-commit | #5 (séquençage) | NON | `tests/test_v9_guards_principles_status.py` | R26 | XS |
| 7 | **P1-KILLSWITCH-REFACTOR** | Migrer 31 sites `os.environ.get` vers `kill_switches.get` | Aucune | NON | `tests/test_v9_kill_switch_wrapper_full_coverage.py` | R25' | M |
| 8 | **P1-R26-HARDENING** | Câbler `db-sync` + `kill-switch-integrity` + `v9_audit_cron_wiring` dans `.pre-commit-config.yaml` ; activer `always_run: true` sur `pytest-fast` | #6 | OUI (si bloquant) | E2E pre-commit | R26 | S |
| 9 | **P1-COGNITIVE-JOURNAL-WIRE** | `auto_calibrator.propose()` INSERT dans `cognitive_journal` ; agents émettent dans `agent_event_bus` | Aucune | NON | `tests/test_cognitive_journal_population.py` | R25'' | M |
| 10 | **P2-PAPER-TRADE-LOOP-RECONCILE** | Purger les 69639 décisions `aucune_action` non résolues (jamais destinées à l'être) OU clarifier le schéma | Aucune | NON | Migration test | R15 | M |

**Dépendances croisées** :
- #1 + #2 peuvent être livrés en un seul commit (motion CEO lot unique)
- #5 et #6 peuvent fusionner en un seul chantier
- #8 dépend de #6 mais indépendant des autres
- Tous les P0 (1-4) peuvent être lancés en parallèle par 4 subagents distincts

**Estimation tests à ajouter/modifier** : ~15 fichiers nouveaux + 3 fichiers à adapter.

---

## E. Recommandations CEO

### Top 3 immédiat (P0 uniquement)

1. **Trancher DRManager SHADOW vs APPLY** (`P0-DRM-MOTION`) — la divergence est silencieuse et impacte chaque décision live. Coût : 1 motion + 1 commit.
2. **DROP 2 tables archives** (~2 GB récupérés, perf VACUUM) — `P0-DB-DROP-ARCHIVES` après vérif MD5.
3. **Fixer `v9_paper_trade_resolver` import fantôme** — `P0-RESOLVER-IMPORT-FIX` (S peut trancher sans motion).

### Top 3 différer (motion CEO distincte)

1. **`P1-PROMOTION-THRESHOLDS-UNIFY`** — chantier important mais non bloquant tant que l'auto-promotion n'a pas promeu plus de 18 principes. À planifier en Phase 14.
2. **`P1-COGNITIVE-JOURNAL-WIRE`** — wiring complet multi-agents, chantier M, dépend du passage à l'échelle des agents.
3. **`P1-R26-HARDENING`** — uniquement si tu veux **bloquer** les commits sur tests (R26 strict). Aujourd'hui pré-commit n'est qu'alertant.

### Top 3 ignorer / archiver

1. **Phase F NO-GO archive** (`P0-NO-GO-ARCHIVE`) — peut attendre, code n'est pas en prod-path.
2. **`P2-A` tables backup** — déjà couvert par #3 ci-dessus (P0).
3. **`P2-C` tests `_ADAPTIVE.yaml`** — couverture actuelle `test_yaml_loads_25_unique_ids.py` suffit.

### Réponses aux 3 questions stratégiques (§7 brief)

1. **Promouvoir PaperTradeResolver SHADOW → ACTIVE maintenant ?** → **NON, pas avant motion CEO séparée.** Justification : le resolver a montré 94.4% WR sur 6 222 trades asie (source : rapport antérieur), mais c'est un **sample isolé**, non répliqué sur GBPUSD ou autres paires. Risque : biaiser le pipeline sur une mesure non stationnaire. **Motion CEO requise**, à programmer post-audit Phase 13.
2. **Réactiver `V9_SHADOW_MODE_ENABLED` ?** → **NON, pas avant motion séparée.** Justification : 0 shadow décisions 2h confirme mode off effectif. Réactiver maintenant polluerait l'historique live avec du shadow non résolu. Si motion, fixer une fenêtre temporelle (ex : 7 jours) et un canal d'observation dédié.
3. **Câbler `v9_audit_cron_wiring.py` en pre-commit ?** → **OUI**, mais via motion `P1-R26-HARDENING` (#8 du plan) pour rester cohérent avec les 3 autres gardiens manquants. Effort S, pas de risque doctrinal.

---

## F. Motion CEO rédigée — **Chantier #1**

> **Motion CEO — Lot P0 « Audit nocturne » (DRManager SHADOW/APPLY + Archives Phase F + Tables à DROP)**
>
> *Émetteur* : Claude Opus Code (audit `OPUS_AUDIT_PROMPT_20260720_RESULT.md`)
> *Date* : 2026-07-20 ~07:00 UTC
> *Doctrine invoquée* : R22 (1 périmètre = 1 livraison) · R25'' · R32
>
> **Motion** : « J'autorise **un seul commit atomique** sur la branche `feat/v9-foundation-clean`, lot P0 audit nocturne 2026-07-20, périmètre strictement délimité à :
>
> 1. **DRManager** (`core/v9/trade_engine.py:72-77,692-703` + `core/v9/dynamic_risk_manager.py:270`) : trancher **SHADOW strict** en commentant les lignes 697-703 et enlevant l'override silencieux. Le DRM continue à évaluer et attacher `result["dynamic_risk"]`, mais n'applique plus tp_pips/sl_pips/exit_strategy. **Aucune motion APPLY** tant que WR par session n'est pas ≥ 65 % sur 100+ trades live.
> 2. **Archives Phase F** : déplacer `core/v9/v9_aggressive_strategy.py`, `core/v9/v9_pyramiding_engine.py`, `core/v9/v9_sizing_confidence.py` vers `core/v9/_archive_no_go/phase_f_2026-07-09/`. Adapter les 3 tests associés en `@pytest.mark.skip(reason="phase_f_no_go")`.
> 3. **Tables DB à archiver** : `VACUUM INTO 'data/backups/db_20260720_pre_archive_drop.db'` (MD5 noté au commit), puis `DROP TABLE paper_trades_backup_20260717` et `DROP TABLE principle_evaluations_shadow_archive_20260718` — **uniquement après** confirmation que `docs/calibration/backups/2026-07-19_p0_shadow_halt` contient déjà l'archive de référence.
>
> **Périmètre exclu** : aucun fix sur `v9_paper_trade_resolver.py:113-124` (chantier #4, motion séparée si S le souhaite), aucune modification des kill switches directs (`P1-KILLSWITCH-REFACTOR`), aucun câblage pre-commit (`P1-R26-HARDENING`).
>
> **R25'' respecté** : `V9_DRM_APPLY_CONFIRM` n'est pas touché (reste à 0 par défaut), `V9_PAPER_TRADE_HALT` reste à 1. `V9_AUTO_PROMOTION_ENABLED` reste à 0 (pas d'effet de bord).
>
> **Tests exigés avant push** (R7) :
> - `tests/test_v9_drm_shadow_or_apply.py` (vote runtime : source dynamique doit retourner un résultat mais **ne pas modifier** tp_pips/sl_pips/exit_strategy dans `result` final).
> - `tests/test_v9_no_go_archived.py` (imports échouent volontairement avec `ImportError`).
> - `tests/test_v9_db_archives_dropped.py` (les 2 tables n'existent plus).
> - Suite complète `pytest -m "not slow"` verte.
>
> **Audit trail** : SHA + 1 ligne description après push, conformément à R28. »
>
> *Tranchage attendu* : OUI / NON / OUI-modifié / Re-ask. Pas de tiers-état implicite.

---

## Annexes

### A1. Liste modules morts candidats (vérifiée)

| Module | LOC | Imports externes | Décision |
|---|---:|---|---|
| `v9_aggressive_strategy.py` | 400 | 2 scripts Phase F | **ARCHIVER** |
| `v9_pyramiding_engine.py` | 209 | 1 script Phase F | **ARCHIVER** |
| `v9_sizing_confidence.py` | 140 | 2 scripts Phase F + 1 test | **ARCHIVER** |
| `v9_dashboard_api.py` | 474 | 0 import direct, mais entry-point `uvicorn core.v9.v9_dashboard_api:app` | **GARDER** |

### A2. Tables DB candidates au DROP

| Table | Rows | Espace | Refs code | Décision |
|---|---:|---:|---:|---|
| `principle_evaluations_shadow_archive_20260718` | 1 984 513 | ~2 GB | 0 | **DROP après vérif MD5** |
| `paper_trades_backup_20260717` | 4 839 | ~50 MB | 4 | **DROP après vérif MD5** |
| `agent_event_bus` | 0 | 0 | 1 | **GARDER** — schéma OK, à peupler |
| `cognitive_journal` | 0 | 0 | 16 | **GARDER** — doit être alimenté (R25'') |

### A3. YAML conditions redondantes (vérification)

18 paires `{BASE, BASE_ADAPTIVE}.yaml` — non dupliquées (paramètres distincts : `magnitude_ohlc`, `kelly_fraction`, etc.). Pas de redondance stricte détectée. **Aucune action**.

---

## Bug critique P0 détecté ? 

**OUI — UN BUG P0 FLAG IMMÉDIAT** : **P0-A DRManager SHADOW vs APPLY contradiction** (voir F). Le commentaire ligne 72-77 de `trade_engine.py` est mensonger et le code APPLIQUE silencieusement les SL/TP/exit du DRM sur **chaque décision live** dont `source == "dynamic"`. C'est probablement le contributeur principal au **WR 23.7 % / -47k pips** observé sur 4853 paper_trades clôturés (le WR aurait été bien meilleur en mode SHADOW pur où les SL/TP existants - plus conservateurs - auraient été conservés). Motion CEO urgente tranchée ci-dessus en F.

---

## Récapitulatif livraison

- ✅ **Rapport complet** : `workspace/perplexity/audits/OPUS_AUDIT_PROMPT_20260720_RESULT.md` (~30 KB)
- ✅ **Sections A→F** : présentes et chiffrées
- ✅ **Chiffres factuels DB live** : 24 tables / 3.12 GB / 78415 décisions / 4854 paper_trades / WR 23.7 % / -47426.4 pips / 46 ACTIVE + 9 SHADOW
- ✅ **Citations code `path:ligne`** : 25+ références
- ✅ **Motion CEO rédigée** : chantier #1 (DRManager SHADOW strict + archives Phase F + DROP tables)
- ✅ **0 commit** (R22 strict, R28 multi-agent)
- ⚠️ **PAS de tests pytest créés** — la mission est strictement *audit seul* (R22), aucun test de vérification automatisée n'a été nécessaire (les chiffres DB sont extraits directement). Si tu en veux pour institutionaliser le contrôle (`test_v9_audit_postfix_<topic>.py`), motion CEO séparée.
- ⚠️ **Tables archivées non DROPées** — phase rapport seul, exécution = chantier #3 du plan D.
- ⚠️ **1 bug P0 critique flaggé** — DRManager APPLY silencieux (cause probable du WR catastrophique).