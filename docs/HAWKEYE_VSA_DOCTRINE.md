# HAWKEYE VSA DOCTRINE — PowerFlow V9

> **Statut** : Document pivot — Source de vérité sur la lecture Hawkeye/VSA  
> **Auteur** : Perplexity (session 2026-08-14) — validé Sön N.  
> **Priorité** : CRITIQUE — tout agent codant ou interprétant un signal Hawkeye DOIT lire ce document avant d'agir.

---

## ⚠️ AVERTISSEMENT STRUCTURANT

**La confusion la plus dangereuse du projet est de traiter Fatman comme un indicateur VSA de volume.  
Ce n'en est PAS un.  
Fatman = force de devises (currency strength meter).  
VSA = lecture volume/spread/close sur une barre.**

Ces deux outils jouent des rôles orthogonaux dans la chaîne de décision.

---

## 1. FATMAN — Ce que c'est réellement

### Définition
Fatman est un **indicateur de force relative inter-devises** (currency strength meter) de la suite Hawkeye Traders.  
Il calcule, en temps réel, la force ou la faiblesse de chaque devise majeure contre toutes les autres,  
en agrégeant des centaines de calculs par seconde sur l'ensemble des paires disponibles.

### Ce qu'il affiche
- Une courbe colorée par devise dans un oscillateur séparé (sous-fenêtre).
- Les couleurs standard : USD=cyan, EUR=vert, JPY=magenta, GBP=orange, AUD=rouge, CAD=jaune, NZD=bleu, CHF=blanc.
- L'axe zéro est la ligne de neutralité.
- **Au-dessus de zéro** = devise forte (demande institutionnelle).
- **En-dessous de zéro** = devise faible (offre institutionnelle).

### Le signal Fatman
**L'alerte se déclenche sur le CROISEMENT DE LA LIGNE ZÉRO.**
- Croisement vers le haut → force croissante → opportunité d'achat sur la paire impliquant cette devise côté base.
- Croisement vers le bas → faiblesse croissante → opportunité de vente sur la paire impliquant cette devise côté base.
- Un croisement divergent (ex. GBP monte / USD descend simultanément) = signal fort sur GBPUSD.

### Ce que Fatman n'est PAS
- ❌ Il ne lit pas le volume d'une barre.
- ❌ Il ne détecte pas l'absorption, No Demand, No Supply.
- ❌ Il ne génère pas de signal d'entrée autonome sur une barre spécifique.
- ❌ Il n'est pas un oscillateur de momentum type RSI/MACD.

### Rôle dans la chaîne PowerFlow
```
FATMAN = FILTRE DE CONTEXTE (sélection de paire/direction)
    ↓
VSA VOLUME = VALIDATION DE L'ENTRÉE (effort/résultat sur la barre)
    ↓
EFFORT/RÉSULTAT = FILTRE FINAL (qualité du setup)
```

**Fatman seul ne génère PAS d'ordre. Il oriente.**

### Paramètre critique
- `LookBack` : nombre de barres calculées. Doit être > 100. Plus c'est grand, plus c'est lent.
- Hawkeye déconseille `CalculateEveryTick = true` → **calcul en end-of-bar uniquement.**

### Fatboy vs Fatman
- **Fatman** : force/faiblesse pure par devise.
- **Fatboy** : ajoute la corrélation entre marchés — si deux paires corrélées divergent, signal de retournement ou confirmation plus fort.

---

## 2. VSA — Volume Spread Analysis (Hawkeye)

### Origine et différence avec le VSA classique
Le VSA original est développé par Tom Williams (basé sur la méthode Wyckoff).  
Hawkeye Traders (Nigel Hawkes) a étendu la méthode avec **deux corrections majeures** :

1. **Intégration de l'Open** : Williams analyse Close/High/Low. Hawkeye intègre l'Open, ce qui évite des faux signaux significatifs sur les gaps et sessions asiatiques.
2. **300+ calculs par barre** : comparaison volume actuel vs moyenne mobile, spread vs ATR, position du close dans le range — tout cela pondéré ensemble.

### Les 3 variables fondamentales

| Variable | Mesure | Signification |  
|----------|--------|---------------|
| **Volume** | Qui participe ? | Institutions = gros volume, retail = petit volume |
| **Spread** (High-Low) | Jusqu'où le prix s'est déplacé | Énergie libérée par la barre |
| **Close Location** | Qui a gagné la barre ? | Close haut = acheteurs dominants, Close bas = vendeurs dominants |

### Classification du Spread (σ-bands)
Hawkeye classe le spread de chaque barre par rapport à la moyenne des N dernières barres :

| Label | Condition |
|-------|-----------|
| **Narrow** | Spread < (moyenne − 0.4σ) |
| **Average** | Spread entre ±0.4σ |
| **Wide** | Spread jusqu'à +0.7σ |
| **Very Wide** | Spread jusqu'à +1.0σ |
| **Ultra Wide** | Spread > +1.0σ |

> Le paramètre `ATR Period` (défaut 20 barres) contrôle cette fenêtre de référence.

### Classification du Volume

| Label | Condition |
|-------|-----------|
| **Very Low** | < 25% de la moyenne |
| **Low** | 25–75% de la moyenne |
| **Average** | 75–125% de la moyenne |
| **High** | 125–200% de la moyenne |
| **Very High** | > 200% de la moyenne |
| **Ultra High** | > 300% de la moyenne |

---

## 3. EFFORT vs RÉSULTAT — Le concept le plus mal codé

### La loi fondamentale
> **L'effort (volume) doit produire un résultat proportionnel (spread + direction du close).**  
> Toute **rupture de cette proportionnalité** révèle une activité institutionnelle cachée.

### Matrice des 8 patterns VSA critiques

| Pattern | Volume | Spread | Close | Signal | Interprétation |
|---------|--------|--------|-------|--------|----------------|
| **Effort Normal** | Haut | Large | Haut | Neutre | Mouvement sain, pas de signal |
| **Up-Thrust** | Variable | Large UP | BAS | 🔴 VENTE | Piège haussier — décharge institution |
| **No Demand** | Très faible | Étroit | Variable UP | 🔴 VENTE | Pas d'intérêt d'achat — continuation baissière |
| **No Supply** | Très faible | Étroit | Variable DOWN | 🟢 ACHAT | Pas d'intérêt de vente — continuation haussière |
| **Absorption / Stopping Volume** | Ultra haut | Narrow ou Average | Variable | ⚠️ INVERSION | L'institution absorbe tout le selling/buying |
| **Climax Volume** | Ultra haut | Large | Opposé au mouvement | 🔄 RETOURNEMENT | Épuisement — fin de tendance imminente |
| **Test de No Supply** | Faible | Narrow | HAUT | 🟢 ACHAT | Confirmation d'absence de vendeurs |
| **Wide Spread Up + High Volume** | Haut | Large UP | HAUT | 🟢 ACHAT | Signal haussier institutionnel |

### L'erreur la plus fréquente en code
**Volume élevé ≠ signal haussier brut.**

Exemple piège :
- Barre avec volume 3x la moyenne (Ultra High) + spread étroit + close au milieu → **Absorption baissière**
- Le code naïf lit "volume très fort" → score haussier élevé → **ERREUR CRITIQUE**
- Le code correct lit volume+spread+close **ensemble** → détecte l'absorption → score baissier ou neutre

### Règle de code impérative
```python
# FAUX (code naïf)
if volume > avg_volume * 2:
    score += bullish_weight  # ❌ ERREUR

# CORRECT (logique VSA)
if volume > avg_volume * 2:
    if spread < avg_spread * 0.8 or close_location < 0.4:
        score += absorption_weight  # signal de RETOURNEMENT, pas de continuation
    elif spread > avg_spread * 1.3 and close_location > 0.6:
        score += bullish_institutional_weight  # là c'est haussier
```

### Close Location — calcul
```python
close_location = (close - low) / (high - low)  # entre 0.0 et 1.0
# > 0.7 = acheteurs dominants
# < 0.3 = vendeurs dominants
# 0.3–0.7 = indécis
```

---

## 4. CHAÎNE DE DÉCISION POWERFLOW — RÔLE DE CHAQUE COMPOSANT

```
┌─────────────────────────────────────────────────────────┐
│  ÉTAPE 1 : CONTEXTE INTER-MARCHÉ (FATMAN)               │
│  Question : Quelle devise est forte/faible ?            │
│  Output : Paire candidate + direction probable          │
│  Trigger : Croisement ligne zéro d'une ou deux devises  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  ÉTAPE 2 : VALIDATION VSA VOLUME (Hawkeye Volume)       │
│  Question : L'effort produit-il un résultat ?           │
│  Output : Type de barre VSA (absorption, no demand...)  │
│  Trigger : End-of-bar uniquement                        │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  ÉTAPE 3 : FILTRE EFFORT/RÉSULTAT                       │
│  Question : Cohérence volume + spread + close ?         │
│  Output : Score de qualité du setup (0–100)             │
│  Règle : Score < 60 → pas d'entrée                      │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  ÉTAPE 4 : CONFIRMATION CONTEXTUELLE                    │
│  Wyckoff phase (accumulation/distribution) ?            │
│  Niveau de liquidité proche ?                           │
│  Session active (Londres/NY) ?                          │
└─────────────────────────────────────────────────────────┘
```

---

## 5. POINTS CRITIQUES POUR LE CODE V9

### ❌ Erreurs identifiées à corriger
1. **Volume haut = haussier** → remplacer par logique volume+spread+close combinée.
2. **Fatman utilisé comme signal d'entrée direct** → Fatman est un filtre de contexte, pas un trigger.
3. **Calcul intra-barre** → passer en end-of-bar (fermeture de bougie confirmée).
4. **Open ignoré dans le calcul VSA** → l'open est obligatoire pour éviter les faux signaux sur gaps.
5. **Pas de pondération σ sur le spread** → utiliser les σ-bands, pas juste une comparaison brute à la moyenne.

### ✅ Règles impératives
- **Fatman** = filtre #1 → orientation paire/direction
- **VSA Volume** = filtre #2 → validation de la barre
- **Effort/Résultat** = filtre #3 → qualité du setup
- Les trois filtres doivent être alignés pour déclencher un signal de qualité institutionnelle.
- Un signal Fatman seul = contexte, pas ordre.
- Un signal VSA seul = information, pas ordre.
- La conjonction des deux = setup tradable.

---

## 6. RÉFÉRENCE PARAMÈTRES HAWKEYE

| Paramètre | Valeur par défaut | Rôle |
|-----------|-------------------|------|
| `ATR Period` | 20 barres | Fenêtre de référence spread |
| `Volume Period` | 20 barres | Fenêtre de référence volume |
| `LookBack` (Fatman) | 100+ barres | Calcul force devises |
| `CalculateEveryTick` | FALSE | End-of-bar UNIQUEMENT |
| Seuil absorption | Volume > 2x moy + spread < 0.8x moy | Détection institutionnelle |
| Seuil No Demand | Volume < 0.5x moy + spread étroit + close mid | Zone de distribution |

---

## 7. LEXIQUE RAPIDE

| Terme | Définition PowerFlow |
|-------|----------------------|
| **Fatman** | Indicateur de force relative de devises — filtre de contexte inter-marché |
| **Fatboy** | Extension Fatman avec corrélation inter-marchés |
| **VSA** | Volume Spread Analysis — lecture comportementale d'une barre via volume+spread+close |
| **Effort** | Volume déployé sur une barre |
| **Résultat** | Spread + direction du close produits par cet effort |
| **Absorption** | Volume ultra-haut + spread étroit → institution absorbe le flux opposé |
| **No Demand** | Volume très bas sur mouvement up → pas d'intérêt institutionnel à l'achat |
| **No Supply** | Volume très bas sur mouvement down → pas d'intérêt institutionnel à la vente |
| **Up-Thrust** | Large spread up + close bas → piège haussier institutionnel |
| **Climax** | Volume extrême + spread large dans la direction du trend → épuisement imminent |
| **Close Location** | (Close - Low) / (High - Low) — qui a dominé la barre |
| **End-of-bar** | Calcul uniquement sur bougie fermée confirmée |

---

## 8. SOURCES ET RÉFÉRENCES

- Hawkeye Traders — Guide MT4/MT5 officiel (Nigel Hawkes)
- Tom Williams — "Master the Markets" (VSA origine)
- Richard Wyckoff — méthode de lecture des forces institutionnelles
- LuxAlgo — implémentation open-source HawkEye Volume Indicator
- Forums : Forex Factory thread VSA, EliteTrader VSA discussion

---

> **Dernière mise à jour** : 2026-08-14  
> **Session** : Perplexity — Audit Hawkeye/VSA PowerFlow V9  
> **Action suivante** : Audit du module VSA dans le code source pour vérifier conformité avec ce document.
