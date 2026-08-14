# DOCTRINE PROPRIÉTAIRE SØN — Interprétation PowerFlow V10

**Statut** : Document vivant — source de vérité interprétative  
**Créé** : 2026-08-14 par Perplexity (élicitation post-audit Hermes)  
**Règle absolue** : Tout agent traitant un signal Hawkeye/VSA/Fatman DOIT lire ce fichier AVANT toute action  

> Ce document capture CE QUI N'EST PAS dans Tom Williams ni AnnieMQ.  
> La doctrine Williams est la couche de structure. L'interprétation Søn est la couche de décision.

---

## 1. PHILOSOPHIE FONDAMENTALE

PowerFlow V10 n'est pas un système VSA classique. C'est un système de **lecture comportementale institutionnelle** qui utilise VSA comme détecteur de structure, Fatman comme contexte de force inter-devises, et la cinétique comme filtre de conviction.

**Trois niveaux de lecture simultanés** :
1. **Structure** (VSA) — Que dit la barre physiquement ? (spread, volume, close location, open)
2. **Contexte** (Fatman/Hawkeye) — Dans quelle direction est le flux institutionnel dominant ?
3. **Conviction** (Cinétique) — Est-ce que la force est en phase d'accélération, d'épuisement, ou de divergence ?

Un signal valide exige les 3 couches alignées. Une seule couche = bruit.

---

## 2. COUCHE STRUCTURE — VSA Søn vs Williams

### 2.1 Ce que Williams dit (correct, mais incomplet)
- Volume élevé + spread large + close haut = MARKUP institutionnel
- Volume élevé + spread étroit = ABSORPTION (retournement)
- close_location < 0.4 sur volume élevé = UPTHRUST (piège)

### 2.2 Ce que Søn ajoute (NON CODÉ à ce jour)

**Lecture fractale multi-TF** :
- Une barre M15 ne se lit pas seule. Elle se lit dans le contexte de la barre M30 et H1 simultanément.
- Un MARKUP M15 sur un MARKDOWN H1 = signal annulé (divergence fractale)
- Un ACCUMULATION M15 sur un ACCUMULATION M30 = signal amplifié (confluence fractale)
- **Règle Søn** : La résolution supérieure (H1) prime toujours sur la résolution inférieure (M15)

**Lecture comportementale de séquence** :
- Ce qui compte n'est pas une barre isolée mais la **séquence comportementale** des 3-5 barres précédentes
- Un MARKUP isolé = bruit. Un MARKUP après 2 ACCUMULATION successifs = signal institutionnel
- Un DISTRIBUTION après MARKUP prolongé = retournement crédible
- **Séquences canoniques à coder** :
  - `ACCUMULATION × 2 → MARKUP` = entrée longue valide
  - `MARKUP × 3+ → DISTRIBUTION` = sortie / short setup
  - `NEUTRAL × 3+ → MARKUP fort` = breakout institutionnel
  - `UPTHRUST → MARKDOWN` = confirmation piège confirmé

**Lecture de l'open (sessions)** :
- L'open de la bougie OVERLAP (12h-16h UTC) par rapport au close asiatique est critique
- Un gap haussier à l'open OVERLAP sur MARKUP = momentum institutionnel fort
- Un gap baissier à l'open OVERLAP sur contexte Fatman haussier = divergence → attendre

---

## 3. COUCHE CONTEXTE — Fatman/Hawkeye Søn vs Williams

### 3.1 Règle absolue (déjà codée post-audit P2)
Fatman = **filtre de sélection de paire et de direction UNIQUEMENT**  
Fatman ≠ trigger d'entrée  
Fatman ≠ sizing  
Fatman ≠ conviction  

### 3.2 Interprétation Søn du delta_force

**Ce que le delta_force signifie vraiment** :
- `delta_force > 50` : flux institutionnel dominant — contexte favorable, PAS un signal
- `delta_force 25-50` : flux institutionnel modéré — meilleure fenêtre selon replay (WR 58-100%)
- `delta_force > 50` : **paradoxalement dégradé en WR** (WR 29% sur delta≥50) — sur-extension, institutionnel déjà positionné
- **Règle Søn** : delta 25-40 = zone optimale. Delta > 50 = méfiance (smart money déjà dans le trade)

**Croisement zéro Fatman** :
- Un croisement de zéro récent (< 3 barres M15) = momentum de force en cours = favorable
- Un croisement de zéro ancien (> 10 barres) = force établie mais peut s'épuiser
- Pas de croisement = force stable = contexte neutre

### 3.3 Sélection de paire selon Søn
- On trade la devise FORTE vs la devise FAIBLE (règle universelle Hawkeye)
- EURUSD haussier = EUR fort + USD faible simultanément (pas EUR fort seul)
- En cas de doute sur la paire, on passe. La clarté est une condition d'entrée.

---

## 4. COUCHE CONVICTION — Cinétique Søn

### 4.1 Concept (NON CODÉ à ce jour)
La cinétique mesure **l'énergie de la tendance** — pas sa direction, son intensité et sa santé.

**3 états cinétiques** :
1. **ACCÉLÉRATION** : force_delta croissant sur 3+ barres → signal amplifié, sizing agressif autorisé
2. **PLATEAU** : force_delta stable → signal normal, sizing standard
3. **ÉPUISEMENT** : force_delta décroissant malgré prix en continuation → signal annulé (divergence cinétique)

**Divergence cinétique (règle critique)** :
- Prix monte mais force_delta baisse = distribution déguisée
- Prix baisse mais force_delta monte = accumulation déguisée
- Dans les deux cas : **NE PAS entrer dans la direction du prix, attendre retournement**

### 4.2 Lien avec v10_cinematics.py (partiellement codé)
- Le module existe mais ses outputs (`pic_force`, `exhaustion_flag`, `divergence_flag`) ne sont pas branchés sur la gate d'entrée finale
- **Action requise** : brancher `exhaustion_flag=True` → blocage entrée systématique
- **Action requise** : brancher `divergence_flag=True` → signal annulé + log raison

---

## 5. CALIBRATION EMPIRIQUE (replay 2026-08-14)

Données issues du replay 5 jours Hermes — source de vérité empirique :

| Paramètre | Valeur optimale | Valeur actuelle | Action |
|---|---|---|---|
| Fenêtre horaire | **12h UTC uniquement** (WR 93%) | 12-16h UTC (WR 22-40% sur 13-15h) | Restreindre |
| delta_force | **25-40** (WR 58-100%) | ≥25 (WR 29% sur 50+) | Resserrer seuil haut |
| TP/SL | 2.0×ATR / 1.0×ATR | Identique | Valider sur 20j |
| Paires prioritaires | **AUDUSD** (Sharpe +0.36), EURUSD borderline | 6 paires | Filtrer USDCHF (Sharpe -1.92) |
| Stat minimum | **20j minimum** | 5j utilisés | Élargir fenêtre replay |

---

## 6. CE QUI RESTE À CAPTURER (backlog élicitation)

Sessions d'élicitation Søn à planifier :

- [ ] **Séquences comportementales canoniques** : les 5-7 patterns que Søn reconnaît intuitivement
- [ ] **Règles de sortie** : Søn sort comment ? Sur barre de signal contraire ? Sur épuisement cinétique ?
- [ ] **Régimes de marché** : Comment Søn adapte-t-il son filtre selon le régime (trending / ranging / choppy) ?
- [ ] **Gestion du risque Søn** : R:R fixe ou variable selon conviction ? Position sizing selon force cinétique ?
- [ ] **Sessions préférées** : OVERLAP exclusif ? Parfois London open ? Jamais Asie ?

**Format d'élicitation recommandé** :
> "Montre-moi un trade que tu aurais pris. Pourquoi ? Qu'est-ce que tu voyais ?"
> → Extraire les règles implicites barre par barre

---

## 7. RÈGLES POUR LES AGENTS

1. **Hermes** : Tu implémentes ce fichier, pas Tom Williams. Lis cette section avant tout patch VSA.
2. **Claude Code / ZCode** : Tout nouveau module VSA doit référencer `SON_INTERPRETATION.md` dans son header.
3. **Perplexity** : Ce fichier est le seul arbitre en cas de divergence entre doctrine Williams et comportement observé.
4. **Tout agent** : Si tu doutes entre Williams et ce fichier, ce fichier gagne.

---

*Document créé le 2026-08-14 par Perplexity (post-audit Hermes VSA 14/08). À enrichir après chaque session d'élicitation Søn.*
