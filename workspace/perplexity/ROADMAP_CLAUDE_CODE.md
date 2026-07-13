# ROADMAP dédiée Claude Code — sessions parallèles 2026-07-13

> Source de vérité pour qu'une session Claude Code **parallèle** scopée
> correctement, sans marcher sur les missions du CEO orchestrateur.
>
> Toute mission non listée ici = sous autorité CEO autopilot prioritaire.
> Toute mission HORS liste = NE PAS Y TOUCHER sans décision CEO.

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

### Chantiers AUTORISÉS pour Claude Code (sessions parallèles futures)

Liste priorisée selon le mandat `Série Autopilot CEO 2026-07-13` :

| # | Chantier | Priorité | Effort | Scope technique | Contraintes |
|---|----------|----------|--------|------------------|-------------|
| **P3** | Adaptive Thresholds | HAUTE | 8-12h | Seuils `COALITION/ANTAGONISM/CONFIANCE_MIN` modulés par `f(vol_regime, news_proximity)`. Nouveau module `core/v9/adaptive_thresholds_at_runtime.py`. Wire-up dans `principle_engine.evaluate_condition`. | R8 backup `principle_engine.py`+config. Tables DB inchangées. Tests ≥ 8. |
| **P4** | Event Calendar dynamique | HAUTE | 6-8h | Enrichir `data/economic_calendar.json` (events datés + impact 1-3). `news_context.py` étendu pour fenêtres NFP/CPI. `principle_engine._load_shared_context` lit `news_phase ≠ "HIGH"`. | Module pur (pas d'écriture DB). R8 backup `news_context.py`. Tests ≥ 6. |
| **P5** | Long-term memory | MOY | 4-6h | `behavior_analyzer._load_behaviors_history(limit=500)` au lieu de 50. Plutôt lecture pure, peu de risque. | Pas de backup MD5 nécessaire (lecture seule DB). Tests ≥ 4. |
| **TG-FIX** | Fix 15 fails `test_telegram_notifier.py` | MOY | 2-4h | Refactoring post-bug 2026-07-11. Comprendre les 15 fails, fixer localement. NE PAS toucher au runtime Telegram (placeholder sanitisé OK). | Pas de R8 backup (script pas dans core/v9). Tests ≥ 18 (15 fails + 3 régression). |
| **P3-WIRE** | Câbler `adaptive_thresholds_at_runtime.py` dans `principle_engine.evaluate_condition` | MOY | 4-6h | Le module de calcul existe (`5abfa2b`) mais n'est branché nulle part — seuils COALITION/ANTAGONISM/CONFIANCE_MIN toujours statiques en prod. Wire-up + kill switch dédié (ne pas réutiliser un switch existant). | R8 backup `principle_engine.py`. Tests ≥ 8 (dont non-régression : switch OFF = comportement strictement identique à avant). |
| **ORDER-BRIDGE** | Lecteur EA du dépôt `data/order_queue/` | BASSE | non estimé | `core/v9/order_executor.py` (`584d68f`) dépose des JSON dans `data/order_queue/` mais rien ne les lit côté MT4. Nécessite une modif EA MT4 = action opérateur (hors autopilot) — ce chantier ne peut livrer QUE le code de lecture/consommation côté V9 (watcher + purge), pas le déploiement EA. | Ne pas activer `V9_EXECUTION_ENABLED`. Tests ≥ 5. |
| ~~**HITL-CFG**~~ | ~~Adapter test_decision_logger_hitl_branching au seuil 80~~ | — | — | **Fait** — vérifié 2026-07-13, 1226 tests verts. | — |

### Chantiers EXPLICITEMENT HORS PÉRIMETRE (CEO autopilot only)

- ❌ **P2 Shadow mode parallèle** — infrastructurel lourd, dépend des choix
  CEO + Søn. Pas à toucher en parallèle. CEO autopilot l'ouvrira si Søn le veut.
- ❌ **PATCH `v9_resolve_decision_auto.py`** pour activer P1 effective (lire
  `signals.exit_strategy_recommended`) — décision CEO + Søn requise d'abord
  sur la stratégie de résolution WIN/LOSS.
- ❌ **Phase 10/12/13** (fédération d'agents / exécution réelle / apprentissage
  WIN/LOSS ≥ 50) — gelées par doctrine Règles 19, fondateur, 30.
- ❌ **Modif core/v9/{auto_calibrator,decision_logger}** — couvertes par des
  P1/P6/O4 et HITL_CONF_HIGH=80 récents, R8 backup posé. Modifs additionnelles
  en parallèle risqueraient des conflits merge.
- ❌ **Modif des constantes de doctrine** (DYNAMIC_BLACKLIST_SESSIONS,
  DYNAMIC_PROFILES, HITL_CONF_HIGH, CONFIANCE_MIN, etc.) — ces seuils ont été
  tranchés par CEO/Søn, toute modification doit passer par DECISIONS_LOG.

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
   mention `@hermes`. CEO valide et merge (R28 = Hermes opérateur git unique).
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
- `R28` = Hermes opérateur git unique, ne jamais auto-push depuis cette
  session sans décision Søn explicite.

## Sécurité / secrets

- Token Telegram runtime : **placeholder sanitisé** dans
  `config/telegram.json` (`8932306765:***`). Vrai token en env var d'un daemon
  externe (R6 : pas de simulation d'envoi Telegram réussi).
- Patron de clés GitHub : dans Windows Credential Manager (`git credential-manager get`
  → username `gestionzen57-alt`, token `ghp_Lx...` — non visible, c'est OK).
- Pas de LLM dans la boucle critique (R18). Pas d'auto-push (R28).
