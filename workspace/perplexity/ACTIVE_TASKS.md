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
