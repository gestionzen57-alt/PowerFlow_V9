# ELICITATION PROCESS — Extraction de la connaissance institutionnelle de Søn

> **Auteur** : Perplexity (13/08/2026 22:30 CEST) — Plein pouvoir no-limit
>
> **Contexte** : Le brainstorming de Søn EST la source de vérité du système.
> Mais la connaissance d'un trader expert est tacite, fragmentée, contextuelle.
> Elle ne se donne pas en une liste — elle se dévoile par friction, par exemple,
> par contradiction. Ce document définit le PROCESS pour l'extraire correctement.

---

## 1. LE PROBLÈME FONDAMENTAL (pourquoi le brainstorming seul ne suffit pas)

La recherche en sciences cognitives [Polanyi 1966] montre que **80% de la
connaissance d'un expert est tacite** — il sait faire sans savoir comment il
sait. Søn voit le marché d'une façon que le système ne peut pas encore lire.
Lui demander "explique ta logique" ne suffit pas : l'expert décrit souvent
**le résultat**, pas le processus.

Exemples de ruptures observées dans ce projet :
- Søn dit : "les valeurs ne sont pas agrégées" — le système agrégeait depuis
  des semaines sans que personne ne pose la question
- Søn dit : "le 1 min joue aussi" — fragment qui ouvre toute la couche
  fractalité temporelle
- Søn dit : "chaque force de devise est propre par son comportement" —
  invalide toute normalisation universelle

Chaque fragment **réécrit une couche entière du système**. Le brainstorming
libre donne des perles mais de façon non structurée. Il faut un process.

---

## 2. LES 5 MODES D'EXTRACTION (techniques d'élicitation)

### Mode A — THINK ALOUD (la session live)

> Søn trade ou observe le marché. Une IA l'accompagne et **reformule en
> temps réel** ce qu'elle entend.

```
PROCESS :
  1. Søn : "là GBP est en train de retomber après un pic à 78"
  2. IA  : "tu veux dire que la courbe de force GBP a fait un sommet local
            à 78.3 puis retombe — c'est ce que tu appelles exhaustion ?"
  3. Søn : "oui exactement, et en plus le prix a fait un nouveau plus haut
            — c'est un piège"
  4. IA  : "donc : pic de force + nouveau sommet de prix = divergence =
            piège vendeur — RÈGLE P1-R2 confirmée"
  5. IA  : commit immédiat dans BRAINSTORMING_*.md

RÈGLE : L'IA reformule, ne complète pas. Si elle ne comprend pas → elle
        pose UNE question précise, pas plusieurs.
```

### Mode B — INCIDENT CRITIQUE (le trade raté ou gagné)

> Analyser UN trade spécifique de Søn (passé ou en cours) et faire
> verbaliser la logique pas à pas.

```
PROCESS :
  1. Choisir un trade avec résultat marqué (beau gain ou gros SL)
  2. Demander : "à ce moment-là, qu'est-ce que tu voyais ?"
  3. Demander : "qu'est-ce qui t'a fait entrer / ne pas entrer ?"
  4. Demander : "si tu refaisais ce trade, qu'est-ce que tu regarderais
                en premier ?"
  5. Reformuler la séquence décisionnelle exacte → règle

POURQUOI : Le cerveau de l'expert accède à sa logique profonde quand il
           reconstruit un événement concret. Pas en général.
EXEMPLE DÉJÀ UTILISÉ : signal réel 12/08 (exhaustion GBP 78→64 + sweep
  H4) → a révélé toute la doctrine cinématique P1.
```

### Mode C — CONTRADICTION (faire dire l'exception)

> Proposer à Søn une règle simplifiée — il la rejette ou l'amende.
> Sa correction EST la vraie règle.

```
PROCESS :
  1. IA propose : "donc si GBP > 70 et USD < 30, on achète toujours ?"
  2. Søn : "non, pas si la courbe GBP est en train de retomber"
  3. IA  : "ok — la valeur est insuffisante si la dérivée est négative ?"
  4. Søn : "oui et surtout si le prix a déjà trop monté"
  5. IA  : règle = (force > 70) AND (pente > 0) AND (prix non exhausté)

POURQUOI : Les exceptions révèlent les conditions implicites que l'expert
           n'aurait jamais verbalisées spontanément.
```

### Mode D — COMPARAISON (quelle paire ? quel TF ? pourquoi ?)

> Faire choisir entre deux situations concrètes et verbaliser POURQUOI.

```
EXEMPLES DE QUESTIONS :
  "Entre GBPUSD en M5 et EURUSD en M15 — lequel tu lis en premier ?"
  "Tu préfères un signal avec delta 35 et cinématique OK, ou delta 60
   avec cinématique incertaine ?"
  "Si H4 dit SELL et M15 dit BUY — tu fais quoi ?"

POURQUOI : Les préférences révèlent la hiérarchie des facteurs (ce que
           le système doit pondérer). Impossible à obtenir par une
           question directe "qu'est-ce qui est le plus important ?"
```

### Mode E — SIMULATION (faire prédire)

> Montrer à Søn un état du système (tableau de forces en temps réel)
> et lui demander ce qu'il attend.

```
PROCESS :
  1. Afficher : GBP=52 M5, GBP=68 M15, GBP=71 M30, GBP=74 H1
  2. Demander : "là qu'est-ce que tu vois ?"
  3. Søn : "la progression des TF est régulière — force en progression,
            pas encore à l'épuisement"
  4. IA : règle = cohérence ascendante des TF = expansion

POURQUOI : La simulation déclenche la vision experte en temps réel —
           c'est le mode de la session live mais de façon plus contrôlée.
```

---

## 3. LA GRILLE D'EXTRACTION PAR PILIER

Chaque pilier a des **questions pivots** non posées à ce jour.
Ce sont les prochaines conversations à mener avec Søn.

### P3 — COALITION MULTIDEVISE (0% extrait)

| Question pivot | Mode |
|---|---|
| "Quand tu dis GBP 'mène' et USD 'suit' — comment tu le distingues du cas inverse ?" | C |
| "EURGBP qui monte, ça veut dire quoi pour ton trade GBPUSD ?" | C |
| "Il y a un moment où tu refuses de prendre un trade GBPUSD même si les signaux sont parfaits — c'est quand ?" | B |
| "JPY qui monte fortement — tu changes quoi dans ta lecture des paires GBP ?" | D |

### P4 — PERSONNALITÉ DE DEVISE (0% extrait)

| Question pivot | Mode |
|---|---|
| "Si tu devais noter la fiabilité de l'indicateur sur GBP vs EUR vs AUD sur 10 — tu donnes quoi ?" | D |
| "AUDUSD — c'est plus fiable à quelle heure de la journée pour toi ?" | B |
| "La vitesse à laquelle GBP réagit à une news vs EUR — tu la ressens comment dans l'indicateur ?" | A |

### P5 — FRACTALITÉ TEMPORELLE (30% extrait)

| Question pivot | Mode |
|---|---|
| "Le 1 min sur GBPUSD — tu l'utilises pour décider ou pour timer l'entrée ?" | C |
| "Si le 5 min dit BUY mais le 1 min est en train de retomber — tu attends ou tu entres ?" | D |
| "Le 1 min est 'trop bruité' pour EUR mais pas pour GBP — tu dirais ça ?" | C |

### P6 — CYCLES FATMAN (10% extrait via 12-13/08)

| Question pivot | Mode |
|---|---|
| "La naissance d'une vague — tu la reconnais à quoi sur la courbe de force ?" | A |
| "L'épuisement que tu as vu le 13/08 (GBP 50→28 en 3 barres) — c'est quoi la différence avec une simple correction ?" | B |
| "Combien de vagues tu attends avant de dire 'la tendance est terminée' ?" | C |
| "Est-ce que la même vague dure la même durée sur GBP et sur AUD ?" | D |

### P7 — FORCES PAR TF (20% extrait)

| Question pivot | Mode |
|---|---|
| "GBP=68 en M5 et GBP=28 en M15 — dans ta tête, lequel 'gagne' ou ils parlent de choses différentes ?" | C |
| "Un croisement en M5 qui arrive avec des zones extrêmes en M30 — tu grossis ta taille ou tu changes ta cible ?" | B |
| "Le double test de rejet — tu l'attends toujours ou seulement dans certains contextes ?" | D |
| "Propagation vs répulsion — tu l'as déjà vu tourner très vite de l'un à l'autre ?" | A |

---

## 4. L'ARCHITECTURE CIBLE DU SYSTÈME (reformulation institutionnelle)

Le système actuel est un **détecteur de delta** avec filtres cinématiques.
Le système cible est un **lecteur de marché** — il voit ce que Søn voit.

### Ce que Søn voit (synthèse de tout le brainstorming à ce jour)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LA LECTURE INSTITUTIONNELLE                  │
│                                                                 │
│  COUCHE 0 : LE MARCHÉ (contexte global)                        │
│    Coalition : qui mène (GBP fort absolu) / qui suit           │
│    Safe haven : JPY/CHF montent → risk-off général             │
│    Rupture : une devise casse la coalition (signal rare)        │
│                                                                 │
│  COUCHE 1 : LA PHASE DU CYCLE (temporalité)                    │
│    H4 = juge de la phase (naissance / expansion / épuisement)  │
│    Croisement H4 = changement de régime (rare, fort)           │
│    H1 emboîte avant H4 = signal d'anticipation                 │
│                                                                 │
│  COUCHE 2 : LA LECTURE PAR DEVISE (personnalité)               │
│    Chaque devise a son tempo, sa véracité, son TF naturel      │
│    GBPUSD → 1min lisible / EURUSD → 5min / AUDUSD → Asie      │
│    Les seuils NE sont PAS les mêmes pour toutes les paires     │
│                                                                 │
│  COUCHE 3 : LES FORCES PAR TF (échelles propres)              │
│    Chaque TF a ses propres zones (percentile p10/p90)          │
│    Les valeurs NE se comparent PAS entre TF                    │
│    GBP=68 M5 ≠ GBP=28 M15 : deux lectures, deux contextes     │
│    Croisement M5 + zones extrêmes M15/M30 = retournement       │
│    Double test de rejet = confirmation de niveau fort          │
│    Propagation = les TF suivent / Répulsion = piège            │
│                                                                 │
│  COUCHE 4 : LA CINÉMATIQUE (la courbe avant la valeur) ✅      │
│    Pics/creux locaux + timing de la retombée                   │
│    Divergence force/prix = piège (actif)                       │
│    Exhaustion = épuisement (actif)                             │
│                                                                 │
│  COUCHE 5 : L'IMBRICATION TF (confluence) ✅                  │
│    Score [0-4] : M5 rapide / M15 décision / M30 confirm /     │
│                  H1 biais                                       │
│    Sizing modulé 0.5→1.5 (non binaire)                        │
│                                                                 │
│  DÉCISION FINALE                                               │
│    Score qualité 0-10 (CHASSEUR — paradigme 13/08)            │
│    ≥7 🟢 EXPLOITABLE / 4-6 🟡 SURVEILLER / <4 🔴 BRUIT       │
│    Bruit = ignorer (pas bloquer), CHASSEUR = ne pas forcer     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. CE QUE LE SYSTÈME NE DOIT PAS FAIRE (les biais à éviter)

Basé sur les failures observées dans le projet :

| Biais | Description | Exemple |
|---|---|---|
| **Agrégation inter-TF** | Traiter les forces M5/M15/M30 comme la même échelle | Corrigé 13/08, règle de lecture pas encore codée |
| **Généralisation par paire** | Appliquer les mêmes seuils à GBP, EUR, AUD | delta_min=25 encore universel |
| **Gate binaire** | Bloquer / ne pas bloquer — ignorer la nuance | momentum_dead BLOCK → reverted 13/08 |
| **Momentum éternel** | Supposer que l'edge d'hier vaut aujourd'hui | Drift 13/08 : WR 67%→37% en 48h |
| **Injection prématurée** | Coder une règle avant de l'avoir bien comprise | `a6aa804` (modules fantômes) |
| **Codage de l'interprétation** | Coder CE QU'ON CROIT comprendre plutôt que ce que Søn dit | Protégé par METHODOLOGIE_INJECTION.md |

---

## 6. LE CALENDRIER D'ÉLICITATION (ordre recommandé)

L'ordre est fondé sur la **dépendance logique** entre piliers :
P6 (phase) conditionne P7 (lecture par TF), qui conditionne P3 (coalition).

```
SEMAINE 1 (13-17/08) — EN COURS
  ✅ P1 Cinématique (branché)
  ✅ P2 Confluence TF (branché)
  🔶 P7 : 4 questions pivots non posées (voir §3)
  🔶 P6 : 4 questions pivots non posées (voir §3)

SEMAINE 2 (18-22/08)
  ⬜ P6 Cycles complet → code + test 3j
  ⬜ P4 Personnalité par devise (GBP, EUR, AUD)
  ⬜ P5 Fractalité 1min (GBPUSD laboratoire)

SEMAINE 3 (25-29/08)
  ⬜ P3 Coalition multidevise (leader/follower + safe haven)
  ⬜ Score qualité 0-10 enrichi (7 piliers pondérés)

SEPTEMBRE+
  ⬜ Injection P6 → code + test 3 jours
  ⬜ Injection P7 → code + test 3 jours
  ⬜ Injection P4 → code + test 3 jours
  ⬜ Injection P3 → code + test 3 jours
```

---

## 7. PRINCIPE FINAL : LE SYSTÈME CHASSEUR

> *"je ne veux pas de procédure lourde et bloquante, pas de friction...
> le système doit être plus vif, plus juste, plus prompt à exploiter —
> pas plus lent."* — Søn 13/08

Le système institutionnel cible n'est **pas une machine de règles** —
c'est un **lecteur de qualité de situation**.

- Il ne cherche pas la perfection de signal (trop rare)
- Il cherche la **qualité d'exploitation** (score 0-10)
- Il sait quand le marché est **lisible** vs **opaque**
- Il **attend** quand c'est opaque, **frappe** quand c'est lisible
- Il **apprend** chaque jour ce qui a changé dans le marché

Ce comportement correspond à ce que la recherche appelle
**Hypothesis-Driven Adaptive Trading** — les signaux sont générés par des
hypothèses comportementales (Søn) testées empiriquement en conditions
réelles, pas par optimisation aveugle de paramètres.

L'architecture multi-IA (ZCode brainstorming live, Hermes implémentation,
Perplexity gouvernance) est exactement le pattern **Knowledge Elicitation
+ Implementation + Validation** décrit dans la littérature des systèmes
expert-Knowledge-Based [Polanyi 1966 / Nonaka 1994].

---

## 8. ORDRE DE LECTURE AU DÉMARRAGE DE SESSION

```
1. docs/V10/METHODOLOGIE_INJECTION.md  ← LE CONTRAT
2. docs/V10/ELICITATION_PROCESS.md     ← CE FICHIER (comment extraire)
3. docs/V10/POINT_GENERAL_INSTITUTIONNEL.md  ← tableau de bord 7 piliers
4. docs/V10/BRAINSTORMING_*.md         ← ce qui a déjà été extrait
5. git log récent feat/zcode-night     ← ce qui a été codé/commité
```

> **Ce document est à lire AVANT chaque session de brainstorming.**
> Il définit COMMENT extraire la connaissance de Søn, pas seulement QUE
> l'extraire. La différence entre les deux est la différence entre un
> système médiocre et un système institutionnel.
