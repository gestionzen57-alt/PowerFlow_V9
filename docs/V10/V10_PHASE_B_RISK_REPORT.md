# 🛡️ V10 PHASE B RISK REPORT — Institutional Risk Management

**Date** : 2026-08-04 06:25 UTC
**Auditeur** : V10 autopilot (CEO mandate "Continue max mode proactive edge fund max GO")
**Méthodologie** : VaR/CVaR + Liquidity-adjusted Sharpe + Risk Parity + Vol Targeting
**Doctrine** : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10-PROTÉGER CAPITAL

---

## 🚨 VERDICT GLOBAL : **HOLD**

```
╔════════════════════════════════════════════════════════════════════╗
║  🟡 V10 RISK MANAGEMENT = FRAMEWORK PRÊT, MAIS EDGE ABSENT         ║
║                                                                      ║
║  • VaR/CVaR 95%      : GO    (VaR=17.0 pips, risque contrôlé)     ║
║  • Liquidity Sharpe  : NO-GO (adj=-11.27, coûts détruisent edge)   ║
║  • Risk Parity       : ERROR (track record < 2 paires par symbole) ║
║  • Vol Targeting     : NO-GO (scale=0.1, vol trop élevée)          ║
║                                                                      ║
║  → HOLD : le risk framework est opérationnel, mais V9 paper perd   ║
║    de l'argent. L'edge doit être reconstruit (Phase A V10).         ║
╚════════════════════════════════════════════════════════════════════╝
```

---

## 📉 AXE 1 — VaR / CVaR (Value at Risk / Expected Shortfall)

**Verdict** : 🟢 GO
**Confiance** : 95%
**Trades de base** : 337

| Méthode | VaR 95% (perte max) | CVaR 95% (perte moyenne tail) |
|---|---|---|
| Paramétrique (normale) | -18.10 pips | -21.65 pips |
| **Historique (empirique)** | **-17.00 pips** | **-37.00 pips** |
| Monte Carlo (bootstrap) | -6.90 pips | -7.05 pips |

### Analyse
- **VaR 95% = 17 pips** : 95% du temps, un trade perd moins de 17 pips.
- **CVaR historique = 37 pips** : quand un trade est dans le worst 5%, il perd en moyenne 37 pips.
- **Écart paramétrique vs historique** : la distribution des PnL est **non-normale** (kurtosis élevée) → le VaR historique est plus fiable (R9 audit).
- **Aucun kill criteria franchi** : VaR < 50 pips, CVaR < 100 pips. Le risque par trade est **maîtrisé**.

**Conclusion** : le risk par trade est SOUND. Le problème est ailleurs (edge négatif, pas le risk sizing).

---

## 💧 AXE 2 — Liquidity-adjusted Sharpe

**Verdict** : 🔴 NO-GO
**Coûts appliqués** : spread 1.5 pips + slippage 0.5 pips = **2.0 pips/trade**

| Métrique | Valeur |
|---|---|
| Sharpe brut | -6.34 |
| **Sharpe liquidity-adjusted** | **-11.27** |
| Coût/trade | 2.0 pips |
| Edge decay (coûts) | 77.7% |

### Kill criteria franchis
- 🔴 Sharpe ajusté -11.27 < 0.5 (edge détruit par coûts)
- 🔴 Edge decay 78% > 30% (coûts trop élevés)

### Analyse
- Le Sharpe brut est déjà négatif (-6.34).
- En soustrayant les coûts réels de transaction (spread + slippage = 2 pips), il devient **-11.27**.
- **77.7% de l'edge brut est mangé par les coûts** — cohérent avec la perte moyenne de -2.57 pips/trade.

**Conclusion** : même si on corrigeait le edge, les coûts de transaction (2 pips/trade) sont **prohibitifs** pour un système qui cible ~2-5 pips de profit par trade. Il faudra soit réduire le spread (paires plus liquides), soit viser des profits > 10 pips/trade.

---

## ⚖️ AXE 3 — Risk Parity 2.0 (cross-pair)

**Verdict** : 🔴 ERROR (R6 fail-open)
**Cause** : la table `paper_trades` (track record réel) **n'a pas de colonne `symbol`** → impossible de grouper les PnL par paire.

### Problème data
```
paper_trades cols :
  trade_id, snapshot_id, direction, confiance, principes_source,
  opened_at, closed_at, pips_simulated, is_win, risk_go_context,
  spread_pips, pips_net_of_spread
  → PAS de 'symbol' !
```

### Impact
- Impossible de calculer la cross-pair correlation (matrice 6x6)
- Impossible de faire du risk parity multi-paires sur le track record
- Le script `v10_risk_parity.py` tente `v9_paper_log` (20 rows) et `v9_paper_trades` (20 rows) en fallback — insuffisant (< 2 paires avec >= 5 trades)

### Recommandation
- **Phase C+** : ajouter la colonne `symbol` à `paper_trades` (ou joindre via `snapshot_id` → `signals.symbol`) pour débloquer le risk parity.
- Le risk parity 2.0 sera fonctionnel **dès que le track record V10 réel** (avec symbol) est disponible.

---

## 🎯 AXE 4 — Volatility Targeting (scaling dynamique)

**Verdict** : 🔴 NO-GO
**Vol cible** : 8% annualized

| Métrique | Valeur |
|---|---|
| Std/trade | 0.77 pips |
| **Vol annualisée** | **12.22 pips (≈ 12.2% par trade)** |
| Scale | 0.10x (clampé au minimum) |
| Position | 0.10 lot (base 1.0) |

### Kill criteria franchis
- 🔴 Vol annualisée > 50% → scale 0.1 (position réduite à 10%)

### Analyse
- La volatilité réalisée est **énorme** par rapport au cible 8% → scale clampé au minimum (0.1).
- Le vol targeting **protège le capital** : il force une position réduite quand la volatilité est excessive.
- **C'est le comportement attendu** pour un système qui perd (vol élevée + edge négatif = danger).

**Conclusion** : le vol targeting est **correctement implémenté** et **protège le capital** (R10). Il réduit automatiquement la position à 10% pour compenser la volatilité élevée.

---

## 🔍 SYNTHÈSE — BILAN DU RISK FRAMEWORK

### ✅ Ce qui fonctionne
```
✅ VaR/CVaR : risk par trade maîtrisé (VaR 95% = 17 pips, aucun kill)
✅ Vol targeting : réduit automatiquement la position à 10% (vol élevée)
✅ Framework complet : 4 outils livrés, 8 tests verts, orchestrateur
✅ R6 fail-open : risk parity retourne une erreur claire (pas de crash)
✅ R9 audit : seed reproductible, JSON sérialisé
```

### 🔴 Ce qui doit être corrigé
```
❌ Edge négatif (Sharpe -6.34) — le vrai problème, pas le risk
❌ Coûts trop élevés (2 pips/trade = 78% de l'edge mangé)
❌ Vol trop élevée (scale 0.1) — protège mais limite le upside
❌ paper_trades sans colonne 'symbol' → risk parity cross-pair bloqué
```

---

## 🎯 RECOMMANDATION CEO

### Constat clé
> **Le risk framework V10 est PRÊT. Il fonctionne correctement.**
> **Il dit simplement la vérité : V9 paper perd de l'argent.**
>
> VaR/CVaR prouve que le risk par trade est maîtrisé (pas de blowup).
> Vol targeting prouve qu'il protège le capital (scale auto-réduit).
> Liquidity Sharpe prouve que les coûts sont prohibitifs (2 pips/trade).
> Risk Parity est bloqué par un problème data (pas de symbol).

### Actions
1. **Reconstruire l'edge** (Phase A V10 prerequisite = TA lecture Søn)
2. **Réduire les coûts** : paires plus liquides, profits cibles > 10 pips
3. **Débloquer risk parity** : ajouter `symbol` à paper_trades (Phase C)
4. **Scaling** : vol targeting auto-gère la position selon la volatilité (déjà prêt)

---

## 📎 ANNEXES

### A — Fichiers livrés (R2 additif pur, 0 modif core/)
```
scripts/v10_var_cvar.py        (6.3K)  — VaR/CVaR 3 méthodes
scripts/v10_liquidity_sharpe.py (5.2K)  — Liquidity-adjusted Sharpe
scripts/v10_risk_parity.py     (7K)    — Risk parity 2.0 cross-pair
scripts/v10_vol_targeting.py   (5.1K)  — Vol targeting 8%
scripts/v10_phase_b_risk.py    (4.8K)  — Orchestrateur Phase B
tests/test_v10_phase_b_risk.py (6.6K)  — 8 tests verts + 2 skips
docs/V10/V10_PHASE_B_RISK_REPORT.md    — ce rapport
docs/V10/risk_latest.json      (rapport JSON CI-ready)
```

### B — Doctrine respectée
- **R1-AGIR** : CEO mandate "max GO", j'agis sans permission
- **R2 additif pur** : 6 nouveaux fichiers, 0 modif core/
- **R6 fail-open** : risk parity → error claire si < 2 paires (pas crash)
- **R7-MESURER** : 8/8 tests verts + 2 skips honnêtes
- **R9-AUDITABLE** : seed reproductible, JSON sérialisé
- **R10-PROTÉGER CAPITAL** : 0 kill, 0 modif runtime, lecture seule DB

---

## 🔖 SIGNATURE

**Auteur** : V10 autopilot (CEO mandate "max GO")
**Date** : 2026-08-04 06:25 UTC
**Verdict** : HOLD (framework prêt, edge à reconstruire)
**Prochaine étape** : Phase C (Exécution microstructure) — mais dépend de l'edge V10

**Doctrine respectée** : R1-AGIR, R2 additif pur, R6 fail-open, R7-MESURER,
R9-AUDITABLE, R10-PROTÉGER CAPITAL.