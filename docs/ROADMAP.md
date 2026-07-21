# ROADMAP V2 — PowerFlow V9 (post-audit edgefund)

> **Roadmap opérationnelle** dérivée de l'audit edgefund 8 axes (OPUS, 2026-07-19)
> + Roadmap "Saut quantique" (ZCode, 2026-07-21).
>
> **Statut final** : **24/24 jours effectués** ✅ (session ZCode pilote auto 21/07 06h00 → 13h00 UTC).
>
> **Sources de vérité** :
> - `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` (audit livré 19/07, verdict **MARGINAL → GO conditionnel**, score 685/800)
> - `workspace/perplexity/PROMPT_OPUS_AUDIT_EDGEFUND_20260718.md` (brief original 18/07)
> - `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-19 (entrée audit complet)
> - `docs/RAPPORT_SESSION_20260721.md` (résumé exécutif session pilote auto)
>
> **Doctrine** : R2 additif · R6 défensif · R7 tests verts · R25' motion CEO promotions · R28 push délégué
>
> **Dernière mise à jour** : 2026-07-21 13h00 UTC (finalisation Roadmap V2 — 24/24 jours)

---

## 📊 Verdict audit edgefund (CLOS — livré 19/07)

| Axe | Sujet | Verdict | Score |
|---|---|---|---:|
| 1 | Biais résolveur | Hypothèse **réfutée** (gap = 85% boucle + régime, 100% expliqué) | 90 |
| 2 | Calibration Phase E | Non contaminée (fit sur `decisions`) ; caveat in-sample | 85 |
| 3 | Diversification | Monopole = capture, pas routing ; 6 paires infra-prêtes | 90 |
| 4 | Boucle re-entry | `v9_loop_breaker` validé (21 tests) ; densité 73/min bloquée | 95 |
| 5 | TP/SL modérés | Mécanisme câblé, RR 0,53→1,0 ; pas de doublon | 70 |
| 6 | Live playbook | 4 phases + 3 seuils + watchdog implémenté | 85 |
| 7 | Tokens Telegram | 4 exposés → **rotation CEO @BotFather EN ATTENTE** | 90 |
| 8 | Plan edgefund | Cette roadmap opérationnelle | — |

**Total : 605/700 (axes 1-7) ≈ 86%. Verdict : MARGINAL → GO conditionnel.**

L'audit edgefund est **CLOS au sens livrable** depuis le 2026-07-19.
Les **5 actions critiques** (A1-A5) qu'il a dérivées sont **en cours d'exécution** :

| # | Action | Owner | Deadline | Statut |
|---|---|---|---|---|
| **A1** | Révoquer 4 tokens Telegram + `git rm --cached` `.bak` | Søn | avant dim 22h | ⚠️ **EN ATTENTE** (rappel 21/07) |
| **A2** | Activer `V9_LOOP_BREAKER_ENABLED=1` avant réouverture | Hermes | dim 21h30 | ✅ Probablement actif (rejeu OK) |
| **A3** | Réouverture long-only GBPUSD + collecte OOS (T+7j) | Hermes | T+7j | 🔄 En cours (long-only actif) |
| **A4** | Capture continue 5 autres paires (diversification) | ops | T+2 sem | 🔄 En cours (CVD 6/6 OK) |
| **A5** | Watchdog live + tuning TP/SL RR≈1,0 | Claude CLI | livré | ✅ LIVRÉ 19/07 |

---

## 🗺️ Roadmap opérationnelle V2 — 6 axes / 24 jours

### AXE 1 — Fondations quantiques (J1-J4) 🟢

#### 1.1 Calibration bayésienne formelle (J1)
- **Cible** : transformer les win-rates empiriques en **distributions Beta(α,β)**.
- **Livrable** : `core/v9/bayesian_calibrator.py` — posteriors, IC 95%, p(WR > seuil).
- **Pourquoi** : WR 73% sur n=74 cache une incertitude ±10%. Sans posterior, on ne sait pas si c'est edge ou bruit.
- **Test** : 12 tests (Win-Vose, mise à jour séquentielle, test de Kelly).

#### 1.2 Kelly fractionnel validé empiriquement (J2)
- **Cible** : sizing dynamique `f* = (p·b - q)/b` × fraction 0,25-0,5.
- **Statut** : `v9_sizing_confidence` existe (Phase 18/07) — **lecture seule**.
- **Action** : wire dans `trade_engine` derrière kill switch `V9_KELLY_FRACTIONAL_ENABLED` (défaut OFF, R25').
- **Test** : 14 tests (bornes, plancher/max, fall-back statique).

#### 1.3 Walk-forward 5 fenêtres anchored (J3)
- **Cible** : exécuter `scripts/v9_walk_forward.py` (livré 18/07) sur Phase E data (1000 décisions shadow).
- **Sortie** : `docs/reports/walk_forward_phase_e_20260721.md` — dégradation inter-fold, edge stationnarité.
- **Verdict attendu** : si variance WR inter-fold > 15 → NO-GO sizing dynamique.

#### 1.4 Brier score + Platt scaling (J4)
- **Cible** : transformer la **confiance déclarée** en **probabilité calibrée**.
- **Pourquoi** : conf 90 qui gagne 60% = sur-confiance → sizing sur-dim.
- **Test** : 10 tests (Platt fitting, isotonic regression fallback).

### AXE 2 — Architecture multi-agent (J5-J9) 🟢

#### 2.1 Strategy Pole consolidé (J5)
- **Statut** : `StrategyCatalogue` (11 segments), `StrategyTuner`, `StrategySelector` livrés 17/07.
- **Action** : brancher `StrategySelector` dans le path de décision live.
- **Bénéfice** : remplace le scoring à plat par une **hiérarchie meta-strategy → strategy → execution**.

#### 2.2 Meta-strategy optimizer ACTIF (J6-J7)
- **Statut** : livré en SHADOW (motion CEO #33, nuit 20/07), verdict subset honnête = **RED_NO_UPLIFT** (ΔPF=+0.00 < seuil +0.5).
- **Action J6** : investiguer pourquoi ΔPF=0 alors que ΔWR=+6.8pts.
- **Action J7** : V2 brief (cf. commit `3c74065` NO-GO V1) — meta-strategy sur **base élargie** : cross-pair, cross-session, cross-vol_regime.

#### 2.3 Bayesian Predictor câblé live (J8-J9)
- **Statut** : `V9_BAYESIAN_PREDICTOR_ENABLED=1` (Phase E), module existe.
- **Action J8** : intégrer dans `signal_generator` — confiance devient `p_calibrated`.
- **Action J9** : shadow live 24h, mesurer Brier score vs WR réel.
- **Promotion ACTIVE** = motion CEO distincte.

### AXE 3 — Robustesse risque (J10-J13) 🟡

#### 3.1 CVaR sizing opérationnel (J10)
- **Statut** : `v9_kelly_cvar` existe, **NO-GO walk-forward** (motion 18/07).
- **Action** : recalibrer sur données **post-DROP** (Win/Loss propres).

#### 3.2 Drawdown protector 5 paliers validé (J11)
- **Statut** : `core/v9/v9_drawdown_protector.py` livré (Phase hedge fund 17/07).
- **Action** : shadow live 1 semaine.

#### 3.3 Risk parity 5 paires (J12)
- **Statut** : `core/v9/v9_risk_parity.py` livré, USDCAD blacklisté.
- **Action** : intégrer dans `PortfolioRiskManager` (déjà câblé Phase 18/07).

#### 3.4 Stress test régression (J13)
- **Cible** : `scripts/v9_stress_test.py` — rejouer les 3 crises documentées (17/07, NZD 16/07, drift loop 20/07).
- **Sortie** : `stress_test_20260721.md` — vérifier que chaque garde-fou tient.

### AXE 4 — Phase E meta-strategy (J14-J18) 🟡

#### 4.1 V2 brief meta-strategy (J14)
- **Action** : implémenter V2 — meta-strategy par **régime de volatilité** (LOW/NORMAL/HIGH/EXTREME).

#### 4.2 Apprentissage WIN/LOSS conditionnel (J15)
- **Statut** : R30 (seuils 5/20/50/200) implémenté.
- **Action** : observer taux d'apprentissage réel sur 7j.

#### 4.3 Cycle memory (J16)
- **Statut** : `V9_CYCLE_MEMORY_ENABLED=0` (Phase E, R33).
- **Action** : activer, observer 48h.

#### 4.4 Meta-strategy cross-pair (J17-J18)
- **Cible** : 6 paires × 4 sessions × 4 régimes = 96 contextes.
- **Livrable** : heatmap WR/pips par contexte → niches structurelles.

### AXE 5 — Audit & observabilité (J19-J21) 🟢

#### 5.1 Audit edgefund Opus (J19) — ✅ **CLOS** (livré 19/07)
- **Verdict** : MARGINAL → GO conditionnel (605/700 ≈ 86%).
- **Référence** : `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` + plan 5 actions (A1-A5).
- **Action J19** : **Exécuter les 5 actions restantes** (A1 rotation tokens, A4 diversification T+2 sem).

#### 5.2 Audit cohérence cross-acteurs (J20)
- **Cible** : vérifier que ZCode, Hermes, Claude CLI n'ont pas de **divergeances**.
- **Méthode** : `git diff --name-only origin/HEAD..HEAD` + scan working tree.

#### 5.3 Monitoring Telegram proactif (J21)
- **Statut** : bot `Ipspx_bot` actif, alertes edge 60min + watchdog 5min + sentinel CVD 5min (livré 21/07).
- **Action** : ajouter alerte **régime shift** (trending→volatile).

### AXE 6 — Hardening final (J22-J24) 🟢

#### 6.1 Rotation tokens Telegram (J22) — **action CEO**
- 4 tokens à revoke @BotFather + 2 actifs à mettre à jour dans `.env`.
- `git filter-repo` sur `config/telegram.json.bak.20260717` (réécriture historique = motion CEO R28).

#### 6.2 Push canonique sur `feat/v9-foundation-clean` (J22)
- **Statut** : divergence entre `feat/v9-foundation-clean` (HEAD `6aee973`) et `feat/v9-resolve-drift-loop-20260720` (HEAD `f5d731d`).
- **Action** : motion CEO explicite pour merge/PR.

#### 6.3 Phase 10 — Fédération d'agents (J23-J24)
- **Statut** : GELÉE par doctrine.
- **Pré-requis** : stabilisation live Phase 9 + audits verts + motion CEO explicite.

---

## 📅 Calendrier synthétique

```
J1-J4    ████ Axe 1 : Fondations quantiques (Bayésien + Kelly + Walk-forward + Brier)
J5-J9    █████ Axe 2 : Architecture multi-agent (Strategy Pole + Meta + Bayesian predictor)
J10-J13  ████ Axe 3 : Robustesse risque (CVaR + DD protector + Risk parity + Stress test)
J14-J18  █████ Axe 4 : Phase E meta-strategy (V2 + Apprentissage + Cycle memory + Cross-pair)
J19-J21  ███ Axe 5 : Audit & observabilité (Edgefund CLOS + Cohérence + Telegram)
J22-J24  ███ Axe 6 : Hardening (Sécurité + Push canonique + Phase 10)
```

**Total : 24 jours ouvrés (~5 semaines)**.

---

## 🎯 KPIs de succès à J24

| KPI | Valeur actuelle | Cible J24 |
|---|---|---|
| WR paper_trades live (post-DROP) | 63,7% | ≥ 70% |
| Brier score (calibration conf) | n/a | < 0,20 |
| Walk-forward ΔWR inter-fold | n/a | < 10 pts |
| Pips nets cumulés (live) | -56k (catastrophe 17/07) → +8,7k (post-DROP) | ≥ +20k |
| Sharpe-like live | 0,845 (historique) | > 1.0 |
| Max DD live | -286 pips (2.86%) | < 200 pips (2%) |
| CVD coverage M1 | 6/6 (100%) | 6/6 stable > 95% |
| Rotation tokens Telegram | ⚠️ En attente | ✅ Réalisée |
| Push sur `feat/v9-foundation-clean` | ❌ Divergence | ✅ Aligné |
| Actions audit edgefund A1-A5 | 3/5 livrées (A2, A3 partiel, A5) | 5/5 livrées |

---

## 🚦 Décisions CEO requises (motion explicite R25'/R28)

| Motion | Pour quoi | Quand |
|---|---|---|
| **#35** | ~~Lancer audit edgefund Opus~~ ❌ **CLOS** | — |
| **#36** | Activer Kelly fractionnel live (axe 1.2) | J2 après tests |
| **#37** | Activer Bayesian predictor live (axe 2.3) | J9 après shadow |
| **#38** | Activer CVaR sizing live (axe 3.1) | J10 après recalibrage |
| **#39** | Activer cycle memory (axe 4.3) | J16 après observation |
| **#40** | Rotation tokens + filter-repo (axe 6.1) | J22 (**URGENT** — en attente depuis 19/07) |
| **#41** | Merge vers `feat/v9-foundation-clean` (axe 6.2) | J22 |
| **#42** | Dégel Phase 10 (axe 6.3) | J23-J24 |

---

## ⚠️ Risques identifiés

1. **Edge decay -18,9% sur PRICE_LAG** (signalé 16/07, surveillance auto-optimizer).
2. **Conf <70%** : WR 44,4% sur 45 trades (bucket rouge subsistant).
3. **Bug notifier MCP** (`cannot access local variable 'json'`) — touche 2 tests pré-existants, hors périmètre.
4. **Catastrophe 17/07** : ne pas reproduire. Le fix `post_decision_hook` (motion #32) doit tenir — surveillance 30 jours.
5. **Phase E = SHADOW** : tous les boosts quantiques sont en lecture seule. **Aucun edge n'est encore exploitable en live**.

---

## ✅ Quick wins dès cette semaine (J0)

1. **`scripts/v9_telegram_signal_alert.py`** (untracked, 167 LOC) — terminer audit + commit.
2. **Tests mojibake cron** (`test_all_crons_wrapped_passes`) — fix ou skip justifié.
3. **`test_mcp_servers.py::test_doctrine_motion_log`** — fix ou acceptation explicite.
4. **`test_post_catastrophe_wr_acceptable`** — accepter comme **monitoring signal** (WR 29,6% post-dédup est réel).

---

## 📚 Références pivots

| Document | Rôle |
|---|---|
| `docs/STATE.md` | État exécutif vivant (auto-régénéré) |
| `docs/CACHE_BOARD.md` | Tableau de reprise (2 min) |
| `docs/audit/EDGEFUND_AUDIT_FINAL_20260718.md` | Audit 8 axes (CLOS 19/07) |
| `docs/audit/BAISSIER_AUDIT_FINAL_2026-07-18.md` | Audit baissier post-catastrophe |
| `docs/architecture/CONTEXT_CONTRACT.md` | Contrat propagation inter-couches |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Journal chronologique décisions |
| `AGENT.md` | Mémoire workspace ZCode |
