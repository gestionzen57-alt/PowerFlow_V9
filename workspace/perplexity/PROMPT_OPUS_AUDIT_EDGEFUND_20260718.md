# 🎯 PROMPT OPUS — Audit complet optimisation edgefund V9 (2026-07-18)

> **Statut** : À valider motion CEO avant lancement
> **Auteur prompt** : ZCode (MiniMax-M3)
> **Motion CEO source** : « lis tous les documents pour le contexte, fait le bilan et propose pour opus un audit complet pour optimisation edgefund » (Søn, 2026-07-18 16h UTC)

---

## 🎯 Mission globale

Tu es **OPUS Claude Code** en mission d'audit hedge fund sur PowerFlow V9.
Ta mission : **établir si V9 peut devenir un système edgefund rentable et produire un plan d'optimisation chiffré** pour atteindre la rentabilité soutenable.

**Doctrine respectée** : R7 (tests verts), R8 (docs), R14 (git = vérité), R18 (code pur), R22 (1 périmètre = 1 livraison), R26 (commit + DECISIONS_LOG), R28 (motion CEO).

**Durée cible** : 18-24h, multi-étapes.

---

## 📂 Contexte obligatoire (lis avant tout)

### A. État runtime au 2026-07-18 16h UTC

**Trois vérités qui s'affrontent** :

| Source | n | WR | Pips | Lecture |
|---|---:|---:|---:|---|
| Décisions résolues (résolveur, hors live) | 8771 | 84.07 % | **+46 628** | 🟢 Backtest optimiste |
| Paper trades clôturés (vérité live batch) | 4817 | 23.67 % | **−47 327** | 🔴 **Catastrophe** |
| Phase E Platt+Beta calibration | 8771 | BSS=0.022 | — | 🟡 Calibration OK mais uplift fragile |

**Écart résolveur vs live : +94 000 pips.** C'est le nœud du problème.

### B. Distribution runtime

- **Décisions résolues** :
  - haussier : 6546 trades, WR 90.19 %, **+44 950 pips** ✅
  - baissier : 2225 trades, WR 66.07 %, +1 678 pips (résolveur optimiste vs paper trades catastrophique)
  - GBPUSD : 8572 / 8771 = **97.7 %** (quasi-monopole)
  - M15 : 8402 / 8771 = **95.8 %** (quasi-monopole)
  - NEUTRE : 8663 / 8771 = **98.7 %** (quasi-monopole)
  - Range : 2026-07-06 14h19 UTC → 2026-07-17 19h35 UTC (11 jours)

- **Paper trades clôturés** : 4817 total
  - 4751 datent du **2026-07-17** (jour catastrophe)
  - 8 datent du 2026-07-18
  - 58 datent du 2026-07-15
  - WR baissier : 1.21 % (3709 trades, −56 178 pips) — **STOPPÉ par motion long-only §15h35**
  - WR haussier : 98.83 % (1108 trades, +8 850 pips) — **edge théorique sain**
  - Resolution delay : 88 % en 0 min (batch replay, pas du live continu)

### C. Pipeline et kill switches actuels

- `capture_server` PID 9528, port 31685 LISTENING ✅
- 7 crons V9 Ready/Enabled ✅
- `V9_TRADER_MINI_ENABLED=1` (paper trade actif)
- `V9_GBPUSD_LONG_ONLY=1` (commit 48e0c14, neutralise baissier GBPUSD)
- `V9_NO_BAISSIERE=1` (commit a92f10d, neutralise baissier global)
- DB `v9_forces.db` : 2.6 GiB (Option B appliquée : −303 MiB, shadow triggered=0 purgées)
- `forces_snapshots last 1h = 0` (marché fermé jusqu'à dimanche 22h UTC, normal)

### D. Commits récents (git log --oneline -20)

```
ab238b1 chore(v9): sync .env (V9_NO_BAISSERE absent du HEAD actuel)
a92f10d feat(v9): no_baissiere_enabled kill switch + 11 tests (motion CEO §15h35)
c0aa416 fix(v9): kill PRICE_LAG boucle 17/07 (-47k pips) + audit document
1d4849f docs(v9): DECISIONS_LOG trace nettoyage scratchpad + .gitignore
42b3183 chore(v9): gitignore data/backups/ + scratchpad/ (-4.2 GB disk)
7b783c9 docs(v9): archive rapports audit DB + brief honnête ZCode (2026-07-18)
c6ff200 security(v9): untrack config/telegram.json.bak (token Hiphopvps_bot exposé)
d1edf86 security(v9): rédige token Telegram exposé dans DECISIONS_LOG (à révoquer BotFather)
ce381cf docs(v9): sync HEAD 0921c44 — activation P2+P3 effective
0921c44 feat(v9): activation P2 Position Manager + P3 Market Regime Global
250aee8 docs(v9): sync post-saut quantique agressif — DECISIONS_LOG + CHANGELOG (NO-GO)
43ea9d5 feat(v9): backtest + grid search agressif — verdict NO-GO (instabilité walk-forward)
852922d chore(v9): checklist + script réactivation dimanche 21h UTC
56072f8 fix(v9): reconstruction magnitude time-based (bisect) — 8770 décisions vs 22
90ddbee feat(v9): pyramiding — adaptateur facteur convergence
ae25778 docs(v9): sync STATE/CACHE_BOARD/AGENT/CHANGELOG/DECISIONS_LOG post-Phase E
f9a1454 feat(v9): sizing par confiance — Kelly fractionnel continu
cb5f258 feat(v9): Phase E Système Prédictif - skill + CLI + docs + kill switches + sync
9621a40 test(v9): Phase E Système Prédictif - 195 tests
bf93150 feat(v9): Phase E Système Prédictif - 5 modules core
```

### E. Modules livrés

| Phase | Module | Statut |
|---|---|---|
| **Phase E** | `v9_cycle_memory.py` (48 tests) | ✅ livré |
| **Phase E** | `v9_bayesian_predictor.py` (57 tests) | ✅ livré |
| **Phase E** | `v9_predictive_engine.py` (32 tests) | ✅ livré |
| **Phase E** | `v9_meta_strategy_optimizer.py` (32 tests) | ✅ livré |
| **Phase E** | `v9_learn_loop.py` (26 tests) | ✅ livré |
| **Phase F** | `v9_aggressive_strategy.py` | ⚠️ livré mais **NO-GO live** (OPUS verdict) |
| **Phase F** | pyramiding (réutilise PyramidingEngine) | ⚠️ livré mais **NO-GO live** |
| **Phase F** | `v9_sizing_confidence.py` (Kelly) | ⚠️ livré mais **NO-GO live** |
| Activation | `V9_GBPUSD_LONG_ONLY=1` (commit 48e0c14) | ✅ actif |
| Activation | `V9_NO_BAISSIERE=1` (commit a92f10d) | ✅ actif |
| Activation | P2 Position Manager + P3 Market Regime Global | ✅ motion CEO §15h30 |

### F. Doctrine (33 règles)

Lire `docs/DOCTRINE.md` intégralement. Points clés :
- R7 : tests verts avant commit, **0 régression**
- R14 : git = vérité (pas de narration non commitée)
- R18 : 100 % stdlib Python, **0 LLM** dans le cœur cognitif
- R22 : 1 périmètre = 1 livraison
- R26 : 1 commit + 1 DECISIONS_LOG entry par session
- R28 : motion CEO explicite avant commit
- R33 : Système Prédictif probabiliste (Bayésien, Calibré, Actionnable, Additif)

---

## 📚 Documents à lire EN PREMIER (avant audit)

1. `AGENTS.md` — rituel de démarrage
2. `SOUL.md` — philosophie + 5 piliers (dont Anticipation)
3. `docs/DOCTRINE.md` — 33 règles
4. `docs/ROADMAP.md` — Phases A-F
5. `docs/STATE.md` — état système + phase actuelle
6. `docs/architecture/PREDICTIVE_ENGINE.md` — archi Phase E
7. `docs/LECTURE_MARCHE_ASYMETRIE_2026-07-18.md` — lecture haussier/baissier
8. `docs/reports/PHASE_E_BILAN_FINAL_20260718.md` — bilan Phase E
9. `docs/reports/SYSTEME_PREDICTIF_BILAN_20260718.md` — synthèse
10. `docs/reports/uplift_bayesian_v2_20260718.md` — backtest edge=0.85
11. `docs/reports/learn_loop_v1_20260718.md` — walk-forward 5-fold
12. `workspace/perplexity/memory/DECISIONS_LOG.md` — historique (1000 dernières lignes)
13. `docs/audit/BAISSIER_AUDIT_FINAL_2026-07-18.md` — audit catastrophe
14. `docs/checklist/SUNDAY_REACTIVATION_20260719.md` — checklist dimanche
15. `CHANGELOG.md` (100 dernières lignes)

---

## 🎯 Mission : 8 axes d'audit edgefund

### **AXE 1 — Diagnostic de la désynchronisation résolveur vs live**

**Question** : Pourquoi le résolveur `ExitSimulator` prédit WR 84 % sur 8771 décisions, alors que le live batch (4751 paper trades du 17/07) avait WR 1.07 % ?

**Tâches** :
1. Lire `core/v9/exit_simulator.py` pour comprendre la mécanique de résolution (chemin de prix forward, fenêtre 4h, TP/SL hardcodés, etc.)
2. Identifier les hypothèses optimistes du résolveur
3. Comparer les `resolution_pips` (cappé 9.5) avec les vraies excursions OHLC depuis `forces_snapshots`
4. Quantifier le **biais d'optimisme** : combien de pips "fantômes" le résolveur a-t-il créés ?
5. Proposer un **mode "pessimiste"** du résolveur (high/low au lieu de mid)

**Livrable** : `docs/audit/RESOLVER_BIAS_20260718.md` (max 300 lignes)

### **AXE 2 — Calibration Phase E sur papier dégradé**

**Question** : Le `v9_bayesian_predictor.py` a été fit sur les 8771 décisions incluant les 4751 catastrophiques du 17/07. Le commit `c0aa416` (fix PRICE_LAG boucle) a-t-il été appliqué **avant** ou **après** le fit ? Si après, la calibration est biaisée.

**Tâches** :
1. Vérifier l'ordre des commits (c0aa416 vs cb5f258/bf93150)
2. Si le fit est postérieur à c0aa416 : audit acceptable
3. Si le fit est antérieur : **re-fit immédiat** sans les 4751 trades catastrophiques
4. Comparer Platt(a,b) et BSS avant/après exclusion
5. Re-mesurer l'uplift walk-forward avec la calibration corrigée

**Livrable** : section dans `docs/audit/RESOLVER_BIAS_20260718.md` ou nouveau `CALIBRATION_AUDIT_20260718.md`

### **AXE 3 — Quasi-monopole GBPUSD/M15/NEUTRE — diversification edgefund**

**Question** : Le système est à 97.7 % GBPUSD, 95.8 % M15, 98.7 % NEUTRE. **Aucune diversification edgefund possible** sur cette base.

**Tâches** :
1. Analyser pourquoi les autres paires (EURUSD, USDJPY, USDCHF, AUDUSD, USDCAD) ne sont jamais déclenchées
2. Vérifier `core/v9/principle_engine.py` et `_load_shared_context` : est-ce un bug de routing ou un manque de triggers ?
3. Quantifier le potentiel edgefund : combien de paper trades par jour par paire faudrait-il pour avoir une diversification viable (≥ 100 trades/paire/semaine) ?
4. Proposer un plan de diversification : quels principes / seuils activer sur les autres paires ?
5. **Rédiger une "diversification policy"** dans `docs/architecture/DIVERSIFICATION_EDGEFUND.md`

**Livrable** : `docs/architecture/DIVERSIFICATION_EDGEFUND.md` (plan chiffré)

### **AXE 4 — Boucle re-entry (déjà fixée, à valider)**

**Question** : Le commit `c0aa416 fix(v9): kill PRICE_LAG boucle 17/07` est censé tuer la boucle re-entry qui a coûté −47k pips. **Est-ce vraiment fixé ? Y a-t-il d'autres boucles potentielles ?**

**Tâches** :
1. Lire `c0aa416 fix(v9): kill PRICE_LAG boucle 17/07 (-47k pips) + audit document`
2. Identifier la cause exacte de la boucle
3. Vérifier qu'aucune autre combinaison (autres principes × autres regimes) ne peut boucler
4. Proposer un **garde-fou générique anti-boucle** : max N trades par (symbol, direction) sur fenêtre glissante M minutes
5. **Implémenter** ce garde-fou en R2 additif (nouveau kill switch `V9_MAX_TRADES_PER_WINDOW`)

**Livrable** : `core/v9/v9_loop_breaker.py` + tests + `docs/architecture/LOOP_BREAKER.md`

### **AXE 5 — TP/SL dynamiques vs hardcodés TP=8/SL=15**

**Question** : Le résolveur utilise TP=8/SL=15 (RR 0.53, edge négatif). Phase F agressive a livré TP dynamique mais verdict NO-GO. **Quel est le bon TP/SL pour un edge sustainable ?**

**Tâches** :
1. Analyser les magnitudes réelles des mouvements GBPUSD M15 NEUTRE (OHLC high-low sur 11 jours)
2. Définir une **stratégie TP/SL modérée** : TP=P75 magnitude, SL=vol_atr × 1.5 (bornes R30 : TP ∈ [5, 20], SL ∈ [5, 20])
3. Tester en paper-trade batch replay sur les 8771 décisions
4. Comparer avec TP=8/SL=15 baseline et avec Phase F agressive
5. Si uplift net (WR ≥ +5 pts ET PF ≥ +1.5) : **commit + activation live** dimanche 22h UTC
6. Sinon : documenter NO-GO et archiver

**Livrable** : `core/v9/v9_moderate_strategy.py` (R2 additif) + tests + `docs/reports/MODERATE_STRATEGY_20260718.md`

### **AXE 6 — Phase E live calibration dimanche 22h UTC**

**Question** : La motion long-only est active. Dimanche 22h UTC, le marché rouvre. Comment orchestrer le passage en live avec un système qui a +94k pips d'écart résolveur/live ?

**Tâches** :
1. Rédiger un **"live calibration playbook"** :
   - T+0 (réouverture) : vérifier MT4, capture_server, kill switches
   - T+1h : premier snap décisions live vs paper trades
   - T+24h : bilan haussier-only
   - T+7j : WR cible ≥ 95 % sur trades haussiers (vs 98.83 % backtest)
2. Définir les **kill switches d'urgence** :
   - DD > -200 pips sur 24h → `V9_TRADER_MINI_ENABLED=0`
   - WR live < 80 % sur 50 trades → `V9_TRADER_MINI_ENABLED=0` + alerte
   - WR live < 60 % sur 50 trades → `V9_GBPUSD_LONG_ONLY=0` + arrêt total
3. **Implémenter** un watchdog live dans `core/v9/v9_live_watchdog.py` (R2 additif)

**Livrable** : `docs/architecture/LIVE_CALIBRATION_PLAYBOOK.md` + `core/v9/v9_live_watchdog.py`

### **AXE 7 — Token Telegram exposé dans l'historique git**

**Question** : `d1edf86 security(v9): rédige token Telegram exposé dans DECISIONS_LOG (à révoquer BotFather)` — le token est rédigé dans le fichier mais **reste dans l'historique git**.

**Tâches** :
1. Identifier TOUS les tokens Telegram exposés dans l'historique (chercher `AAEP7_`, `8790798269:`, etc.)
2. Lister les commits concernés
3. **Recommander** un `git filter-repo` pour nettoyer l'historique (R28 motion CEO obligatoire)
4. **OU** recommander de ne PAS nettoyer (risque de casser le remote et la traçabilité)
5. Documenter la décision

**Livrable** : `docs/security/TOKEN_HISTORY_AUDIT_20260718.md`

### **AXE 8 — Plan d'optimisation edgefund final**

**Question** : Au terme de cet audit, V9 peut-il devenir un système edgefund ? Quelles sont les 3-5 actions critiques pour y arriver ?

**Tâches** :
1. Synthétiser les résultats des axes 1-7
2. Produire un **plan d'optimisation chiffré** avec :
   - 3-5 actions critiques (chacune avec owner, deadline, criterion de succès)
   - Budget edgefund cible (ex : WR ≥ 70 %, PF ≥ 3, Sharpe ≥ 1, DD ≤ -300 pips)
   - Timeline (T+1j, T+1sem, T+1mois, T+3mois)
3. Décision GO / NO-GO / MARGINAL sur l'edgefund
4. Si GO : quels modules prioritaires à commit en live dimanche 22h UTC

**Livrable final** : `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` (~500 lignes, doc de référence)

---

## 🔧 Garde-fous de la mission

### Doctrine stricte (R7, R14, R18, R22, R26, R28)

- **R7** : tests verts avant commit, **0 régression tolérée**
- **R14** : git = vérité — chaque affirmation chiffrée doit être vérifiable par SQL ou git log
- **R18** : **0 LLM dans le cœur cognitif**. Pas d'appel à Anthropic / OpenAI / Ollama dans `core/v9/`. Tu peux utiliser un LLM pour la **rédaction** (DECISIONS_LOG, docs) mais pas pour le **raisonnement trading**.
- **R22** : 1 axe = 1 périmètre = 1 livraison atomique (commit par axe)
- **R26** : 1 commit + 1 DECISIONS_LOG entry par axe
- **R28** : motion CEO explicite enregistrée AVANT tout commit. Si une nouvelle motion est nécessaire en cours d'audit, ESCALADE à Søn

### Critères d'arrêt

- ❌ **Régression** tests existants (2157 verts baseline + 11 no_baissiere = 2168) → STOP, fixer d'abord
- ❌ **Découverte critique** (ex : calibration post-catastrophe biaisée) → STOP, escalade immédiate
- ❌ **>2h bloqué** sur un axe → documente et passe à l'axe suivant
- ❌ **motion CEO usurpée** (committer sans motion) → STOP total

### Anti-patterns

- ❌ **Modifier `core/v9/config.py`** (R30 strict) — borne les kill switches
- ❌ **Modifier `core/v9/order_executor.py`** (Phase 12 gelée — pas d'exécution réelle)
- ❌ **Modifier les YAML principes** (R23 strict)
- ❌ **Touch aux `core/v9/v9_cycle_memory.py`, `v9_bayesian_predictor.py`, `v9_predictive_engine.py`, `v9_meta_strategy_optimizer.py`, `v9_learn_loop.py`** (Phase E déjà committée, additif strict)
- ❌ **Inventer des modules fictifs** (cf Hermès) — si tu crées un persona, déclare-le explicitement dans le commit message

---

## 📐 Critères chiffrés de succès (par axe)

| Axe | Critère | Cible | Bonus |
|---|---|---:|---|
| 1 | Quantification biais résolveur | ≥ 30 % du spread live/backtest expliqué | +20 % si mode pessimiste livré |
| 2 | Calibration corrigée | BSS post-correction ≥ +0.05 vs baseline | Walk-forward std ≤ 5 pts |
| 3 | Diversification | ≥ 3 paires avec ≥ 50 trades/semaine | Roadmap chiffrée |
| 4 | Boucle re-entry | Aucun commit avec boucle identique | Garde-fou générique livré |
| 5 | TP/SL modérés | WR ≥ 80 %, PF ≥ 3, DD ≤ -300 sur 8771 replay | +10 si Sharpe ≥ 1 |
| 6 | Live playbook | 3 seuils d'arrêt, watchdog livré | Activation dimanche OK |
| 7 | Token audit | Liste exhaustive + recommandation chiffrée | Nettoyage si motion |
| 8 | Plan edgefund | GO / NO-GO / MARGINAL avec 3-5 actions | Timeline + budget chiffré |

**Score total possible** : 8 axes × 100 points = 800 points + bonus.

**Score cible** : ≥ 600/800 pour que Søn accepte la livrable finale.

**Si < 600/800** : NO-GO edgefund, archive l'audit et passer en mode « stabilisation ».

---

## 🎬 Workflow d'exécution (8 étapes)

### Étape 0 : Initialisation

```bash
git pull --rebase
python -m pytest tests/ -q --tb=line  # baseline 2168 verts attendus
```

Si moins de 2168 verts → STOP, fixer d'abord.

### Étape 1 : Axes 1-7 (audit proprement dit)

Pour chaque axe :
1. Lire les docs/docs existants
2. Faire l'analyse chiffrée
3. Écrire le livrable (chemin indiqué)
4. Si modification de code : créer la branche feature, écrire les tests, commit

### Étape 2 : Axe 8 (synthèse)

Après les 7 axes, produire `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` :
- 1 page résumé exécutif
- 1 tableau scoring par axe
- 3-5 actions critiques chiffrées
- Décision GO/NO-GO/MARGINAL

### Étape 3 : Commit et push

1 commit par axe + 1 commit final de synthèse (R22 strict).

### Étape 4 : Validation motion CEO

Avant push du commit final, **escalade à Søn** avec :
- Résumé du scoring (≥ 600 ?)
- Décision GO/NO-GO/MARGINAL
- 3-5 actions critiques chiffrées

**Pas de push sans motion CEO explicite** (R28).

---

## 🎓 Anti-hubris

- **Tu peux échouer.** Si tu trouves que V9 ne peut PAS devenir edgefund, dis-le. **L'honnêteté prime sur le narratif.**
- **Tu peux escalader.** Si tu découvres quelque chose de bloquant (ex : calibration irrémédiablement biaisée), **STOP et escalade immédiatement**.
- **Tu peux proposer NO-GO.** Le verdict NO-GO sur Phase F (commit 43ea9d5) a été **la bonne décision** d'OPUS. **Recommandation équivalente ici = courage, pas échec.**

---

## 🎯 Søn — motion CEO attendue

Avant de lancer OPUS, **tranche les questions suivantes** :

1. **« oui go full audit 8 axes »** : OPUS exécute les 8 axes, livrable final = EDGEFUND_AUDIT_FINAL_20260718.md
2. **« oui go axes 1-4 seulement »** : focus diagnostic + diversification, skip TP/SL et live playbook (déjà travaillés par Hermès)
3. **« oui go axe 8 seulement »** : juste le plan d'optimisation final, sans diagnostic profond (économie de temps)
4. **« non, attends »** : pas d'audit maintenant, focus sur dimanche 22h UTC

**Recommandation ZCode** : **option 2 (axes 1-4)** — diagnostic + diversification sont les 2 angles morts les plus critiques. Axe 8 (plan final) sera dérivé naturellement des 4 diagnostics.

**Mais à toi Søn.**

---

*Prompt rédigé le 2026-07-18 16h UTC par ZCode, à la demande de Søn « lis tous les documents pour le contexte, fait le bilan et propose pour opus un audit complet pour optimisation edgefund ».*

*Doctrine : R7, R8, R14, R18, R22, R26, R28. Motion CEO attendue avant lancement.*

*Bilan runtime au 2026-07-18 16h UTC : paper trades -47 327 pips live, backtest +46 628 pips. Edge haussier +8 850 pips théorique. Système non rentable aujourd'hui mais structure d'optimisation viable sous motion long-only.*
