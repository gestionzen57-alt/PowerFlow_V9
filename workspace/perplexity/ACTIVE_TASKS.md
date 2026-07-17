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
| **✅ DynamicRiskManager ACTIF 2026-07-17** — motion CEO Søn, V9_DYNAMIC_RISK_ENABLED=1, RR 0.53→1.63 | ~~HAUTE~~ **ACTIF** | — | Opus + Søn |
| **⏸️ Promotion 4 SHADOW — REPORTÉE** — critère (WR>50% n≥10) non atteint. VOL_GATE 33% (n=24), ANTAGONIST n=1, LOCK/RESPIRATION 50% (n=12). Ré-évaluer J+2 | HAUTE | 5min | J+? |
| **✅ BOUCLE FERMÉE LIVRÉE** — SHADOW→ACTIVE massif + auto-calibrateur writable + auto-optimizer | ~~HAUTE~~ **TERMINÉ** | — | ZCode |
| **✅ DIVERSIFY A+B+C LIVRÉS** — 6 principes réanimés + SignalFusionEngine + benchmark | ~~HAUTE~~ **TERMINÉ** | — | Opus |
| **✅ Audit clôture semaine** — 4 angles morts + durcissement crons + look-ahead disculpé | ~~HAUTE~~ **TERMINÉ** | — | Opus |
| Rotation token Telegram (AAEP7... a fuité) | MOYENNE | 30min | Søn |
| VPS déploiement | BASSE | 2h | Søn |

## Cron Windows V9 — état 2026-07-17 10:15 UTC

| Tâche | Fréquence | Statut |
|-------|-----------|--------|
| V9_AutoRestart | 5 min | ✅ Ready |
| V9_HeartbeatCheck | 5 min | ✅ Ready |
| V9_HeartbeatAlert | 60 min | ✅ Ready |
| V9_ResolveLoop | 10 min | ✅ Ready (--apply actif) |
| V9_CalibrationLoop | 2h | ✅ Ready |
| V9_ArbiterRecal | 6h | ✅ Ready |
| V9_MetaAgentScan | 30 min | ✅ Ready |
| V9_LearningLoop | quotidien 23h00 UTC | ✅ Ready |
| V9_TelegramWatch | continu | ✅ En cours |
| V9_TelegramAgent | N/A | ✅ Ready |
| V9_AutoCalibrator | 6h | ✅ Ready |
| V9CaptureWatchdog | 5 min | ✅ Running |

## Gelé (ne pas démarrer)
- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Phase 12 — exécution d'ordres réelle** — interdit fondateur, E refusé
- **Distillation LLM Phase 13** — pas d'infra locale
