# LECTURE DES FORCES PAR TIMEFRAME — échelles propres, pas d'agrégation (Søn 13/08)

> **Mandat CEO (13/08, brainstorming)** : *"la valeur des forces est propre
> au time frame, le moteur de l'indicateur la calcule avec tous les facteurs
> qui lui sont propres... les valeurs ne sont pas agrégées ! c'est pour cela
> qu'il y a une lecture sur chaque time frame pour lire les valeurs de
> forces... c'est pour cela que la lecture temporelle est complexe... un
> croisement en 5 min avec des valeurs dans les zones dynamiques extrêmes
> en 15 min 30 min peut montrer le retournement, confirmer avec double test
> de niveau de rejet de prix, ou après croisement une répulsion."*
>
> **Statut** : brainstorming actif. Ce document corrige une hypothèse fausse
> (agrégation des forces) et reformule la lecture temporelle correcte.

---

## CORRECTION FONDAMENTALE — les forces ne sont PAS agrégées

### L'erreur (hypothèse fausse)

J'avais supposé que les forces M5/M15/M30/H1 devaient être cohérentes
(le M15 = agrégation du M5). J'ai vu GBP=68 en M5 et GBP=28 en M15 au même
moment et j'ai crié "incohérence !".

### La vérité (correction Søn)

**Chaque timeframe a sa PROPRE échelle de force.** Le moteur de l'indicateur
Fatman calcule la force de chaque devise avec TOUS les facteurs propres à
ce timeframe (fenêtre, lissage, sensibilité, volatilité du TF...). Les
valeurs ne sont pas agrégées d'un TF à l'autre.

```
M5  : GBP=68  → "GBP très fort" DANS L'ÉCHELLE M5
M15 : GBP=28  → "GBP faible" DANS L'ÉCHELLE M15
M30 : GBP=37  → "GBP moyen-faible" DANS L'ÉCHELLE M30
H1  : GBP=45  → "GBP moyen" DANS L'ÉCHELLE H1
```

Ces 4 valeurs ne se contredisent PAS — elles se lisent chacune dans leur
propre échelle. C'est comme lire la température en Celsius, Fahrenheit et
Kelvin : 0°C = 32°F = 273K, trois échelles, une réalité.

### La conséquence pour la lecture

**On ne compare JAMAIS les valeurs brutes entre TF.** On compare :
- La valeur d'un TF à SES PROPRES zones (extrêmes, moyennes, seuils)
- La DIRECTION du mouvement dans chaque TF (monte/descend, croise/décroise)
- Le TIMING des événements (le M5 croise avant le M15 ?)

---

## JUXTAPOSITION DE LA LECTURE — comment lire les forces par TF

### Principe 1 — LIRE CHAQUE TF DANS SON ÉCHELLE

```
POUR CHAQUE TF (M5, M15, M30, H1) :
  1. Calibrer les zones de CE TF :
     - zone basse (force faible) : percentile < 25 de l'historique du TF
     - zone moyenne : percentile 25-75
     - zone haute (force forte) : percentile > 75
     - zone DYNAMIQUE EXTRÊME : percentile > 90 ou < 10
  2. Lire la valeur DANS ces zones (pas en absolu)
  3. Lire la direction (pente, accélération) DANS ce TF
```

### Principe 2 — LA CASCADE TEMPORELLE (le croisement se propage)

```
UN CROISEMENT M5 (GBP passe au-dessus de USD) :
  → regarder si les valeurs M15/M30 sont dans les ZONES DYNAMIQUES EXTRÊMES
  → si OUI : le croisement M5 + zones extrêmes M15/M30 = RETOURNEMENT POSSIBLE
  → si NON : croisement M5 isolé = bruit probable
```

### Principe 3 — LA CONFIRMATION PAR LE PRIX (double test de rejet)

```
APRÈS UN CROISEMENT M5 + ZONES EXTRÊMES M15/M30 :
  → CONFIRMER avec le prix : double test de niveau de rejet
    1er test : le prix touche un niveau (résistance/support) et rebondit
    2e test : le prix retouche le niveau et rebondit à nouveau
  → double test réussi = retournement CONFIRMÉ
  → sinon = pas de confirmation, on attend
```

### Principe 4 — LA RÉPULSION APRÈS CROISEMENT

```
APRÈS UN CROISEMENT, DEUX SCÉNARIOS :
  A. PROPAGATION : le croisement se confirme (M15 puis M30 puis H1 suivent)
     → le rapport de force CHANGE VRAIMENT → trader la nouvelle phase
  B. RÉPULSION : le croisement est suivi d'un écart violent des forces
     (GBP monte fort + USD baisse fort, ou l'inverse)
     → tension extrême = le croisement était un PIÈGE (faux signal)
     → le rapport de force REVIENT à l'ancien → trader le retour
```

---

## LE PATTERN COMPLET (reformulé)

### La séquence de lecture (ce que le système doit VOIR)

```
ÉTAPE 1 — CROISEMENT M5
   Le M5 croise (GBP passe au-dessus/en-dessous de USD)
   → alerte "croisement M5" (volonté de changer de rapport de force)

ÉTAPE 2 — ZONES DYNAMIQUES EXTRÊMES M15/M30
   Regarder si les valeurs M15/M30 sont dans les zones extrêmes
   (percentile > 90 ou < 10 de leur propre échelle)
   → si OUI : le croisement M5 est SIGNIFICATIF (retournement possible)
   → si NON : le croisement M5 est faible (bruit probable)

ÉTAPE 3 — DOUBLE TEST DE REJET DE PRIX (confirmation)
   Le prix touche un niveau et rebondit (1er test)
   Le prix retouche le niveau et rebondit (2e test)
   → double test réussi = retournement CONFIRMÉ
   → sinon = pas de confirmation, on attend

ÉTAPE 4 — PROPAGATION OU RÉPULSION (après le croisement)
   A. PROPAGATION : M15 → M30 → H1 suivent le croisement
      → le rapport de force change VRAIMENT → trader la nouvelle phase
   B. RÉPULSION : écart violent des forces après le croisement
      → le croisement était un piège → trader le retour à l'ancien rapport
```

### La stratégie (ce que le système doit FAIRE)

```
ENTRÉE (retournement confirmé) :
  - Croisement M5 + zones extrêmes M15/M30 + double test de rejet réussi
  → entrer dans la direction du croisement

ENTRÉE (répulsion) :
  - Croisement M5 suivi d'une répulsion (écart violent)
  → entrer dans le sens du RETOUR (l'ancien rapport de force)

SORTIE :
  - Propagation complète (M15+M30+H1 alignés) = tenir la position
  - Répulsion = sortir immédiatement (le croisement était un piège)
```

---

## CE QUE LE SYSTÈME DOIT IMPLÉMENTER (règles à injecter)

| Règle | Description | Où |
|---|---|---|
| **R1 — Calibration par TF** | Zones (basse/moyenne/haute/extrême) par percentile, calculées sur l'historique de CHAQUE TF | Nouveau module |
| **R2 — Lecture par TF** | Lire la valeur dans les zones de SON TF, jamais en absolu | Nouveau module |
| **R3 — Croisement M5 + zones extrêmes** | Croisement M5 significatif si M15/M30 dans zones extrêmes | Nouveau module |
| **R4 — Double test de rejet de prix** | Confirmation par 2 tests de niveau (touche + rebond ×2) | Nouveau module |
| **R5 — Propagation vs Répulsion** | Après croisement : détecter si les TF suivent (propagation) ou s'écartent violemment (répulsion) | Nouveau module |

---

## MÉTRIQUE DE RÉUSSITE

- Le système lit chaque TF dans SON échelle (zones par percentile)
- Le système détecte : croisement M5 + zones extrêmes M15/M30 = retournement
  possible
- Le système confirme par le double test de rejet de prix
- Le système distingue propagation (trader la nouvelle phase) vs répulsion
  (trader le retour)
- Taux de bonnes décisions > 55% sur 30 setups

---

## DOCUMENTS LIÉS

- `docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` — la matrice complète
  (personnalité de devise, fractalité, cycles)
- `docs/V10/LECTURE_STRATEGIE_CHANGEMENT_PHASE.md` — le changement de phase
  par croisement H4 (à relire avec la correction : chaque TF a son échelle)
- `core/v10/v10_cinematics.py` — le module cinématique (à étendre en
  calibration par TF)

---

> **Note Hermes** : ce document corrige l'hypothèse fausse d'agrégation.
> Les forces sont propres à chaque TF — la lecture temporelle est complexe
> parce qu'elle exige de lire chaque TF dans son échelle, puis de croiser
> les événements (croisement M5 + zones extrêmes M15/M30 + double test de
> rejet + propagation/répulsion). Chaque réponse de Søn affine ce modèle.