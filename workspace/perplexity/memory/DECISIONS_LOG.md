# DECISIONS_LOG — journal daté des décisions structurantes

Journal chronologique. Chaque entrée reprend une décision déjà actée côté code/doctrine
(voir `docs/STATE.md` §« Décisions actées » et les checkpoints référencés) — ce journal
n'invente pas de nouvelles décisions, il les indexe pour une reprise rapide côté
continuité multi-provider.

## Format d'entrée
```
### AAAA-MM-JJ — Titre
- Décision :
- Motivation :
- Impact / portée :
- Référence :
```

## Historique

### 2026-07-20 — Motion CEO #3 : DynamicRiskManager APPLY officiel (conditionnel R30)
- **Décision** : passage du `DynamicRiskManager` de SHADOW à **APPLY officiel**, conditionné
  à la validation des bornes SL[6,25]/TP[4,40] par R30 (hit_rate ≥ 60% sur ≥ 50 résolutions
  par profil de phase, sur données live 19-20/07). Si toutes les bornes sont validées :
  `V9_DYNAMIC_RISK_ENABLED=1` activé + commit. Si une borne échoue : rapport CEO + retour
  sans activation. Test `test_v9_drm_shadow_or_apply.py` doit être VERT.
  Livrable obligatoire : `docs/reports/DRM_APPLY_VALIDATION_20260720.md`.
- **Motivation** : le DRM a été validé en SHADOW (rejeu 2000 décisions, 0 crash, RR 0.53→1.21).
  L'audit edgefund (2026-07-19) confirme l'edge haussier réel. La calibration des phases
  (climax/trend/accumulation/distribution/retour) est désormais éprouvée sur données live.
  Motion CEO Søn 2026-07-20 09h36 CEST.
- **Observation critique (Opus, non commitée)** : le tree contient une modif non-commitée
  d'un autre acteur sur `core/v9/trade_engine.py` qui repasse le DRM de APPLY à SHADOW
  strict + défaut `_dynamic_risk_enabled()` ON→OFF. **À arbitrer par CEO avant activation.**
- **Impact / portée** : activation conditionnelle `V9_DYNAMIC_RISK_ENABLED=1`. Tests DRM
  indépendants du wrapper `trade_engine` (testent `DRM.evaluate()` directement).
  Doctrine R32 : décision CEO tracée.
- **Référence** : motion CEO Søn 2026-07-20 09h36 CEST ; commit `a9f6191` (session Opus) ;
  `docs/architecture/DYNAMIC_RISK_MANAGER.md` ; DOCTRINE R30/R32.

### 2026-07-20 — Motion CEO #4 : DROP batch catastrophe 17/07 + re-résolution sur prix réels
- **Décision** : suppression des 3 690 trades GBPUSD baissier 2026-07-17 (WR 1%, −56 089 pips)
  de la DB. Séquence obligatoire : (1) backup MD5 dans `backups/drop_batch_20260720/` avant
  tout DROP ; (2) DROP via `v9_db_hygiene.py` ou script dédié avec `--apply --backup` ;
  (3) correction idempotence `post_decision_hook` (commit `4bd310f`, 7 clôtures par snapshot) ;
  (4) re-résolution des décisions orphelines via `v9_resolve_decision_auto.py --apply` sur
  prix réels ; (5) livraison `docs/reports/DROP_BATCH_20260720.md` (métriques avant/après).
- **Motivation** : le batch du 17/07 (3 690 trades, WR 1%, −56 089 pips) est une catastrophe
  documentée liée au régime baissier GBPUSD non-stationnaire et à la boucle re-entry (déjà
  tuée : `c0aa416` + `v9_loop_breaker`). Garder ces trades contamine les métriques live,
  les calibrations de phase et les décisions futures. Le bug d'idempotence `post_decision_hook`
  (7 clôtures par snapshot) doit être corrigé AVANT la re-résolution pour éviter de reproduire
  le problème.
- **Contrainte absolue** : backup MD5 obligatoire (R8) avant tout DROP. Pas d'activation
  live sans confirmation CEO post-rapport.
- **Impact / portée** : suppression 3 690 lignes `paper_trades` + `decisions` associées.
  Métriques live nettoyées. Re-résolution sur prix réels = décisions orphelines closes
  correctement. `V9_EXECUTION_ENABLED=0` inchangé.
- **Référence** : motion CEO Søn 2026-07-20 09h36 CEST ; commit `4bd310f` (bug idempotence) ;
  `scripts/v9_db_hygiene.py` ; `scripts/v9_resolve_decision_auto.py` ; DOCTRINE R8/R26.

### 2026-07-20 — Motion CEO 3 activations (OPUS Code) — P2 PM + P3 MRG vérifiés, CVD migré
- **Décision** : motion CEO Søn « 3 activations simultanées » (P2 Position Manager,
  P3 Market Regime Global, CVD tick-level). Kill switches déjà posés à 1 par Hermes
  (commit `5b4a782`). Périmètre Opus Code = **vérifier câblage + smoke/rejeu + migration DB**.
- **Baseline** : `pytest tests/ -q` = **2355 passed / 2 failed / 3 skipped / 4 xfailed /
  2 xpassed** (12m04). Les 2 fails : (a) `test_cvd_enabled_default_off` — régression
  DIRECTE de l'activation CVD=1 dans le fichier déployé (le test lisait le fichier réel) ;
  (b) `test_all_crons_wrapped_passes` — mojibake cp1252/UTF-8 dans la capture stdout du
  subprocess (fragilité d'environnement Windows, **pré-existante**, hors périmètre R22).

- **Chantier A — Position Manager (P2)** : câblage confirmé `trade_engine.close_open_trades()`
  (~L943-959) lit `position_manager_enabled()` ; fallback R6 = nested try/except → un échec
  PM conserve le pips ExitSimulator (aucun crash). Smoke : `paper_trade_run --dry-run` OK
  (16 trades ouverts, 0 crash). Smoke fonctionnel direct (env live chargé) : PM active
  break-even (armé +30 %), partial close (locké 2.25 pips), time/stagnation-exit — les 3
  comportements déclenchent, `is_win=1`, pips managé 4.55. **12 tests PM verts**.
- **Chantier B — Market Regime Global (P3)** : injection `global_regime` dans
  `DynamicRiskManager.evaluate()` confirmée (modulateur TP interne, L224-228). Régime détecté
  live = **risk_on, tp_modulation=1.10** (TP élargi). Rejeu **100 contextes réels** :
  `contextes=100/100 | crashes=0 | modulés(ON)=100/100 | neutre(None)=100/100`
  → modulateur appliqué ON, **rétro-compatible** quand `global_regime=None`. **18 tests MRG verts**.
- **Chantier C — CVD tick-level MT4** :
  - C1 (fait) : backup MD5 `backups/pre_cvd_migration_20260720.md5`
    (`99fe58170a7420ad1863331f342b735a`). Migration `v9_migrate_cvd.py` exécutée sous WAL
    (writer live actif) → colonnes `cvd_delta`/`cvd_cumul` (INTEGER) ajoutées.
    `PRAGMA integrity_check` AVANT=ok / APRÈS=**ok (0 violation)**. **Idempotence** confirmée
    (re-run = « déjà à jour »). **12 tests CVD verts** (après fix du test default-off).
  - C3 (vérifié, manuel Søn) : EA `ea/V9_Sonde_M1.mq4` émet déjà `cvd_delta`/`cvd_cumul`
    (L127-130 : delta = tick_volume signé selon mouvement ask/bid ; L311 payload JSON).
    **Recompilation + redéploiement à faire manuellement dans le terminal MT4** (hors dépôt,
    non pilotable depuis Python).
  - C2 (**DIFFÉRÉ, décision Opus R6**) : redémarrage `capture_server` (port 31685, PID vivant)
    **NON exécuté**. Justification : marché **OUVERT** (lundi 20/07 09h33 CEST) → un restart
    perdrait des ticks live ; et `_effective_columns` du serveur (cache figé au boot) ne
    peuplera `cvd_*` que si l'EA est recompilé (C3, manuel, non fait). Restart maintenant =
    perte de ticks pour **zéro bénéfice**. **Séquence recommandée** : recompiler l'EA PUIS
    redémarrer `capture_server` **ensemble en fenêtre contrôlée** (idéalement marché fermé,
    via `scripts/stop_v9_capture_watchdog.bat` + `start_...`, ou kill PID → le
    `V9CaptureWatchdog` relance sur port down).
- **Correctif (R7)** : `tests/test_cvd_integration.py::test_cvd_enabled_default_off` isolé du
  fichier déployé (vide le cache `kill_switches._switches`) → teste le contrat CODE (défaut
  OFF), pas la config live. Test vert. Aucun autre test impacté par PM=1/MRG=1 (ces
  switches sont lus via `os.environ` direct, non chargé en pytest).
- **Observation (transparence, NON commitée)** : le tree contient une modif **non-commitée**
  de `core/v9/trade_engine.py` d'un autre acteur (background) qui **repasse le DRM de APPLY à
  SHADOW strict** + défaut `_dynamic_risk_enabled()` ON→OFF. Hors périmètre — non touchée,
  non commitée. Mes vérifs B testent `DRM.evaluate()` en direct → verdict indépendant de ce wrapper.
- **Impact / portée** : P2 + P3 vérifiés fonctionnels ; CVD DB migrée (additif, 0 violation).
  `V9_EXECUTION_ENABLED=0` inchangé. Aucune régression injustifiée (R7).
- **Référence** : motion CEO 2026-07-20 09h06 CEST ; commit `a9f6191` ; backup MD5.

### 2026-07-19 — Audit edgefund complet 8 axes (OPUS) — thèse renversée + watchdog live
- **Décision** : audit edgefund 8 axes exécuté sous motion CEO « oui go full audit 8 axes »
  (Søn). Livrables lecture seule + 1 module additif. Verdict **MARGINAL → GO conditionnel**.
- **Trouvaille structurante** : l'hypothèse du prompt (« résolveur optimiste = +94k pips de
  gap ») est **réfutée par les données**. Le résolveur mid-only est même **plus pessimiste**
  en OHLC (+3 666 pips). Le gap = **85 % boucle re-entry** (déjà tuée : `c0aa416` +
  `v9_loop_breaker`, 21 tests) + **non-stationnarité régime baissier** (mitigée long-only).
  L'edge **haussier est réel et transfère** backtest→live (WR 93 % ≈ 98,8 %).
- **Axe 2** : calibration Phase E **non contaminée** (fit sur `decisions`, pas les
  paper_trades boucle) → re-fit = no-op. Caveat réel = in-sample (exiger walk-forward OOS).
- **Axe 3** : monopole GBPUSD = **couverture capture**, pas bug routing. Les 6 paires sont
  routées et ≥ 175 entrées/sem → diversification infra-prête (capture continue requise).
- **Axe 6 (module livré)** : `core/v9/v9_live_watchdog.py` (R2 additif, kill switch
  `V9_LIVE_WATCHDOG_ENABLED` défaut **OFF**, lecture seule paper_trades). Seuils DD 24h
  < −200, WR<80 % (warn), WR<60 % (P0). 12 tests verts. Recommande, ne mute pas config (R30).
- **Axe 7 (sécurité)** : **4 tokens Telegram exposés** dans git (HEAD + historique) →
  reco **rotation BotFather** (P0, action CEO), **pas** de filter-repo. `.bak` tracké à
  désindexer.
- **Impact / portée** : 6 docs audit (`docs/audit/`, `docs/architecture/`,
  `docs/security/`) + `v9_live_watchdog.py` + tests. **0 régression** (baseline 2270 passed /
  10 failed préexistants / 3 skipped). Aucun kill switch activé par l'audit.
- **Référence** : `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` (synthèse + plan 5 actions).

### 2026-07-19 — Pré-réouverture §23h UTC (OPUS) — Watchdog opérationnel + câblage kill switches

- **Décision** : 3 chantiers R22 strict livrés avant réouverture forex 23h UTC. Motion CEO
  « Construis le watchdog maintenant » interprétée comme mandat d'activation runtime
  (`V9_LIVE_WATCHDOG_ENABLED=1`). Push délégué à Hermes (R28).
- **Chantier A (watchdog opérationnel)** : 5 défauts corrigés dans `core/v9/v9_live_watchdog.py` :
  (1) action P0 = `V9_PAPER_TRADE_HALT=1` + `V9_NO_BAISSIERE=1` au lieu de `V9_GBPUSD_LONG_ONLY=0`
  (qui ré-autorisait les shorts au lieu d'arrêter — faute de sécurité) ; (2) connexion read-only
  stricte `file:...?mode=ro` ; (3) win-rate segmenté `symbol='GBPUSD' AND direction='haussiere'`
  (jointure `decisions` via `snapshot_id`, `wr_recent`→`wr_long_only_gbpusd`) ; (4) `dd_24h_pips`
  →`net_pnl_24h_pips` (c'était un P&L net, pas un drawdown) ; (5) `db_error` distinct de `no_data`
  (DB muette = danger → alerte p0). Runner `scripts/v9_live_watchdog_run.py` (CLI, JSON, exit code
  0-4, log JSONL, Telegram optionnel, `--apply-recommendations` avec blacklist long-only). Wire
  `kill_switches.live_watchdog_enabled()` + `paper_trade_halt_enabled()`. 12 → 18 tests watchdog
  + 7 tests runner, verts.
- **Chantier B (kill switches runtime P0.4)** : `v9_loop_breaker.py` lit désormais
  `core.v9.kill_switches` (fallback `os.environ` seulement si import échoue) → le cron qui lance
  le supervisor sans wrapper honore enfin le `.env`. `kill_switches.loop_breaker_enabled()` ajouté.
  Entrée `V9_LIVE_WATCHDOG_ENABLED=1` + `V9_PAPER_TRADE_HALT=0` + 4 seuils dans `v9_kill_switches.env`
  (+ doc `.env.example`). 2 scripts `.bat` : `install_v9_live_watchdog_cron.bat` (V9_LiveWatchdogLoop,
  5 min), `install_v9_paper_trade_loop_wrapper.bat` (refit V9_PaperTradeLoop via
  `v9_load_kill_switches.py`, backup XML). `--dry-run` validés.
- **Chantier C (doc)** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md` créé, `STATE.md`
  maj phase, présente entrée.
- **Test-impact justifié (R7)** : 2 tests loop_breaker + 2 tests watchdog qui supposaient
  « env non posé = OFF » sont passés à un OFF explicite (`setenv "0"`) — conforme à la convention
  déjà en place (cf. `test_p3_wire_integration`) car le switch lit maintenant le `.env` (où il vaut
  1). Aucune fonction ni test supprimé.
- **Impact** : `v9_live_watchdog.py` (réécrit, additif) + `v9_loop_breaker.py` (helper `_ks_get`)
  + `kill_switches.py` (+4 fonctions) + `v9_kill_switches.env` (+ bloc watchdog) + `.env.example`
  + 1 runner + 2 fichiers tests + 2 `.bat`. Aucun `trade_engine.py` ni `config.py` touché. Aucun
  YAML modifié. Aucune migration DB.
- **Smoke test réel** : `python scripts/v9_live_watchdog_run.py --json` → `status=ok`,
  `wr_long_only_gbpusd=1.0` (50 trades), `net_pnl_24h_pips=-28.0`.
- **Référence** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`.
- **Action CEO seule** : rotation 4 tokens via @BotFather (`8656…`, `8790…`, `8932…`, `8948…`)
  avant 22h UTC.

### 2026-07-18 — Chantier C : CVD (Cumulative Volume Delta) tick-level MT4 — OFF
- **Décision** : ajout du **CVD tick-level** dans la couche forces, derrière kill switch
  `V9_CVD_ENABLED` (défaut **OFF**). L'EA `V9_Sonde_M1.mq4` émet `cvd_delta`/`cvd_cumul`
  (buy agressif si ask monte, sell si bid baisse, × tick volume MT4) ; `forces_reader`
  les parse ; `scene_builder` expose `cvd_cumul` + un flag `cvd_divergence` (prix↑/CVD↓).
- **Migration prod SÛRE (décision CEO — livraison standalone)** : colonnes `cvd_delta`/
  `cvd_cumul` ajoutées à `forces_snapshots` via `scripts/v9_migrate_cvd.py` **explicite,
  idempotent** (ADD COLUMN SQLite = O(1), sûr à 2.9 GB). `CREATE TABLE IF NOT EXISTS` ne
  touche pas la table prod ; `capture_server._get_effective_columns` intersecte
  `FORCES_COLUMNS` avec les colonnes réelles → **aucune régression avant migration**.
  Je ne mute PAS la prod : Hermes lance la migration + l'opérateur recompile/redéploie l'EA.
- **Contrainte MT4** (R : broker MT4 uniquement) : `iVolume`/`Volume` (tick volume proxy),
  `Ask`/`Bid`, `MarketInfo` — aucune syntaxe MQL5. Replay historique : CVD=0 (pas de tick).
- **Impact / portée** : additif (R2). db_schema (schéma + `migrate_cvd`), capture_server
  (intersect colonnes), forces_reader (passthrough), scene_builder (`_cvd_assessment` gated),
  kill_switches (`cvd_enabled`), EA (globals + OnTick + JSON). 12 tests nouveaux verts
  (`tests/test_cvd_integration.py`), 53 tests forces/scene/regime verts (0 régression).
- **Déploiement requis (Hermes/opérateur)** : (1) `python scripts/v9_migrate_cvd.py`,
  (2) redémarrer capture_server (recharge cache colonnes), (3) recompiler+redéployer l'EA,
  (4) `V9_CVD_ENABLED=1` quand validé Søn.
- **Référence** : `core/v9/db_schema.py`, `scripts/v9_migrate_cvd.py`,
  `core/v9/capture_server.py`, `core/v9/forces_reader.py`, `core/v9/scene_builder.py`,
  `core/v9/kill_switches.py::cvd_enabled`, `ea/V9_Sonde_M1.mq4`,
  `docs/architecture/CONTEXT_CONTRACT.md` (couches 1/2).

### 2026-07-18 — Chantier B : CVaR sizing institutionnel (plafond sur Kelly existant) — OFF
- **Décision** : ajout d'un **plafond CVaR 95%** sur le sizing, derrière kill switch
  `V9_KELLY_CVAR_ENABLED` (défaut **OFF**). Taille max = `CVAR_BUDGET_PIPS / cvar_95(returns
  récents de la paire)` ; si la perte-queue attendue dépasse le budget, `position_size`
  est réduit. Appliqué dans `trade_engine.process()` après le PortfolioRiskManager.
- **Conflit tranché (HITL, décision CEO Søn)** : le spec demandait `kelly_fractional()` +
  `cvar_95()` dans `risk_manager.py`. Or **Kelly existe déjà 2×** (`paper_risk_manager.
  _kelly_fraction` live + `v9_sizing_confidence.kelly_fraction_raw` backtest). Décision :
  **ne PAS dupliquer** — Chantier B ajoute uniquement la brique manquante (CVaR, 0 match
  préalable) et **réutilise** le sizing Kelly existant. Site d'intégration = `trade_engine`
  (choix CEO), en plafonnant le `position_size` déjà produit (pas de re-sizing).
- **Motivation** : borner la perte-queue par paire (expected shortfall) sans toucher au
  moteur Kelly. `cvar_95` = E[perte | perte ≥ VaR], valeur positive, 0.0 si pas de perte nette.
- **⚠️ Caveat** : le sizing Kelly live a un **verdict NO-GO walk-forward** (entrée du
  2026-07-18, variance 45pts). Activer `V9_KELLY_CVAR_ENABLED` en live = **override CEO
  explicite**. Par défaut OFF → `position_size` inchangé, zéro régression.
- **Impact / portée** : additif (R2). `cvar_95()` + `cvar_position_cap()` (pures, stdlib,
  R18) dans `risk_manager.py` ; `_recent_returns_pips()` + bloc plafond dans `trade_engine.py` ;
  4 constantes config (`CVAR_CONFIDENCE/BUDGET_PIPS/LOOKBACK_TRADES/MIN_TRADES`). 14 tests
  nouveaux verts (`tests/test_kelly_cvar.py`), 65 tests risk/trade_engine verts (0 régression).
- **Référence** : `core/v9/risk_manager.py`, `core/v9/trade_engine.py` (bloc 3a3),
  `core/v9/config.py`, `core/v9/kill_switches.py::kelly_cvar_enabled`,
  `config/v9_kill_switches.env`.

### 2026-07-18 — Chantier A : Regime gate primaire (exploitabilité) — SHADOW/OFF
- **Décision** : le régime de marché devient un **gate primaire** de la couche
  Exploitabilité, derrière kill switch `V9_REGIME_GATE_ENABLED` (défaut **OFF**).
  Quand ON : `evaluate_window()` lit `RegimeDetector.get_current_regime(symbol, tf)`
  et force `statut='refuse'` (`raison_refus=regime_volatile`) si le régime est
  `volatile` avec confiance > `REGIME_GATE_VOLATILE_CONF` (config, 0.7).
- **Motivation** : le régime était produit (`regime_snapshots`, 607k lignes) mais
  **jamais consommé** par le path d'exploitabilité (0 match `grep regime` dans
  `scene_builder`/`exploitability_evaluator`). Combler ce gap = filtrer les
  cassures en régime dangereux (REJET/volatile).
- **Choix structurels (décision CEO Søn, 2 questions HITL)** :
  1. **Lecture N-1** — `regime_detector.detect()` tourne APRÈS l'exploitabilité
     dans `orchestrator.run_chain` ; le gate lit le régime déjà persisté du
     snapshot précédent. **Ordre pipeline inchangé** (additif, zéro réordonnancement).
  2. **`get_current_regime()` étend `regime_detector`** (règle d'or : un seul
     module de vérité régime, pas de `regime_classifier.py`). Mapping 6→3 :
     CASSURE/EXTENSION→trending, PALIER/RETOUR_EQUILIBRE/NEUTRE→ranging, REJET→volatile.
     `confidence` = vote majoritaire sur les 8 devises.
- **Impact / portée** : additif (R2), **zéro régression** (kill switch OFF =
  passthrough total). `scene['regime_gate']` propagé in-memory (pas de migration
  DB). 15 tests nouveaux verts (`tests/test_regime_gate.py`). Activation = validation Søn.
- **Référence** : `core/v9/regime_detector.py` (get_current_regime), `kill_switches.py`
  (regime_gate_enabled), `exploitability_evaluator.py` (_apply_regime_gate),
  `scene_builder.py` (_regime_gate), `config.py` (REGIME_GATE_VOLATILE_CONF),
  `docs/architecture/CONTEXT_CONTRACT.md` (couches 2/5/6).

### 2026-07-18 — Saut quantique agressif : RECADRÉ + verdict NO-GO (instabilité walk-forward)
- **Décision** : mission « stratégie agressive + pyramiding + sizing confiance » livrée
  en **couche backtest lecture-seule** (motion CEO — recadrage), pas d'activation live.
  4 chantiers additifs (R2) : `v9_aggressive_strategy` (TP/SL dynamique + magnitude OHLC
  réelle + garde-fou short régime-dépendant), `v9_sizing_confidence` (Kelly fractionnel,
  réutilise config KELLY_*), `v9_pyramiding_engine` (adaptateur **réutilisant** le
  `PyramidingEngine` Phase 13.2, +paliers confiance +contradiction ×0.5),
  `scripts/v9_aggressive_paper_trade.py` + `v9_aggressive_optimize.py`.
- **Motivation** : le baseline du prompt (paper_trades WR 90.3 %/+27k/PF 4.96) était
  **faux** — réel WR 23.7 %/−47k, dominé par les shorts 1.2 % WR. `resolution_pips`
  capé (9.5) → magnitude reconstruite depuis l'OHLC forward (MFE/MAE, 8770 décisions).
- **Résultat mesuré (non extrapolé)** : TP agressif capte ~3× les pips (+154k vs +46k)
  mais ~4× le drawdown ; **variance WR inter-fold 45.3 pts >> seuil d'arrêt 15** → edge
  **période-spécifique** (un uptrend GBPUSD), non stationnaire. Grid search : **0/60
  configs stables**. **Verdict NO-GO live.**
- **Impact / portée** : additif, lecture seule, 0 régression (168 tests nouveaux verts).
  `trade_engine`/`config`/`order_executor`/YAML **non touchés**. Aucune promotion sans
  revue Søn (R28).
- **Référence** : `docs/reports/AGGRESSIVE_QUANTUM_LEAP_20260718.md`,
  `docs/reports/AGGRESSIVE_OPTIMIZE_20260718.md`, commits 057daeb→43ea9d5.

### 2026-07-18 — Niveau quantique : 5 leviers (PRM câblé, walk-forward, position manager, risk-on/off, morning brief)
- **Décision** : passage prototype → production via 5 leviers :
  - **P0 (survie)** : `PortfolioRiskManager` **câblé** dans `trade_engine.process()`
    après le gate `risk_manager`, avant l'ouverture. Bloque le trade (exposition
    nette/heat/circuit breaker/drawdown 24h) ou réduit le sizing (corrélation).
    Kill switch `V9_PORTFOLIO_RISK_ENABLED` (défaut **ON**). `_get_open_trades`
    enrichi du `symbol` (LEFT JOIN decisions) ; `_build_context` peuple `symbol`.
  - **P1 (confiance)** : `core/v9/walk_forward.py` + `scripts/v9_walk_forward.py`.
    5 fenêtres anchored, calibration in-sample → test out-of-sample. Rapport
    `docs/reports/walk_forward_20260718.md`. Verdict brut EDGE_REEL **mais**
    caveat de provenance obligatoire : résolution offline artefactuelle (WR 98 %
    ≠ live). À lire en valeur relative (stabilité seuil, dégradation inter-folds).
  - **P2 (performance)** : `core/v9/position_manager.py` — break-even 30 % TP,
    partial close 50 %, time-exit stagnation. Intégré dans `close_open_trades()`
    derrière kill switch `V9_POSITION_MANAGER_ENABLED` (défaut **OFF** — R2 : la
    résolution live reste `ExitSimulator` tant que non activé par le CEO).
  - **P3 (contexte)** : `core/v9/market_regime_global.py` — force USD + sentiment
    risk-on/off depuis `forces_snapshots`. **Injecté** dans le `DynamicRiskManager`
    (param optionnel `global_regime`, modulateur de TP). Kill switch
    `V9_MARKET_REGIME_GLOBAL_ENABLED` (défaut **OFF**). DRM rétro-compatible.
  - **P4 (transparence)** : `scripts/v9_daily_report.py` étendu (additif) — P&L
    veille, WR par dimension (symbole/direction/session), edge decay (24h/7j/vie),
    statut principes. Flags `--brief` / `--telegram`.
- **Motivation** : le PRM existait mais n'était pas câblé (risque portfolio non
  géré = survie). Les 4 autres leviers ajoutent confiance/performance/contexte/
  transparence sans casser l'existant (R2).
- **Impact / portée** : 5 nouveaux modules/scripts + 5 fichiers de tests
  (67 tests verts sur le périmètre). Kill switches : P0 ON, P2/P3 OFF (activation
  = décision CEO). Brief live révèle honnêtement l'edge decay SEVERE (24h -0.15
  vs 7j +0.22 pips/trade) et le baissier GBPUSD (WR 1 % sur 3709). 6 échecs
  pré-existants `test_v9_baissier_audit.py` (script `v9_strategy_v3.py`, hors
  périmètre) non introduits par cette session.
- **Référence** : session « niveau quantique 5 leviers » 2026-07-18.
