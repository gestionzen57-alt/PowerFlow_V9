# 🏦 PLAN D'ACTION — Edge Fund Quantique Institutionnel — PowerFlow V10

> **Vision :** Transformer PowerFlow V10 d'un système d'apprentissage autonome en
> un **edge fund quantique crédible face aux institutions** (allocateurs, family
> offices, prime brokers, fonds de fonds).
> **Horizon :** 90 jours. **Invariant :** R10 (capital protégé, paper-only sans `V9_EXECUTION_ENABLED`).

---

## 🎯 OBJECTIF STRATÉGIQUE

Devenir **investissable** : un institutionnel doit pouvoir auditer, comprendre,
et faire confiance au système. Cela exige **5 leviers** : Rigueur quantique,
Protection du capital (R10), Gouvernance, Transparence/Reporting, Scalabilité.

---

## 🧭 LEVIER 1 — RIGUEUR QUANTIQUE (anti-overfit, crédibilité méthodologique)

> *Un institutionnel ne demande pas "est-ce que tu gagnes ?" mais "comment sais-tu que tu gagnes, et sur combien d'échantillon hors-échantillon ?"*

| # | Action | Livrable | Métrique de passage |
|---|--------|----------|---------------------|
| 1.1 | Audit walk-forward systématique de chaque edge | `v10_walk_forward_validator.py` rapport par edge | 100% des edges validés sur échantillon hors-échantillon |
| 1.2 | Seuil anti-bruit renforcé | Edge = WR ≥ 50% **ET** n ≥ 30 **ET** Δ ≥ 2.0p | 0 edge de bruit dans la carte |
| 1.3 | Backtest replay → live cohérent | Rapport comparaison replay vs live résolu | Écart WR replay/live < 10 pts |
| 1.4 | Métriques standard fonds | Sharpe, Sortino, max DD, Calmar, drawdown, VaR, profit factor | Rapport `v10_fund_metrics.py` |
| 1.5 | Benchmark vs passif | Comparaison à buy-and-hold USD, EUR | Alpha mesuré, pas juste WR |
| 1.6 | Documenter les hypothèses | `docs/V10/V10_QUANT_METHODOLOGY.md` | Chaque stratégie = hypothèse + validation |

---

## 🧭 LEVIER 2 — PROTECTION DU CAPITAL (R10, seul vrai garde-fou)

> *C'est LE critère de passage institutionnel. Un fonds qui perd 40% en 1 mois est mort, même si son WR est excellent.*

| # | Action | Livrable | Métrique de passage |
|---|--------|----------|---------------------|
| 2.1 | Audit R10 complet | Test d'exercice de chaque gate (DD, position, levier, net, opposées, corr) | 100% des gates exercés et testés |
| 2.2 | Kill switch documenté + accessible | `docs/V10/KILL_SWITCH.md` + procédure | Kill switch = 1 commande, CEO Søn |
| 2.3 | Stress test | Simulation DD 10% → halt auto | Halt déclenché < 1 barre |
| 2.4 | Risk limit institutionnel | VaR 95%, position max, levier max par compte | Rapport `v10_risk_shield` conforme |
| 2.5 | Séparation des capitaux | Paper/Shadow/Active strictement séparés | 0 mélange, 0 ordre réel non validé |

---

## 🧭 LEVIER 3 — GOUVERNANCE (qui décide, comment, et est-ce réversible ?)

> *Un institutionnel veut savoir qui a le doigt sur le bouton, et que ce n'est pas une IA seule.*

| # | Action | Livrable | Métrique de passage |
|---|--------|----------|---------------------|
| 3.1 | Matrice de décision claire | CEO Søn = stratégique, Hermes = opérationnel | Document `GOVERNANCE.md` |
| 3.2 | Journal des décisions structuré | `DECISIONS_LOG.md` + chaque décision traçable | 100% des décisions journalisées |
| 3.3 | Politique de promotion SHADOW→ACTIVE | Gates objectifs (WR, Sharpe, consistency, n) | Aucune promotion non méritée |
| 3.4 | Revue de risque périodique | Comité (CEO + auditeur) | Revue mensuelle documentée |
| 3.5 | Limite d'autonomie de l'IA | R10 = limite absolue, kill switch CEO | 0 dépassement documenté |

---

## 🧭 LEVIER 4 — TRANSPARENCE & REPORTING (chaque chiffre vérifiable)

> *Un institutionnel audite. Tout doit être reproductible bit-pour-bit (R14).*

| # | Action | Livrable | Métrique de passage |
|---|--------|----------|---------------------|
| 4.1 | Rapport nocturne complet | `v10_night_cron.sh` + `reports/v10_night_report_*.json` | Rapport produit chaque nuit |
| 4.2 | Bilan quotidien actionnable | `v10_daily_bilan.py` | WR, PnL, Sharpe, reco R8 |
| 4.3 | Carte des edges publique | `v10_replay_batch` + `v10_edges_telegram_alert` | Carte rafraîchie hebdo |
| 4.4 | Audit V9→V10 | `v10_v9_principles_audit.py` | 45/47 couverts, 0 gaps |
| 4.5 | Rapport d'audit exécutable | `HERMES_PROMPT_AUDIT_EDGE_FUND.md` | Audit reproductible par IA/humain |
| 4.6 | Notifications Telegram | signaux, bilan, R8, edges | CEO informé en temps réel |

---

## 🧭 LEVIER 5 — SCALABILITÉ (perf, multi-paires×TF, infra stable)

> *Un institutionnel veut un système qui tient la charge, pas un prototype.*

| # | Action | Livrable | Métrique de passage |
|---|--------|----------|---------------------|
| 5.1 | Perf pipeline | `v10_replay_batch` optimisé (rolling window HMM) | 18 paires×TF < 5 min |
| 5.2 | DB saine | `count()` au lieu de `PRAGMA` sur >5GB | Fraîcheur < 1h |
| 5.3 | Crons fiables | nocturne + live + replay hebdo | 100% `execution_success` |
| 5.4 | Tests continus | `pytest tests/test_v10_*.py` | 1186/1186 verts |
| 5.5 | Documentation | `AGENTS.md`, `SOUL.md`, `docs/V10/` | À jour à chaque livraison |

---

## 🗺️ FEUILLE DE ROUTE 90 JOURS

| Phase | Semaines | Levier prioritaire | Livrable clé |
|-------|----------|--------------------|--------------|
| **P1** | 1-2 | Rigueur quant (L1) | Audit walk-forward complet, `V10_QUANT_METHODOLOGY.md` |
| **P2** | 3-4 | Risque R10 (L2) | Stress test + kill switch documenté, audit R10 |
| **P3** | 5-6 | Gouvernance (L3) | `GOVERNANCE.md`, politique promotion, comité de risque |
| **P4** | 7-8 | Reporting (L4) | Rapport fund metrics, benchmark passif, audit reproductible |
| **P5** | 9-10 | Scale (L5) | Perf multi-paires×TF, infra stable, tests continus |
| **P6** | 11-12 | **Audit complet** | Exécuter `HERMES_PROMPT_AUDIT_EDGE_FUND.md` → rapport |

---

## 🎯 DÉFINITION DE "PRÊT INSTITUTIONNEL" (Definition of Done)

Le V10 est **prêt institutionnel** quand l'audit (P6) conclut **OUI** sur :
1. **Rigueur quant** : edges validés hors-échantillon, pas de look-ahead, Δ ≥ 2p.
2. **R10 strict** : DD halt, position max, levier max, opposées bloquées, zéro ordre réel non validé.
3. **Gouvernance** : kill switch CEO, décisions journalisées, promotion méritée.
4. **Transparence** : chaque chiffre traçable (R9), git = source de vérité (R14).
5. **Scale** : 1186+ tests verts, perf 18 paires×TF, crons 100% fiable.

**Score global audit ≥ 80/100** avec **0 FAIL critique R10** = PRÊT.
Sinon = CONDITIONNEL (liste des actions pour atteindre le seuil).

---

## 🔑 INVARIANT ABSOLU

**R10 inchangé quoi qu'il arrive** : paper/SHADOW obligatoire, zéro ordre réel
sans `V9_EXECUTION_ENABLED==1`. Le passage institutionnel ne justifie **jamais**
le relâchement de la protection du capital.

---

*Fin du plan d'action. Chaque levier est indépendant et peut être exécuté en parallèle par des sous-agents. L'audit (L4.5 / P6) est la porte de sortie vers le statut institutionnel.*
