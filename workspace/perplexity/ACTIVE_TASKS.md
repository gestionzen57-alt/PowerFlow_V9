# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/STATE.md` (auto-régénéré par `scripts/v9_sync_state.py`).
Ce fichier ne fait qu'organiser la même information par statut d'exécution
pour une reprise rapide.

---

## ⏰ TODO CEO — PRIORITÉ 2026-08-03 (snapshot session 03/08)

**Phase actuelle** : **Phase 12 FTMO Challenge — ACTIVE** (motion CEO 02/08,
commit `8d0fcee`). Système opérationnel avec bénéfice mesuré **+758.5 pips
cumulé L7+L8** (L7 ON Phase 117, L8 ON Phase 121). Walk-forward L8 verdict
PROMOTE 5/5. Phase 12 surveillance quotidienne automatisée (commit `dd3e06c`).

### P0 — BLOQUANT (à traiter cette semaine)

| # | Action | Effort | Pourquoi | Comment |
|---|---|---|---|---|
| **A1** | **Rotation 4 tokens Telegram @BotFather** | 5 min | Token Hiphopvps → 401 Unauthorized, Ipspx dupliqué → 404. Communication Telegram **coupée** (alertes auto-calibrator, heartbeat, watchdog, optimizer). | `@BotFather` → `/revoke` → 2 nouveaux tokens → `scripts/v9_rotate_telegram_tokens.py --hiphop-token X --ipspx-token Y --apply` (test `--validate-only` avant) |
| **A2** | **Réparer DB v9_forces.db** (page 825461 btreeInitPage error 11) | 30 min | Bloque OOS freeze test Phase 105 + risque silencieuse sur décisions live. | `backups/repair_v4_log_20260801.txt` trace le run précédent. Refaire + `PRAGMA quick_check` |

### P1 — IMPORTANT (sous 2 semaines)

| # | Action | Effort | Pourquoi | Comment |
|---|---|---|---|---|
| **A3** | Rejouer `scripts/v9_oos_freeze_test.py` post-réparation DB | 15 min | Phase 105 verdict DEGRADED (DB corrompue). Doit repasser STABLE/DRIFT avant FTMO Challenge live. | `--apply` après fix A2 |
| **A4** | Activer `PYRAMIDING_BOOST_STARS` / `PYRAMIDING_BOOST_SUPER_STARS` | 1 min | Sortie des clous FTMO (DD cap). Motion CEO explicite requise. | `config/v9_kill_switches.env` |
| **A5** | Activer `V9_AUTO_CALIBRATOR_ENABLED=1` (auto-calibrator writable) | 1 min | Boucle fermée R30 — recalibre seuils/profil tous les 100 trades. | Motion CEO explicite (R25' strict) |
| **A6** | Activer `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1` | 1 min | Seuils modulés session × vol × news × TF (autopilot P3) | Motion CEO explicite |

### P2 — OPTIMISATION (sous 1 mois, ROI décroissant)

| # | Action | Effort | Bénéfice | Comment |
|---|---|---|---|---|
| **A7** | Implémenter L9 (filtre temporel < 14h UTC) | 1-2 j | +520 pips projeté (54% temps bloqué). Phase 125 documenté, non implémenté. | Kill switch `V9_MEGA_EDGE_L9_TIME_FILTER_ENABLED` (défaut OFF). Motion CEO requise. |
| **A8** | Activer `V9_TRADER_MINI_ENABLED=1` (Brief Q1 baseline) | 1 min | Multiplicateur weigher [0.85, 1.05] sur consolidate. Subtil, bornées resserrées. | Motion CEO explicite (R25' descriptif) |
| **A9** | Activer `V9_REGIME_GATE_ENABLED=1` (Phase 18/07) | 1 min | Refuse exploitation en regime volatile si conf>0.7 | Motion CEO |
| **A10** | Activer `V9_BEAR_PERCEPTION_ENABLED=1` (shadow → APPLY) | 1 min | Perception baissière | Motion CEO |
| **A11** | Recalibrer `V9_KELLY_CVAR_ENABLED` (NO-GO walk-forward) | 1-2 j | CVaR sizing cap sur Kelly existant. Recalibrer sur données post-DROP. | Réservé quand WIN/LOSS ≥ 50 propres |
| **A12** | Activer `V9_TELEGRAM_SIGNAL_ALERT_ENABLED=1` post-rotation A1 | 1 min | Alertes signal Telegram. Bloqué par A1. | Après A1 |

### P3 — DOCUMENTATION / GOUVERNANCE (à faire en parallèle)

| # | Action | Effort | Pourquoi |
|---|---|---|---|
| **A13** | Purger 50+ dossiers `backups/token_rotation_*` (01-02/08) | 5 min | Backup R8 inutile une fois rotation appliquée. Pollue le working tree (50+ untracked). `git clean` ou `rm -rf backups/token_rotation_*/` |
| **A14** | Committer `scripts/v9_phase12_daily_monitor.py` (379 LOC) | 1 min | Code Phase 12 livré mais pas tracké. Doit être dans le repo (R14). |
| **A15** | Replay state sync `python scripts/v9_sync_state.py` après commit | 1 min | Régénère AGENT.md / STATE.md / CACHE_BOARD.md depuis sources réelles |

### Ordre d'exécution recommandé

```
A1 (5 min) → A2 (30 min) → A3 (15 min) → A4-A6 (5 min) → A13 (5 min) → A14-A15 (5 min)
─────────────────────────────────────────────────────────────────────────
Temps total P0+P1+P3 : ~1h CEO
Phase 12 FTMO live monitorable 24/7
```

### Métriques de validation post-exécution

- `data/v9_l7_promotion_report.json` doit rester QUASI_PROMOTE
- `data/v9_l8_promotion_report.json` doit rester PROMOTE
- `data/v9_phase12_monitor_state.json` doit avoir `last_run` < 24h
- `data/v9_cron_pipeline.log` ne doit pas avoir d'erreur
- `pytest tests/test_v9_l7_l8_mega_edge.py` (et l7/l8 walkforward) : 81/81 verts
- `data/v9_forces.db PRAGMA quick_check` : ok

### Périmètre GELÉ (rappel)

- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Distillation LLM Phase 13** — pas d'infra locale GPU
- L9 sans motion CEO explicite (recommandation Phase 124, gain projeté élevé mais restrictif)

### Périmètre ACTIF

- **Phase 12 FTMO Challenge** — exécution réelle (motion CEO 02/08)
- **Auto-calibrator/optimizer/promoter** — boucle fermée (R30, kill switch ON par défaut en cours d'activation)
- **L7** (GRAMMAR/ELASTIC pur no-stars) — ON (Phase 117)
- **L8** (n_principes >= 5) — ON (Phase 121), verdict PROMOTE 5/5

---

## Terminé — Session 2026-07-14 (ZCode + Hermes parallèle)

Motion CEO Søn « go activer tous pour le prochain level go go ».

### 🔥 Pipeline LIVE (nouveau)
- `deploy_v9.py --start` lancé par Søn → **37 décisions produites en 30 min**
- Dernier snapshot : 2026-07-14T15:29 (GBPUSD M1, non-stale)
- Pipeline cognitif complet : scènes → comportements → fenêtres → signaux → décisions
- 1 décision `preparer_entree` (baissiere, confiance=80)
- Shadow mode actif : 0 divergence sur 24h
- **Telegram testé ✅** — message envoyé avec succès

### 🔥 7 crons Windows installés et réparés (nouveau)
- **Problème corrigé** : les 3 tâches existantes (`V9_AutoRestart`, `V9_HeartbeatCheck`, `V9_HeartbeatAlert`) utilisaient `python` sans chemin absolu → pointaient vers le mauvais venv → échouaient silencieusement
- **Solution** : 7 wrappers `.bat` avec chemin venv absolu `C:\projet\V9\.venv\Scripts\python.exe`
- **4 nouvelles tâches** créées (manquantes avant) : `V9_ResolveLoop`, `V9_CalibrationLoop`, `V9_ArbiterRecal`, `V9_MetaAgentScan`

| Tâche | Fréquence | Statut |
|-------|-----------|--------|
| V9_AutoRestart | 5 min | ✅ Prêt |
| V9_HeartbeatCheck | 5 min | ✅ Prêt |
| V9_HeartbeatAlert | 60 min | ✅ Prêt |
| V9_ResolveLoop | 10 min | ✅ Prêt |
| V9_CalibrationLoop | 2h | ✅ Prêt |
| V9_ArbiterRecal | 6h | ✅ Prêt |
| V9_MetaAgentScan | 30 min | ✅ Prêt |

### ZCode (3 commits)
- **A1+A2+P2+P3-WIRE ON** — 6 tests adaptés
- **P1-RESOLVE** — `resolve_one()` lit `signals.exit_strategy_recommended`
- **SHADOW-EXPAND** — shadow évalue A1+A2
- **Backfill P1** — 60 119 signaux DYNAMIC
- **Re-résolution DYNAMIC** — 8 420 décisions (WR=85.6%)
- **71 paper trades** résolus
- **Requête Fable 5** prête

### Hermes (3 commits)
- **P3-CONSUME** 🏆 — ADAPTIVE_VOL_GATE.yaml (10 tests)
- **Doctrine assouplie** — R7, R22, R25', R28
- **F = A+B+C+D** — principle_scores (5), colonnes P6, paper trades effacés

## En cours / restant

| Chantier | Priorité | Effort | Qui |
|----------|----------|--------|-----|
| **✅ NIVEAU QUANTIQUE LIVRÉ 2026-07-18** — 5 leviers institutionnels (PRM câblé + walk-forward + position manager + risk-on/off + rapport quotidien) | ~~HAUTE~~ **TERMINÉ** | — | Opus + ZCode |
| **✅ DynamicRiskManager ACTIF** — V9_DYNAMIC_RISK_ENABLED=1, RR 0.53→1.63 | ~~HAUTE~~ **ACTIF** | — | Opus + Søn |
| **✅ BOUCLE FERMÉE LIVRÉE** — auto-calibrateur writable + auto-optimizer + auto-promotion | ~~HAUTE~~ **TERMINÉ** | — | ZCode |
| **✅ DIVERSIFY A+B+C LIVRÉS** — 6 principes réanimés + SignalFusionEngine | ~~HAUTE~~ **TERMINÉ** | — | Opus |
| **✅ CHANTIERS A+B+C LIVRÉS 2026-07-18 §19h35** — regime gate + CVaR sizing + CVD tick-level (kill switches OFF) | ~~HAUTE~~ **TERMINÉ** | — | Opus (`fbca486`) |
| **✅ NOTIFIER DYNAMIQUE 2026-07-18 §21h30** — system prompt live + routing data + reply_markup | ~~MOYENNE~~ **TERMINÉ** | — | Hermes (`66bca85`) |
| **⏸️ AUDIT EDGEFUND (motion §17h45)** — prompt Opus prêt, en attente validation CEO pour lancement | MOYENNE | 1-2h | Opus (quand validé) |
| **⏸️ Activer P2 Position Manager** (`V9_POSITION_MANAGER_ENABLED=1`) | HAUTE | 1min | Søn (décision CEO) |
| **⏸️ Activer P3 Risk-on/off** (`V9_MARKET_REGIME_GLOBAL_ENABLED=1`) | HAUTE | 1min | Søn (décision CEO) |
| **⏸️ Activer Chantier A/B/C** quand usage décide (`V9_REGIME_GATE/KELLY_CVAR/CVD_ENABLED`) | MOYENNE | 1min ×3 | Søn (motion distincte) |
| **⏸️ Re-évaluer 2 SHADOW** (ANTAGONIST, VOL_GATE) — LOCK/RESPIRATION déjà promus | MOYENNE | 5min | J+? |
| Corriger 6 tests pré-existants (baissier audit + encoding) | BASSE | 30min | — |
| VPS déploiement | BASSE | 2h | Søn |

### Sprint 2026-07-18 §17h15→21h35 (résumé)
- `152d418` câblage V9_DYNAMIC_TP_SL + activation kill_switches (ZCode/Hermes, motion §17h15 « go r28 »)
- `fbca486` regime gate + CVaR sizing + CVD tick-level (Opus, 41 tests verts)
- `66bca85` notifier Telegram dynamique + prompt Opus audit edgefund (Hermes, 12 tests verts)
- `a4acfac` refresh data/strategy_pole (Hermes, chore pur)

**Tous additifs R2 (aucune régression). Kill switches OFF par défaut.**

## Sprint 2026-08-01 — Phases 105-107 motion CEO #42

**Pilote automatique total**, livrées en 1 session :

| Phase | Statut | Tests | Verdict | Commit |
|---|---|---|---|---|
| 105 — OOS DB Freeze Test | ✅ LIVRÉ | 15/15 | DEGRADED (DB corrompue, escalade CEO) | `dbf800c` |
| 106 — Refactoring trade_engine.py | ✅ LIVRÉ (4/6 sous-méthodes) | 16/16 | OK (scope reporté en 106-bis) | `e1a1f6b` |
| 107 — FTMO Sizing Validator 1000-trades | ✅ LIVRÉ | 23/23 | **GO** (marges 50%/92%/68%) | `c2385da` |

**Bilan** : 3 commits atomiques, 54 nouveaux tests verts, 0 régression.
Suite périmètre touché : **106/106 verts**.

**Travail en attente (CEO motion requise)** :
- Réparer DB source `data/v9_forces.db` (page 825461, btreeInitPage error 11) avant Phase 12 FTMO Challenge
- Rejouer `scripts/v9_oos_freeze_test.py` post-réparation pour verdict STABLE/DRIFT
- Activer `PYRAMIDING_BOOST_STARS` / `PYRAMIDING_BOOST_SUPER_STARS` = motion CEO explicite (sortie des clous FTMO)
- Phase 106-bis : extraire `_apply_risk_gates_and_sizing()` + `_finalize_trade()` (~1-2 jours)
- Cron quotidien `v9_ftmo_sizing_validator.py` 06:00 UTC pour monitoring live

**Doctrine** : R2 additif strict, R6 défensif, R7 106/106 verts, R8 MD5 streaming, R14 git vérité, R22 sous-unité unique par phase, R26 DECISIONS_LOG + STATE.md, R28 Hermes opérateur git unique.



## ⏸️ TODO CEO — Action A1 : Rotation tokens Telegram (BLOQUANT communication Telegram)

**Statut** : 23/23 tests verts. Script prêt. **Action CEO requise sur BotFather.**

### Étape CEO (5 min)

1. Ouvrir Telegram → `@BotFather`
2. Pour chaque bot (`@Ipspxbot`, `@Hiphopvps_bot`) :
   - `/revoke` → choisir le bot → copier le nouveau token
   - OU `/token` → régénérer si `/revoke` indisponible
3. Une fois les 2 nouveaux tokens en main, lancer :

```bash
cd C:\projet\V9
.venv\Scripts\python.exe scripts/v9_rotate_telegram_tokens.py \
    --hiphop-token "<NOUVEAU_TOKEN_HIPHOP>" \
    --ipspx-token "<NOUVEAU_TOKEN_IPSPX>" \
    --apply
```

4. Vérifier post-rotation :

```bash
.venv\Scripts\python.exe scripts/v9_rotate_telegram_tokens.py --validate-only
```

→ Sortie attendue : 3 OK (config/telegram.json + .env Hiphopvps + .env Ipspx dupliqué)

### Rollback si problème

```bash
# Lister les backups
ls backups/token_rotation_*/

# Restaurer
cp backups/token_rotation_YYYYMMDD_HHMMSS/telegram.json.bak config/telegram.json
cp backups/token_rotation_YYYYMMDD_HHMMSS/.env.bak .env
```

### Livraisons Hermés (déjà commitées après exécution CEO)

- `scripts/v9_rotate_telegram_tokens.py` (~370 lignes, modes apply/dry-run/validate-only)
- `tests/test_v9_rotate_telegram_tokens.py` (23/23 verts)
- Backup MD5+SHA256 automatique avant rotation (R8)

### Pourquoi maintenant

- Token Hiphopvps retourne **401 Unauthorized** au `getMe` (vérifié 01/08 19:06 UTC)
- Token Ipspx dupliqué `.env` retourne **404 Not Found**
- Communication Telegram **cassé** (alertes auto-calibrator, heartbeat, watchdog, optimizer)
- Risque : si DB se corrompt à nouveau, on ne reçoit plus d'alerte CEO

### Métriques

- Effort CEO : 5 min
- Rollback : <1 min (cp 2 fichiers)
- 0 risque : backup MD5 avant chaque rotation, validation getMe pre+post

---

## Cron Windows V9 — état 2026-07-18

| Tâche | Fréquence | Statut |
|-------|-----------|--------|
| V9_AutoRestart | 5 min | ✅ Ready |
| V9_HeartbeatCheck | 5 min | ✅ Ready |
| V9_HeartbeatAlert | 60 min | ✅ Ready |
| V9_ResolveLoop | 10 min | ✅ Ready (--apply) |
| V9_CalibrationLoop | 2h | ✅ Ready |
| V9_ArbiterRecal | 6h | ✅ Ready |
| V9_MetaAgentScan | 30 min | ✅ Ready |
| V9_LearningLoop | quotidien 23h00 UTC | ✅ Ready |
| V9_TelegramWatch | continu | ✅ En cours |
| V9_TelegramAgent | N/A | ✅ Ready |
| V9_AutoCalibrator | 6h | ✅ Ready |
| V9CaptureWatchdog | 5 min | ✅ Running |
| V9_DailyReport | quotidien 07h00 UTC | ✅ Ready |
| V9_StrategyPoleScan | 2h | ✅ Ready |

## Gelé (ne pas démarrer)
- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Phase 12 — exécution d'ordres réelle** — interdit fondateur, E refusé
- **Distillation LLM Phase 13** — pas d'infra locale


## ⏸️ TODO CEO — Phase 115 : Activation manuelle L7 (verdict QUASI_PROMOTE)

**Contexte** : Phase 111 (verdict QUASI_PROMOTE 3/5) + Phase 114 (dedup idempotent).
Le walk-forward L7 montre un edge preserve (WR +0.44pt, PNL gain +32.6p sur 30j).

**Recommandation Hermés (R28)** :
- ACTIVER L7 (V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED=1)
- Benefice statistique valide : edge preserve (3/5 conditions R25')
- Cout : 0 (defaut OFF, dev par defaut securite)
- Risque : drift, mais sample identique a la fenetre de validation

**Sinon** : laisser OFF (defaut R25' strict). Benefice non capture.

**Motion CEO requise pour activation manuelle**.
