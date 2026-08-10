# ORCHESTRATION STATE — PowerFlow V10

> Maintenu par Perplexity CEO No-Limit
> Dernière mise à jour : **2026-08-10 13:40 CEST**

---

## 🗺️ État branches — 13:40 CEST

| Branche | HEAD | Tests | Statut |
|---|---|---|---|
| `feat/v10-c20-healthy` | `8017be3` | ✅ 1292/24* | 🟢 **PRINCIPALE** |
| `feat/v10-unified` | `8845191` | ✅ 1325/1325 | ✅ Merged |
| `feat/replay-fullstack-v10` | `d2ccca2` | ✅ 1310/1310 | ✅ Live |
| `feat/v9-foundation-clean` | — | ✅ docs | ✅ Orchestration |

*24 échecs environnementaux (DB vide worktree .c20-test) — passent sur worktree principal avec vraie DB 18GB.

---

## Edge M15 — 10/08/2026 13:34 CEST

Paires actives  : EURUSD / USDCAD / USDCHF (M15 uniquement)
WR replay       : 59.35% | PF : 1.925 | Sharpe : 0.256
Blacklist        : USDJPY (WR 20%) + GBPUSD H1/M30 + toutes paires H1/M30
Statut          : LIVE_GATE_OPEN (WR≥0.48 & PnL>0)
Validation OOS  : TERMINÉE — WFA_MARGINAL
Décision R10    : ATTENTE revue WFA (WR moyen 51.64% < cible 52% stable)

### Test filtre régime HMM (H3/H4) — 14:17 CEST → RÉFUTÉ

Hypothèse : filtrer RANGING/VOLATILE améliore l'edge. **Réfutée honnêtement.**
- Replay + régime : WR 55.13% (vs 59.74% sans) — **dégrade**, 1198 trades filtrés
- WFA + régime : WR moyen 53.55% ± 12.03%, 1/3 fenêtres ≥52% — WFA_MARGINAL
- Le filtre réduit trop le volume (73 trades vs 171) et n'améliore pas la stabilité
- Conclusion : l'edge M15 n'est PAS robuste au régime — pas de GO LIVE R10

### Résultat Walk-Forward hors-échantillon (WFA M15) — 13:38 CEST

Méthode : 5 fenêtres non-chevauchantes de 160 barres sur 800 barres M15,
ReplayEngine C10, EURUSD/USDCAD/USDCHF, session LONDON.

| Fenêtre | n_trades | WR | PF | Sharpe |
|---|---|---|---|---|
| w1 | 24 | 62.50% | 3.155 | 0.457 |
| w2 | 16 | 50.00% | 1.614 | 0.181 |
| w3 | 10 | 40.00% | 0.919 | -0.037 |
| w4 | 47 | 48.94% | 0.922 | -0.034 |
| w5 | 74 | 56.76% | 2.177 | 0.296 |

**Verdict : WFA_MARGINAL**
- WR moyen : 51.64% ± 7.61% | PF moyen : 1.757 | Sharpe moyen : 0.173
- Fenêtres WR ≥ 0.52 : 2/5
- Auto-audit P5 : all_ok=True (WR moyen ≥ 0.50), mais **ni WFA_PASS (4/5) ni WFA_FAIL (<0.50)**

**Lecture honnête** : le WR replay post-hoc 59.35% (sélection EURUSD/USDCAD/USDCHF)
ne se confirme PAS pleinement hors-échantillon. 2/5 fenêtres ≥ 52%, 3/5 < 52%.
W3 et W4 (fenêtres médianes) sont en perte → instabilité temporelle de l'edge.

---

## 🚦 Gate GO LIVE — Roadmap

| # | Critère | Statut | Prochaine action |
|---|---|---|---|
| 1 | Tests ≥ 1310 | ⚠️ 1292/24 env | Rétablir DB `.c20-test` |
| 2 | 56 modules C11-C20 | ✅ | — |
| 3 | API RecalibDecision | ✅ | — |
| 4 | Kill audit V9 | ✅ | — |
| 5 | StaleGuard | ✅ | — |
| 6 | DataGapValidator | ✅ | — |
| 7 | Learning cycle | ✅ | — |
| 8 | Port 31685 | ✅ | — |
| 9 | EURUSD HTF | ✅ récupéré | — |
| 10 | simulation_tested | ✅ 50 trades | — |
| 11 | win_rate_ok | ✅ 59.35% (M15 replay) | — |
| 12 | sharpe_ok | ⚠️ 0.256 | WFA confirme partiellement |
| 13 | profit_factor_ok | ✅ 1.925 (replay) | — |
| 14 | **wfa_robust** | ⚠️ WFA_MARGINAL (2/5) | Recalibrer ou élargir paires |
| 15 | **broker_connected** | ❌ | **Søn : IBKR REST credentials** |
| 16 | **feed_active** | ❌ | **Søn : FeedHandler C19 activé** |
| 17 | Score DV ≥ 80 | ⚠️ 58.33 | Besoin critères 14-16 |
| 18 | **R10 levée** | ❌ | **Décision Søn CEO uniquement** |

---

## 🏗️ Prochaines étapes — WFA_MARGINAL

Le WFA ne valide PAS un edge stable pour GO LIVE :
1. **Recalibrer les seuils M15** — réduire la dépendance post-hoc (tester sans USDCHF qui n'a que WR 50%).
2. **Élargir l'échantillon** — le WR moyen 51.64% sur 171 trades OOS est trop proche de 50% pour être actionnable.
3. **Pas de promotion R10** — l'edge M15 seul ne justifie pas de levée R10 (WFA 2/5).

*Prochain jalon : rétablir suite tests complète + WFA sur paires stabilisées.*
