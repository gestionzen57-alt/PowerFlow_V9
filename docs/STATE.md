# STATE — PowerFlow V9

> **Source de vérité vivante.** La section AUTO ci-dessous est générée
> automatiquement par `scripts/v9_sync_state.py` depuis les sources réelles
> (DB, pytest, git, disque). Ne pas éditer manuellement.
>
> Pour l'historique complet des phases, voir [`JOURNAL_PHASES.md`](JOURNAL_PHASES.md).

## État courant — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-18 23:24 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `a4acfac chore(v9): refresh data/strategy_pole (auto-calibrator post-commit)` | `git log --oneline -1` |
| Tests collectés | 2283 | `pytest --collect-only` |
| Tables DB | 25 | `sqlite3 data/v9_forces.db` |
| Index DB | 58 | `sqlite3` |
| Taille DB | 2.61 GB | `du -h` |
| Décisions | 75877 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 134017 | DB |
| Scènes | 76009 | DB |
| Principle evals | 924308 | DB |
| Régime snapshots | 607304 | DB |
| Paper trades | 4817 | DB |
| Principle scores | 226 | DB |
| Principes YAML | 55 (45 ACTIVE + 10 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 9 | `ls mcp_servers/*.py` |
| Crons Ready | 14 | `Get-ScheduledTask (PowerShell)` |
| V9_TRADER_MINI_ENABLED | 1 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 1 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 1 | env |
| V9_LEARNING_OFFSET_ENABLED | 1 | env |
| V9_DYNAMIC_RISK_ENABLED | 1 | env |
| V9_BLACKLIST_SYMBOLS | USDCAD | env |
| V9_GBPUSD_LONG_ONLY | 1 | env (activé 2026-07-18 §6.10) |
| V9_BEAR_PERCEPTION_ENABLED | 1 | env (shadow) |
| V9_CONSTITUTIVE_CURRENCY_FILTER | 0 (défaut OFF, R22) | env (shadow) |
| V9_CYCLE_MEMORY_ENABLED | 0 | env (Phase E, R33) |
| V9_META_STRATEGY_OPTIMIZER_ENABLED | 1 | env (Phase E) |
| V9_BAYESIAN_PREDICTOR_ENABLED | 1 | env (Phase E) |
| V9_PREDICTIVE_ENGINE_ENABLED | 1 | env (Phase E) |
| V9_LEARN_LOOP_ENABLED | 1 | env (Phase E) |

<!-- /AUTO:STATE -->

## Phase actuelle


**Session Opus 2026-07-19 — Pré-réouverture 23h UTC (watchdog opérationnel + câblage kill switches) :**

Trois chantiers R22 strict (chantier A watchdog + chantier B kill switches + chantier C doc) :
- **A** : 5 corrections `v9_live_watchdog.py` (action P0 = `V9_PAPER_TRADE_HALT=1` au lieu de
  désactiver long-only, read-only URI `mode=ro`, segmentation GBPUSD long-only via jointure
  `decisions`, renommage `net_pnl_24h_pips`, distinction `db_error` vs `no_data` → alerte p0)
  + runner `scripts/v9_live_watchdog_run.py` (CLI + JSON + exit code 0-4 + log JSONL + Telegram
  optionnel + `--apply-recommendations` avec blacklist long-only) + wire
  `kill_switches.live_watchdog_enabled()` / `paper_trade_halt_enabled()`. 12 → 18 tests + 7 runner.
- **B** : `v9_loop_breaker.py` corrigé pour lire `core.v9.kill_switches` (P0.4 résolu, `os.environ`
  seulement en fallback) + entrée `V9_LIVE_WATCHDOG_ENABLED=1` dans `v9_kill_switches.env`
  (motion CEO « Construis le watchdog » interprétée comme activation runtime) + 2 scripts `.bat`
  d'installation des tâches `V9_LiveWatchdogLoop` (5 min) et refit `V9_PaperTradeLoop` via wrapper
  (`--dry-run` validés).
- **C** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md` (checklist HITL) + maj `STATE.md`
  + entrée `DECISIONS_LOG.md`.
- **Hors périmètre (R22)** : 4 tokens Telegram (rotation = action CEO @BotFather), axes 1/2/3/5/7
  audit (déjà livrés). Aucun `trade_engine.py` ni `config.py` touché.
- **Tests** : baseline préservée (10 fails préexistants inchangés) + 25 nouveaux/adaptés watchdog.
- **Smoke test réel** : `python scripts/v9_live_watchdog_run.py --json` → `status=ok`,
  WR GBPUSD long-only = 100 % (50 trades), P&L net 24h = −28 pips.

**Session Claude Code 2026-07-18 — REGIME_GATE + CVaR + CVD (3 chantiers, tous kill switch OFF) :**

Trois chantiers additifs (R2) livrés, tous derrière kill switch **défaut OFF** (zéro
régression, activation = validation Søn). 41 tests nouveaux verts.

- **Chantier A — Regime gate primaire** (`V9_REGIME_GATE_ENABLED=0`) : le régime
  (trending/ranging/volatile) filtre l'exploitabilité. `RegimeDetector.get_current_regime()`
  (mapping 6→3, confiance = cohérence 8 devises) ; `exploitability_evaluator` force
  `statut=refuse` si volatile & conf>0.7 ; `scene['regime_gate']` propagé. Lecture N-1
  (ordre pipeline inchangé — décision CEO). 15 tests.
- **Chantier B — CVaR sizing** (`V9_KELLY_CVAR_ENABLED=0`) : Kelly **non dupliqué**
  (existait déjà 2×) — ajout `cvar_95()` + plafond `cvar_position_cap()` sur le sizing
  Kelly existant, câblé dans `trade_engine` après le PRM. ⚠️ caveat NO-GO walk-forward :
  activation live = override CEO. 14 tests.
- **Chantier C — CVD tick-level MT4** (`V9_CVD_ENABLED=0`) : EA `V9_Sonde_M1.mq4` émet
  cvd_delta/cvd_cumul ; `forces_reader` parse ; `scene_builder` expose cvd_cumul +
  cvd_divergence. Migration DB **standalone idempotente** (`scripts/v9_migrate_cvd.py`) —
  prod intacte tant que non lancée ; `capture_server` intersecte les colonnes réelles.
  Déploiement requis : migration + redémarrage capture_server + recompilation EA. 12 tests.

Détail : `DECISIONS_LOG.md` §2026-07-18 (Chantiers A/B/C), `CONTEXT_CONTRACT.md` (couches 1/2/5/6).

---

**Session Hermes 2026-07-19 (~12h15–13h00 UTC) — Push pré-réouverture §23h UTC + bilan 48h :**

3 commits R22 strict poussés sur `origin/feat/v9-foundation-clean` (`dcd2fed..289fa93`),
HEAD local/remote alignés sur `289fa93` :

- `2026256` — **Chantier A** : `v9_live_watchdog.py` opérationnel (P0 halt switch +
  read-only `mode=ro` + segmentation GBPUSD long-only via jointure `decisions` +
  `net_pnl_24h_pips` renommé + distinction `db_error` vs `no_data`).
- `4137b41` — **Chantier B** : `scripts/v9_live_watchdog_run.py` (CLI `--json` /
  `--alert-telegram` / `--apply-recommendations` avec blacklist long-only / log JSONL)
  + 2 `.bat` d'install (`install_v9_live_watchdog_cron.bat` 5min SYSTEM,
  `install_v9_paper_trade_loop_wrapper.bat` refit via `v9_load_kill_switches.py`)
  + `V9_LIVE_WATCHDOG_ENABLED=1` dans `config/v9_kill_switches.env`.
- `289fa93` — **Chantier C** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`
  + maj `STATE.md` (cette entrée) + `DECISIONS_LOG.md`.

**Tests pré-push** : 58 verts (5 fichiers : `test_v9_live_watchdog`,
`test_v9_live_watchdog_run`, `test_v9_loop_breaker`, `test_kill_switch_integration`,
`test_v9_load_kill_switches`). 0 fail.

**État opérationnel 19/07 13h UTC** :

| Composant | État | Action requise |
|---|---|---|
| Push origin | ✅ `dcd2fed..289fa93` | aucune |
| Cron `V9_LiveWatchdogLoop` | ✅ installé, prochaine exec 12:58 | aucune |
| Cron `V9_PaperTradeLoop` | ⚠️ KO depuis 12:50 (code -2147024894 = FILE_NOT_FOUND) | **refit 23h UTC en CMD admin** |
| `capture_server` (port 31685) | ✅ vivant depuis 18/07 23h45 fix daemon-mort | surveillance watchdog 5min |
| Tokens BotFather (4) | ⚠️ exposés dans `config/telegram.json` (8656… 8790… 8932… 8948…) | rotation CEO avant 22h |
| Notification Telegram CEO | ⏸ BLOQUÉE par runtime (POST `api.telegram.org` via `terminal` refusé) | opt-in explicite Søn |

**Verdict semaine 20/07 → 26/07** : système **mieux protégé qu'avant 48h** (5 goulots
corrigés : loop breaker, TP/SL dynamiques R30 5-20 pips, Platt+Beta re-fité sans
catastrophe 17/07, no_baissiere global, PRICE_LAG kill). Edge haussier structurel
confirmé (+8850 pips WR 98.83% sur 1108 trades) **uniquement si** : (1) refit
`V9_PaperTradeLoop` 23h UTC, (2) capture_server tient 5 jours (risque Windows
Update / reboot sans AutoStart). Risques résiduels honnêtes : Phase E = DRAFT
validé motion CEO (pas livraison), CVaR sizing NO-GO walk-forward (OFF par défaut),
CVD tick-level attend migration DB + redéploiement EA MT4.

Référence : `workspace/perplexity/memory/DECISIONS_LOG.md`
§2026-07-19 « Push pré-réouverture §23h UTC + bilan 48h », checklist
`docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`.

---

**Session Hermes 2026-07-18 (~21h30 UTC, motion §17h45) — Notifier Telegram dynamique + prompt Opus audit edgefund :**

Refonte du `system prompt` du notifier (état réel lu live au lieu d'un
prompt figé juillet 2026) + routing intention data → slash commande
(`_route_data_intent()`, 15 règles) + support `reply_markup` (claviers
inline Telegram). 12/12 tests verts (`test_telegram_notifier_interactive`,
zéro réseau, `urlopen` monkeypatché). **Aucun** fichier `core/v9/*` modifié,
aucun YAML touché, aucun DB migré. Audit anti-régression : 2 hits
`execution_enabled` lecture seule sur l'affichage statut — pas
d'activation. Commit `66bca85`. Détail : `DECISIONS_LOG.md` §2026-07-18
« Notifier Telegram dynamique + prompt Opus audit edgefund ».

**Session Hermes 2026-07-18 (~21h35 UTC) — Refresh `data/strategy_pole/` :**
commit chore `a4acfac` (métadonnées `last_updated`/`generated_at` issues
de l'auto-calibrateur, +14/-14 lignes sur 3 JSON, aucune logique).

**Prompt Opus livré** : `workspace/perplexity/PROMPT_OPUS_AUDIT_EDGEFUND_20260718.md`
(15 sections). Statut **« À valider motion CEO avant lancement »** — ne
s'auto-exécute pas.

---

**Session CEO 2026-07-18 (10h57–11h30 UTC) — Correctifs Telegram : notifier 400 + spam « décision peu fiable » :**

Deux bugs Telegram corrigés et vérifiés (tests verts) :

- **Notificateur (`scripts/v9_telegram_notifier.py`)** :
  - *Cause* : `send_telegram` envoyait `parse_mode: "HTML"` → Telegram
    rejetait (HTTP 400) les messages de commandes contenant du Markdown
    (`**...**`). `/help` etc. ne étaient jamais livrés ; seul le fallback
    « Commande inconnue » (sans `**`) passait.
  - *Fix* : envoi en **texte brut** (strip des `**`, plus de `parse_mode`).
    Log du corps des erreurs HTTP pour diagnostic.
  - *LLM réactivé* : Ollama Cloud renvoyait 405 → LLM désactivé sur texte
    libre. Réactivé via **OpenRouter** (`tencent/hy3:free`) avec mémoire de
    conversation. `_read_llm_config` corrigé (priorité explicite
    OPENROUTER_API_KEY > V9_LLM_API_KEY > LLM_API_KEY > OLLAMA_API_KEY —
    l'ancien ordre attrapait la mauvaise clé 57-caractères et donnait 401).
  - *Validation* : `--send-help` livré (avant 400) ; `--send-text` → réponse
    LLM 3.1s livrée ; daemon `--watch` relancé, traite `/last` `/paper`
    `/principles` en live.
- **DecisionLogger (`core/v9/decision_logger.py`) — spam « décision peu fiable »** :
  - *Cause* : rate-limiter process-global (mémoire) mourait à chaque
    `run_chain()` (DecisionLogger recréé) → 1 notif / snapshot au lieu de
    1 / 5 min → spam GBPUSD M15 conf=80.
  - *Fix* : rate-limit **persistant sur disque**
    (`logs/.hitl_telegram_ratelimit.json`), horloge `time.monotonic()`
    intra-process + `time.time()` (epoch) + `pid` inter-process. 1 notif /
    5 min / (symbol×TF), compteur agrégé « +N similaires supprimées ».
  - *Validation* : simulation inter-process → send → block → block →
    send+suppressed=2 après 300s → block. Tests
    `test_decision_logger_hitl_branching.py` (15) + `test_decision_logger.py`
    (16) = 31 verts.
- **Déploiement** : `DecisionLogger` tourne dans le serveur live (port 31685,
  VPS) — le fix n'est actif qu'après git pull VPS + restart du pipeline.

Détail : `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-18
« Correctifs Telegram : notifier 400 + rate-limit persistant decision_logger ».

---

**Session CEO 2026-07-18 (10h30 UTC) — Motion « pivot Telegram + anti-spam » :**

Pivot du bot Telegram Hipyhop → Ipspx_bot (token 8790798269:***) pour
séparer chat IA bidirectionnel et arrêt du spam auto-calibrateur.

- **Anti-spam auto-calibrateur** : `_notify_telegram_best_effort` ne notifie
  QUE si changement réel (`n_session_proposals > 0` OU threshold proposé OU
  promotions/démotions). Cycle « 0 ajustements » = silencieux.
- **Anti-spam auto-optimizer** : idem, silencieux si
  `n_optimizations_applied == 0`.
- **Pivot `config/telegram.json`** : Hipyhop_bot → Ipspx_bot, chat_id=1401055223.
- **Token Ipspx dans `.env`** (gitignoré) sous `TELEGRAM_BOT_TOKEN_IPSPX`.
- **Tests** : `tests/test_auto_calibrator.py` + `tests/test_auto_optimizer.py`
  → 26/26 verts en 2.21s.
- **À faire VPS** : remplacer `<your_ipspx_bot_token_here>` dans `.env` par
  vrai token + restart `start_telegram_notifier.bat`.

Détail complet : `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-18
« Pivot Telegram Hipyhop → Ipspx + anti-spam auto-calibrateur/optimizer ».

---

**Session CEO 2026-07-17 (18h30 UTC) — Motion « orchestre et optimise au max » :**

Quatre motions CEO successives (« go débloquer tout », « continue optimiser au max »,
« orchestre et délègue Claude Code Opus », « mets tous les documents à jour ») ont
transformé V9 en 2h :

- **4752 paper_trades clôturés** (vs 59 avant), **WR 90.3%, +27239 pips cumulés**.
- **Pôle Stratégie data-driven** livré : `StrategyCatalogue` (11 segments),
  `StrategyTuner` (grid search TP/SL), `StrategySelector` (hiérarchie
  metric_history → grid_search → default), `compute_meta_metrics`
  (WR/PF/max_drawdown/sharpe_like).
- **Top 1 stratégie validée** : PRICE_LAG_AT_NODE_BIRTH × new_york = WR 97%,
  PF 17.15, +7.31 pips/trade sur n=3293 trades.
- **MCP server `strategy_pole_server.py`** : **11 tools** (7 + 4 délégués Opus).
- **Skills catalogue Hermes** : 3 skills (strategy-pole, paper-trade-ops,
  à enrichir en quant-fund/coherence-audit/performance-tuning).
- **Crons actifs** : V9_PaperTradeLoop (10min), V9_StrategyPoleRecompute (60min).
- **Performance x10** : 540ms/snapshot → 57ms/snapshot (caches mémoire,
  index DB couvrant, singleton instances, calibration async thread).
- **4 commits pushés** sur `feat/v9-foundation-clean` : `2159619`,
  `3206a78`, `7a8ec8d`, `57d79de`.

Doctrine respectée : R6 défensif, R18 pas de LLM dans le cœur cognitif,
R23 principes YAML respectés, Phase 12 exécution réelle toujours interdite.

**Session Opus 2026-07-17 (fin) — Validation DynamicRiskManager + look-ahead disculpé** :
Rejeu SHADOW du DynamicRiskManager sur **2000 décisions résolues** : **100 % en
`source=dynamic`, 0 fallback, 0 crash** → moteur robuste. Le garde-fou **climax**
isole les pires trades (WR 20 %). Mais l'activation APPLY **restructure l'économie**
(RR 0.53→1.21, TP ×2) → **NON promu cette session** : la vérité terrain (WR) est
trompeuse. **Look-ahead ExitSimulator testé et écarté** : fenêtre résolveur propre
(`timestamp > start` strict), et re-résolution intrabar (800 décisions, high/low,
pessimiste) donne **89.2 % vs 89.8 % mid-only (Δ+0.5 pt), 0 barre ambiguë**. Le WR
haut = géométrie TP 8/SL 15 (RR 0.53), pas un bug → cohérent avec le batch frais
≈ breakeven. **Chantier « fix look-ahead » réorienté** vers un pilotage
espérance/RR. Reprise lundi : capture + heartbeat OK vérifiés ; **MT4 = seul vrai
risque** (aucun script ne le relance, GUI session). Rapport :
`docs/reports/dynamic_risk_validation_20260717.md`. Lecture seule (aucun `core/v9/*`
modifié).

**Session Opus 2026-07-17 (soir) — Biais « distribution » diagnostiqué + dashboard** :
Le « 85 % distribution » est **diagnostiqué** (outil `scripts/v9_dashboard_risk.py`,
lecture seule) : (1) `behavior_analyzer` étiquette `culmination` toute qualification
persistant ≥3 barres à intensité non décroissante (= **persistance**, 85.4 % des
comportements) ; (2) `phase_classifier` #4 mappe `culmination`→`distribution` (choix
testé). **Découverte : le 85 % est NON-STATIONNAIRE** — artefact de l'échantillon
*résolu* (ancien ~GBPUSD, `point_de_rupture` rare) ; en **récent**, `point_de_rupture`
≈ 59 % → **CASSURE** pré-empte (distribution 15.9 %, cassure 58.9 %). **Ne bloque pas
l'activation lundi.** Nouveau point de vigilance APPLY = part de **CASSURE** (profil
agressif SL18/TP22). Correctif éventuel = **amont** `behavior_analyzer`, cycle dédié.
Dashboard : espérance/paire + RR statique réalisé 0.53 vs dynamique planifié 1.63.
74 tests verts. Aucun `core/v9/*` modifié.

**Session Opus 2026-07-17 — Risk Manager Dynamique (cycles + phases), SHADOW** :
Le système lisait le marché en haute définition mais tradait en basse définition
(TP=8/SL=15 statiques). Introduction d'une gestion du risque adaptative à la
**phase du cycle** (accumulation/cassure/trend/distribution/climax/retour),
modulée par la coalition (HTF ×1.5 / LTF ×0.8) et gardée par la session.
Détection **code pur (R18)** à partir des signaux déjà produits (cinématique,
coalitions, confluences MTF, régime, phase comportementale). **Statut SHADOW** :
évalue et décrit (`result["dynamic_risk"]`), n'applique rien — activation APPLY
= décision CEO. Replay 2000 décisions : la phase **climax** isole les pires
trades (WR 20 %, −6.3 pips → garde-fou « aucune nouvelle position »), trend et
accumulation le meilleur pips moyen. Livrables : `market_cycle_detector.py`,
`phase_classifier.py`, `dynamic_risk_manager.py`, hook `trade_engine` (étape 4b),
**54 tests** (1503→1557, tous verts), `docs/architecture/DYNAMIC_RISK_MANAGER.md`,
DOCTRINE **R32**. Kill switch `V9_DYNAMIC_RISK_ENABLED`. Additif (R2), non
bloquant (R6).

**Session Opus 2026-07-17 (soir) — Audit de clôture semaine : fiabilité sim + 4 angles morts + durcissement crons** :
Audit stratège avant la fermeture du marché (21h UTC). **Fiabilité** : le WR `paper_trades`
(58, 48.3 %) n'est **pas fiable** (pips fixes +8/−15, résolution instantanée en batch — pas
de forward-test). Le vrai forward-sim est le résolveur `decisions` (ExitSimulator DYNAMIC,
chemin de prix 4h) : le cumulé 85.5 % est gonflé par l'historique ; le batch frais de 169
décisions récentes draine à **56.8 % WR / +0.1 pip** → **système ≈ breakeven sur données
fraîches**. **9 gaps de la semaine vérifiés vivants** (MTF boost 102 émis, session multiplier
actif, `tick_volume` capturé). **4 nouveaux angles morts corrigés** (tous additifs, `scripts/`) :
(1) heartbeat lisait `bar_time` (heure broker +3h) → âge −180 min → alerte DOWN ~3h30 en
retard → corrigé sur `timestamp` UTC ; (2) `apply_resolutions` avait un bloc live-update
`principle_scores` **code mort** (NameError avalé depuis 14/07) → corrigé ; (3) `V9_ResolveLoop`
tournait en **dry-run** (sans `--apply`) → boucle non fermée → `--apply` ajouté + drain de 169
décisions ; (4) **8/12 crons en `python` nu** → `0x80070002` → réécrits en `.venv` absolu +
`WorkingDirectory` + `-X utf8`. **Durcissement logoff** : 11 crons passés en `S4U` (tournent
session fermée, vérifiés result 0 dont réseau) ; `V9CaptureWatchdog` laissé Interactive (MT4).
**Risque résiduel** : `--autorestart` relance le capture_server Python headless mais **pas MT4**
(GUI, lié session) → MT4 doit tourner à la réouverture dimanche 22h UTC. `config.py` /
`order_executor.py` / `core/v9/*` non touchés. Détail : `DECISIONS_LOG.md §2026-07-17 (soir)`.

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