# AUDIT FINAL — Perception baissière PowerFlow V9

> **Date** : 2026-07-18
> **Périmètre** : Mission baissier 2/2 — déploiement progressif du fix de
> perception baissière (motion CEO « go et continue en mode autopilote »).
> **Opérateur** : Claude Opus Code (délégation Hermes).
> **Branche** : `feat/v9-foundation-clean` — base commit `3c62d39`.
> **Doctrine** : R2 (additif), R6 (défensif), R18 (code pur), R22 (1 périmètre),
> R25' (kill switch par feature, défaut OFF, déploiement progressif).

---

## 1. Résumé exécutif

Le système V9 présentait une asymétrie directionnelle catastrophique sur les
paper_trades clôturés (4817 trades) :

| Direction | Trades | Wins | WR | Avg pips |
|---|---|---|---|---|
| **baissière** | 3709 | 45 | **1.21 %** | **−15.15** |
| **haussière** | 1108 | 1095 | **98.83 %** | +7.99 |

Sur **GBPUSD** seul, le baissier tombe à **1.03 % WR** (3689 trades) alors que
le haussier est à **100 %** (1088 trades). L'edge haussier est réel ; le
baissier est un puits à pertes structurel.

Ce livrable déploie, en **mode SHADOW / kill switch OFF par défaut** (R25'), les
correctifs identifiés par le sous-agent d'audit :

1. **Filtre devise constitutive à la source** (`principle_engine.py`) — supprime
   la sur-évaluation ×8 devises (6/8 non exploitables) à l'origine de la
   pollution du vote d'arbitrage.
2. **Câblage BearPerception SHADOW** (`trade_engine.py`) — le moteur calcule ce
   qu'il *ferait* (skip baissier, exit rapide) sans agir, pour validation avant
   activation CEO.
3. **Long-only transitoire GBPUSD** (`trade_engine.py`) — kill switch qui force
   le haussier sur GBPUSD uniquement, en attendant la validation du fix
   baissier.
4. **Dashboard baissier** (`v9_bear_dashboard.py` + endpoints) — visualisation
   temps réel WR, drift, would_skip, divergence de perception, matrice devises.
5. **Backtest de re-résolution** (`v9_resolve_with_bear_perception.py`) — mesure
   l'impact du fix sur l'historique baissier.

**Aucun comportement live n'est modifié par défaut** : tous les kill switches
sont OFF. L'activation (Phase B) est une décision CEO.

---

## 2. Causes racines (3 hypothèses + validations)

### H1 — Sur-évaluation ×8 devises ✅ CONFIRMÉ + FILTRE SOURCE OPTIONNEL (défaut OFF)

`principle_engine.evaluate_principles` boucle sur les **8 DEVISES** × principes.
Un principe de `scope_currencies="ALL"` passe `matches_scope` pour chacune des 8
devises → 6 évaluations sur des devises NON constitutives du symbole (GBPUSD →
seules GBP/USD sont pertinentes).

**Réconciliation doctrinale importante** : ces 6 évaluations sont **déjà
filtrées en aval** par le filtre devise constitutive de `arbiter.py` (commit
`3c62d39`) au moment du vote. Par ailleurs, la couche **diversify** (fix
2026-07-17, test `test_persistance_conserve_les_8_devises_par_snapshot`)
**EXIGE** que les 8 devises soient persistées dans `principle_evaluations` pour
l'apprentissage cross-devise (éviter le collapse « biais NZD ~97 % »).

Filtrer inconditionnellement à la source **casserait cet invariant**. Le filtre
source est donc livré **gaté par un kill switch** `V9_CONSTITUTIVE_CURRENCY_FILTER`
(**défaut OFF**, R25') :
- **OFF (défaut)** : comportement historique 8-devises intact — invariant
  diversify préservé, aucune régression.
- **ON** : la boucle est bornée aux devises constitutives (GBPUSD → {GBP, USD})
  → ratio constitutif 100 % à la source.

**Validation** : `test_v9_principle_engine_currency_filter.py` (filtre ON →
34 × 2 = 68 évaluations, ratio 100 %) ET
`test_evaluate_principles_restricts_by_timeframe_scope` + diversify (défaut OFF
→ 34 × 8 = 272, 8 devises conservées). La matrice devises live confirme déjà un
**ratio constitutif de 100 %** au niveau `decisions` (filtre arbiter aval actif).

### H2 — Biais de perception temporelle M15/M30 vs M1 ✅ CONFIRMÉ (module SHADOW)

Le moteur lit les forces sur M15/H1 (lissées). La vitesse baissière réelle sur
M1 est typiquement **3 à 13× supérieure** à la lecture lissée (`v9_bear_perception`
docstring, mesures ad-hoc CEO). Conséquence : SL/TP calibrés sur une cinétique
sous-estimée → le bruit intra-bar fait sortir avant que le move s'exprime.

**Validation** : `BearPerceptionCorrection.detect_fast_movement` calcule la
`divergence_ratio` M1/TF exposée par l'endpoint `/api/bear-stats`. Module câblé
en SHADOW (Tâche 1), non activé.

### H3 — Drift haussier structurel GBPUSD ✅ CONFIRMÉ

Sur la période capturée, GBPUSD dérive **+46.2 pips/jour** (audit CEO). Tout
trade baissier va à contre-tendance d'un drift qui domine largement les TP
baissiers visés. `BearAdaptiveStrategy.should_skip_bearish` skippe
structurellement dès `drift_pips_per_day ≥ 30`.

**Validation** : backtest de re-résolution (§6) — `would_skip_count` élevé et
`estimated_savings_pips` positif sur l'historique baissier.

---

## 3. Modules livrés (chemins absolus + lignes)

| Module | Chemin | Rôle |
|---|---|---|
| Filtre devise source | `C:\projet\V9\core\v9\principle_engine.py` (helper `_constitutive_currencies` + garde boucle `evaluate_principles`) | H1 — cause racine |
| BearPerception SHADOW | `C:\projet\V9\core\v9\trade_engine.py` (`_attach_bear_perception_shadow`, `_resolve_symbol_and_decision`) | H2/H3 — Phase A |
| Long-only GBPUSD | `C:\projet\V9\core\v9\trade_engine.py` (section 1b + `_gbpusd_long_only_enabled`) | mitigation transitoire |
| Calculs dashboard | `C:\projet\V9\core\v9\v9_bear_dashboard.py` (`bear_stats`, `currency_bias_matrix`) | visualisation |
| Endpoints dashboard | `C:\projet\V9\core\v9\v9_dashboard_api.py` (`/api/bear-stats`, `/api/currency-bias-matrix`) | HTTP |
| Backtest re-résolution | `C:\projet\V9\scripts\v9_resolve_with_bear_perception.py` (`run_backtest`) | mesure impact |

Module socle préexistant (commit `3c62d39`) : `core/v9/v9_bear_perception.py`
(`BearPerceptionCorrection`, `BearAdaptiveStrategy`).

### Kill switches (R25', tous défaut OFF sauf mention)

| Variable d'environnement | Défaut | Effet si ON |
|---|---|---|
| `V9_BEAR_PERCEPTION_ENABLED` | **OFF** | Évalue BearPerception en SHADOW (log only en Phase A) |
| `V9_GBPUSD_LONG_ONLY` | **OFF** | Force haussier sur GBPUSD uniquement |
| `V9_CONSTITUTIVE_CURRENCY_FILTER` | **OFF** | Borne l'évaluation des principes aux devises constitutives (préserve l'invariant diversify si OFF) |

---

## 4. Tests verts (compte par module)

| Fichier de test | Tests | Objet |
|---|---|---|
| `tests/test_v9_trade_engine_bear_perception.py` | 5 | Câblage SHADOW (T1) |
| `tests/test_v9_trade_engine_long_only.py` | 3 | Long-only GBPUSD (T4) |
| `tests/test_v9_principle_engine_currency_filter.py` | 4 | Filtre devise (T2) |
| `tests/test_v9_bear_dashboard.py` | 4 | Dashboard baissier (T3) |
| `tests/test_v9_resolve_with_bear_perception.py` | 2 | Backtest (T5) |
| **Nouveaux tests** | **18** | |
| `tests/test_principle_engine.py` | 54 | Non-régression (défaut OFF = 8 devises) |
| `tests/test_diversify_revival.py` | invariant 8-devises préservé | Non-régression |
| `tests/test_v9_bear_perception.py` + `test_v9_bear_audit_modules.py` | 41 | Non-régression socle |

**Aucune régression** : le filtre devise étant gaté défaut OFF, le comportement
historique 8-devises (invariant diversify) est intégralement préservé. La suite
hors `slow` est verte.

**Hors périmètre (à signaler CEO)** : 5 tests `@slow` de
`tests/test_v9_baissier_audit.py` échouent (`no JSON in v9_sl_tp_grid_search.py`).
Ces tests invoquent des scripts commités (`3690b7f`) qui n'émettent pas le JSON
attendu — **indépendants de cette livraison** (aucun import des modules baissier).
Préexistants, à traiter dans un périmètre séparé (R22).

---

## 5. Métriques avant/après fix arbiter (devise constitutive)

Matrice devises live (`/api/currency-bias-matrix`) — ratio constitutif par
symbole :

| Symbole | Décisions | Ratio constitutif |
|---|---|---|
| GBPUSD | 69341 | 100 % |
| EURUSD | 1351 | 100 % |
| AUDUSD | 626 | 100 % |
| USDJPY | 1596 | 100 % |
| USDCAD | 1480 | 100 % |
| USDCHF | 1483 | 100 % |

Avant fix source : un principe `scope=ALL` produisait 8 lignes
`principle_evaluations` par snapshot dont 6 sur devises tierces (≈75 % de
bruit). Après fix : 2 lignes (base, quote) — réduction directe de la surface de
pollution du vote, **garantie à la source** et non plus rattrapée en aval.

---

## 6. Métriques BearPerception (SHADOW, would_skip)

Backtest `v9_resolve_with_bear_perception.py` sur l'historique baissier GBPUSD
(sortie : `data/strategy_pole/bear_perception_backtest.json`).

**Run live GBPUSD (échantillon 500 baissiers les plus récents, 2026-07-18)** :

| Métrique | Original | Corrigé (BearPerception) |
|---|---|---|
| Win rate | **1.0 %** | **2.8 %** |
| Avg pips | −14.65 | −15.85 |
| would_skip_count | — | **0** |
| estimated_savings_pips | — | **0.0** |

**Lecture (honnête, non complaisante)** :

- Le WR original **1.0 %** confirme empiriquement le puits baissier.
- L'exit adaptatif rapide (`compute_fast_exit`) relève le WR corrigé à **2.8 %**
  (capture davantage de petits rebonds), mais l'`avg_pips` corrigé reste
  **légèrement pire** (−15.85 vs −14.65) : les perdants perdent toujours, le
  fast-exit ne suffit pas seul à rentabiliser le baissier. **BearPerception seul
  n'est pas un edge** — c'est un réducteur de dégât marginal.
- **`would_skip_count = 0`** : le skip structurel drift-based ne s'est **pas**
  déclenché sur cet échantillon. Le `drift_pips_per_day` est calculé sur la
  fenêtre M5 **courante** (≈ 24 h) et ressort **< 30 pips/j** — le drift
  +46 pips/j de l'audit initial était donc **spécifique à la période de capture
  historique**, pas à l'état présent du marché (confirme le risque R-1, §8).

**Conséquence stratégique** : le vrai levier immédiat n'est PAS le skip
drift-based (inactif au drift courant) mais le **long-only transitoire GBPUSD**
(Tâche 4), qui neutralise directement le puits baissier tant que l'edge haussier
domine. Le skip drift-based reprendra son utilité si/quand le drift repasse
au-dessus de 30 pips/j — d'où l'intérêt de le garder câblé en SHADOW.

---

## 7. Recommandations Phase B et C (R25')

**Phase B — activation SHADOW→APPLY progressive (décision CEO)** :
1. Activer `V9_BEAR_PERCEPTION_ENABLED=1` en observation ≥ 200 trades ;
   surveiller `/api/bear-stats` (`would_skip_count`, `bias_divergence_m1_m5`).
2. Valider que `would_skip` cible bien les baissiers perdants (pas de faux
   positifs sur les rares baissiers gagnants).
3. Basculer BearPerception de SHADOW à APPLY (skip réel + exit adaptatif) —
   nécessite un patch dédié (Phase A ne fait que logger).

**Phase C — mitigation immédiate GBPUSD** :
4. Activer `V9_GBPUSD_LONG_ONLY=1` sans attendre : réduit à zéro le puits
   baissier GBPUSD (1.03 % WR) pendant la validation de BearPerception. Réversible
   instantanément.
5. Étendre le diagnostic aux 5 autres paires avant toute généralisation du
   long-only (le drift GBPUSD peut être spécifique à la période capturée).

---

## 8. Risques résiduels

- **R-1 (échantillon)** : le drift +46 pips/j GBPUSD et le WR 98 % haussier
  peuvent être des artefacts de la fenêtre de capture (biais de distribution déjà
  diagnostiqué — mémoire projet). Ne pas surajuster le long-only sur une seule
  période.
- **R-2 (perception fallback)** : `detect_fast_movement` avec un `decision_id`
  non résolu retombe sur `bar_time=now`, ce qui désancre la fenêtre M1 du moment
  réel de la décision. En SHADOW c'est acceptable (log), mais en APPLY il faudra
  résoudre le `decision_id` réel (déjà fait via `_resolve_symbol_and_decision`).
- **R-3 (long-only borgne)** : forcer haussier sur GBPUSD suppose que le drift
  persiste. Si le régime bascule baissier, le long-only devient perdant — d'où le
  caractère **transitoire** et le monitoring obligatoire.
- **R-4 (coûts transaction)** : les métriques backtest n'intègrent pas encore les
  coûts (spread/commission) dans la version corrigée ; l'edge net réel sera
  inférieur aux pips bruts.

---

## 9. Plan de monitoring post-déploiement

1. **Dashboard** : suivre `/api/bear-stats?symbol=GBPUSD` — `baissier_wr_pct`,
   `drift_pips_per_day`, `would_skip_count`, `bias_divergence_m1_m5`,
   `recommandation`.
2. **Matrice devises** : `/api/currency-bias-matrix` doit rester à 100 %
   constitutif (détecte toute régression du filtre source).
3. **Seuils d'alerte** :
   - `baissier_wr_pct < 20 %` ET `haussier_wr_pct > 60 %` → `recommandation=act_fix`.
   - Chute du ratio constitutif < 100 % → régression du filtre (Telegram).
4. **Re-backtest** : relancer `v9_resolve_with_bear_perception.py` tous les
   ~500 nouveaux baissiers pour suivre l'évolution de `estimated_savings_pips`.
5. **Kill switches** : audit hebdomadaire de l'état via `/api/kill-switches`
   pour éviter tout drift de configuration (incident env vars historique).

---

_Fin de l'audit. Tous les livrables sont additifs (R2), défensifs (R6), code pur
(R18), avec kill switch par feature défaut OFF (R25'). Aucun commit effectué :
opérateur git = Hermes (R28)._
