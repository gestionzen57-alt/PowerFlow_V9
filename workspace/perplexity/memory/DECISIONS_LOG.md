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

### 2026-07-20 19h00 UTC — Motion CEO #17+23+25 : câblage runtime + validation batch 7 TF
- **Motion #17 (câblage runtime)** : `core/v9/regime_detector.py` accepte
  `timeframe` au constructeur. Si fourni + TF dans `REGIME_TIMEFRAME_OVERRIDES`,
  les seuils sont lus depuis l'override (audit Opus Phase 2). Sans timeframe
  → legacy global (R2 additif strict). Config explicite prime toujours.
  Runtime safe : RECALIBRAGE NON ACTIF (M5/M15/M30/H1 commentés dans le
  dict — motion #18 ready-not-active, R25' strict validation 2 sem.).
- **Motion #23 (validation batch)** : `v9_regime_recalibration_validate.py
  --all-tf` boucle M1/M5/M15/M30/H1/H4/D1 sur 299 bars et affiche Δ NEUTRE_RATE.
  Résultat bilatéral GBPUSD (motion #23) :
    - M5 : NEUTRE 60.9% → 1.7% (Δ -59.2 pts)
    - H1 : NEUTRE 100% → 2.0% (Δ -98.0 pts) ← legacy le pire
  Hypothèse validée côté bilatéral. Reste à valider runtime vote majoritaire
  8 devises (câblage motion #17 prêt).
- **Motion #25 (validation câblage runtime)** : 5 snapshots GBPUSD M5
  testés avec `RegimeDetector()` vs `RegimeDetector(timeframe='M5')` vs
  `RegimeDetector(config={'seuil_palier':0.9, ...})`. Pas de divergence
  car M5 n'est PAS dans `REGIME_TIMEFRAME_OVERRIDES` (motion #18 ready-
  not-active). Runtime safe.
- **Vérification** : 468 tests verts, 0 régression, 0 XFAIL.
- **Référence** : commits `1b64ad0` (câblage runtime) + `5149bfb` (--all-tf).

### 2026-07-20 18h10 UTC — Motion CEO #18 : recalibrage motion #10 prêt, non-activé (R25')
- **Décision** : préserver l'activation runtime du recalibrage Opus Phase 2.
  Les seuils M1/M5/M15/M30/H1 = 0.9-1.0 PALIER, 2.0 CASSURE, N_MIN=2 sont
  documentés en commentaire sous `REGIME_TIMEFRAME_OVERRIDES`
  (`core/v9/config.py`). Pour activer runtime : décommenter les 6 lignes.
- **R25' strict** : activation live = validation 2 semaines paper-trade
  (motion CEO §5). Pas de validation runtime avant 2 semaines. Les seuils
  legacy (H1 n_min=2, H4 palier=0.7/n_min=2) restent en place — safe.
- **Référence** : commit `d1c82c4` « docs(v9): REGIME_TIMEFRAME_OVERRIDES
  motion #10 documentée (NON ACTIVE) ».
- **Prochaine étape** : motion CEO future pour validation 2 semaines.
  Pendant ce temps : NEUTRE_RATE_24H=83% continue d'alerter (watchdog
  WARN, cf commit `ca55efb`).

### 2026-07-20 18h00 UTC — Motion CEO #10+11+15 : recalibrage RegimeDetector per-TF
- **Motion #10 (audit Opus Phase 2)** : `workspace/perplexity/PROMPT_OPUS_REGIME_RECALIBRATION_20260720.md`
  (28 KB, lecture seule) confirme que `SEUIL_PALIER=0.5` global est
  statistiquement absurde (P50 |step| = 1.5-2.0 sur M1-H4). PALIER=0.5%
  observé en base, NEUTRE=91%. Cause : (P10)^3 probabilité jointe trop stricte
  avec N_MIN=3.
- **Motion #11 (préparation)** : `scripts/v9_migrate_resolver_columns.py`
  (NEW, 96 LOC, R2 additif) prépare l'ajout de colonnes
  `pips_simulated_resolver` + `exit_reason_resolver` à `paper_trades`.
  Dry-run validé, --apply en attente de coordination Opus pour ne pas
  bloquer le pipeline live pendant ALTER TABLE.
- **Motion #15 (livraison per-TF, R2 additif)** : `core/v9/config.py`
  ajoute `REGIME_SEUILS_BY_TF` (dict M1/M5/M15/M30/H1/H4/D1) + helper
  `get_regime_seuils_for_tf(timeframe)` avec override env
  (`REGIME_SEUIL_PALIER_M5=0.9` etc.). Seuils par TF (audit Opus) :
  - M1 : PALIER<1.0  CASSURE>1.5  N_MIN=2
  - M5-M30/H1 : PALIER<0.9  CASSURE>2.0  N_MIN=2
  - H4 : PALIER<0.7  CASSURE>1.5  N_MIN=1
  - D1 : PALIER<0.5  CASSURE>1.0  N_MIN=2  **DISABLED** (P50=0.02 → 72% faux PALIER)
- **Tests** : `tests/test_regime_seuils_by_tf.py` (NEW, 7 verts) — défaut
  par TF, override env, fallback legacy TF inconnu, lowercase normalization.
- **État runtime** : **PAS D'ACTIVATION LIVE** (R25' motion CEO #10 §5 :
  validation 2 semaines paper-trade requise avant promotion). Le détecteur
  `core/v9/regime_detector.py` lit encore `SEUIL_PALIER` legacy (ligne 127).
  Câblage runtime (motion CEO future) :
  ```python
  # Dans RegimeDetector.__init__, remplacer self.seuil_palier/... par :
  from core.v9.config import get_regime_seuils_for_tf
  self.seuil_palier, self.seuil_cassure, self.n_min, _, self.enabled = (
      get_regime_seuils_for_tf(timeframe)
  )
  ```
- **Vérification** : 467 tests verts, 0 régression, 0 XFAIL.
- **Référence** : commits `ccbd86d` (simulation fix) + `b8a0f2f` (per-TF dict).

### 2026-07-20 17h35 UTC — Motion CEO #9 : dedup 1001 paper_trades fantômes
- **Décision** : supprimer les 1001 paper_trades fantômes de la DB (tous WIN
  par construction du bug idempotence post_decision_hook). Conséquence :
  bilan comptable désormais honnête.
- **Incident** : commit `c47dc68` (2026-07-20 10h20) a fixé `_trade_already_open`
  pour qu'il compte TOUT trade du couple (snapshot_id, direction), ouvert
  OU fermé. Mais la DB contenait encore 1001 trades fantômes créés pendant
  la catastrophe 17/07 et la récidive 19-20/07.
- **Root cause** : `post_decision_hook` (TradeEngine fraîche par snapshot)
  + ancien `_trade_already_open` (filtre `closed_at IS NULL`) = un snapshot
  dont le trade était clôturé redevenait éligible → 14-17 trades par snapshot_id.
- **Impact avant/après** :
  - Avant : 1179 trades, WR 95.5%, pips_sum +8618 (gonflé de +8384 virtuels)
  - Après : 178 trades, WR 69.5%, pips_sum +233.8 (réel)
- **Fix R2 additif** : `scripts/v9_dedup_paper_trades.py` (285 LOC) :
  - `--dry-run` par défaut (sécurité)
  - `--archive-only` : copie fantômes vers `paper_trades_fantomes_archive.db`
  - `--apply` : MD5 backup obligatoire + archive + DELETE en transaction
  - `--skip-md5-check` : autorisé UNIQUEMENT si archive existe (DB live WAL)
- **Tests** : `tests/test_v9_dedup_paper_trades.py` (5 verts) — analyze,
  archive idempotent, apply remove only dupes, apply idempotent, no-op propre.
- **Vérification runtime** : 1179 → 178 trades, archive 1001 fantômes
  dans `backups/dedup_paper_trades_20260720/`. WR réel 69.5%.
- **Référence** : commit `ec53c35` « fix(v9): dedup paper_trades fantômes ».

### 2026-07-20 14h50 UTC — Motion CEO #6+7+8 : edge alert + ACTIVE resolver + audit Opus
- **3 livraisons CEO en série** (auto-promotion R25'' lecture-first) :
  1. **Motion #6** : `scripts/v9_edge_alert.py` (NEW, 322 LOC) + 8 tests verts +
     Scheduled Task `V9_EdgeAlert` 60min. Détecte 3 patterns : EDGE_BAISS_24H
     (WR<40%, n>=10, pips<-100), EDGE_HAUSSE_24H, WORST_PAIRS_24H. Alerte
     Telegram réelle envoyée 14h43 UTC : baissier 24h WR 30.8% / -480.9 pips.
  2. **Motion #7** : `scripts/v9_paper_trade_run.resolve_active()` +
     `_resolver_enabled()` (livré 78 LOC). Résout la dette xfail 5 tests
     « ACTIVE PaperTradeResolver ». Contrat : dict {is_win, pips, exit_reason,
     tp_used, sl_used}, fallback legacy si resolver raise (R6 défensif).
     Promotion ACTIVE pipeline = motion CEO future (R25').
  3. **Motion #8** : audit Opus regime-detection (`PROMPT_OPUS_REGIME_AUDIT_20260720.md`,
     17 KB). Findings clés :
     - NE PAS activer `V9_REGIME_GATE_ENABLED` (gain marginal 2.5 pips,
       pas de couverture du cas baissier graduel).
     - Ouvrir chantier méta-régime 3 niveaux (micro/meso/macro) — Phase 1
       lecture seule + backtest 7j pour valider gate 70%+.
     - NEUTRE biaisé 92% — calibration à revoir, ajouter `neutre_rate_24h`
       au watchdog.
     - Lecture cross-pair manquante — ajouter `cross_pair_dispersion` au
       RegimeDetector (R2 additif).
- **Vérification** : 408 tests verts (suite trade_engine/supervisor/kill_switch/
  drm/resolve/paper_trade/risk/edge_alert), 0 régression, 0 XFAIL (dette ACTIVE
  résolue). Capture server :31685 alive, pipeline LIVE.
- **Référence** : commits `4a78820`, `adf4cef`, `PROMPT_OPUS_REGIME_AUDIT_20260720.md`.

### 2026-07-20 14h35 UTC — Motion CEO #5 : P0 kill switches lus via kill_switches.get()
- **Décision** : remplacer les 7 `os.environ.get()` directs du `trade_engine`
  par des appels à `core.v9.kill_switches.get()` qui lisent `os.environ`
  en priorité puis le fichier `.env` en fallback.
- **Incident 2026-07-20 14h15 UTC** : paper_trade GBPUSD short
  (`pt_d255e1149326`) ouvert alors que `V9_GBPUSD_LONG_ONLY=1` ET
  `V9_NO_BAISSIERE=1` dans `config/v9_kill_switches.env`. 8 paper_trades
  baissiers sur 10 contournent le filtre en 24h. Le `post_decision_hook` du
  trade_engine n'a PAS appliqué le filtre long_only/no_baissiere.
- **Root cause** : les 7 helpers `_trade_engine_enabled`,
  `_portfolio_risk_enabled`, `_market_regime_global_enabled`,
  `_kelly_cvar_enabled`, `_gbpusd_long_only_enabled`, `_no_baissiere_enabled`,
  `_dynamic_risk_enabled` lisaient `os.environ.get(...)` DIRECTEMENT. Si
  le subprocess ne charge pas le `.env` via `v9_load_kill_switches.py`
  (cas du cron `V9_PaperTradeLoop`), `os.environ` est vide → switch OFF
  même si le `.env` dit ON. Le fix P0.4 du 19/07 avait corrigé
  `v9_loop_breaker.py` mais oublié ces 7 helpers du trade_engine.
- **Fix R2 additif** : `kill_switches.get()` centralise la lecture
  (hiérarchie `env > fichier > défaut`). Comportement legacy préservé
  si le wrapper charge le `.env` (cas subprocess direct).
- **Tests** : `tests/test_trade_engine_kill_switches_centralized.py`
  (5 tests verts — env prioritaire, fallback fichier, override).
  `tests/test_trade_engine_no_baissiere.py` + `test_v9_trade_engine_long_only.py`
  mockent `kill_switches._load()` pour isoler du `.env` prod + reset
  du cache `_switches` entre tests.
- **Vérification manuelle** : `python scripts/v9_live_watchdog_run.py --json`
  → `wr_long_only_gbpusd=0.8`, `net_pnl_24h=-150 pips` (avant fix).
- **Référence** : commit `d443096` « fix(v9): P0 kill switches lus via kill_switches.get() ».

### 2026-07-20 14h15 UTC — Fix P0 résolveur décisions non schedulé (8 paper_trades bloqués 3h)
- **Décision** : 3 fixes additifs R2 pour garantir la résolution des décisions
  `preparer_entree` même si le daemon dédié n'est pas schedulé.
- **Incident 2026-07-20 13h55 UTC** : `v9_resolve_decision_auto_daemon.py` n'était
  PAS installé en cron Windows. ~70k décisions non résolues s'accumulaient, donc
  `TradeEngine.close_open_trades()` (filtre `d.is_win IS NOT NULL` ligne 862)
  ne pouvait PAS fermer les 8 paper_trades ouverts depuis 10:50 UTC
  (4×GBPUSD, 3×AUDUSD, 1×USDJPY, 1×USDCHF).
- **Root cause** : aucun `.bat` n'installait le daemon en Scheduled Task. Le
  `V9_PaperTradeLoop` (5 min) appelle `TradeEngine.run_batch()` → `close_open_trades()`
  qui filtre sur décision résolue. Cercle vicieux : pas de décision résolue →
  trade jamais fermé → décision jamais marquée closed → résolveur ne voit rien.
- **Fix 1 — helper R6 fail-safe** : `scripts/_resolve_pending.py` (NEW, 197 LOC).
  Capture backup MD5 auto dans `backups/resolve_pending_auto/md5_YYYYMMDD.txt`
  (1/jour, idempotent). Délègue à `v9_resolve_decision_auto.resolve_one()` +
  `apply_resolutions()` avec limit=50 (sécurité cron timeout).
- **Fix 2 — préfix supervisor** : `scripts/v9_supervisor.run_paper_trade_cycle`
  appelle `resolve_pending()` avant `run_batch()`. Try/except R6 : best-effort,
  ne bloque jamais le cycle. Le bug originel ne peut plus se reproduire : même
  si le daemon dort, le cycle paper-trade réveille la résolution.
- **Fix 3 — cron dédié filet** : `scripts/install_v9_resolve_decision_loop.bat`
  + Scheduled Task `V9_ResolveDecisionLoop` (5 min, SYSTEM, wrapper kill switches).
  Installé via `schtasks /Create`. Backup tâche : `backups/V9_ResolveDecisionLoop_original.xml`.
- **Fix 4 — `.gitignore` exception** : `!scripts/install_v9_resolve_decision_loop.bat`
  (le `.bat` était gitignoré, comme les autres installateurs cron).
- **Tests** : `tests/test_resolve_pending_supervisor.py` (NEW, 5 tests verts).
  Fixture : copie du schéma prod (sqlite_master CREATE statements) + 1 décision
  + 5 prix futurs + 1 trade ouvert. Reproduit le bug + valide le fix.
- **Vérification manuelle** : `--apply --limit 100` → 56 décisions résolues
  (42.9% WR, -3.4 pips/trade). Cycle supervisor 15:55 UTC → 8 paper_trades
  fermés (1W/7L, -43 pips latents). Daemon JSON confirmé : 0/0/0 (plus rien).
- **Impact / portée** : additif R2 (zéro régression). 5 nouveaux tests verts,
  257 autres verts. 5 tests `test_paper_trade_resolver_active_mode.py` étaient
  déjà rouges AVANT (référencent `_resolver_enabled` non implémenté dans runner
  `v9_paper_trade_run.py`) — hors périmètre R22.
- **Référence** : commit `fcf9162` « fix(v9): P0 résolveur décisions non schedulé ».

### 2026-07-20 13h10 CEST — Motion CEO R32-CLOSE : DRM APPLY permanent, R32 fermée
- **Décision** : le `DynamicRiskManager` opère en mode **APPLY par défaut, de façon
  permanente**. **R32 est fermée** — la contrainte « SHADOW obligatoire » est levée.
  Aucun retour SHADOW sans motion CEO explicite. Décision Søren, **irréversible sauf
  motion CEO**.
- **Motivation** : principe directeur CEO — « le système doit être autonome et évoluer
  sans règle bloquante. DRM APPLY est le mode permanent. Aucune friction doctrinal. »
  Toute règle gelant l'adaptation automatique doit être révisée ou supprimée.
- **Impact / portée** : `docs/DOCTRINE.md` (en-tête principe directeur + R32 réécrite en
  « DRM APPLY permanent »). Les 3 tests `xfail` de `tests/test_v9_drm_shadow_or_apply.py`
  (qui assertaient SHADOW-strict) → **convertis en tests verts** vérifiant le mode APPLY.
  **Aucune modif `core/v9/*`** (DRM déjà en APPLY). `V9_EXECUTION_ENABLED=0` inchangé.
- **Référence** : `docs/DOCTRINE.md` §Règle 32 · `docs/STATE.md` §Phase actuelle ·
  commit R32-CLOSE. Périmètre strict : tests/ + docs/ uniquement.

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

### 2026-07-20 — Traitement en lot des 17 échecs post-DROP + 4 motions CEO (R22)
- **Décision** : résorber les échecs pytest laissés par le DROP 17/07 (Chantier 2)
  selon décisions CEO 12h40 CEST, périmètre STRICT `tests/`+`scripts/`+`docs/`,
  **aucune modif `core/v9/*`**, `V9_EXECUTION_ENABLED=0` inchangé, commit sélectif.
- **Cartographie réelle** : 17 échecs (pas 9). Groupe **A** (5 baissier audit,
  `pstdev` vide post-DROP), **B** (4 caractérisation inversée par design post-DROP),
  **C** (5 cluster DRM SHADOW — le working tree contenait des modifs de tests
  non-committées retirant les `xfail` et assertant l'état *post-Motion CEO #1*
  alors que le core fait encore APPLY), **D** (1 doublons haussier), **E** (1 signal
  perf réel), **F** (1 mojibake pré-existant `test_all_crons_wrapped_passes`).
- **Motion C (Option 2 — revert, PAS de modif core)** : `git checkout HEAD` sur
  `test_perf_paper_vs_decisions_divergence.py`, `test_trade_engine_dynamic_risk.py`,
  `test_v9_drm_shadow_or_apply.py` + suppression des 2 non-trackés
  `test_drm_shadow_strict_applied.py` et `test_db_no_17jul_batch.py` (backup
  scratchpad R8). Restaure les `xfail` documentant le bug R32 **sans bloquer**.
  **DRM reste APPLY** (motion CEO validée ce matin `a9f6191`).
- **Motions A+B (skips vestigiaux)** : `@pytest.mark.skip` sur 5 tests baissier
  audit (A) + 3 tests caractérisation post-DROP (`test_divergence_confined`,
  `test_decisions_dynamic…higher`, `test_re_resolve_wr_realistic`) (B). Tests
  **conservés** (réversibilité R8, motif explicite dans le `reason`).
- **Motion B (dédup données)** : 18 doublons GBPUSD M15 haussier (3 snapshots ×7,
  `opened_at` 19/07 15h41→20/07 00h05 ; bug idempotence corrigé par `bff59e2`)
  supprimés, trade légitime = plus ancien par `opened_at`. Backup in-DB
  `paper_trades_dedup_20260720` (18 lignes, R8), `quick_check`=ok, pas de VACUUM.
  **paper_trades 1 173 → 1 155**. Les 993 doublons du 17/07 (vague backtest début
  juillet) sont **hors périmètre**.
- **Signal E laissé rouge (décision CEO)** : `test_post_catastrophe_wr_acceptable`
  — WR paper live (18/07+) **35.6 % → 29.6 % (n=27)** post-dédup (< plancher 40 %).
  Non skippé : signal réel de perf live à surveiller, échantillon petit.
- **Baseline finale** : seuls **E** + **F** rouges (les 2 « pré-existants » tolérés
  par la motion). Groupe D → `test_no_duplicate_snapshot` **XPASS** post-dédup.
- **Référence** : `docs/reports/DEDUP_HAUSSIER_20260720.md`, `docs/STATE.md`
  §Phase actuelle, backup scratchpad `group_c_backup_20260720/`.

### 2026-07-20 — DROP batch catastrophe 17/07 GBPUSD baissier (Chantier 2, R22)
- **Décision** : DROP audité et réversible des **3 690 paper_trades GBPUSD
  baissier** (WR 1.03 %, -56 089.8 pips), puis re-résolution des décisions non
  résolues. Motion CEO = audit `PERF_PAPER_VS_DECISIONS_20260720.md` §15h00.
- **Prédicat FIXE** : `snapshot_id LIKE 'v9-GBPUSD-%' AND direction='baissiere'`.
  Le total 3 690 / -56 089 pips correspond exactement au chiffre CEO (= tous les
  baissier GBPUSD, cœur = burst 17/07 15h09→19h25). Haussier GBPUSD (1 075,
  WR 100 %, +8 767 pips) et autres paires **préservés**.
- **Méthode (R8)** : script dédié `scripts/v9_drop_batch_17jul.py` (dry-run par
  défaut, `--apply --backup` exige `md5_pre.txt`). Backup triple : MD5 pré-DROP
  (`d4a985…`), table in-DB `paper_trades_dropped_17jul_baissier` (3 690 lignes,
  restaurable), dump JSON hors-DB. Transaction unique BEGIN IMMEDIATE, garde
  `deleted == cible` sinon ROLLBACK. **Aucun VACUUM** (writer live actif).
  `PRAGMA quick_check` = ok post-op.
- **Résultat global paper_trades** : 4 854 → 1 164 trades ; WR 23.69 % → **95.53 %** ;
  pips **-47 426.4 → +8 663.4** (swing **+56 089.8**).
- **Re-résolution** : `v9_resolve_decision_auto.py --apply --skip-no-future-prices`
  → 134 décisions résolues (56 W / 78 L, WR 41.8 %, -2.1 pips moyens), DYNAMIC.
- **Baseline pytest** : **2355 passed / 17 failed** (≥ 2355 requis ✓ ; avant
  mission = 2362/8). Les 9 nouveaux échecs sont des conséquences directes/attendues
  du retrait des données baissier (tests de caractérisation + analyse baissier
  bâtis sur la catastrophe), **pas** des bugs du code commité : 4 tests `test_perf…`
  (WR GBPUSD/paper/DYNAMIC/post-catastrophe désormais post-DROP), `test_v9_re_resolve`
  (WR nettoyé 95 % > borne 80 %), 5 `test_v9_baissier_audit` (JSON `strategy_pole`
  réécrits par cron background 10:10-10:12 + grid-search short = « aucun trade »
  post-DROP, cohérent `V9_NO_BAISSIERE=1`). Tous compagnons/vestiges non commités
  → recalibrage en motion dédiée (cf. rapport §Impact tests).
- **Findings hors périmètre (GO CEO = 3 690 baissier uniquement)** — non traités,
  flaggés pour motion dédiée : (a) résidu duplication **haussier** 19-20/07
  (3 snapshots ×7 = 18 lignes, même bug idempotence) → `test_no_duplicate_…`
  reste rouge ; (b) `test_db_no_17jul_batch` (non commité) attend la fenêtre 17/07
  entière vidée = détruirait les 1 075 haussier profitables → contradiction avec
  la préservation mission/audit, non satisfait par sur-suppression.
- **Portée** : `V9_EXECUTION_ENABLED=0` inchangé. Commit sélectif (script + rapport
  + DECISIONS + STATE ; backups locaux non commités, réversibilité via table in-DB).
- **Référence** : `docs/reports/DROP_BATCH_20260720.md` ; `scripts/v9_drop_batch_17jul.py`.

### 2026-07-20 — Fix P0 idempotence `post_decision_hook` (Chantier 1, R22)
- **Décision** : corriger la garde d'idempotence de `TradeEngine` qui
  n'empêchait pas la ré-ouverture d'un snapshot déjà tradé mais clôturé.
- **Root cause** : `_trade_already_open` (core/v9/trade_engine.py) filtrait
  `AND closed_at IS NULL` → ne détectait que les trades ENCORE ouverts. En fin
  de batch `close_open_trades()` clôture les trades ; au passage suivant le
  hook `post_decision_hook` (une `TradeEngine` fraîche par snapshot) retrouvait
  le snapshot « libre » et le ré-ouvrait, empilant jusqu'à **7 paper_trades
  clôturés sur un seul snapshot_id** (catastrophe 17/07, récidive 19-20/07
  constatée par l'audit `PERF_PAPER_VS_DECISIONS_20260720.md`).
  NB : la description initiale de la mission (« re-clôture ») était inexacte —
  le hook appelle `process()` qui **ré-ouvre**, il n'appelle pas
  `close_open_trades()`. Le symptôme (7 trades/snapshot) est identique.
- **Correctif** : la garde compte désormais TOUT trade du couple
  (snapshot_id, direction), ouvert OU fermé. Un snapshot = une décision = au
  plus un paper_trade. Nom de méthode conservé (rétro-compat des stubs de
  test). `raison_blocage` : `trade_deja_ouvert` → `snapshot_deja_trade`.
- **Portée** : `run_batch()` **non modifié** (son code appelle la même garde
  via `process()`) — seuls les doublons pathologiques disparaissent ; les
  snapshots réellement neufs s'ouvrent toujours. `V9_EXECUTION_ENABLED=0`
  inchangé.
- **Hors périmètre (à traiter en motion dédiée)** : `scripts/v9_paper_trade_run.py::is_trade_already_open`
  garde volontairement `closed_at IS NULL` (contrat testé par
  `test_is_trade_already_open_ignore_clos`) — chemin cron parallèle, non touché
  ici (R22 : 1 périmètre).
- **Tests** : `tests/test_trade_engine_idempotence.py` (2 tests neufs :
  détection d'un trade clôturé + idempotence bout-en-bout ouverture→clôture→
  re-traitement, 0 doublon). Baseline avant fix = **2362 passed / 8 failed**
  (les 8 : 5 DRM SHADOW↔APPLY d'un autre acteur, 2 DB historique 17/07
  Chantier 2, 1 mojibake cron) ; après fix = **2364 passed / 8 failed**
  (aucune régression, +2 tests idempotence).
- **Référence** : commit Chantier 1 ; `core/v9/trade_engine.py` L734-745, L1426-1449.

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
