# PowerFlow V10 — Système Cognitif Forex

> **Statut : 2026-08-10 12:28 CEST**
> Branche principale : `feat/v10-c20-healthy` | HEAD : `748177d`
> Tests : **1325/1325** ✅ | Shadow : pipeline complet actif
> **R10 maintenu — aucun capital réel engagé**

---

## Mission

Système cognitif financier auto-apprenant pour le trading Forex.
Lecture multi-facteurs (Fatman, VSA, Wyckoff, SMC, ICT, multi-TF).
Décisions autonomes en mode shadow — capital réel uniquement sur mandat Søn CEO.

> **Règle absolue** : Ne jamais engager de capital réel sans décision explicite de Søn.

---

## 📊 État actuel — 10/08/2026

| Composant | Statut |
|---|---|
| Tests | ✅ 1325/1325 |
| Modules C11-C20 | ✅ 56 modules |
| ShadowTrader | 🔄 En cours — pipeline complet, WR 0.50 réaliste |
| DeploymentValidator | ✅ Score 83.33 |
| SystemHealthChecker | ✅ 13/13 OK |
| IBKR LiveConnector | ❌ Non connecté (décision Søn) |
| Capital réel | ❌ R10 maintenu |

---

## 🧠 Architecture V10

### Pipeline de décision (7 couches)
```
Signal brut
  ↓ 1. Filter Compositor (session/OTE/SMC/régime)
  ↓ 2. Risk Shield + Net Exposure
  ↓ 3. RL Score (upgrade A3→A2 si score ≥ 0.55)
  ↓ 4. Grammar V9 (patterns Fatman Bible)
  ↓ 5. Fractal Context (multi-TF boost/veto)
  ↓ 6. Wyckoff Gate (VSA consolidé)
  ↓ 7. Structure S1-S9 (BOS/CHoCH)
  ↓
Décision : BUY/SELL (A1/A2) | WAIT (A3/NONE)
```

### Modules intelligence
- **Bayesian Recalibrator** — ajustement dynamique des seuils
- **RL Adapter + Promotion** — reinforcement learning par paire/TF
- **Regime HMM** — détection tendance/range/transition
- **Error Learner + Learning Continuum** — mémoire des erreurs
- **Meta Optimizer** — optimisation des paramètres globaux

---

## 🚦 Gate GO LIVE — Progression

| Critère | Statut |
|---|---|
| Tests ≥ 1310 | ✅ 1325 |
| simulation_tested ≥ 50 | ✅ 100+ |
| win_rate_ok | ✅ |
| sharpe_ok | ✅ 0.42 |
| wfa_robust | ✅ True |
| broker_connected | ❌ Søn : connexion IBKR ou MT4 |
| feed_active | ❌ Søn : FeedHandler C19 |
| **Score DV** | **83.33 / 100** |
| **R10 levée** | **Décision Søn après 200 trades shadow validés** |

---

## 📚 Documents piliers

| Document | Contenu |
|---|---|
| `DOCTRINE_PERFORMANCE.md` | Règles P1-P7 — pipeline complet, anti-proxy, alarmes |
| `ORCHESTRATION_STATE.md` | État live branches + roadmap GO LIVE |
| `DECISIONS_LOG_2026_08_10.md` | Toutes les décisions structurantes du jour |
| `AGENTS.md` | Rôles Hermes / ZCode / Perplexity / Søn |
| `docs/V10/STATE.md` | État technique détaillé V10 |

---

## 📝 10 Règles V10 (R1-R10)

| Règle | Principe |
|---|---|
| R1 | Doctrine première — une règle claire vaut mieux que 10 floues |
| R2 | Additif strict — jamais modifier un module existant, toujours ajouter |
| R3 | Audit trail — tout commit est traçable et réversible |
| R4 | Tests d’abord — aucune fonctionnalité sans test |
| R5 | Un module = une responsabilité |
| R6 | Fail-open — exception → log + continuer, jamais crasher |
| R7 | Honnêteté métrique — aucune métrique mock sans label explicite |
| R8 | Infrastructure séparée du code métier |
| R9 | Source de vérité unique — un seul endroit par information |
| **R10** | **Capital réel = mandat Søn CEO uniquement** |

---

## ⚡ Lancer rapidement

```bash
# Vérifier l'état système
python scripts/run_deployment_validator_10_08.py

# ShadowTrader pipeline complet
python scripts/run_shadow_continuous.py

# Dashboard métriques (ZCode, bientôt)
python scripts/shadow_dashboard.py

# Tests complets
pytest tests/test_v10_*.py -q
```

---

## 📖 Historique V9 (archivé)

V9 a été killé le 10/08/2026 après audit : 336 trades, WR 44.51%, PnL -865 pips.
L’architecture V10 remplace intégralement V9. Les rapports V9 sont conservés dans `reports/BILAN_*.md` pour audit historique uniquement.

---

*PowerFlow V10 — Søn CEO + Perplexity No-Limit + Hermes + ZCode — 2026-08-10*
