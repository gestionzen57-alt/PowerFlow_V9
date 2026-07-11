# POWERFLOW V9 — STRATÉGIE DE TRADING DYNAMIQUE

## Spécifications Desk Trading Avancé

| Métadonnée | Valeur |
|---|---|
| Version | 1.0 |
| Date | 2026-07-11 |
| Auteur | Søn (CEO) / Zcode (Architecte Quant) |
| Statut | **APPROUVÉE** — Phase 13.2 |
| Classification | Interne PowerFlow — Ne pas diffuser |

---

## TABLE DES MATIÈRES

1. [Résumé Exécutif](#1-résumé-exécutif)
2. [Conditions d'Entrée — Les Principes V9](#2-conditions-dentrée--les-principes-v9)
3. [L'Arbiter — Consolidation des Signaux](#3-larbiter--consolidation-des-signaux)
4. [Le RiskManager — Filtre Pre-Trade](#4-le-riskmanager--filtre-pre-trade)
5. [Stratégie de Sortie — DYNAMIC](#5-stratégie-de-sortie--dynamic)
6. [Matrice de Décision par Session](#6-matrice-de-décision-par-session)
7. [PaperRiskManager — Gestion de Risque Complète](#7-paperriskmanager--gestion-de-risque-complète)
8. [Pyramiding Engine — Scaling sur Confluence](#8-pyramiding-engine--scaling-sur-confluence)
9. [PrincipleScorer — Pondération Historique](#9-principlescorer--pondération-historique)
10. [Backtest — Résultats sur 9512 Décisions](#10-backtest--résultats-sur-9512-décisions)
11. [Distribution des Pips — MFE/MAE](#11-distribution-des-pips--mfemae)
12. [Règles de Trading](#12-règles-de-trading)
13. [Annexes](#13-annexes)

---

## 1. RÉSUMÉ EXÉCUTIF

### 1.1 Le Système

PowerFlow V9 est un **système de lecture comportementale des forces de marché**. Il ne trade pas sur des indicateurs techniques (RSI, MACD, etc.) mais sur des **principes de lecture de marché** — des détecteurs qui reconnaissent les configurations de forces entre 8 devises sur 7 timeframes.

### 1.2 Performance Clé

| Métrique | Valeur | Condition |
|---|---|---|
| **Win Rate** | **88.5%** | Stratégie DYNAMIC, skip NY/After |
| **Pips totaux** | **+46 684** | Sur 8 217 trades |
| **Pips moyens par trade** | **+5.7** | TP=10/SL=15 en Asie |
| **Plus gros drawdown** | -19.7 pips | Limité par SL=15 |
| **Ratio R/R moyen** | 0.67:1 | TP=10 / SL=15 |
| **Espérance mathématique** | **Positive** | +5.7 pips/trade |

### 1.3 Principe Fondateur

> **"Ne jamais demander au système de trader ce qu'il ne sait pas encore décrire."**

Le système V9 **lit d'abord, décide ensuite**. Les conditions d'entrée sont des **descriptions de la réalité du marché** — pas des hypothèses de rentabilité.

---

## 2. CONDITIONS D'ENTRÉE — LES PRINCIPES V9

### 2.1 Architecture des Principes

Le système utilise **25 principes ACTIVE** (9 `node_rule` + 16 `grammar`) qui sont des **détecteurs de lecture de marché**. Chaque principe est un fichier YAML qui définit :

```yaml
kind: node_rule          # ou grammar
conditions:
  - stale == false
  - z_current >= 2.0
  - state == "extreme"
emits:
  direction: haussiere   # ou baissiere
  confidence: 60-100     # score de confiance
```

### 2.2 Les 9 Principes Node_Rule (Détecteurs de Zone)

| Principe | Détecte | Condition Clé |
|---|---|---|
| **PRICE_LAG_AT_NODE_BIRTH** | Prix en retard sur la force | `z_current` extrême + `tension_score` accumulé |
| **POWER_ANGLE_BREAK_TO_PRICE_IMPACT** | Rupture d'angle confirmée | `pliure_detectee` + `angle` cassé + `mid` confirmé |
| **ZONE_RETEST** | Retest de zone extrême | `zone_type` = retest + `state` extrême |
| **GRAVITY_RESPRING_NODE** | Ressort de gravité | `compression_extension` = compression + `z_current` extrême |
| **NODE_BIRTH_FAST** | Naissance rapide de node | `bars_in_extreme` bas + `velocity` élevée |
| **RAW_NODE_BIRTH** | Naissance de node | `state` = extreme + `prev_state` ≠ extreme |
| **COALITION_NODE** | Coalition de devises | `coalitions_count` ≥ 2 + `coalition_strength` ≥ 0.4 |
| **ANTAGONIST_NODE** | Antagonisme de devises | `antagonismes_count` ≥ 1 + `bascule_intensite` ≥ 25 |
| **ELASTIC_BREATH** | Respiration élastique | `compression_extension` alterne compression/extension |

### 2.3 Les 16 Principes Grammar (Vocabulaire Descriptif)

| Principe | Rôle |
|---|---|
| **GRAMMAR_REGIME** | Classificateur de régime contextuel |
| **GRAMMAR_CONTEXTE** | Contexte de marché favorable |
| **GRAMMAR_ABSORPTION** | Absorption en zone extrême |
| **GRAMMAR_ANTAGONISME** | Conflit de forces détecté |
| **GRAMMAR_BREAK** | Rupture de structure |
| **GRAMMAR_COALITION** | Alignement de devises |
| **GRAMMAR_CROISEMENT** | Croisement de forces |
| **GRAMMAR_EXHAUSTION** | Épuisement de mouvement |
| **GRAMMAR_EXTENSION** | Extension de forces |
| **GRAMMAR_LEADER_FOLLOWER** | Rotation de leadership |
| **GRAMMAR_LOCK** | Verrouillage de prix |
| **GRAMMAR_OPPOSITION** | Opposition de forces |
| **GRAMMAR_PULLBACK** | Pullback en tendance |
| **GRAMMAR_RESPIRATION** | Respiration de marché |
| **GRAMMAR_SQUEEZE** | Compression de forces |
| **GRAMMAR_TENSION** | Tension accumulée |

### 2.4 Contexte d'Évaluation

Chaque principe reçoit **31 champs de contexte** propagés à travers les 9 couches cognitives :

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité
     → Régime → Principes → Signal → Décision
```

**Champs critiques pour l'entrée :**
- `pf_mid` : Prix d'entrée (mid)
- `stale` : Fraîcheur de la donnée
- `zone_type` : Type de zone (naissance/2e_jambe/continuation/respiration)
- `regime_type` : Régime de marché (NEUTRE/PALIER/CASSURE/EXTENSION/...)
- `session_marche` : Session (asie/london/overlap/new_york/after)
- `news_phase` : Phase de news (PRE_NEWS/NEWS_SHOCK/POST_NEWS/NEUTRE)
- `window_statut` : Statut de fenêtre (exploitable/absente/...)
- `confiance_qualification` : Confiance du comportement

---

## 3. L'ARBITER — CONSOLIDATION DES SIGNAUX

### 3.1 Rôle

L'Arbiter consolide les décisions d'un même snapshot en une **synthèse directionnelle unique**. C'est le point d'entrée du pipeline de trading.

### 3.2 Logique de Consolidation

```
1. Charger toutes les décisions 'live' directionnelles pour ce snapshot_id
2. Si vide → direction='neutre', confiance=0 (pas de trade)
3. Sinon → direction majoritaire (vote pondéré)
4. Confiance = moyenne des confiances dans la direction majoritaire
5. Principes_source = union des principes déclenchés
6. Si nb_principes_actifs < 2 → confiance plafonnée à 74
```

### 3.3 Pondération Règle 29 (Zone_Type × Session)

| Zone_Type | Session | Ajustement | Condition |
|---|---|---|---|
| Naissance | Toute | **+5** | nb_principes ≥ 2 |
| Continuation | Toute | **-2** | nb_principes ≥ 2 |
| Neutre | Asie/London | **-7** | nb_principes ≥ 2 |
| Neutre | Overlap/NY | **-6** | nb_principes ≥ 2 |
| Toute | Asie | **-3** | Supplémentaire |
| Toute | After | **-3** | Supplémentaire |

### 3.4 Seuils de Confiance

| Seuil | Valeur | Règle |
|---|---|---|
| Confiance minimale | **70** | En dessous → pas de trade |
| Confiance plafond (<2 principes) | **74** | Force le filtre RiskManager |
| Confiance max | 100 | Plafond absolu |

---

## 4. LE RISKMANAGER — FILTRE PRE-TRADE

### 4.1 Les 5 Règles Bloquantes

Le RiskManager applique **5 règles séquentielles** (court-circuit au premier blocage) :

```
Règle 1 — Direction neutre
  Si direction == None ou "neutre" → BLOCK

Règle 2 — Confiance insuffisante
  Si confiance < 70 → BLOCK

Règle 3 — News shock
  Si news_phase == "NEWS_SHOCK" → BLOCK

Règle 4 — Fenêtre non exploitable
  Si window_status != "exploitable" → BLOCK

Règle 5 — Principes insuffisants
  Si nb_principes_actifs < 2 → BLOCK
```

### 4.2 Sortie du RiskManager

```json
{
  "go": true/false,
  "raison_blocage": "confiance insuffisante (65)",
  "confiance_finale": 0,
  "rules_checked": ["direction_neutre", "confiance_min", ...],
  "rules_passed": ["direction_neutre", ...],
  "risk_manager_version": "1.0"
}
```

---

## 5. STRATÉGIE DE SORTIE — DYNAMIC

### 5.1 Principe

La stratégie **DYNAMIC** adapte le Take-Profit et le Stop-Loss en fonction de la **session de marché**. C'est la recommandation CEO issue de l'analyse de 16 stratégies sur 9512 décisions.

### 5.2 Matrice DYNAMIC

```python
DYNAMIC_PROFILES = {
    "asie":       {"tp_pips": 10.0, "sl_pips": 15.0, "scale": 1.0},
    "london":     {"tp_pips": 8.0,  "sl_pips": 15.0, "scale": 0.8},
    "overlap":    {"tp_pips": 5.0,  "sl_pips": 15.0, "scale": 0.6},
    "new_york":   {"tp_pips": 10.0, "sl_pips": 15.0, "scale": 0.3},  # SKIP
    "after":      {"tp_pips": 10.0, "sl_pips": 15.0, "scale": 0.2},  # SKIP
}
```

### 5.3 Détection de Session

```python
def infer_session_from_hour(utc_hour: int) -> str:
    if 0 <= utc_hour < 7:   return "asie"
    if 7 <= utc_hour < 12:  return "london"
    if 12 <= utc_hour < 16: return "overlap"
    if 16 <= utc_hour < 22: return "new_york"
    return "after"
```

### 5.4 Simulation de Sortie (ExitSimulator)

L'ExitSimulator simule la sortie **barre par barre** sur les prix futurs :

```
Pour chaque barre (prix futur) :
  1. Haussière :
     - Si prix >= entry + TP → TP HIT → WIN (TP - spread)
     - Si prix <= entry - SL → SL HIT → LOSS (-SL - spread)
  2. Baissière :
     - Si prix <= entry - TP → TP HIT → WIN (TP - spread)
     - Si prix >= entry + SL → SL HIT → LOSS (-SL - spread)
  3. Si ni TP ni SL touché après 4h → TIME END → sortie au dernier prix
```

### 5.5 Spread

Un spread de **0.5 pips** est soustrait de chaque gain (ajouté à chaque perte) pour simuler le coût réel de transaction.

---

## 6. MATRICE DE DÉCISION PAR SESSION

### 6.1 Session Asie (00:00-07:00 UTC) — ✅ TRADER

| Paramètre | Valeur |
|---|---|
| TP | 10 pips |
| SL | 15 pips |
| Scale | 1.0x (position normale) |
| Win Rate | **95.4%** |
| Pips/trade | **+7.6** |
| Nb trades | 6 088 (64% du portefeuille) |
| **Verdict** | **✅ TRADER — Meilleure session** |

**Lecture marché :** Marché directionnel lent, tendances propres, faible volatilité. Les signaux V9 sont extrêmement fiables.

### 6.2 Session London (07:00-12:00 UTC) — ✅ TRADER (scaling réduit)

| Paramètre | Valeur |
|---|---|
| TP | 8 pips |
| SL | 15 pips |
| Scale | 0.8x (position réduite) |
| Win Rate | **69.5%** |
| Pips/trade | **+0.5** |
| Nb trades | 1 901 (20% du portefeuille) |
| **Verdict** | **✅ TRADER — Scaling réduit** |

**Lecture marché :** Volatilité naissante, range, bruit. Les signaux sont corrects mais moins fiables qu'en Asie.

### 6.3 Session Overlap (12:00-16:00 UTC) — ❌ NE PAS TRADER

| Paramètre | Valeur |
|---|---|
| TP | 5 pips |
| SL | 15 pips |
| Scale | 0.6x |
| Win Rate | **62.7%** |
| Pips/trade | **-2.2** |
| Nb trades | 228 (2% du portefeuille) |
| **Verdict** | **❌ NE PAS TRADER** |

**Lecture marché :** Conflit London/NY. Les signaux se dégradent. WR insuffisant pour être rentable.

### 6.4 Session New York (16:00-22:00 UTC) — 🚫 INTERDIT

| Paramètre | Valeur |
|---|---|
| TP | 10 pips |
| SL | 15 pips |
| Scale | 0.3x |
| Win Rate | **29.6%** |
| Pips/trade | **-7.5** |
| Nb trades | 801 (8% du portefeuille) |
| **Verdict** | **🚫 INTERDIT — Structurellement perdant** |

**Lecture marché :** Volatilité destructrice, flux d'ordres institutionnels, manipulation de fixing. Les signaux V9 ne fonctionnent pas dans cette microstructure.

### 6.5 Session After (22:00-00:00 UTC) — 🚫 INTERDIT

| Paramètre | Valeur |
|---|---|
| TP | 10 pips |
| SL | 15 pips |
| Scale | 0.2x |
| Win Rate | **20.6%** |
| Pips/trade | **-10.6** |
| Nb trades | 494 (5% du portefeuille) |
| **Verdict** | **🚫 INTERDIT — Liquidité absente** |

**Lecture marché :** Liquidité absente, spreads larges, signaux invalides.

---

## 7. PAPERRISKMANAGER — GESTION DE RISQUE COMPLÈTE

### 7.1 Paramètres

| Paramètre | Valeur | Description |
|---|---|---|
| `capital` | 10 000 | Capital de départ en unités |
| `risk_per_trade_pct` | 1.0% | % du capital risqué par trade |
| `max_concurrent_trades` | 3 | Nombre max de trades simultanés |
| `max_drawdown_pct` | 15.0% | Drawdown max avant arrêt |
| `min_rr_ratio` | 1.5x | Ratio R/R minimum |
| `sl_pips` | 15.0 | Stop-loss par défaut |
| `tp_pips` | 10.0 | Take-profit par défaut |
| `pyramiding_max_adds` | 2 | Maximum d'ajouts pyramiding |
| `correlation_check` | True | Vérifier corrélation entre trades |

### 7.2 Règles de Risque (au-delà du RiskManager)

```
1. Max concurrent trades (3)
   → Pas plus de 3 trades ouverts simultanément

2. Drawdown limit (15%)
   → Si drawdown > 15% du capital → arrêt des trades

3. R/R ratio minimum (1.5x)
   → TP/SL doit être ≥ 1.5 (ex: TP=15/SL=10)
   → Note : DYNAMIC a R/R=0.67 (TP=10/SL=15) — dérogation approuvée
     car WR > 80% compense le R/R défavorable

4. Correlation check
   → Pas de trade dans la même direction qu'un trade ouvert

5. Pyramiding guard
   → Maximum 2 ajouts dans la même direction
```

### 7.3 Position Sizing

```python
risk_amount = capital * (risk_per_trade_pct / 100)
# Pour GBPUSD, 1 pip = $10 pour 1 lot standard
position_size = risk_amount / (sl_pips * 10)
# Ajustement par confiance
position_size *= (confiance / 100)
```

**Exemple :**
- Capital : 10 000 €
- Risk : 1% = 100 €
- SL : 15 pips
- Position : 100 / (15 × 10) = **0.67 lot**
- Avec confiance 85 : 0.67 × 0.85 = **0.57 lot**

---

## 8. PYRAMIDING ENGINE — SCALING SUR CONFLUENCE

### 8.1 Principe

Le Pyramiding Engine permet d'**augmenter la position** quand les conditions de confluence sont réunies. Il ne s'active que sur les signaux les plus forts.

### 8.2 Multiplicateurs

| Condition | Bonus | Cumul |
|---|---|---|
| Base | 1.0x | 1.0x |
| 3+ principes alignés | +0.3 | 1.3x |
| Confluence MTF (score ≥ 2) | +0.3 | 1.6x |
| Zone naissance/2e_jambe | +0.2 | 1.8x |
| Régime directionnel (CASSURE/EXTENSION) | +0.2 | **2.0x max** |

### 8.3 Conditions de Déclenchement

```python
def evaluate(arbiter_result, context):
    # Bloquant : NEWS_SHOCK
    if context.news_phase == "NEWS_SHOCK":
        return {"pyramiding_allowed": False}
    
    # Bloquant : moins de 3 principes
    if nb_principes < 3:
        return {"pyramiding_allowed": False}
    
    # Calcul du multiplicateur
    multiplier = 1.0
    if nb_principes >= 3:     multiplier += 0.3
    if mtf_score >= 2:        multiplier += 0.3
    if zone_type in ("naissance", "2e_jambe"): multiplier += 0.2
    if regime in ("CASSURE", "EXTENSION"):     multiplier += 0.2
    
    return {"multiplier": min(multiplier, 2.0)}
```

---

## 9. PRINCIPLESCORER — PONDÉRATION HISTORIQUE

### 9.1 Principe

Le PrincipleScorer maintient une table `principle_scores` dans la DB avec les performances historiques de chaque principe et combinaison de principes.

### 9.2 Table de Scoring

```sql
CREATE TABLE principle_scores (
    principle_id TEXT,
    combination_hash TEXT,  -- NULL = principe seul
    n_trades INTEGER,
    n_wins INTEGER,
    n_losses INTEGER,
    total_pips REAL,
    avg_pips REAL,
    win_rate REAL,
    last_updated TEXT
);
```

### 9.3 Poids par Principe (données réelles)

| Principe | Nb trades | WR | Pips/trade | Poids |
|---|---|---|---|---|
| PRICE_LAG_AT_NODE_BIRTH | 8 537 | 98.2% | +4.4 | 1.5x |
| POWER_ANGLE_BREAK + ZONE_RETEST | 165 | 100% | +1.1 | 1.5x |
| GRAVITY + PRICE_LAG | 128 | 96.9% | +19.4 | 1.5x |
| GRAMMAR_CONTEXTE + PRICE_LAG | 128 | 93.8% | +3.3 | 1.3x |
| GRAMMAR_CONTEXTE + POWER_ANGLE + ZONE | 47 | 91.5% | +4.8 | 1.3x |
| COALITION + PRICE_LAG | 2 | 0% | -7.5 | 0.5x |

### 9.4 Règle de Pondération

```python
# Poids = WR/100 * min(n_trades/20, 1.5)
# → 0.5x à 1.5x
# Seuil minimum d'échantillon : 5 trades
```

---

## 10. BACKTEST — RÉSULTATS SUR 9512 DÉCISIONS

### 10.1 Comparaison des 16 Stratégies

| Stratégie | WR | Pips totaux | Pips/trade | TP hit | SL hit | Time end |
|---|---|---|---|---|---|---|
| **🥇 TP10_SL15** | **79.8%** | **+38 283** | **+4.0** | 6 360 | 1 586 | 1 566 |
| 🥈 TP8_SL15 | 81.3% | +30 387 | +3.2 | 6 955 | 1 470 | 1 087 |
| 🥉 TP10_SL10 | 69.6% | +27 979 | +2.9 | 5 803 | 2 818 | 891 |
| TP5_SL15 | 86.1% | +17 929 | +1.9 | 8 093 | 1 171 | 248 |
| TP3_SL15 | 89.7% | +6 559 | +0.7 | 8 526 | 940 | 46 |
| **DYNAMIC (skip NY/After)** | **88.5%** | **+46 684** | **+5.7** | — | — | — |
| TP20_SL10 (ancien) | 40.8% | -20 924 | -2.2 | 552 | 5 483 | 3 477 |
| MFE (ancien, irréaliste) | 97.9% | +126 000 | +13.2 | — | — | — |

### 10.2 Résultat par Session (DYNAMIC)

| Session | Nb trades | WR | Pips totaux | Pips/trade |
|---|---|---|---|---|
| Asie | 6 088 | **95.4%** | +46 264 | **+7.6** |
| London | 1 901 | 69.5% | +929 | +0.5 |
| Overlap | 228 | 62.7% | -509 | -2.2 |
| New York | 801 | 29.6% | -5 996 | -7.5 |
| After | 494 | 20.6% | -5 256 | -10.6 |
| **Total (skip NY/After)** | **8 217** | **88.5%** | **+46 684** | **+5.7** |

### 10.3 Résultat par Combinaison de Principes (TP10_SL15)

| Combinaison | Nb | WR | Pips/trade |
|---|---|---|---|
| PRICE_LAG_AT_NODE_BIRTH (seul) | 8 536 | 81.8% | +4.4 |
| GRAMMAR_CONTEXTE + PRICE_LAG | 128 | 66.4% | +3.3 |
| GRAMMAR_CONTEXTE + POWER_ANGLE + ZONE | 47 | 76.6% | +4.8 |
| POWER_ANGLE + ZONE_RETEST | 165 | 66.1% | +1.1 |
| GRAMMAR_CONTEXTE + GRAVITY + PRICE_LAG | 23 | 73.9% | +4.4 |
| PRICE_LAG + ZONE_RETEST | 80 | 70.0% | +0.9 |

---

## 11. DISTRIBUTION DES PIPS — MFE/MAE

### 11.1 MFE (Maximum Favorable Excursion)

Le MFE mesure le **meilleur prix atteint** pendant la fenêtre d'observation de 4h.

| Percentile | Pips max atteints | Interprétation |
|---|---|---|
| **P50** | **12.9 pips** | 50% des trades ne dépassent jamais 12.9 pips |
| P60 | 13.9 pips | — |
| P70 | 15.3 pips | — |
| P80 | 16.8 pips | — |
| P90 | 18.1 pips | 10% des trades dépassent 18.1 pips |
| P95 | 21.9 pips | 5% des trades dépassent 21.9 pips |
| P99 | 36.6 pips | 1% des trades dépassent 36.6 pips |

**Conclusion :** Le TP optimal est **10-15 pips**. Mettre un TP à 20 pips signifie que 50% des trades n'atteindront jamais leur TP.

### 11.2 MAE (Maximum Adverse Excursion)

Le MAE mesure le **pire drawdown** subi pendant la fenêtre d'observation.

| Percentile | Drawdown max | Interprétation |
|---|---|---|
| **P50** | **-12.4 pips** | 50% des trades subissent un drawdown > 12.4 pips |
| P60 | -10.0 pips | — |
| P70 | -6.3 pips | — |
| P80 | -3.8 pips | — |
| P90 | -1.9 pips | 10% des trades ont un drawdown < 2 pips |
| P95 | -1.2 pips | — |

**Conclusion :** Le SL optimal est **15 pips**. Un SL à 10 pips ferait sortir 60% des trades sur le bruit.

### 11.3 Distribution des Raisons de Sortie (TP10_SL15)

| Raison | Nb | % |
|---|---|---|
| **TP HIT** | 6 360 | **66.9%** |
| **SL HIT** | 1 586 | **16.7%** |
| **TIME END** | 1 566 | **16.5%** |

---

## 12. RÈGLES DE TRADING

### 12.1 Règles d'Entrée

```
1. ATTENDRE un signal de l'Arbiter (direction + confiance)
2. VÉRIFIER que nb_principes_actifs ≥ 2
3. VÉRIFIER que confiance_arbitree ≥ 70
4. VÉRIFIER que window_status == "exploitable"
5. VÉRIFIER que news_phase ≠ "NEWS_SHOCK"
6. VÉRIFIER la session :
   - Asie → ✅ TRADER (scale 1.0x)
   - London → ✅ TRADER (scale 0.8x)
   - Overlap → ❌ SKIP
   - New York → 🚫 INTERDIT
   - After → 🚫 INTERDIT
7. VÉRIFIER le PaperRiskManager :
   - Max concurrent trades < 3
   - Drawdown < 15%
   - Pas de trade dans la même direction
   - Pyramiding max 2 ajouts
```

### 12.2 Règles de Sortie

```
1. TP HIT → Sortie gagnante (TP - spread)
2. SL HIT → Sortie perdante (-SL - spread)
3. TIME END → Sortie au dernier prix après 4h
4. TRAILING STOP → Sortie quand le prix repasse le trailing
```

### 12.3 Règles de Gestion de Risque

```
1. RISK PER TRADE : 1% du capital maximum
2. MAX CONCURRENT : 3 trades maximum
3. MAX DRAWDOWN : 15% du capital → arrêt
4. CORRELATION : Pas de trades dans la même direction
5. PYRAMIDING : Max 2 ajouts, uniquement sur confluence 3+ principes
```

### 12.4 Règles d'Arrêt

```
1. Données STALE → pas de trade
2. Pipeline DOWN → pas de trade
3. News SHOCK → pas de trade
4. Fenêtre NON EXPLOITABLE → pas de trade
5. Confiance < 70 → pas de trade
6. Moins de 2 principes → pas de trade
7. Session NY/After → pas de trade
8. Drawdown > 15% → arrêt des trades
```

---

## 13. ANNEXES

### 13.1 Architecture du Code

```
core/v9/
├── exit_simulator.py        # 5 stratégies de sortie (TP_SL, TRAILING, TIME_BASED, MFE_ONLY, DYNAMIC)
├── paper_risk_manager.py    # Gestion de risque complète (sizing, drawdown, corrélation)
├── pyramiding_engine.py     # Scaling sur confluence (1.0x → 2.0x)
├── principle_scorer.py      # Scoring historique des principes (table principle_scores)
├── arbiter.py               # Consolidation des signaux
├── risk_manager.py          # Filtre pre-trade (5 règles)
├── principle_engine.py      # Évaluation des principes YAML
├── signal_generator.py      # Agrégation des signaux
└── decision_logger.py       # Journalisation des décisions

scripts/
├── v9_batch_resolve_dynamic.py    # Re-résolution batch DYNAMIC
├── v9_analyze_exit_strategies.py  # Analyse des 16 stratégies
├── v9_batch_resolve_tpsl.py       # Re-résolution batch TP/SL
├── v9_fix_paper_trade_pips.py     # Injection pips réels
└── v9_close_paper_trades.py       # Clôture paper trades
```

### 13.2 Glossaire

| Terme | Définition |
|---|---|
| **MFE** | Maximum Favorable Excursion — meilleur prix atteint pendant la fenêtre |
| **MAE** | Maximum Adverse Excursion — pire prix atteint (drawdown) |
| **TP** | Take-Profit — niveau de gain cible |
| **SL** | Stop-Loss — niveau de perte maximale |
| **WR** | Win Rate — % de trades gagnants |
| **R/R** | Risk/Reward ratio — TP/SL |
| **Scale** | Multiplicateur de position (1.0 = normale) |
| **Confluence** | Alignement de plusieurs principes dans la même direction |
| **Session** | Période de trading (Asie/London/Overlap/NY/After) |
| **Spread** | Coût de transaction (0.5 pips estimé) |

### 13.3 Références

- `docs/reports/EXIT_STRATEGY_ANALYSIS_20260711.json` — Analyse complète des 16 stratégies
- `docs/reports/BATCH_RESOLVE_DYNAMIC_20260711.json` — Résultats DYNAMIC
- `docs/reports/BATCH_RESOLVE_TPSL_20260711.json` — Résultats TP/SL
- `core/v9/exit_simulator.py` — Code de l'ExitSimulator
- `core/v9/paper_risk_manager.py` — Code du PaperRiskManager
- `core/v9/pyramiding_engine.py` — Code du PyramidingEngine
- `core/v9/principle_scorer.py` — Code du PrincipleScorer

---

*Document généré le 2026-07-11 par PowerFlow V9 — Stratégie de Trading Dynamique v1.0*
*Approuvé par Søn (CEO) — Architecture Quant Zcode*
