# PROMPT OPUS CODE — Audit complet PowerFlow V9 (post-fix nocturne)

> **Destinataire** : Claude Opus Code (CLI ou API Sonnet 4.5)
> **Émetteur** : Søn CEO + Hermes (orchestration)
> **Date d'envoi** : 2026-07-20 ~06:15 UTC
> **Doctrine** : R6 additif/défensif · R18 zéro LLM · R22 1 périmètre = 1 livraison · R25' kill switch par feature · R26 tests verts avant commit · R28 Hermes push
> **Mode** : Code + analyse, **PAS de commit** (R22 strict, R28 respecte le flow multi-agent). Tu retournes un **rapport structuré** + éventuellement du code, je commit après review.

---

## 0. Mission en une phrase

**Produire un audit structurel complet de PowerFlow V9** post-fix nocturne (5 commits pushés cette nuit), identifier les **gaps restants par ordre d'impact**, et **proposer un plan d'action concret en chantiers numérotés** que le CEO tranchera motion par motion.

---

## 1. Contexte hérité — l'état réel au 2026-07-20 ~06:15 UTC

### 1.1 Branche / commits récents

```
9054725 fix(v9): mark test_send_appele_pour_nouvelle_decision xfail
0faf2e9 fix(v9): câblage 9 Scheduled Tasks + audit script
6bd23d7 fix(v9): scripts audit baissier --json flag + tests slow verts
b9e8ba5 fix(v9): drift YAML↔DB PRICE_LAG_AT_NODE_BIRTH
6a8cf1b feat(v9): wire shadow PaperTradeResolver + audit/recalibrage CLI
5c09a60 feat(v9): PaperTradeResolver paramétrique + drift detector
334ccf6 fix(v9): P0 migration robustness (review 01:01Z)
1072999 feat(v9): réconciliation kill switches (P0 halt + shadow unique)
```

### 1.2 DB live (lecture seule via `file:data/v9_forces.db?mode=ro`)

- 25 tables utilisateur, ~44 index utilisateur
- DB size ~2.84 GB
- 134k forces_snapshots, 76k decisions, 1.07M principle_evaluations, 612k regime_snapshots
- 4853 paper_trades clôturés, 1150 wins, **WR 23.7%**, pips -47k (catastrophe)
- principles : **46 ACTIVE / 9 SHADOW** (alignés YAML↔DB)
- paper_trades ouverts actuellement : 15 (en cours)

### 1.3 Marché live (snapshot 06:11 UTC)

- Capture server OK, port 31685 listening
- Pipeline OK : 2418 signals 24h, 2405 decisions 24h, 36 paper_trades 24h (21 clôturés, 10 wins, WR 47.6% — sample non significatif)
- Régime actuel : NEUTRE
- Décisions live 2h : 504 aucune_action, 53 surveiller, 33 preparer_entree
- Aucune décision `open_long` GBPUSD depuis la réouverture
- Pas de shadow résiduel depuis 23:00 UTC hier (V9_SHADOW_MODE_ENABLED=0 effectif)

### 1.4 Fixes appliqués cette nuit (par subagent + Hermes)

| Commit | Effet |
|---|---|
| 1072999 | P0 shadow↔live coexistence (index UNIQUE source_type) + câblage V9_PAPER_TRADE_HALT |
| 334ccf6 | Migration robustness (review) : dédup intra-source_type, savepoint, drop-after-create |
| 5c09a60 | PaperTradeResolver paramétrique (tf×vol×session×conf) + drift detector |
| 6a8cf1b | Wire shadow PaperTradeResolver + audit/recalibrage CLI |
| b9e8ba5 | Drift YAML↔DB PRICE_LAG_AT_NODE_BIRTH (46/9 alignés) |
| 6bd23d7 | Scripts audit baissier `--json` flag + 5 tests slow verts |
| 0faf2e9 | **Câblage 9 Scheduled Tasks** (auto-calibrator SKIP 12j) + audit script |
| 9054725 | xfail test telegram obsolète post-refactor |

### 1.5 Gaps doctrinaux identifiés par subagent audit (deleg_b01b2781)

23 contradictions factuelles doc↔code↔DB + 7 doctrine wiring gaps. Les principaux non encore résolus :

1. **DRManager contre R32** — subagent affirme contradiction mais vérification montre que `trade_engine.py:72-74` documente explicitement SHADOW, donc **FALSE POSITIVE** probable. À re-confirmer.
2. **4 fichiers lisent `os.environ.get` direct** : `core/v9/auto_calibrator.py`, `v9_dynamic_tp_sl.py`, `trade_engine.py`, `kill_switches.py` (fallback). Wrapper cron couvre, mais code reste fragile.
3. **`v9_auto_promotion.py` vs `auto_calibrator.py`** — double moteur avec seuils divergents (20/60 vs 70%/100/1.0).
4. **`_load_shared_context` import absent** dans `core/v9/v9_paper_trade_resolver.py:119` —吞 silencieuse de l'exception.
5. **202 décisions shadow résiduelles 2h** post-flip `V9_SHADOW_MODE_ENABLED=0` — orchestrateur a continué à produire.
6. **R26/R28 hooks absents** : pas de pre-push gate ni rebase forcé.
7. **Décisions 7j non résolues** : 12 306 (mais `V9_ResolveLoop` re-câblé cette nuit, prochain run OK).
8. **TP=8/SL=15 RR=0.53** — exit simulator inversé structurellement perdant.
9. **4750 paper_trades en 1 jour** (17/07) — batch replay vs continu, suspect.

### 1.6 Fichiers que tu dois connaître intimement

**Core pipeline** (lecture obligatoire) :
- `core/v9/db_schema.py` (FORCES_COLUMNS, helpers migration)
- `core/v9/signal_db.py` + `core/v9/principle_db.py` + `core/v9/decision_db.py` (coexistence live/shadow post-P0)
- `core/v9/principle_engine.py` (write_evaluations_to_db, lifecycle)
- `core/v9/signal_generator.py` (compute_signal, _write_to_db)
- `core/v9/trade_engine.py` (process, _paper_trade_halt_enabled check)
- `core/v9/shadow_evaluator.py` (run_shadow_pass, isolation)
- `core/v9/kill_switches.py` (loader central)
- `core/v9/auto_calibrator.py` (run_calibration_cycle, propose-only)
- `core/v9/v9_paper_trade_resolver.py` (paramétrique, livré SHADOW)
- `core/v9/v9_resolution_drift.py` (détecteur divergence)
- `core/v9/orchestrator.py` (run_chain, source_type flow)

**Scripts CLI** :
- `scripts/v9_paper_trade_run.py` (résolution fixe 5.5/-17.5 historique)
- `scripts/v9_close_paper_trades.py` (copie decisions→paper_trades)
- `scripts/v9_resolve_decision_auto.py` (resolveur décisions)
- `scripts/v9_auto_calibrator.py` (wrapper cron)
- `scripts/v9_load_kill_switches.py` (loader env)
- `scripts/v9_sync_state.py` (regen AGENT/STATE/CACHE_BOARD)
- `scripts/v9_audit_cron_wiring.py` (audit câblage cron — livré cette nuit)

**Cron (Windows Scheduled Tasks — 11 tâches V9_*)** : toutes wrappées avec `v9_load_kill_switches.py`.

---

## 2. Périmètre EXACT de cette livraison (1 chantier, R22 strict)

### CHANTIER UNIQUE — Audit structurel post-fix + Plan d'action

**Sortie attendue** (rapport structuré Markdown, pas de code exécutable requis) :

#### Section A — Inventaire technique actuel

1. **Code coverage** : combien de modules `core/v9/*.py` totalisent combien de lignes, dépendances internes, modules morts (non importés).
2. **Tables DB** : 25 tables — lesquelles servent encore, lesquelles sont des backups/archive (ex `paper_trades_backup_20260717`, `principle_evaluations_shadow_archive_20260718`) → candidat DROP ?
3. **Fichiers YAML** : 55 principes — review des conditions_yaml, identification des principes à conditions similaires (dédup candidate).

#### Section B — Doctrine wiring audit (chaque règle)

Pour chaque règle doctrine (R1-R32, ou celles listées dans `docs/DOCTRINE.md`), vérifier :
- **R18** (zéro LLM dans core) : `grep -r "openai\|anthropic\|claude" core/v9/` → 0 attendu.
- **R25'** (kill switch par feature) : tous les modules core qui peuvent muter des seuils ont-ils un `os.environ.get(V9_xxx)` ou un wrapper `kill_switches.get()` ?
- **R26** (tests verts avant commit) : `v9_guards.py` enforce-t-il vraiment ? Les hooks Git existent ?
- **R28** (multi-agent commit+push) : qui commit quand, qui push, audit trail ?
- **R30** (boucle fermée) : `V9_AutoCalibrator` + `V9_ResolveLoop` + `V9_PaperTradeLoop` forment-ils une vraie boucle ? Y a-t-il un feedback loop mesurable ?
- **R32** (DRManager SHADOW/APPLY) : confirmer lecture `core/v9/trade_engine.py:662-704` — SHADOW only ou override runtime ?

#### Section C — Gaps structurels (P0/P1/P2)

Classe chaque gap en P0 (bloquant), P1 (important), P2 (qualité). Inclus ceux identifiés par subagent audit + tous nouveaux.

**Format par gap** :
- **P?** — titre court
- **Symptôme** : observé vs attendu
- **Cause racine** : citation code `path:ligne`
- **Fix proposé** : 1-3 phrases
- **Motion CEO requise** : oui/non, lequel
- **Effort estimé** : S/M/L/XL

#### Section D — Plan d'action numéroté

Liste ordonnée de chantiers avec :
- Titre + chantier ID (ex: P0-SHADOW-RESIDUAL, P1-OS-ENV-MIGRATE)
- Dépendances entre chantiers
- Motion CEO explicite à obtenir pour chacun (R25'')
- Estimation de tests à ajouter/modifier
- Risque doctrinal (R1-R32 violations)

#### Section E — Recommandations CEO

- Top 3 chantiers à activer **immédiatement** (P0 uniquement)
- Top 3 chantiers à différer (motion CEO distincte)
- Top 3 chantiers à ignorer / archiver
- **Motion CEO rédigée** prête-à-coller pour le chantier #1

---

## 3. Contraintes strictes

- **R6** : try/except défensif sur tout appel DB/fichier/env (les nouveaux scripts que tu écris).
- **R18** : zéro LLM dans `core/v9/*.py` (audit seulement — pas de modif core).
- **R22** : 1 périmètre = 1 livraison (audit seul, pas de fix).
- **R28** : tu **ne commit PAS**. Tu peux créer des fichiers temporaires dans `tmp/` ou `scratchpad/` mais pas dans le repo final.
- **Pas de modif `core/v9/*`** sauf si tu trouves un bug critique P0 (et tu le signales en section C, motion CEO requise).
- **Lecture seule** sur `data/v9_forces.db` (utilise `file:data/v9_forces.db?mode=ro`).
- **Style** : KISS, DRY, FR/EN mix OK en commentaires.
- **Tests** : tu peux ajouter des tests dans `tests/test_v9_audit_postfix_<topic>.py` UNIQUEMENT pour les vérifications automatisables (ex: « grep no commit dans la branche »).

---

## 4. Format de réponse attendu

```markdown
# Audit Opus Code V9 — 2026-07-20

## A. Inventaire technique
... (chiffres + listes)

## B. Doctrine wiring audit
### R18 (zéro LLM core)
- Verdict : OK / VIOLATION
- Preuve : `grep ...`
### R25' (kill switch par feature)
...

## C. Gaps structurels
### P0 — titre
- Symptôme : ...
- Cause : ...
- Fix : ...
### P1 — ...
### P2 — ...

## D. Plan d'action numéroté
1. Chantier #1 (dépendances, motion, tests, effort)
2. Chantier #2
...

## E. Recommandations CEO
- Top 3 immédiat
- Top 3 différé
- Top 3 ignorer

## F. Motion CEO rédigée (chantier #1)
```
Motion CEO : « ... »
```

## Annexes
- A1. Liste modules morts candidats
- A2. Tables DB candidates au DROP
- A3. YAML conditions redondantes
```

Réponse **français**, structurée, factuelle, sans blabla.

---

## 5. Output final attendu

- **1 rapport Markdown** dans `workspace/perplexity/audits/OPUS_AUDIT_20260720.md` (≤ 30 KB)
- **0 commit** (je m'en occupe)
- **Motion CEO rédigée** pour le chantier P0 #1
- Si tu trouves un **bug critique P0** dans ton audit (data corruption, sécurité, doctrine violation grave) → **flag immédiat** en début de rapport + motion CEO d'urgence.

---

## 6. Contexte skill Hermes utiles

- `powerflow-v9-coherence-audit` : patterns d'audit cross-référencement
- `powerflow-v9-quant-fund` : état chiffré cible
- `powerflow-v9-paper-trade-ops` : bilan paper-trade
- `powerflow-v9-orchestrator` : patterns de délégation multi-agent
- `powerflow-v9-ceo-prompt-generator` (celui-ci) : patterns de prompts Opus

---

## 7. Question stratégique pour toi, Opus

**À la fin de ton audit, recommande :**
1. **Faut-il promouvoir le PaperTradeResolver SHADOW→ACTIVE** (commit `5c09a60`) maintenant ? Le calibrateur a montré asie WR 94.4% sur 6 222 trades.
2. **Faut-il réactiver V9_SHADOW_MODE_ENABLED** pour observer le shadow parallèle ?
3. **Faut-il câbler l'audit `v9_audit_cron_wiring.py` en pre-commit** pour empêcher le décâblage futur ?

Sois direct dans tes recommandations — le CEO tranchera sur motion explicite.

---

*Prompt rédigé 2026-07-20 ~06:15 UTC par Hermes (profile powerflow) sur motion CEO « il y a claude opus de disponible, demande audit complet puis tu avises ».*
