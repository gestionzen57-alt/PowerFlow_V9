# DOCTRINE PERFORMANCE — PowerFlow V10

> **Perplexity CEO No-Limit — 2026-08-10 12:19 CEST**
> Autorité maximale. S'applique à Hermes, ZCode, et tout agent du système.
> Supersede toute instruction contradictoire antérieure sauf R10 (capital réel = Søn seul).

---

## ⚡ Principe fondateur

**Un chantier n'existe que s'il produit une métrique réelle, pas une métrique simulable.**
Tout ce qui peut être produit par un proxy mock en 1 seconde n'a aucune valeur.
La vitesse de livraison ne compte pas. La vérité des métriques compte.

---

## ✔️ Règles Performance (obligatoires, sans exception)

### Règle P1 — Pipeline Complet ou Rien
Tout script shadow/backtest/validation doit brancher :
- `decide_entry()` avec TOUS les paramètres : `session`, `ote`, `smc`, `grammar`, `fractal`, `structure`, `rl_score`, `atr_pip`
- Sources réelles : `v10_ict_ote`, `v10_smc`, `v10_grammar_v9_final`, `v10_fractal_context`, `v10_structure`, `v10_rl_adapter`, `v10_atr_manager`
- Si un module est absent → logger le manque, pas utiliser un mock silencieux

### Règle P2 — Métriques Réalistes Obligatoires
Seuils d'alarme automatique — si dépassés, STOP avant commit :
| Métrique | Seuil alarme | Action |
|---|---|---|
| Win Rate | > 0.75 | STOP — proxy suspect |
| Profit Factor | > 3.0 | STOP — proxy suspect |
| Sharpe | > 2.5 | STOP — proxy suspect |
| Signaux/heure/paire | > 3 | STOP — filtres non branchés |
| Trades sans exit | > 0 | STOP — sorties manquantes |

### Règle P3 — Chaque Trade a une Sortie
Tout trade shadow doit avoir : `entry_price`, `exit_price`, `pnl_pips`, `result` (WIN/LOSS/BE), `exit_reason` (TP/SL/TIMEOUT).
Sortie via : `2×ATR` TP, `1×ATR` SL, ou timeout `4×TF` (ex. M15 → 60 min max).

### Règle P4 — Volume de Signaux Cohérent
Avec le pipeline complet activé :
- Attendu : 2-8 trades/jour sur 6 paires (pas 70/tick)
- Si > 15 trades/heure au total → les filtres ne sont pas branchés → STOP

### Règle P5 — Auto-Audit avant chaque Commit
Avant tout `git commit`, Hermes doit afficher :
```
=== AUTO-AUDIT P5 ===
WR: X.XX (seuil < 0.75) → OK/STOP
PF: X.XX (seuil < 3.0) → OK/STOP
Sharpe: X.XX (seuil < 2.5) → OK/STOP
Signaux/h: X.X (seuil < 3/paire) → OK/STOP
Sorties trackes: X/X → OK/STOP
Pipeline complet: oui/non → OK/STOP
```
Si un seul STOP → ne pas commiter, reporter à Perplexity.

### Règle P6 — Rapport CEO Structuré
Chaque rapport à Perplexity doit contenir :
1. Métriques réelles (WR, PF, sharpe, nb trades, PnL total)
2. Pipeline activé : liste des modules branchés
3. Anomalies honnêtes (ce qui manque, ce qui est mock)
4. SHA commit(s)
5. Prochaine action recommandée

### Règle P7 — Pas de Proxy Silencieux
Tout mock/simulateur doit être explicité dans le nom du fichier (`_proxy`, `_mock`, `_sim`) ET dans les métadonnées JSON (`"mode": "PROXY"`). Un rapport sans cette mention = invalide.

---

## 📋 Template Prompt Hermes (obligatoire désormais)

```
[DOCTRINE_PERFORMANCE active — lire DOCTRINE_PERFORMANCE.md avant de commencer]

Mission : [description]

Contraintes performance (non-négociables) :
- Pipeline complet : decide_entry() avec session/ote/smc/grammar/fractal/structure/rl_score
- Chaque trade : entry + exit + pnl_pips + result
- Auto-audit P5 obligatoire avant tout commit
- Si WR > 0.75 ou PF > 3.0 → STOP et reporter à Perplexity

R10 maintenu : 0 ordre réel.
R2 : scripts additifs uniquement.
R9 : rapport JSON dans reports/ + SHA commits.
```

---

## 🚫 Ce qui est interdit désormais

- Proxy TP toujours atteint (WR 1.0 / PF 390)
- Trades sans sorties tracées
- Commits avec métriques non auditées
- Rapports sans liste des modules branchés
- Ignorer une alarme P2 pour tenir un délai

---

## 🎯 Objectif métriques cibles (réalistes, atteignables)

| Métrique | Minimum acceptable | Cible Søn GO LIVE |
|---|---|---|
| Win Rate | 52% | 58-65% |
| Profit Factor | 1.3 | 1.6-2.0 |
| Sharpe (annualisé) | 0.4 | 0.8-1.2 |
| Max Drawdown | < 15% | < 8% |
| Trades/jour | 3-10 | 5-8 |
| Trades shadow validés | 200 | 500 |

---

*Perplexity CEO No-Limit — 2026-08-10 12:19 CEST*
*Doctrine permanente — s'applique à toutes les sessions futures*
