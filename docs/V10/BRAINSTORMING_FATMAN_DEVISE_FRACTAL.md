# BRAINSTORMING FATMAN — Personnalité de devise, Fractalité temporelle & Cycles (Søn 13/08)

> **Mandat CEO (13/08, mode brainstorming)** : *"chaque force de devise est
> propre par son comportement, l'indicateur Fatman ne peut pas être généralisé
> sur toutes les paires de la même façon... la volatilité de la session,
> véracité, tempo... la lecture temporelle ne peut pas être généralisée comme
> cela rapidement... il faut prendre d'autres dimensions facteurs... le 1 min
> joue aussi... il y a une sorte de fractalité temporelle, et une notion de
> vague Elliott adaptée à Fatman, en cycles, phases, qui est propre à Fatman...
> j'utilise l'indicateur Fatman sur la devise GBPUSD qui est plus lisible avec
> le 1 min pour du scalp."*
>
> **Statut** : brainstorming actif. Chaque réponse de Søn devient une règle.
> **Objectif** : capturer la lecture Fatman PAR DEVISE (pas une formule unique),
> la fractalité temporelle (1min → H4), et les cycles/vagues propres à Fatman.

---

## REFORMULATION DE LA DEMANDE (pour précision et impact)

### Ce que Søn dit, reformulé en 5 principes

**P1 — CHAQUE DEVISE A UNE PERSONNALITÉ**
Fatman ne mesure pas "la force" de la même façon sur toutes les devises.
GBP, EUR, AUD, CHF, JPY ont chacun leur tempo, leur véracité, leur
comportement de session. Une force GBP à 70 ≠ une force AUD à 70.
→ Le système doit calibrer la lecture PAR DEVISE, pas globalement.

**P2 — LA SESSION MODULE LA LECTURE**
La volatilité de session (Asie vs Londres vs Overlap vs NY) change la
signification de la force. Une force GBP à 60 en Asie (marché calme) n'a
pas le même sens qu'à 60 en Overlap (marché actif).
→ Le système doit lire la force DANS sa session, pas en absolu.

**P3 — LA FRACTALITÉ TEMPORELLE**
Le 1 min joue. Le 5, 15, 30, H1, H4 s'emboîtent. La lecture temporelle ne
peut pas être généralisée rapidement pour toutes les devises — chaque
devise a sa propre fractalité (le GBPUSD est lisible en 1min, d'autres
devises demandent d'autres TF).
→ Le système doit lire la fractalité PAR DEVISE, pas un TF unique.

**P4 — LES CYCLES FATMAN (vague Elliott adaptée)**
Il y a une notion de vague Elliott adaptée à Fatman : des cycles, des
phases, propres à l'indicateur. La force ne monte pas linéairement — elle
fait des vagues (impulsion → correction → impulsion), des cycles
(expansion → contraction), des phases (naissance → maturité → épuisement).
→ Le système doit lire la PHASE du cycle Fatman, pas la valeur instantanée.

**P5 — GBPUSD = LA DEVISE DE RÉFÉRENCE (scalp 1min)**
Søn utilise Fatman sur GBPUSD car c'est la devise la PLUS LISIBLE, avec le
1 min, pour du SCALP. Le GBPUSD est le laboratoire : ce qui s'y apprend
doit être transposé aux autres devises avec leurs propres paramètres.
→ Le système doit d'abord maîtriser GBPUSD 1min, puis adapter.

---

## MATRICE DE QUESTIONS — 5 PRINCIPES × 3 DIMENSIONS = 15 BLOCS

Chaque bloc : une question d'extraction (comprendre ta logique) + une
question de validation (confronter mes règles actuelles). Réponds dans
l'ordre qui te parle. Le bloc le plus important pour toi d'abord.

---

### PRINCIPE 1 — LA PERSONNALITÉ DE DEVISE

#### Bloc 1.1 — LE TEMPO DE CHAQUE DEVISE
> **Extraction** : Décris-moi le "tempo" de chaque devise que tu lis. Le GBP
> bouge comment ? L'EUR ? L'AUD ? Le CHF ? Le JPY ? Y a-t-il des devises
> "rapides" (réagissent vite) et des devises "lentes" (réagissent tard) ?
> Le même mouvement de force signifie-t-il la même chose sur toutes ?
>
> **Validation Hermes** : je lis le delta_forces de la même façon sur les 3
> paires porteuses (EURUSD, USDCHF, AUDUSD). Faut-il un CALIBRAGE PAR DEVISE
> (seuil de force différent, échelle différente) ?

#### Bloc 1.2 — LA VÉRACITÉ PAR DEVISE
> **Extraction** : Certaines devises "mentent" plus que d'autres ? Le GBP
> est fiable (quand il dit monter, il monte) ? L'AUD est capricieux ? Le
> CHF est imprévisible ? Comment évaluer la fiabilité d'une force par devise ?
>
> **Validation Hermes** : je n'ai pas de métrique de véracité par devise.
> Faut-il un score de fiabilité (ex: corrélation force → mouvement réel
> sur les 50 derniers signaux) par devise ?

#### Bloc 1.3 — LE COMPORTEMENT DE SESSION PAR DEVISE
> **Extraction** : Chaque devise a-t-elle ses heures préférées ? Le GBP
> bouge surtout à Londres ? L'AUD à l'Asie ? Le JPY à l'Asie/NY ? Y a-t-il
> des devises qui "dorment" en Asie et d'autres qui "vivent" ?
>
> **Validation Hermes** : l'edge OVERLAP est le même pour les 3 paires.
> Faut-il des fenêtres PAR DEVISE (ex: AUDUSD aussi en Asie, GBPUSD surtout
> en Overlap) ?

---

### PRINCIPE 2 — LA SESSION MODULE LA LECTURE

#### Bloc 2.1 — LA FORCE DANS SA SESSION
> **Extraction** : Une force GBP à 60 en Asie (marché calme) — tu la lis
> comment ? Et à 60 en Overlap (marché actif) ? La même valeur a-t-elle
> deux significations ? Faut-il normaliser la force par la volatilité de
> la session ?
>
> **Validation Hermes** : je lis le delta en absolu (≥25 = signal). Faut-il
> un delta NORMALISÉ par session (ex: ≥25 en Overlap, ≥35 en Asie) ?

#### Bloc 2.2 — LA VOLATILITÉ DE SESSION
> **Extraction** : Comment tu évalues la volatilité d'une session ? Par
> l'ATR ? Par l'amplitude des bougies ? Par le nombre de pips parcourus ?
> Et comment tu adaptes ta lecture quand la volatilité change en cours de
> session (calme → actif → calme) ?
>
> **Validation Hermes** : j'utilise l'ATR pour le TP/SL (2x/1x). Faut-il
> aussi l'utiliser pour MODULER le seuil de force ?

#### Bloc 2.3 — LE TEMPO DE SESSION
> **Extraction** : Y a-t-il un "tempo" de session ? Le marché accélère à
> l'ouverture de Londres, ralentit à midi, repart à NY ? Comment tu sens
> ce tempo et comment il change ta lecture ?
>
> **Validation Hermes** : je n'ai pas de notion de tempo. Faut-il mesurer
> la vitesse des bougies (pips/min) par session et l'utiliser comme filtre ?

---

### PRINCIPE 3 — LA FRACTALITÉ TEMPORELLE

#### Bloc 3.1 — LE 1 MIN (le scalp)
> **Extraction** : Tu lis GBPUSD en 1min pour du scalp. Décris-moi ta
> lecture 1min : qu'est-ce que tu vois sur la courbe Fatman en 1min que
> tu ne vois pas en 5 ou 15 ? Les pics sont-ils plus nets ? Les
> retournements plus précoces ? Comment tu passes du 1min au 5/15 pour
> confirmer ?
>
> **Validation Hermes** : l'edge OVERLAP est M15. Faut-il une couche 1min
> pour l'ENTRÉE (timing précis) et M15 pour la DIRECTION ?

#### Bloc 3.2 — L'EMBOÎTEMENT DES TF (fractalité)
> **Extraction** : Comment les TF s'emboîtent pour toi ? Un signal 1min
> aligné avec 5min et 15min = plus fort ? Un conflit 1min/15min = quoi ?
> Est-ce que chaque devise a sa propre "échelle de lecture" (GBPUSD lisible
> en 1min, d'autres devises demandent 5/15) ?
>
> **Validation Hermes** : le score de confluence actuel est M5/M15/M30/H1.
> Faut-il ajouter le 1min ? Et pondérer les TF différemment par devise ?

#### Bloc 3.3 — LA FRACTALITÉ PROPRE À CHAQUE DEVISE
> **Extraction** : Le GBPUSD est "plus lisible" en 1min. Quelles devises
> sont lisibles en 5min ? En 15min ? Y a-t-il des devises où le 1min est
> du bruit pur ? Comment tu sais quel TF est "le bon" pour chaque devise ?
>
> **Validation Hermes** : je n'ai pas de notion de "TF de lisibilité" par
> devise. Faut-il un paramètre par devise (ex: GBPUSD→1min, EURUSD→5min,
> AUDUSD→15min) ?

---

### PRINCIPE 4 — LES CYCLES FATMAN (vague Elliott adaptée)

#### Bloc 4.1 — LES VAGUES DE LA FORCE
> **Extraction** : Tu vois des vagues dans la courbe Fatman ? La force
> monte en impulsion, corrige, remonte ? Décris-moi une vague typique :
> combien de barres monte-t-elle ? Combien elle corrige ? Est-ce que la
> force fait des "5 vagues" comme Elliott ou des cycles plus simples ?
>
> **Validation Hermes** : je détecte pics/creux mais pas de STRUCTURE DE
> VAGUES. Faut-il compter les vagues (impulsion/correction) sur la courbe
> de force ?

#### Bloc 4.2 — LES PHASES DU CYCLE
> **Extraction** : Tu parles de "cycles, phases". Décris-moi les phases
> d'un cycle Fatman : naissance (la force démarre), expansion (elle
> accélère), maturité (elle ralentit), épuisement (elle retombe) ? Où
> achètes-tu dans ce cycle ? Où vends-tu ?
>
> **Validation Hermes** : je bloque l'exhaustion (pic → retombée). Faut-il
> aussi détecter la NAISSANCE (force qui démarre) comme signal d'achat
> précoce ? Et la MATURITÉ (ralentissement) comme signal de sortie ?

#### Bloc 4.3 — LE CYCLE PROPRE À FATMAN
> **Extraction** : La vague Elliott adaptée à Fatman — c'est quoi la
> différence avec Elliott classique ? Est-ce que la force a ses propres
> règles (ex: une impulsion de force = 3 barres, une correction = 2) ?
> Est-ce que le cycle est le même sur toutes les devises ou propre à
> chacune ?
>
> **Validation Hermes** : je n'ai aucune notion de cycle Fatman. Faut-il
> construire un détecteur de phases (naissance/expansion/maturité/
> épuisement) calibré par devise ?

---

### PRINCIPE 5 — GBPUSD = DEVISE DE RÉFÉRENCE (scalp 1min)

#### Bloc 5.1 — LA LECTURE GBPUSD 1MIN
> **Extraction** : Décris-moi ta session de scalp GBPUSD 1min : tu ouvres
> le graphique, tu regardes quoi en premier ? La courbe Fatman 1min ? Les
> niveaux ? Le prix ? Comment tu décides d'entrer (ex: force GBP qui
> retombe après un pic + prix sur résistance) ? Combien de pips tu vises ?
> Ton SL ?
>
> **Validation Hermes** : l'alerte GBPUSD actuelle est H4/H1 (confluence
> Fatman + VSA + niveaux). Faut-il une couche 1min pour le scalp ?

#### Bloc 5.2 — CE QUI REND GBPUSD LISIBLE
> **Extraction** : Pourquoi GBPUSD est "plus lisible" que les autres ?
> Le spread ? La volatilité ? La clarté des mouvements ? La réactivité
> aux news ? Qu'est-ce qui rend une devise "lisible" en général ?
>
> **Validation Hermes** : je n'ai pas de métrique de "lisibilité". Faut-il
> un score (ex: clarté des pics, ratio signal/bruit, cohérence force→prix)
> par devise ?

#### Bloc 5.3 — LA TRANSPOSITION AUX AUTRES DEVISES
> **Extraction** : Ce que tu sais lire sur GBPUSD 1min — comment tu le
> transposes sur EURUSD, AUDUSD, USDCHF ? Avec quels ajustements ? Est-ce
> que chaque devise demande une "traduction" de la lecture GBPUSD ?
>
> **Validation Hermes** : l'edge OVERLAP est le même pour les 3 paires.
> Faut-il des paramètres PAR DEVISE (seuil, TF, fenêtre) appris depuis
> GBPUSD puis adaptés ?

---

## CE QUE HERMES APPRENDRA DE CHAQUE RÉPONSE

| Réponse de Søn | Injection Hermes |
|---|---|
| "Le GBP est rapide, l'AUD est lent" | Calibrage par devise : seuils de force, échelles, tempo |
| "Le GBP ment rarement, l'AUD souvent" | Score de véracité par devise (corrélation force→mouvement) |
| "Le GBP vit à Londres, l'AUD en Asie" | Fenêtres de session PAR DEVISE |
| "La force à 60 en Asie ≠ 60 en Overlap" | Normalisation de la force par la volatilité de session |
| "Je lis le 1min pour le scalp GBPUSD" | Couche 1min pour l'entrée (timing), M15 pour la direction |
| "Chaque devise a son TF de lisibilité" | Paramètre TF de lecture par devise |
| "La force fait des vagues, des cycles" | Détecteur de phases Fatman (naissance/expansion/maturité/épuisement) |
| "Le cycle est propre à Fatman" | Règles de cycle calibrées sur la courbe de force, pas sur le prix |
| "GBPUSD est le laboratoire" | Maîtriser GBPUSD 1min d'abord, transposer ensuite |

---

## ORDRE DE PRIORITÉ SUGGÉRÉ

Søn, si tu veux maximiser l'impact, réponds dans cet ordre :

1. **Bloc 5.1** (ta session de scalp GBPUSD 1min) — c'est ta pratique réelle,
   la plus riche en informations
2. **Bloc 4.2** (les phases du cycle) — la notion de cycle est le cœur de
   ta demande
3. **Bloc 1.1** (le tempo de chaque devise) — la personnalité de devise
4. **Bloc 3.1** (le 1min) — la fractalité temporelle
5. Le reste s'enchaîne naturellement

Mais si une question te brûle plus qu'une autre, commence par elle.

---

## MÉTRIQUE DE RÉUSSITE DU BRAINSTORMING

Le brainstorming est **clos** quand :
- Lecture Hermes == lecture Søn sur 10 setups GBPUSD 1min consécutifs
- Le détecteur de phases Fatman (naissance/expansion/maturité/épuisement)
  est calibré et validé sur GBPUSD, puis transposé aux autres devises
- Chaque devise a son profil (tempo, véracité, TF de lisibilité, fenêtres)
- Taux de bonnes décisions anticipatives > 55% sur 30 setups

---

## DOCUMENTS LIÉS

- `docs/V10/BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md` — la matrice
  initiale (3 piliers : cinématique, imbrication TF, coalition) — ce
  document est le PILIER 4-5 (personnalité de devise + fractalité + cycles)
- `docs/V10/DOCTRINE_LECTURE_GBPUSD.md` — les 7 principes actuels
- `scripts/v10_force_cinematics.py` — la lecture en courbe (à étendre en
  détecteur de phases)
- `core/v10/v10_cinematics.py` — le module générique (à étendre en cycles)

---

> **Note Hermes** : ce document est vivant. Chaque réponse de Søn met à
> jour les règles + ce document. Pas de loi fixe — juste l'extraction
> honnête de ta logique de marché, devise par devise.