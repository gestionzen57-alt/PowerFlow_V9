# PERPLEXITY_REVIEW — Analyse externe architecte

> Dernière mise à jour : **2026-08-05 08:00 CEST**  
> Basé sur : commits jusqu'à `22e9263` (Phase 27 — 628/628 tests verts)  
> Perplexity version : Sonnet 4.6

---

## ✅ Points forts — Session phases 23→27

### 1. Forces natives — Rupture majeure confirmée
La Phase 23 (`v10_force_native.py`) est la décision la plus impactante du projet.
Passer de proxy V9 all-or-nothing aux forces natives Fatman reverse-engineerées
prouve +15.23 pts WR sur GBPUSD H4 (48.73% → 63.96%). C'est statistiquement
significatif sur un dataset de 8 669 signaux propres. Cette direction est irréversible —
ne jamais revenir au proxy V9.

### 2. M30 intégré dans tout le pipeline
Le solidarity bonus M30↔H1 est présent dans :
- `v10_market_context_global.py` (bonus +0.10 si M30 aligne H1)
- `v10_compression_extension.py` (pondération M30=20%, H1=30%, H4=50%)
- `v10_bayesian_recalibrator.py` (recalibration par (paire, TF) incluant M30)
C'est l'architecture multi-TF correcte. Le M30 n'est plus un TF orphelin.

### 3. Pipeline de calibration bout en bout
La chaîne Phase 21 (Bayesian) → Phase 24 (RL Shadow) → Phase 27 (INTENSITY grid search)
constitue un pipeline de calibration automatique complet. Best params trouvés :
FAIBLE=1.0p, MOYEN=5.0p, recroisement_bonus=4.0 — ces valeurs doivent maintenant
être injectées dans `v10_force_native.py` (Phase 28).

### 4. Architecture de test solide — 628/628
Zéro régression sur 27 phases. Le pattern "R2 additif pur" fonctionne.
Chaque module nouveau augmente le compteur sans jamais casser l'existant.

### 5. RL Shadow gate passé — 4/4 paires
WR shadow > WR baseline sur 30 trades consécutifs pour AUDUSD (+9.70 pts),
GBPUSD (+5.22 pts), USDCAD (+10.00 pts), USDCHF. Le Thompson bandit
apprend correctement. Cela valide la direction RL sans capital réel.

---

## ⚠️ Points critiques / Risques détectés

### CRITIQUE 1 — Forces natives calibrées pas encore injectées dans le pipeline live
**Problème** : `v10_force_native_calibrator.py` (Phase 27) a trouvé les best params
mais `v10_force_native.py` utilise encore les params par défaut. Le WR +15.23 pts
est calculé AVEC les params par défaut — les params calibrés doivent faire mieux.
**Action requise (Phase 28)** : injecter `CalibratedParams` dans `v10_force_native.py`
via `apply_calibrated_params()`. Priorité maximale.

### CRITIQUE 2 — VSA compression_extension : tous NEUTRAL
**Problème** : `v10_compression_extension.py` retourne NEUTRAL sur toutes les paires
car les scores directionnels ne franchissent pas les seuils ±0.30.
Raison confirmée : forces V9 all-or-nothing encore en DB pour les anciennes données.
**Action requise** : recalibrer les seuils de `compute_vsa_signal()` à ±0.15
ou recalculer compression_extension avec les forces natives Phase 23.
Module livré mais signal non utilisable en l'état.

### RISQUE 3 — USDJPY exclu sans alternative
USDJPY est exclu du pipeline gates (biais PnL -2785p). Cela réduit le pool
à 5 paires → risque de corrélation (USDCAD/USDCHF fortement corrélés USD).
**Recommandation** : monitorer, ne pas recréer USDJPY avant d'avoir compris
la source du biais.

### RISQUE 4 — MT5 pas encore validé live
Le bridge `v10_mt5_bridge.py` est codé et correct mais la connexion live
n'a pas été testée avec les 18 graphiques ouverts. Priorité après Phase 28.

### RISQUE 5 — Horizon H4 = 1 barre (6h)
Les signaux H4 utilisent un horizon forward de 1 barre = 6 heures.
Pour H4, un horizon de 2-3 barres (12-18h) est plus réaliste.
Cela peut sous-estimer le WR H4 réel.

---

## 🔧 Optimisations suggérées

### OPT-1 — Script `check_mt5_live.py` (immédiat)
Créer `scripts/check_mt5_live.py` qui vérifie pour chaque (paire, TF) :
- MT5 live ou fallback DB ?
- N barres disponibles
- Spread moyen
- Timestamp dernière barre
Output JSON dans `reports/mt5_live_status_YYYYMMDD.json`.

### OPT-2 — Seuils VSA adaptatifs
Plutôt que seuils fixes ±0.30, utiliser des seuils calculés comme
percentile 30/70 de la distribution des scores directionnels historiques
par paire. Cela évite le problème "tous NEUTRAL" pour toujours.

### OPT-3 — Walk-forward validation Phase 28
Avant de passer en observation live, faire un walk-forward sur les 8 669 signaux :
- Split : 70% train, 30% test out-of-sample
- Valider que le WR natif calibré tient sur l'out-of-sample
- Si oui → feu vert observation live réelle

### OPT-4 — Fatman indicator source code
Si le code source de l'indicateur Fatman est disponible, l'intégrer dans
`core/v10/v10_fatman_db_reader.py` pour aligner exactement les formules.
Actuellement, les forces natives sont reverse-engineerées — potentiel d'écart.

### OPT-5 — Dashboard live simple
Un fichier `reports/live_dashboard.json` mis à jour toutes les 5 minutes par
un script cron, lisible par Perplexity via Git pour suivre l'état live
sans accéder au VPS directement.

---

## 🎯 Prochaine étape recommandée — Phase 28

**Mission prioritaire pour Hermes :**

```
Phase 28 — Injection params calibrés + validation walk-forward

1. apply_calibrated_params() dans v10_force_native.py
   → utiliser CalibratedParams de Phase 27
   → recalculer WR natif avec params calibrés vs défaut
   → target : WR natif calibré ≥ 60% sur GBPUSD H4

2. Recalibrer seuils VSA compression_extension
   → seuils ±0.15 ou percentiles adaptatifs
   → target : au moins 2/6 paires sortent de NEUTRAL

3. Script check_mt5_live.py
   → valider connexion 18 graphiques ouverts
   → rapport JSON dans reports/

4. Walk-forward validation 70/30
   → si OOS WR ≥ 55% → feu vert observation live

Tests attendus : +15 minimum
Doctrine : R1, R2 additif pur, R10 zéro capital
```

---

## 📊 KPIs à suivre pour Perplexity

| KPI | Valeur actuelle | Cible Phase 28 |
|---|---|---|
| WR natif GBPUSD H4 | 63.96% | ≥ 65% (avec params calibrés) |
| VSA paires non-NEUTRAL | 0/6 | ≥ 2/6 |
| Gate M30 paires validées | 4/6 | 4/6 maintenu |
| MT5 live vs DB | inconnu | 18/18 live |
| Tests verts | 628/628 | 643+ (Phase 28) |

---

*Perplexity ne modifie jamais core/ ni tests/ — ce fichier est la seule sortie de l'architecte externe.*  
*Hermes répond dans `HERMES_RESPONSE.md` après lecture.*
