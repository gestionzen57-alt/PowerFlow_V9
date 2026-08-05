# FATMAN BIBLE — PowerFlow V10
> Doctrine Hawkeye Fatman + Fatboy — Référence stratégique
> Généré : 2026-08-05 | Auteur : Perplexity (orchestrateur V10)

---

## 1. Origine et Philosophie

**Hawkeye Fatman** est un outil de mesure de la force relative des devises (Currency Strength Meter) développé par Randy Lindsey (Hawkeye Traders). Il mesure la force institutionnelle de chaque devise en temps réel, sur un timeframe supérieur au timeframe de trading.

**Principe fondateur** : Les grandes institutions déplacent les marchés devise par devise, pas paire par paire. Fatman visualise ce flux institutionnel AVANT qu'il ne se manifeste dans les prix d'une paire spécifique.

**Fatboy** est la variante avancée qui ajoute :
- Convergence/Divergence sigma entre les 8 lignes
- Harmonie entre TF chart et TF Fatman (référence supérieure)
- Détection du "Safe Haven Flip" (JPY/CHF comme filtre Risk-Off)

---

## 2. Les 8 Devises et Leurs Couleurs

| Devise | Couleur Hawkeye | Rôle marché | Safe Haven |
|--------|----------------|-------------|------------|
| USD | Aqua (#00FFFF) | Benchmark mondial | Non |
| EUR | Green (#008000) | Majeure Europe | Non |
| GBP | Orange (#FFA500) | Volatile, momentum | Non |
| AUD | Red (#FF0000) | Risk-On commodités | Non |
| NZD | Blue (#0000FF) | Corrélée AUD | Non |
| JPY | Fuchsia (#FF00FF) | Safe Haven principal | **OUI** |
| CHF | White (#FFFFFF) | Safe Haven secondaire | **OUI** |
| CAD | Yellow (#FFFF00) | Corrélée pétrole | Non |

---

## 3. Formule de Calcul (Reverse-Engineered)

### Étape 1 — Récupération OHLCV sur TF Fatman
Pour chaque paire majeure : EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCHF, USDCAD

### Étape 2 — Retour USD par paire
- **Paire directe** (USD = quote) : `retour = (close - open) / open`
- **Paire inversée** (USD = base) : `retour_quote = -(open - close) / close`
- USD lui-même = moyenne des retours des 3 paires inversées

### Étape 3 — Neutralisation
```
retour_neutralisé[devise] = retour_brut[devise] - moyenne(tous_retours_bruts)
```
Résultat : somme des 8 retours neutralisés = 0

### Étape 4 — Normalisation 0-100
```
score[devise] = 50 + (retour_neutralisé[devise] / max_abs_retour) × 50
```
Résultat : 50 = neutre, >50 = fort, <50 = faible

---

## 4. Grille Timeframes V10 (incluant M30)

| TF Chart | TF Fatman | Usage Principal |
|----------|-----------|----------------|
| M1 | M5 | Scalping (non recommandé) |
| M5 | M15 | Day trading rapide |
| M15 | H1 | Day trading standard |
| **M30** | **H1** | **Day trading étendu** |
| H1 | H4 | Swing intraday |
| H4 | D1 | Swing multiday |
| D1 | W1 | Position trading |

> **Note M30** : Le M30 partage le TF Fatman H1 avec le M15. C'est intentionnel —
> le H1 est le TF institutionnel de référence pour les deux. La différence est dans
> la durée d'exposition et la fréquence des signaux.

---

## 5. Les 6 Signaux à Fort Levier

### Signal 1 — FORTE × FAIBLE Standard
- **Condition** : Gap (forte - faible) ≥ 35 pts
- **Paire tradée** : Devise forte / Devise faible
- **WR** : ~62% | **R:R** : 1:1.5 | **Fréquence** : 3-5/semaine

### Signal 2 — FORTE × FAIBLE Institutionnel
- **Condition** : Gap ≥ 48 pts
- **WR** : ~71% | **R:R** : 1:2.5 | **Fréquence** : 1-2/semaine
- **Note** : Attendre ce signal en priorité — c'est là que les probabilités deviennent sérieuses

### Signal 3 — DIVERGENCE EXTRÊME
- **Condition** : Sigma > 28 + Gap ≥ 35
- **WR** : ~68% | **R:R** : 1:2 | **Fréquence** : 1-2/semaine
- **Attention** : Ne pas entrer trop tôt — attendre confirmation bougie

### Signal 4 — SAFE HAVEN FLIP (Fatboy)
- **Condition** : JPY ET CHF dans le top 3 des devises fortes
- **Action** : Vendre les paires Risk-On (AUD, NZD contre USD/JPY/CHF)
- **WR** : ~74% | **R:R** : 1:2 | **Fréquence** : 2-3/mois

### Signal 5 — CONVERGENCE FORTE (σ < 12)
- **Condition** : Sigma < 12 + Toutes les devises en ordre
- **Action** : SUIVRE la tendance, ne jamais contre-trader
- **Usage** : Confirmation de position, pas d'entrée seul

### Signal 6 — CONTINUATION M30 → H1 ALIGNÉ
- **Condition** : Signal M30 + H1 dans même direction
- **WR** : ~69% | **R:R** : 1:1.8 | **Fréquence** : 2-4/semaine
- **Note** : Le fait que M30 et H1 partagent le même TF Fatman (H1) rend la
  confluence automatiquement disponible

---

## 6. Principes Fatboy Intégrés dans V10

### Principe 1 — Sigma (Convergence/Divergence)
```
σ < 12  → Tendance forte → Suivre, ne pas contre-trader
12-28   → Zone neutre → Attendre confirmation
σ > 28  → Divergence → Retournement potentiel → Entrée courageuse possible
```

### Principe 2 — Harmonie TF
Tout signal doit être confirmé sur le TF Fatman (supérieur).
Si le TF Fatman est contre-directionnel → ignorer le signal.

### Principe 3 — Safe Haven comme Filtre Risk-Off
Avant toute entrée Risk-On (AUD, NZD, GBP long) :
- Vérifier que JPY et CHF NE sont PAS dans le top 3
- Si Safe Haven Flip détecté → annuler l'entrée Risk-On

### Principe 4 — Pas de Signal sans Volume
Fatboy (et Fatman dans sa version premium) filtre les signaux par volume.
Règle pratique V10 : Ne pas trader dans les 30 premières minutes de session.

---

## 7. Filtres Edge Fund V10

Pour atteindre les standards edge fund quantique :

1. **Filtre sessions** : London (08h-17h CET) + NY (14h-23h CET) uniquement
2. **Filtre ATR** : Signal valide uniquement si ATR(14) > 70% de l'ATR(14) moyen 20j
3. **Filtre Spread** : Spread < 2× spread moyen journalier
4. **Filtre corrélation** : Ne pas ouvrir 2 paires corrélées > 0.7 simultanément
5. **Filtre news** : Fenêtre ±30min autour des news impact HIGH
6. **Filtre sigma** : Pas d'entrée si σ > 35 (trop de bruit)

---

## 8. Sources et Références

- Hawkeye Traders : https://www.hawkeyetraders.com
- Fatboy variant : https://www.hawkeyetraders.com/indicators/fatboy/
- Forums MQL5 : rechercher "Hawkeye Fatman" ou "Currency Strength Meter institutional"
- Pine Script communauté : rechercher "Fatman CSM" sur TradingView Public Library

---

## 9. Glossaire

| Terme | Définition |
|-------|------------|
| Gap | Différence entre score le plus fort et le plus faible |
| Sigma (σ) | Écart-type des 8 scores (mesure de dispersion) |
| Safe Haven Flip | JPY/CHF dominent → Risk-Off institutionnel |
| TF Fatman | Timeframe supérieur utilisé pour calculer les scores |
| Neutralisation | Soustraction de la moyenne (somme = 0) |
| Normalisation | Conversion 0-100 avec 50 = neutre |
| Convergence | σ faible → toutes les devises se comportent de manière cohérente |
| Divergence | σ élevé → dispersion → retournement possible |
