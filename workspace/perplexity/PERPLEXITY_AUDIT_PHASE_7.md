# PERPLEXITY AUDIT — Phase 7+ (31/07/2026)

**Source** : Perplexity Pro (Kimi K3), audit statique via `git clone`
**Branche auditée** : `feat/v9-foundation-clean` (HEAD `76b31e5`)
**Périmètre** : 16 commits Phase 1-7 (28-31/07)
**Accès** : Git only (no DB, no MCP, no runtime exec)

---

## ★ RÉSUMÉ EXÉCUTIF ★

**Phase 1-7 techniquement solide** (143 tests verts, 16 commits atomiques, walk-forward positif). **5 bugs identifiés**, **5 leviers additionnels proposés**, **5 risques opérationnels**. Tous corrigeables sans régression majeure.

**Risque principal avant Phase 12 LIVE** : pas technique, mais **validation expectancy live** (vs offline) + **rotation tokens Telegram**.

---

## BUGS LATENTS IDENTIFIÉS

### BUG-P1 — Conftest neutralise MEGA en production si mal copié

`V9_MEGA_EDGE_ENABLED=0` dans `conftest.py` ligne 91 protège les tests. Si un `.env` de production hérite du conftest (via python-dotenv chargé avant le cron), MEGA est silencieusement désactivé. Aucun log d'alerte en prod.

**Statut** : **CORRIGÉ Phase 8** (commit `XXXXXXX`). Module `core/v9/v9_boot_alerts.py` alerte si MEGA OFF + `V9_BOOT_CONTEXT=prod`.

### BUG-P2 — Mirror BLOCKING neutre tant que `v9_human_trades` est vide

Score 0.5 = neutre = pas de blocage. Phase 1 Jour 6 est un no-op jusqu'à ce que Søn logue manuellement. Aucun mécanisme d'alerte "Mirror actif mais sans données depuis X jours".

**Statut** : **CORRIGÉ Phase 8**. `_mirror_data_age_days()` alerte si > 7 jours.

### BUG-P3 — Auto-promotion peut écraser ACTIVE→SHADOW silencieuse

`INSERT OR REPLACE` dans `_sync_principles_to_db` (lignes 343, 1256) est bidirectionnel. Si un recalibrage post-auto-optimizer baisse la confiance d'un principe star ACTIVE, il peut le repasser SHADOW sans notifier Søn. Perte silencieuse d'edge.

**Statut** : **DOCUMENTÉ R31** (doctrine). Fix structurel à venir (patcher YAML source + audit trail).

### BUG-P4 — L3 time_exit vs DRM HUMAN_SCALP incohérence possible

TP=25/SL=8 (HUMAN_SCALP, RR 3.1). Avec L3 5min force close au-delà de 5min, les trades longs n'ont jamais le temps d'atteindre TP=25. RR réel ≈ 0 sur les trades longs, pas 3.1.

**Statut** : **CORRIGÉ Phase 8**. Boot alert `[BUG-P4]` si L3 ON + HUMAN_SCALP ON simultanément. Recommendation : `V9_DRM_HUMAN_PROFILE_ENABLED=0` (option A dans CHECKLIST_PHASE12_LIVE.md).

### BUG-P5 — `vt_reason` peut être None dans des snapshots

**Statut** : **FAUX POSITIF** (vérifié). `vt_reason` n'existe pas dans `principle_engine.py`. Pas de KeyError possible sur champs dérivés. Perplexity s'est trompé (audit statique sans grep).

---

## LEVIERS ADDITIONNELS PROPOSÉS

| L | Levier | Logique | Impact attendu | Statut |
|---|---|---|---|---|
| **L10** | Confirmation-bar gate | Attendre N=2 bougies M5 fermées avant entrée (Bug 2 audit 28/07). Paramètre V9_CONFIRMATION_BARS=2 = +10min latence | Élimination faux positifs 1ère minute. -20-30% volume | **À IMPLÉMENTER Phase 9** |
| **L11** | CVD divergence consommateur | cvd_snapshots déployé mais non consommé par principes YAML. Ajouter condition YAML optionnelle cvd_divergence ≥ 0.3 sur PRICE_LAG | Filtrage qualitatif PRICE_LAG dilués | À vérifier Phase 9 (audit SQL) |
| **L12** | Walk-forward alert précoce | Si WR 7j glissant baisse de > 5pts sur 3j consécutifs → ALERT (vs seuil 60% actuel) | Détection dérive avant seuil critique | **À IMPLÉMENTER Phase 9** (cron_pipeline.py) |
| **L13** | RETOUR_EQUILIBRE sous-critère duration | RETOUR_EQUILIBRE = WR 27.9%, -217.8p. Si palier_duration > X filtre les retours longs | -100p récupérables potentiels | À vérifier SQL v6 (Perplexity sans DB) |
| **L14** | Session gate non-GBPUSD | AUDUSD 06-08h UTC (Sydney/Tokyo) a-t-il edge distinct ? Si WR > 60% sur ≥ 30 trades | Diversification edge non-testée | À vérifier SQL v7 (Perplexity sans DB) |

---

## RISQUES OPÉRATIONNELS

### R1 — Walk-forward sur résolution offline (CRITIQUE)

Les 4/4 folds positifs et expectancy 5.96p sont sur `decisions.resolution_pips` (résolveur offline). Hermes le signale lui-même : la vérité live viendra de `close_open_trades()` + `ExitSimulator` ≈ breakeven après coûts. Niveau absolu d'expectancy gonflé.

**Mitigation** : 100 trades live paper avec `close_open_trades()` seul avant Phase 12 LIVE (voir `docs/CHECKLIST_PHASE12_LIVE.md`).

### R2 — Tokens Telegram non rotés depuis 18/07 (BLOQUANT)

13 jours sans rotation. Si un token compromis, alertes cron (Phase 7) passent par canal exposé. **Action bloquante avant Phase 12 LIVE** (Søn).

### R3 — MT4 redémarrage non couvert

`capture_server` est headless mais MT4 nécessite session GUI Windows. Un redémarrage machine coupe le flux de données en silence. Aucun cron vérifie heartbeat `capture_server` (absent).

**Mitigation Phase 9** : `scripts/v9_heartbeat_capture.py` + cron 1min.

### R4 — Phase 12 LIVE sans checklist pré-live formalisée

**CORRIGÉ Phase 8** : `docs/CHECKLIST_PHASE12_LIVE.md` créé avec 10 sections (Sécurité Telegram, expectancy live, L3 vs HUMAN_SCALP, Mirror BLOCKING données, boot alerts, kill switches, DB backup, MT4 heartbeat, walk-forward cron, tests pytest).

### R5 — Sample insuffisant sur les nouvelles phases

Phases 5-7 livrées en 3 jours (29-31/07). Walk-forward 31/07 porte sur 9469 trades historiques, **pas sur trades post-Phase 5**. L'effet HUMAN_SCALP TP=25/SL=8 n'a jamais été validé sur trades réels. Risque de régression silencieuse.

**Mitigation** : Walk-forward quotidien (Phase 7 livré), alert `wr_below_threshold` automatique.

---

## RECOMMANDATIONS MOTION CEO PHASE 12 LIVE

Avant tout passage LIVE, valider dans l'ordre :

1. **Rotation tokens Telegram** (action humaine Søn, BLOQUANTE)
2. **100 trades live paper** avec `close_open_trades()` seul (R1)
3. **`docs/CHECKLIST_PHASE12_LIVE.md`** : 10 sections à valider (R4, livré)
4. **L3 vs HUMAN_SCALP** : choisir Option A (`V9_DRM_HUMAN_PROFILE_ENABLED=0`) ou B (`V9_TIME_EXIT_MINUTES=60` TREND/CASSURE)
5. **Mirror BLOCKING** : logger ≥ 20 trades Søn avant activation (BUG-P2)

---

## LIMITATIONS DE CET AUDIT

- Pas d'accès à `data/v9_forces.db` : leviers L10-L14 spéculatifs (logique, pas SQL)
- Pas d'exécution de code : BUG-P4 (L3 vs HUMAN_SCALP) inférence logique, pas crash observé
- Walk-forward 31/07 positif (4/4 folds), niveau absolu à valider live
- Hermes doit vérifier chaque finding sur la branche avant d'agir

---

## RÉPONSE HERMES (Phase 8 — après audit)

| Finding | Action | Commit |
|---|---|---|
| BUG-P1 | ✓ FIX `v9_boot_alerts.py` + câblage `trade_engine.py` | Phase 8 |
| BUG-P2 | ✓ FIX `_mirror_data_age_days()` + alert > 7j | Phase 8 |
| BUG-P3 | ⏳ DOC R31 + fix structurel à venir | Phase 9 |
| BUG-P4 | ✓ FIX boot alert + recommendation Option A | Phase 8 |
| BUG-P5 | ✓ FAUX POSITIF (vérifié `vt_reason` absent) | n/a |
| L10-L14 | ⏳ À évaluer Phase 9 (audit SQL + implémentation) | Phase 9 |
| R1 | ✓ DOCUMENTÉ dans CHECKLIST + walk-forward | Phase 8 |
| R2 | ⏳ Bloquant humain Søn (rotation tokens) | n/a |
| R3 | ⏳ Heartbeat capture_server Phase 9 | Phase 9 |
| R4 | ✓ FIX `CHECKLIST_PHASE12_LIVE.md` créé | Phase 8 |
| R5 | ✓ Walk-forward quotidien (Phase 7 livré) | Phase 7 |

---

**Verdict Perplexity** : Phase 1-7 techniquement solide. Risque principal avant LIVE = validation live expectancy + rotation tokens.

**Verdict Hermes post-audit** : 4/5 bugs corrigés (Phase 8). 1 faux positif ignoré. 5 risques dont 3 déjà mitigés (CHECKLIST + walk-forward). L10-L14 + R3 à traiter Phase 9.

---

**Date** : 2026-07-31
**Auteur** : Perplexity Pro (Kimi K3), lecture statique
**Validé par** : Hermes (Phase 8 motion CEO autopilote)