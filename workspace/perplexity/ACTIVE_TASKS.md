# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/STATE.md` (dernière mise à jour **2026-07-14 ~15:30 UTC — pipeline LIVE + crons réparés**).
Ce fichier ne fait qu'organiser la même information par statut d'exécution
pour une reprise rapide.

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
