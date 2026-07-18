# 🗺️ Roadmap PowerFlow V9 — Phase B/C/D et au-delà


> **Note CEO 2026-07-18** : MT4 = plateforme de lecture de l'indicateur SDI (ticks/volumes spécifiques). MT5 n'est PAS implémenté.

> **État actuel** : commit `48e0c14` (2026-07-18 09:14 UTC) — V9_GBPUSD_LONG_ONLY=1
> **Contexte** : capture server mort depuis 9h, dernière décision live = 14/07
> **Doctrine** : R22 (1 périmètre = 1 livraison), R25' (kill switch par feature, OFF par défaut)

---

## 🎯 Vue d'ensemble — 4 phases opérationnelles

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE A (livrée 2026-07-18) : NEUTRALISER LE RISQUE          │
│ ✅ V9_GBPUSD_LONG_ONLY=1 (kill switch ON)                   │
│ ✅ BearPerception SHADOW (V9_BEAR_PERCEPTION_ENABLED=0)     │
│ ✅ Filtre devise SHADOW (V9_CONSTITUTIVE_CURRENCY_FILTER=0) │
│ ✅ Dashboard baissier + monitoring doc                      │
│ ✅ 250 tests verts, 8 commits pushés                        │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE B (T+7 à T+30 jours) : VALIDER LES SHADOW MODES       │
│ ⏳ Redémarrer capture server (priorité #1 immédiat)         │
│ ⏳ 60 jours de shadow mode BearPerception (log only)         │
│ ⏳ 60 jours de filtre devise source (gated)                 │
│ ⏳ Daily monitoring long_only (cf MONITORING_LONG_ONLY.md)  │
│ ⏳ Revues hebdo T+7, T+14, T+21, T+30                      │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE C (T+30 à T+90 jours) : ACTIVER SI EDGE CONFIRMÉ     │
│ ⏸️ BearPerception SHADOW → ON (si would_skip sauve ≥ 30%)  │
│ ⏸️ Filtre devise source ON (si couche diversify repensée)   │
│ ⏸️ Long-only GBPUSD désactivé si edge baissier fixé         │
│ ⏸️ Walk-forward monthly (validé Phase A — bonus subagent)   │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE D (T+90 à T+180 jours) : ÉTENDRE LE PÉRIMÈTRE          │
│ ⏸️ Audit baissier root cause (filtrer à la source)         │
│ ⏸️ Étendre long-only aux autres paires haussières fortes    │
│ ⏸️ Étendre bear_perception à USDJPY/EURUSD si besoin       │
│ ⏸️ Mode "régime de marché" (A/B/C adaptatif automatique)   │
└──────────────────────────────────────────────────────────────┘
```

---

## 🚨 PHASE 0 (URGENT — 2026-07-18, maintenant)

### 🔴 Action #1 — Redémarrer le capture server

**Statut** : Capture server MORT depuis 9h (dernier bar M5 = 23:57 UTC hier).
Le pipeline de décision est gelé. Aucune nouvelle décision live n'est générée.

```bash
# Diagnostic (skill daemon-mort)
tasklist //FI "IMAGENAME eq python.exe"   # chercher capture_server
curl http://127.0.0.1:31685/test 2>&1    # socket connect

# Fix
python -m core.v9.capture_server &       # foreground (recommandé)
python scripts/v9_ops.py start           # ou via v9_ops

# Vérification
tasklist //FI "IMAGENAME eq python.exe"
curl http://127.0.0.1:31685/test
```

**Risque si non fait** : `V9_GBPUSD_LONG_ONLY=1` ne peut pas être validé
(0 décision GBPUSD générée). Phase B bloquée.

### 🔴 Action #2 — Diagnostic capture server mort

Identifier pourquoi le capture server est tombé. Hypothèses :
- Crash OOM (DB grossit)
- Reboot Windows sans AutoStart
- Bug MT4 (Expert Advisor désynchronisé)
- Perte réseau (MT4 ↔ EA ↔ Python daemon)

Skill de référence : `powerflow-v9-live-ops` §9 (daemon-mort).

---

## 📋 PHASE A (LIVRÉE ✅ — 2026-07-18)

### ✅ Réalisations

| Composant | Statut | Commit |
|---|---|---|
| `V9_GBPUSD_LONG_ONLY=1` | 🟢 ACTIF | `48e0c14` |
| BearPerception SHADOW | 🟡 SHADOW | `fa8b4e9` |
| Filtre devise SHADOW (gated) | 🟡 SHADOW | `fa8b4e9` |
| Dashboard baissier (2 endpoints) | 🟢 LIVRÉ | `fa8b4e9` |
| Walk-forward validation | 🟢 LIVRÉ | `fa8b4e9` |
| Doc lecture de marché (17 KB) | 🟢 LIVRÉ | `124649e` |
| Doc audit final (266 lignes) | 🟢 LIVRÉ | `fa8b4e9` |
| Doc monitoring long_only (6 KB) | 🟢 LIVRÉ | `48e0c14` |
| 250/250 tests verts | 🟢 OK | cumulé |
| 9 subagents Opus délégués | 🟢 INTÉGRÉS | — |

### ✅ Stack final

- 12 modules core (strategy_pole, drawdown_protector, risk_parity, monte_carlo,
  auto_promotion, telegram_alerts, dashboard_api, portfolio_risk_manager,
  edge_validator, speed_bias_analyzer, bear_perception, bear_strategy,
  movement_analyzer)
- 12 MCP tools (strategy_pole 11 + hedge_fund_summary 1)
- 7 skills catalogue Hermes
- 9 endpoints dashboard live
- 3 crons Windows actifs
- 8 commits CEO sur `feat/v9-foundation-clean`

---

## 📅 PHASE B (T+7 à T+30 jours) — VALIDATION SHADOW

### 🎯 Objectifs

1. **Valider BearPerception** : 60 jours de shadow mode, mesure would_skip vs réel
2. **Valider filtre devise** : 60 jours de gated mode, mesure pollution NZD/AUD
3. **Valider long_only** : 60 jours avec edge haussier GBPUSD confirmé
4. **Redémarrer capture server** : prérequis absolu

### 📋 Tâches (par priorité)

#### B1 — Redémarrer capture server + monitoring 24/7

**Action immédiate** :
- `v9_ops.py start` ou `python -m core.v9.capture_server`
- Vérifier que `forces_snapshots` se remplit (SELECT COUNT(*) WHERE bar_time > now)
- Cron monitoring toutes les 10 min : alerte Telegram si 0 snapshot depuis 30 min

**Livrable** : cron `V9_CaptureServerMonitor` (via schtasks)

#### B2 — Daily monitoring long_only

**Action quotidienne** :
```bash
# Snapshot quotidien
PYTHONPATH=. python -c "
from core.v9.v9_bear_dashboard import bear_stats
print(bear_stats(r'C:\projet\V9\data/v9_forces.db', 'GBPUSD'))
"
```

**Métriques trackées** (cf `MONITORING_LONG_ONLY_2026-07-18.md`) :
- WR GBPUSD haussier (cible ≥ 95%)
- Pips GBPUSD haussier cumulé
- Drift GBPUSD (cible > 0)
- long_only_override_count

**Livrable** : `data/monitoring/long_only_daily.json` (snapshot quotidien)

#### B3 — Validation BearPerception (60 jours)

**Mesure** : pour chaque décision baissière GBPUSD, comparer :
- Trade actuel (perte) vs trade avec `would_skip=True` (sauvé)
- Trade actuel (perte) vs trade avec `would_exit` fast (moins de perte)

**Critères d'activation Phase C** :
- `would_skip` aurait sauvé ≥ 30% des trades perdants
- `would_exit` aurait amélioré avg_pips de ≥ 20%

#### B4 — Validation filtre devise (60 jours)

**Mesure** : avec et sans filtre, comparer :
- Distribution haussier/baissier par symbole
- Ratio decision.currency IN (base,quote) / total

**Critères d'activation Phase C** :
- Filtre source ne casse pas la couche diversify (pas de régression sur
  principle_scores, regime_snapshots, etc.)

#### B5 — Revues hebdo

**Tous les lundis** (T+7, T+14, T+21, T+30) :
- Revue métriques long_only
- Décision maintenir/désactiver
- Update DECISIONS_LOG §6.X si décision

---

## 🚀 PHASE C (T+30 à T+90 jours) — ACTIVATION CONDITIONNELLE

### 🎯 Conditions d'activation

Chaque kill switch passe de SHADOW → ON **uniquement si** :
1. Validation Phase B ≥ 30 jours positive
2. Décision CEO explicite (motion "go X")
3. Tests verts + push

### 📋 Tâches

#### C1 — Activer `V9_BEAR_PERCEPTION_ENABLED=1`

Si would_skip sauve ≥ 30% des trades perdants.

**Implémentation** : changer `0` → `1` dans env.
**Effet attendu** : trade_engine utilise `should_skip_bearish()` au lieu de logger.
**Risque** : si bug, peut skipper des trades gagnants. R6 défensif en place.

#### C2 — Activer `V9_CONSTITUTIVE_CURRENCY_FILTER=1`

Si filtre source ne casse pas la diversify + améliore ratio décisions/symbole.

**Pré-requis** : repenser la couche diversify 17/07 (actuellement elle
exige les 8 devises). Subagent Phase A a noté ce conflit R22.

**Action** : créer `v9_diversify_v2.py` qui :
- Garde 8 devises pour apprentissage (R22 diversify)
- Mais filtre le vote d'arbitrage par devise constitutive

#### C3 — Désactiver `V9_GBPUSD_LONG_ONLY=0` si root cause baissier fixé

Si l'audit root cause a résolu le bug baissier (cf Phase D), désactiver le
long-only et laisser l'arbiter émettre naturellement.

#### C4 — Walk-forward monthly (bonus subagent déjà livré)

Le module `core/v9/walk_forward.py` est livré. L'activer :
```bash
# Mensuel
python scripts/v9_walk_forward.py --report
```

Effet : valide que les stratégies catalogue restent robustes hors-sample.

---

## 🔬 PHASE D (T+90 à T+180 jours) — ÉTENDRE LE PÉRIMÈTRE

### 🎯 Objectifs

1. **Auditer les 5 autres paires** (EURUSD, USDJPY, AUDUSD, USDCAD, USDCHF)
2. **Étendre long_only** aux paires haussières fortes
3. **Étendre BearPerception** aux paires à drift baissier
4. **Mode "régime" automatique** : classification A/B/C adaptative

### 📋 Tâches

#### D1 — Audit multi-paires

Pour chaque paire (EURUSD, USDJPY, AUDUSD, USDCAD, USDCHF) :
- Distribution haussier/baissier
- Drift quotidien
- WR historique
- Décision : activer long_only ou bear_perception ?

**Livrable** : `docs/audit/MULTI_PAIR_AUDIT_2026-XX-XX.md`

#### D2 — `v9_regime_classifier.py` (nouveau)

Module qui classifie automatiquement le régime de marché (A/B/C) :
- Détecte drift haussier → mode A
- Détecte drift baissier → mode C
- Sinon → mode B

**Input** : 30 jours de paper_trades + forces_snapshots
**Output** : `regime = 'A' | 'B' | 'C'`
**Action** : adapte automatiquement la stratégie (long_only, short_only, range)

**Câblage** : dans `trade_engine.process()` après arbiter.

#### D3 — Étendre long_only multi-paires

```bash
# Long-only sur toutes les paires haussières fortes
V9_LONG_ONLY_SYMBOLS=GBPUSD,EURUSD,USDJPY
```

#### D4 — Étendre bear_perception multi-paires

```bash
V9_BEAR_PERCEPTION_SYMBOLS=GBPUSD,USDJPY,USDCHF
```

---

## 🧪 PHASE E (T+180 à T+365 jours) — NIVEAU INSTITUTIONNEL

### 🎯 Niveau hedge fund mondial

1. **Multi-stratégie** : strategy_pole + regime_classifier + sentiment analysis
2. **Portfolio risk** : corrélation inter-paires, VaR, CVaR
3. **Exécution réelle** : passage simulation → live (si R25' validé)

### 📋 Tâches (hors R22 — Phase 12 gelée)

- `v9_sentiment_analyzer.py` : NLP news + sentiment
- `v9_correlation_engine.py` : corrélation inter-paires
- `v9_var_calculator.py` : Value at Risk historique + Monte Carlo
- `v9_execution_engine.py` : bridge MT4 pour exécution réelle (Phase 12)

---

## 📋 Backlog — Améliorations continues

### 🔧 Qualité code

| Item | Priorité | Effort |
|---|---|---|
| Tests slow `test_v9_baissier_audit.py` à fix | 🟠 P1 | 1h |
| Refactor `principle_engine.py` (boucle 8 devises) | 🟠 P1 | 4h |
| Mettre à jour `principle_evaluations` post-fix devise | 🟠 P1 | 2h |
| Cleanup `data/v9_forces.db` (1.5 GB → optimiser) | 🟡 P2 | 2h |

### 📚 Documentation

| Item | Priorité | Effort |
|---|---|---|
| Tutoriel "comment ajouter un principe YAML" | 🟡 P2 | 1h |
| Runbook capture server mort (déjà skill) | 🟢 OK | — |
| Diagramme architecture V9 | 🟡 P2 | 2h |

### 🧪 Tests

| Item | Priorité | Effort |
|---|---|---|
| Tests d'intégration DB (init schema) | 🟠 P1 | 3h |
| Tests performance (regression < 100ms) | 🟡 P2 | 2h |
| Tests E2E paper-trade bout-en-bout | 🟠 P1 | 4h |

### 🔌 Outils

| Item | Priorité | Effort |
|---|---|---|
| Telegram alertes (déjà livré, à activer) | 🟠 P1 | 30min |
| Cron monitoring capture server (cf B1) | 🟠 P1 | 30min |
| Dashboard Grafana (optionnel) | 🟢 P3 | 8h |

---

## 📊 Indicateurs de succès (KPIs)

### Phase B (T+30 jours)

- Capture server uptime ≥ 95%
- Daily monitoring actif (1 snapshot/jour dans `data/monitoring/`)
- 0 régression tests
- WR GBPUSD haussier ≥ 95% (cible)

### Phase C (T+90 jours)

- BearPerception ON si validation OK
- Filtre devise ON si validation OK
- WR global stable ou amélioré
- Drawdown < 5% capital

### Phase D (T+180 jours)

- 3+ paires avec edge confirmé (WR > 70%)
- Drift haussier documenté sur 5 paires
- Mode régime adaptatif opérationnel

---

## 🎯 Décisions CEO prioritaires (immédiat)

| Priorité | Motion | Statut |
|---|---|---|
| 🔴 P0 | Redémarrer capture server | **À FAIRE IMMÉDIATEMENT** |
| 🟠 P1 | Activer monitoring daily | Manuel, T+1 |
| 🟠 P1 | Décider extension long_only EUR/USDJPY | T+30 |
| 🟡 P2 | Activer BearPerception (si Phase B OK) | T+60 |
| 🟢 P3 | Diversification multi-paires Phase 12 | T+180 |

---

## 📚 Références

- `DECISIONS_LOG.md` §6.1 → §6.10 : historique décisions
- `docs/STATE.md` : état live système
- `docs/audit/BAISSIER_AUDIT_FINAL_2026-07-18.md` : audit Phase A
- `docs/LECTURE_MARCHE_ASYMETRIE_2026-07-18.md` : philosophie lecture
- `docs/monitoring/MONITORING_LONG_ONLY_2026-07-18.md` : KPIs Phase B
- Skill `powerflow-v9-live-ops` : opérations capture server

---

*Roadmap rédigée le 2026-07-18 par Hermes sur motion CEO.*
*À réviser tous les 30 jours ou après chaque livraison majeure.*

> *"La roadmap n'est pas une carte figée — c'est un compas qui s'oriente selon les vents."*