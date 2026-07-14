# ROADMAP dédiée Claude Code — sessions parallèles 2026-07-13

> Source de vérité pour qu'une session Claude Code **parallèle** scopée
> correctement, sans marcher sur les missions du CEO orchestrateur.
>
> Toute mission non listée ici = sous autorité CEO autopilot prioritaire.
> Toute mission HORS liste = NE PAS Y TOUCHER sans décision CEO.
>
> **Resync 2026-07-14 18:45 UTC** : Fable 5 hors service. Hermes a repris P3-CONSUME-EXTEND
> (mandat CEO 18:35). Boucle apprentissage activée (cron `V9_LearningLoop` Ready 18:43).
> ZCode continue SHADOW-EXPAND en parallèle. Périmètre ZCode strict = SHADOW-EXPAND uniquement.

## Contexte opérationnel

- **CEO orchestrateur principal** (cette session Hermes) tient les chantiers
  prioritaires du `mandat autopilot CEO 2026-07-13` (cf `logs/autopilot_status.md`
  et `DECISIONS_LOG.md` §2026-07-13).
- **Claude Code, en parallèle**, peut traiter les chantiers de cette roadmap
  **sous contrainte** :
  - `feat/v9-foundation-clean` est la branche de référence — toute modif
    doit partir d'elle et y revenir via PR (pas de merge direct sur master).
  - Tests verts avant commit (R26, R7).
  - 1 commit par chantier (R22).
  - Tests `--ignore=tests/test_telegram_notifier.py` (15 fails pré-existants,
    dette hors périmètre).
  - Backup MD5 R8 pour toute modif `core/v9/*` (cf `tools/doc_sync.py --update`
    + dossier `docs/calibration/backups/<date>_<chantier>/`).

## Périmètre STRICT alloué à Claude Code

### Chantiers déjà livrés (NE PAS REFAIRE)

- ❌ **P1 DYNAMIC signal** — commit `331382f`. Ne pas modifier
  `signals.exit_strategy_recommended`. Schéma DB fixe (3 colonnes ajoutées,
  `_ensure_column` migration).
- ❌ **P6 vol_regime** — commit `9592ce3`. Module pur `core/v9/vol_regime.py`
  (197 LOC). Calibration empirique 9970 fenêtres M15 GBPUSD. Branché dans
  `principle_engine._load_shared_context`. NE PAS modifier les seuils
  `(2.13, 3.20, 5.50, 11.34)` sans recalibration datée + DECISIONS_LOG.
- ❌ **Brief O4** — commit `bd1ca6f`. `DYNAMIC_BLACKLIST_SESSIONS = frozenset({"new_york","after"})`.
  `is_session_tradable(session) → bool`. `decision_logger._determine_action`
  defense-in-depth. `HITL_CONF_HIGH=80` (acté). NE PAS toucher.
- ❌ **P3 adaptive_thresholds (module seul)** — commit `5abfa2b`. Module pur
  `core/v9/adaptive_thresholds_at_runtime.py` (~200 LOC), calibration
  vol/news/TF. **PAS ENCORE câblé dans `principle_engine.evaluate_condition`**
  — c'est un chantier ouvert distinct, voir `P3-WIRE` ci-dessous.
- ❌ **P5 long-term memory** — commit `c84aba4`. `BEHAVIOR_HISTORY_LOOKBACK`
  10 → 50 dans `BehaviorAnalyzer`. NE PAS re-modifier sans nouvelle calibration.
- ❌ **Q1→Q5 (série saut quantique, session Claude Code séparée)** — trader-mini
  (`e1bb23f`), auto-calibrateur (`1b6cd69`), dashboard HITL (`58cf95d`),
  multi-paires (`5215c1d`), VPS doc (`d9d9345`), `order_executor.py` double
  verrou (`584d68f`, `V9_EXECUTION_ENABLED` toujours à 0). Voir
  `docs/checkpoints/CHECKPOINT_20260713_QUANTUM_LEAP.md`.
- ❌ **P4 Event Calendar dynamique** — commit `05f8232`, antérieur à cette
  roadmap. 7 events (NFP/ISM_PMI/CPI_US/FOMC_RATE/FOMC_MINUTES/GDP_US/
  RETAIL_SALES_US), `core/v9/news_context.py` module pur, déjà câblé dans
  `principle_engine._load_shared_context` (`news_phase`,
  `coalition_news_allow`). 7 tests `tests/test_news_context.py`. NE PAS
  REFAIRE (redécouvert par erreur listé "AUTORISÉ" ci-dessous jusqu'au
  2026-07-13, session Claude Code — voir DECISIONS_LOG §"2026-07-13 —
  Session Claude Code (mission MISSION_NEXT_20260713.md)").
- ❌ **TG-FIX** — commit `b447d71`, 2026-07-13. 15 échecs
  `tests/test_telegram_notifier.py` corrigés (cause réelle : `CONFIANCE_MIN`
  65→80 dans `scripts/v9_telegram_notifier.py`, jamais répercuté dans les
  tests). Runtime non touché. NE PAS REFAIRE.
- ❌ **P3-WIRE** — commit `1babf14`, 2026-07-13. `adaptive_thresholds_at_runtime.py`
  câblé dans `PrincipleEngine._load_shared_context` (pas `evaluate_condition`
  littéralement — les 3 constantes `COALITION_THRESHOLD`/`ANTAGONISM_THRESHOLD`
  vivent dans `scene_builder.py`, couche immuable, non touchée). Kill switch
  dédié `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED`, OFF par défaut, purement
  descriptif (aucun principe YAML ne consomme encore ces champs).
  Non-régression bit-à-bit vérifiée (`tests/test_p3_wire_integration.py`,
  8 tests). NE PAS REFAIRE. Activation du switch = décision Søn distincte,
  non posée par ce commit.
- ❌ **ORDER-BRIDGE** — commit `3e01eca`, 2026-07-14. `core/v9/order_queue_watcher.py`
  (neuf) + CLI `scripts/v9_order_queue_watcher.py`. Classe/purge (archivage
  seul, jamais suppression) les commandes JSON de `data/order_queue/`
  déposées par `order_executor.py`. Dry-run par défaut. 12 tests. NE PAS
  REFAIRE. Le volet EA MT4 (lecture réelle côté terminal) reste une action
  opérateur distincte, non couverte par ce commit.
- ❌ **P2 Shadow mode** — commit `0c0c334`, 2026-07-14. Architecture tranchée
  en session (feu vert Søn explicite couvrant la validation prévue par cette
  roadmap). `core/v9/shadow_evaluator.py` rejoue principes→signal→décision
  avec kill switches expérimentaux actifs (P3-WIRE), tagué `source_type=
  "shadow"`, jamais les couches perceptuelles (regime_detector/zone_detector
  — `INSERT OR REPLACE` keyé snapshot+currency, corruption si re-detect()
  sur un snapshot déjà live). `ShadowDecisionLogger` neutralise la collision
  `decision_id` déterministe par snapshot_id + le pré-check qualité de
  `_write_to_db` + le branchement HITL Telegram. Hook `orchestrator.
  run_chain()` non-bloquant, kill switch dédié `V9_SHADOW_MODE_ENABLED` OFF
  par défaut. Alerte de divergence isolée dans
  `scripts/v9_shadow_divergence_report.py` (seul point réseau, hors chemin
  cognitif — R18). 24 tests. Détail complet des 3 pièges de corruption
  identifiés : DECISIONS_LOG §2026-07-14. NE PAS REFAIRE.

### Chantiers AUTORISÉS pour Claude Code (sessions parallèles futures)

Liste priorisée selon le mandat `Série Autopilot CEO 2026-07-13` :

| # | Chantier | Priorité | Effort | Scope technique | Contraintes |
|---|----------|----------|--------|------------------|-------------|
| ~~**P3**~~ | ~~Adaptive Thresholds~~ | — | — | **Fait (partiel)** — module pur `5abfa2b` + wire-up context `1babf14` (P3-WIRE). Reste ouvert : consommation réelle dans `evaluate_condition`/YAML, voir §Proposés ci-dessous. | — |
| ~~**P4**~~ | ~~Event Calendar dynamique~~ | — | — | **Fait** — commit `05f8232`, antérieur à cette roadmap. Voir "déjà livrés" ci-dessus. | — |
| ~~**P5**~~ | ~~Long-term memory~~ | — | — | **Fait** — commit `c84aba4`. `BEHAVIOR_HISTORY_LOOKBACK` 10→50. Voir "déjà livrés" ci-dessus. | — |
| ~~**TG-FIX**~~ | ~~Fix 15 fails `test_telegram_notifier.py`~~ | — | — | **Fait** — commit `b447d71`, 2026-07-13. 1226→1241 verts. Voir "déjà livrés" ci-dessus. | — |
| ~~**P3-WIRE**~~ | ~~Câbler `adaptive_thresholds_at_runtime.py`~~ | — | — | **Fait** — commit `1babf14`, 2026-07-13. Kill switch dédié OFF par défaut. Voir "déjà livrés" ci-dessus. | — |
| ~~**ORDER-BRIDGE**~~ | ~~Lecteur EA du dépôt `data/order_queue/`~~ | — | — | **Fait** — commit `3e01eca`, 2026-07-14. Watcher + purge côté V9. Voir "déjà livrés" ci-dessus. | — |
| ~~**HITL-CFG**~~ | ~~Adapter test_decision_logger_hitl_branching au seuil 80~~ | — | — | **Fait** — vérifié 2026-07-13, 1226 tests verts. | — |
| ~~**P2**~~ | ~~Shadow mode parallèle~~ | — | — | **Fait** — commit `0c0c334`, 2026-07-14. Voir "déjà livrés" ci-dessus. | — |

Table entièrement clôturée au 2026-07-14 — voir §Chantiers proposés
ci-dessous pour la suite (aucun n'est encore autorisé, à trancher avec Søn).

### Chantiers PROPOSÉS pour prochaine session (aucun autorisé — à trancher avec Søn)

**Resync 2026-07-14 18:45 UTC** : Fable 5 hors service (pas de crédit, info Søn).
P3-CONSUME-EXTEND **repris par Hermes** (mandat CEO 18:35 « fait ce qu'il faut »).
Boucle apprentissage **activée** par Hermes (cron `V9_LearningLoop` installé Ready 18:43 UTC,
2 propositions PENDING générées — `signal:haussiere:weight_offset` score=73.52,
`signal:baissiere:weight_offset` score=27.91). NE PAS marcher sur le périmètre Hermes
(P3-CONSUME-EXTEND).

| # | Chantier | Priorité proposée | Effort estimé | Scope technique | Pourquoi maintenant | Qui |
|---|----------|--------------------|----------------|------------------|----------------------|-----|
| ~~**P3-CONSUME**~~ | ~~Consommation réelle adaptive thresholds~~ | HAUTE | 6-10h | **REPRIS PAR HERMES** — voir `workspace/perplexity/COORDINATION_NOTE.md` §2026-07-14 18:45 UTC. ADAPTIVE_VOL_GATE livré (`5e1b9df`), reste à étendre le pattern aux 26 autres principes. | Complète un chantier déjà à 80% livré ; peut être évalué en shadow mode (P2 livré) avant toute activation live. | **Hermes** |
| **SHADOW-EXPAND** | Étendre `SHADOW_ENV_OVERRIDES` | MOY | 2-4h | `core/v9/shadow_evaluator.py` n'évalue que P3-WIRE aujourd'hui. Ajouter trader_mini_weigher / auto_calibrator (déjà gated OFF, Briefs Q1/Q2) comme candidats shadow. | P2 livré et testé — coût marginal faible pour élargir la couverture. | **ZCode (en cours, parallèle)** |
| **P1-RESOLVE** | Patch `v9_resolve_decision_auto.py` pour lire `signals.exit_strategy_recommended` | MOY | ~4h | Active P1 effectivement pour la résolution WIN/LOSS (aujourd'hui `DEFAULT_EXIT_STRATEGY="DYNAMIC"` codé en dur dans le resolver, ignore la recommandation par signal). | Nécessite une décision Søn sur la stratégie de résolution — ne PAS ouvrir sans confirmation explicite. | — |
| **TELEGRAM-RUNTIME** | Fix token Telegram réel | BASSE (opérationnel, pas code) | non estimé | `config/telegram.json` contient un placeholder sanitisé depuis plusieurs sessions — bloque en pratique `v9_shadow_divergence_report.py --send` et toute alerte HITL/low-confidence. | Blocage récurrent documenté depuis 2026-07-07, jamais résolu ; nécessite le vrai token de Søn, pas un chantier code. | Søn (token) |

### Chantiers EXPLICITEMENT HORS PÉRIMETRE (fondateur/doctrine, aucune session)

- ❌ **Phase 10/12/13** (fédération d'agents / exécution réelle / apprentissage
  WIN/LOSS ≥ 50) — gelées par doctrine Règles 19, fondateur, 30.
- ❌ **Modif core/v9/{auto_calibrator,decision_logger}** — couvertes par des
  P1/P6/O4 et HITL_CONF_HIGH=80 récents, R8 backup posé. Modifs additionnelles
  en parallèle risqueraient des conflits merge.
- ❌ **Modif des constantes de doctrine** (DYNAMIC_BLACKLIST_SESSIONS,
  DYNAMIC_PROFILES, HITL_CONF_HIGH, CONFIANCE_MIN, etc.) — ces seuils ont été
  tranchés par CEO/Søn, toute modification doit passer par DECISIONS_LOG.
- ❌ **`core/v9/order_executor.py` / `V9_EXECUTION_ENABLED`** — Phase 12,
  activation exclusivement Søn (R12 fondateur, R28).

## Procédure de coordination

1. **Claim d'une mission** : avant de coder, ajouter un `- [ ]` dans la
   file d'attente `logs/autopilot_status.md` (section "Sessions parallèles
   Claude Code") avec timestamp et votre identifiant.
2. **Documentation immédiate** : créer l'entrée DECISIONS_LOG datée à la
   fin de chaque mission (cf templates section §6.2 DECISIONS_LOG.md).
3. **Backup R8** : pour toute modif d'un `core/v9/*`, poser le backup MD5 AVANT
   (commande : `mkdir -p docs/calibration/backups/<YYYY-MM-DD>_<chantier>` +
   `git show HEAD:core/v9/<file>.py > <backup>/<file>.py.bak` + `md5sum`).
4. **Tests obligatoires** : pytest du fichier de test du module touché doit
   être 100% vert avant commit. La suite globale (`pytest tests/ -q
   --ignore=tests/test_telegram_notifier.py`) doit passer 0 fail.
5. **Commit atomique** : 1 commit par mission, R22 + R26 respectées.
6. **Notification CEO** : PR ouverte vers `feat/v9-foundation-clean` avec
   mention `@hermes`. CEO valide et merge (R28 = Hermes opérateur git unique — assouplie 14/07 : délégation possible sur motion CEO explicite).
7. **Tests cumulés** : CEO met à jour `docs/STATE.md` (table phases + résumé
   exécutif + section dédiée) ET `workspace/perplexity/BOARD.md` + `ACTIVE_TASKS.md`
   + `exchange.md` + `DECISIONS_LOG.md`.

## Référence pivot

- `docs/STATE.md` : source de vérité vivante — voir section « SÉRIE AUTOPILOT
  CEO 2026-07-13 » pour l'état actuel.
- `workspace/perplexity/BOARD.md` : 1-min pour la phase en cours.
- `workspace/perplexity/ACTIVE_TASKS.md` : qui fait quoi, priorité, blocage.
- `logs/autopilot_status.md` : journal de session CEO autopilot (inclut
  cette roadmap en référence).
- `workspace/perplexity/memory/DECISIONS_LOG.md` : journal daté de toutes
  les décisions structurantes (inclut Brief O4 résolu 13/07 01:50 UTC).
- `R28` = Hermes opérateur git unique — assouplie 2026-07-14 : push autorisé
  depuis une session uniquement sur instruction directe et explicite de Søn
  (sinon handoff Hermes). Jamais d'auto-push sans cette décision.

## Sécurité / secrets

- Token Telegram runtime : **placeholder sanitisé** dans
  `config/telegram.json` (`8932306765:***`). Vrai token en env var d'un daemon
  externe (R6 : pas de simulation d'envoi Telegram réussi).
- Patron de clés GitHub : dans Windows Credential Manager (`git credential-manager get`
  → username `gestionzen57-alt`, token `ghp_Lx...` — non visible, c'est OK).
- Pas de LLM dans la boucle critique (R18). Pas d'auto-push (R28).
