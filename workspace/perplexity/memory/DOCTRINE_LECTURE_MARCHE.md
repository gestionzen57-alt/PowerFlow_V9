---
statut: ACTIF
source_de_verite: NON
derniere_mise_a_jour: 2026-06-29
proprietaire: PowerFlow V8
remplace: —
remplace_par: —
portee: doctrine
domaine: doctrine
priorite: P0
cree_le: 2026-06-08
mis_a_jour: 2026-06-29
auteur: claude-code — MAJ: MiniMax-M3 (doctrine duale Søn live 29/06)
---

# Doctrine de Lecture du Marché — PowerFlow V8

> Document fondateur. Chaque décision de trading découle de ces principes.
> Toute modification nécessite une décision numérotée dans STATE.md.

---

## 1. Le SDI — le coeur de PowerFlow

Le **SDI** (Strength Deviation Index) mesure la force relative de chaque devise
sur une échelle normalisée **0 → 100**. C'est LA source de vérité.

- 8 devises suivies : GBP, USD, EUR, JPY, CHF, CAD, AUD, NZD
- **Le prix et le bridge en sont des conséquences, pas des causes.**
- Le SDI est **borné** : une devise ne peut pas monter indéfiniment.
  Plus elle est haute, plus elle a consommé son énergie directionnelle.

> Tout part des 8 forces. Pas du prix, pas du bridge, pas des patterns.
> Le prix n'est que la conséquence de l'interaction des 8 forces.

### Hiérarchie de lecture (ordre inviolable)

```
1. SDI (8 forces)       → coeur — qui est fort / faible / en coalition ?
2. Comportements        → courbure, nœud, synchro, bosses (fractaux, tout TF)
3. Coalition            → leader/bloc pondère les zones SDI
4. Structure du flux    → perception : où va l'argent entre les devises ?
5. Ticks                → lecture complémentaire, n'initient pas
```

---

## 2. Principe mean-reversion : l'extrême précède le retournement

**Règle fondamentale** : le SDI à l'extrême ne signifie pas « continuer » — il signifie « la pression s'est accumulée ».

> "Un marché ne reste pas à l'extrême. Il y va pour en revenir."

Conséquences :
- La **confluence multi-TF** sur PowerFlow est **inversée** vs la doctrine classique :
  - 3/3 TF alignés → WR **17.4%** (épuisement, C2 calibration 600+ patterns)
  - 0/3 TF alignés → WR **34.4%** (retournement imminent)
- Un scorer qui booste sur la confluence multi-TF se pénalise lui-même

---

## 2bis. Le SDI est le coeur — prix et bridge sont conséquences

> Le SDI est le coeur du système. Le prix, le bridge, les patterns découlent
> des 8 forces, pas l'inverse. Lire le SDI d'abord, tout le temps.

- **Le prix ne parle pas en premier.** Ce sont les forces individuelles des devises qui se combinent.
- **Le bridge peut retarder.** Le 17/06, le bridge montrait ΔF=+59 (GBP fort) alors que le M1 montrait USD=94.
- **Les patterns sont des ombres portées des forces.** Lire les forces 8d directement.

Avant toute lecture de GBPUSD, vérifier les 8 forces sur M1 ou M5 :
- Qui est fort (>75 ou seuil dynamique) ?
- Qui est faible (<25 ou seuil dynamique) ?
- Qui est en coalition (USD+JPY, EUR+GBP, etc.) ?

---

## 3. Zones d'intérêt — comportement et construction du timeframe supérieur

> ⚠️ **Principe fondamental** : les zones d'intérêt (extrêmes de forces) ne sont pas des points d'entrée.
> Ce sont les **chantiers de construction du timeframe supérieur**. Le comportement qui s'y produit
> (rejet, absorption, équilibre) est ce qui bâtit la prochaine bougie H1/H4/D1.

Les seuils numériques ci-dessous sont des **repères de calibrage, pas des règles figées**.
Ils évolueront avec l'apprentissage automatique (C5). Ce qui est invariant, c'est le
**comportement attendu dans chaque zone**.

### 3.1 Les 3 comportements fondamentaux dans une zone d'intérêt

Quand une devise atteint une zone extrême (<25 ou >75 en seuil fixe, seuil dynamique en C5),
le marché peut adopter 3 comportements :

| Comportement | Signal | Construction HTF | Action |
|-------------|--------|------------------|--------|
| **REJET** (rejection) | La devise repart brusquement depuis l'extrême. Wick visible, ΔF s'inverse avec volume tick. | **Clôture HTF en opposition** — construit un rejet HTF (mèche, doji, pin bar). | Fenêtre de retournement ouverte. Surveillance active LTF pour croisement. |
| **ABSORPTION** (accumulation) | La devise stationne à l'extrême. ΔF plat ou qui oscille. Ticks présents mais pas de mouvement prix. | **Construction d'une base HTF** — accumulation de capital pour le prochain move. | Surveiller la rupture de la zone. Pas de trade tant que l'absorption n'a pas résolu. |
| **ÉQUILIBRE** (equilibrium) | La devise revient au centre (40-60) sans combat. L'extrême n'a pas tenu. | **Rejet faible** — la zone n'était pas significative. Pas de construction HTF. | Retour à l'attente. L'extrême non confirmé est un faux signal. |

> **Règle** : seul le **REJET** construit un vrai setup. L'ABSORPTION est un signal d'alerte,
> l'ÉQUILIBRE est un bruit.

Appliquer cette grille de lecture aux extrêmes, quelle que soit la valeur exacte du seuil.

### 3.2 Calibrage des seuils (provisoire, évolutif C5)

Les seuils ci-dessous sont des **repères de départ**. Ils seront recalibrés automatiquement
par apprentissage continu (C5) selon TF×session×inertie devise. Ne pas les traiter comme absolus.

#### Facteur Timeframe

La dispersion naturelle des forces varie selon le TF :

| Timeframe | Dispersion typique | Repère extrême bas | Repère extrême haut |
|-----------|-------------------|--------------------|-------------------|
| **M1** | ±15-20 | < 20 | > 80 |
| **M5** | ±20-25 | < 22 | > 78 |
| **M15** | ±20-25 | < 22 | > 78 |
| **H1** | ±25-30 | < 25 | > 75 |
| **H4** | ±25-30 | < 25 | > 75 |
| **D1** | ±30-35 | < 30 | > 70 |

Un score de 70 sur M1 est banal (dispersion faible). Un score de 70 sur D1 est extrême (dispersion large).

#### Facteur Session

L'amplitude des forces varie selon la session :

| Session | Amplitude | Ajustement repère | Comportement typique |
|---------|-----------|-------------------|----------------------|
| **ASIAN** | Faible (±15-20) | Seuils resserrés : >72 / <28 | Range serré, peu de vrais extrêmes |
| **LONDON** | Forte (±25-35) | Seuils standards : >75 / <25 | Forte amplitude, vrais extrêmes |
| **NY** | Forte (±25-35) | Seuils standards : >75 / <25 | Volatilité élevée, moves rapides |
| **OVERLAP** | Très forte (±30-40) | Seuils élargis : >78 / <22 | Pics de volatilité, faux extrêmes fréquents |
| **AFTER** | Faible (±15-20) | Seuils resserrés : >72 / <28 | Épuisement, retour vers moyenne |

**Règle** : un USD à 68 en ASIAN peut être un signal plus fort qu'un USD à 75 en LONDON.

#### Facteur Inertie de la Devise

Chaque devise a une amplitude naturelle diffrente :

| Devise | Inertie | Amplitude typique | Repère extrême haut | Particularité comportementale |
|--------|---------|-------------------|--------------------|-------------------------------|
| **GBP** | Forte | ±25-35 | > 78 | REJET rapide, peu d'ABSORPTION |
| **USD** | Forte | ±25-35 | > 78 | Réactif news, REJET ou ABSORPTION selon contexte macro |
| **EUR** | Modérée | ±20-25 | > 75 | ÉQUILIBRE fréquent, moins de vrais REJET |
| **JPY** | Modérée | ±20-25 | > 75 | ABSORPTION longue — tendance lente |
| **CHF** | Faible | ±15-20 | > 72 | REJET précoce, plafonne vite |
| **CAD** | Modérée | ±20-25 | > 75 | ABSORPTION liée aux commodities |
| **AUD** | Modérée | ±20-25 | > 75 | REJET risk-on/off |
| **NZD** | Faible | ±15-20 | > 72 | ÉQUILIBRE fréquent (volume faible) |

**Règle** : CHF à 72 = signal d'épuisement plus fort que GBP à 78. L'inertie détermine la signification du score et le **type de comportement attendu** (REJET vs ABSORPTION vs ÉQUILIBRE).

#### Matrice de décision

| Contexte | Zone | Lecture | Action |
|----------|------|---------|--------|
| **Extrême haut** | Score au-dessus du repère | Atteint la zone de construction HTF | Surveiller le comportement (REJET/ABSORPTION/ÉQUILIBRE) |
| **Extrême bas** | Score en-dessous du repère | Atteint la zone de construction HTF | Surveiller le comportement (REJET/ABSORPTION/ÉQUILIBRE) |
| **Zone intermédiaire** | Entre les deux repères | Pas de chantier HTF en cours | Attendre — le marché ne construit rien |
| **Extrême + coalition opposée** | Extrême + leader adverse | Chantier HTF sous tension maximale | Fenêtre ouverte pour un REJET |
| **ABSORPTION prolongée** | Extrême stationnaire >30 min | Accumulation terminée, rupture imminente | Préparer l'entrée dans la direction du bloc opposé |
| **REJET confirmé** | force_cycle_phase = CROISEMENT/INVERSION | HTF en construction effective | Signal fort — la zone a tenu son rôle |

> ⚠️ **Piège** : trader l'extrême dans sa direction initiale = entrer quand le marché va construire le TF supérieur en sens inverse.
> **Piège C5** : confondre le calibrage (chiffres provisoires) avec la doctrine (comportements). Les seuils changent, les comportements restent.

---

## 3bis. Lecture d'une arrivée en zone extrême — la scène complète

> **Principe** : un SDI à 75 n'est pas un événement en soi. C'est l'histoire de son arrivée qui donne son sens.
> Chaque arrivée en zone extrême est une **scène unique** avec sa propre signature.
> Le WR est une conséquence de la lecture correcte de la scène, pas une cause des seuils.

Une zone extrême ne se lit pas comme un seuil franchi. Elle se lit comme une **scène complète** à 6 dimensions :

### Dimension 1 — TRAJECTOIRE : d'où vient-on ?

| Champ | Question | Pourquoi c'est important |
|-------|----------|--------------------------|
| **Origine** | D'où venait le SDI avant ? (zone opposée extrême / neutre / transition) | Une arrivée depuis l'extrême opposé = retournement en cours. Depuis le neutre = mouvement frais. |
| **Vitesse** | Combien de minutes pour passer de l'ancienne zone à l'actuelle ? | Rapide (< 15 min) = momentum violent, risque d'épuisement précoce. Lent (> 2h) = construction solide. |
| **Profil** | Montée directe ? Consolidation puis cassure ? Oscillation ? | Le profil raconte la détermination du mouvement. |
| **Temps dans l'ancienne zone** | Depuis combien de temps on était dans la zone précédente ? | Long séjour en zone opposée = accumulation de tension. Court = mouvement encore jeune. |

### Dimension 2 — ALIGNEMENT MULTI-TF : tous les TF racontent-ils la même histoire ?

| Champ | Question |
|-------|----------|
| **Position par TF** | Où est chaque TF (M5/M15/M30/H1/H4) dans sa propre zone ? |
| **Cohérence** | Sont-ils alignés (même direction) ou divergents ? |
| **Premier arrivé** | Quel TF a atteint sa zone extrême en premier ? (le leader temporel) |
| **Cascade** | Y a-t-il une cascade en formation (LTF → MTF → HTF) ou au contraire un HTF qui traîne ? |

**Règle** : si le M5 est extrême mais le H4 est neutre, le mouvement est probablement une respiration dans un range. Si le H4 est extrême et le M5 le rejoint, c'est une cascade directionnelle.

### Dimension 3 — CARTE DES COALITIONS : qui pousse ?

| Champ | Question |
|-------|----------|
| **Devise motrice** | USD, GBP, EUR, JPY, etc. — qui est à l'extrême ? |
| **Coalitions** | EUR+GBP contre USD ? Coalitions sur tous les TF ou juste un ? |
| **Largeur** | Le mouvement est général (8 devises) ou spécifique à une paire ? |
| **Opposition** | Y a-t-il une devise qui résiste (coalition adverse en formation) ? |

**Règle** : une devise extrême soutenue par son bloc (EU, SH, COM) est plus significative qu'une devise extrême isolée. Une coalition qui tient sur tous les TF = mouvement structurel.

### Dimension 4 — HISTOIRE RÉCENTE : qu'est-ce qui s'est passé avant ?

| Champ | Question |
|-------|----------|
| **Précédent extrême** | Y a-t-il eu une zone extrême opposée dans les N heures ? |
| **Compression préalable** | Y a-t-il eu une phase LOCK/SQUEEZE avant l'arrivée ? |
| **Patterns détectés** | Quels patterns ont été vus dans la montée (REJECTION, DIVERGENCE, COALITION) ? |
| **Tension accumulée** | Depuis combien de temps le marché construisait ce mouvement ? |

**Règle** : plus la tension accumulée avant l'arrivée est longue, plus le comportement à la zone (REJET/ABSORPTION/ÉQUILIBRE) sera violent.

### Dimension 5 — CONTEXTE MARCHÉ : dans quel cadre ?

| Champ | Question |
|-------|----------|
| **Session** | Asia / London / NY / chevauchement / After |
| **Régime volatilité** | COMPRESSION / CALM / NORMAL / EXPANSION / SPIKE |
| **Texture** | STRUCTURAL / NEWS_SPIKE / SESSION_FRICTION / MM_NOISE |
| **Heure relative** | Début/milieu/fin de session, chevauchement |

**Règle** : un extrême en ASIAN (faible amplitude naturelle) est plus significatif qu'un extrême en OVERLAP (forte amplitude, faux signaux fréquents).

### Dimension 6 — SIGNATURE COMPORTEMENTALE : que fait le prix maintenant ?

| Champ | Question |
|-------|----------|
| **Comportement à la zone** | Pause / continuation / rejet / absorption ? (cf. §3.1) |
| **Tick** | Fréquence tick à l'arrivée (explosion ou apathie) ? |
| **Spread** | Comportement du spread (dilatation, contraction) ? |
| **Réaction** | Le prix rebondit sur la zone ou la traverse ? |

### Synthèse — lecture en 3 questions

Avant toute décision sur un extrême, répondre à :

1. **Quelle est l'histoire de cette arrivée ?** (trajectoire + histoire récente)
2. **Qui est aligné ?** (multi-TF + coalitions)
3. **Que fait le prix maintenant ?** (comportement + tick)

> **Règle absolue** : ne jamais lire un extrême comme un seuil. Toujours le lire comme une scène complète.
> Les seuils numériques (75/25, 80/20) ne sont que des repères de départ. La scène est la source de vérité.

---

## 4. Comportements récurrents fractaux

> Les 6 comportements ci-dessous sont des **signaux de lecture récurrents**.
> Ils se reproduisent à l'identique sur tous les TFs (M1, M5, H1, H4).
> Le TF détermine la portée temporelle, pas le mécanisme.

### 4.1 Courbure M5 — sens provisoire

La pente de la force USD (M5, deltas entre bougies consécutives) s'aplatit progressivement
jusqu'à s'inverser. Le ralentissement progressif de la pente en zone extrême donne
le **sens provisoire** du prochain mouvement.

**Limite** : une courbure peut se reproduire plusieurs fois (bosses dégressives) avant
la vraie fin de jambe. Ne jamais conclure sur une seule inflexion.

### 4.2 Zone extrême M1 — fenêtre de scalp

Le M1, tant qu'il reste en zone extrême (>80), est une **fenêtre d'exécution scalp**
dans la direction donnée par M5. Le M1 ne dit jamais le sens — il dit seulement
si la fenêtre est ouverte. Dès que M1 sort de sa zone extrême, la fenêtre se referme.

**Piège** : un croisement/décroisement M1 des forces (USD croise puis re-décroise GBP
en 2-3 min) peut sembler un signal de retournement. Ce n'est qu'un sursaut sans suite
**sauf si confirmé par M5 ou synchro GBP+EUR**.

### 4.3 Synchro GBP+EUR — fin d'une respiration

Quand GBP et EUR — qui montaient en miroir de la baisse USD — ralentissent puis basculent
négatifs **à la même minute** (ou 1 min d'écart max), ce double-arrondi synchrone signale
la fin de la respiration et la reprise du mouvement d'origine.

**Critère** : 2 bougies M1 consécutives où les deux pentes ralentissent puis basculent ensemble.
Pas une bougie isolée.

### 4.4 Nœud à 3 — signal de scalp actif (deux issues)

Quand les 3 écarts (`|USD-GBP|`, `|USD-EUR|`, `|GBP-EUR|`) se contractent simultanément
vers un minimum commun sur M1, c'est un signal d'entrée scalp dans le sens de la jambe
HTF en cours qui reprend.

**Deux issues selon la résolution (1-2 bougies après) :**

| Contexte | Résolution | Action |
|----------|-----------|--------|
| Jambe HTF active | Hiérarchie nette se redessine (USD > GBP/EUR) | Entrée scalp (sens jambe HTF) |
| Fin de session / palier déjà acté | Devises restent proches/emmêlées | Consolidation — pas d'entrée |

**Fenêtre de validité** : du nœud jusqu'au prochain extrême M1 atteint.

### 4.5 Bosses dégressives — cycles multiples avant fin de jambe

Tant qu'USD reste en zone haute — même en formant des bosses successives chacune plus basse
que la précédente — il continue de construire le TF supérieur dans le même sens.
Le marché peut faire 2, 3, 4 bosses dégressives avant de réellement sortir de la zone haute.
Chaque bosse a son propre cycle synchro/désynchro GBP-EUR sans que cela change la construction HTF.

### 4.6 Nœud H1 — signal fort et durable (comportement fractal)

Le même mécanisme de nœud (convergence des 3 écarts vers un minimum) existe **sur H1, et
probablement sur tout TF**, avec une portée proportionnelle à l'échelle :

- **Nœud H4/H1** → mouvement qui domine les heures suivantes (toute une session ou plus)
- **Nœud M5** → bosse/jambe de quelques dizaines de minutes
- **Nœud M1** → mouvement de quelques minutes (scalp)

**Le filtre de confiance** : avant de traiter un nœud comme signal fort, vérifier s'il existe
une **divergence H4 préexistante** (une devise déjà retournée sur H4, l'autre pas encore).
Validé sur 3 dates indépendantes (11/05, 16/06, 17/06) : 3/3 cascades fortes avaient une
divergence H4 préexistante ; 0/2 nœuds faibles ne l'avaient pas.

### Hiérarchie de lecture consolidée

```
H1/H4   → direction de fond (ne se dément pas sur un simple ressac M5)
  ↓
M5      → courbure = sens provisoire — attention aux bosses multiples
  ↓
M1      → zone extrême = fenêtre de scalp (pas un signal de sens)
  ↓
GBP+EUR → synchro = fin d'UNE bosse (pas forcément fin de jambe)
  ↓
Nœud 3  → hiérarchie nette = scalp / emmêlées = consolidation
  ↓
Tick    → contraction range/volume = confirmation du pivot
```

---

## 5. Coalition et zones SDI

Le **comportement de coalition** (leader devise, blocs EU/SH/COM) donne du poids
supplémentaire aux zones extrêmes du SDI.

- **USD leader + zone extrême haute + JPY/CAD qui suivent** → coalition safe haven
  = signal plus fort qu'USD seul à l'extrême
- **GBP leader + zone extrême haute + EUR qui suit** → coalition risque
  = signal plus fort
- **Devise extrême sans coalition** (leader seul, pas de suiveur) → signal moins fort,
  l'extrême peut être plus fragile

> Lire la coalition en même temps que les zones SDI. Une devise extrême soutenue
> par son bloc est plus significative qu'une devise extrême isolée.

Blocs canoniques : EU (EUR+GBP+CHF) · SH (USD+JPY) · COM (AUD+NZD+CAD).

---

## 6. Structure du flux — perception multidevise

> PowerFlow ne prédit pas le prochain tick. Il **perçoit l'état du flux à l'instant** :
> où va l'argent entre les 8 devises ?

### 6.1 Le mécanisme énergétique (ex-Cascade HTF→LTF)

Un croisement sur H4 (ou tout TF porteur) est un signal important mais **pas le seul**.
Chaque fenêtre de temps a ses propres signaux :

| Phase | TF | Ce qui se passe | Signature SDI |
|-------|-----|----------------|---------------|
| **Stockage** | H4/H1 | Une devise remonte depuis le bas, écart se réduit | Plusieurs bougies H4 creusent l'écart |
| **Croisement** | TF porteur | Devise passe de l'autre côté du pair | USD > GBP sur H4 |
| **Attente** | TF porteur (open) | La bougie suivante ouvre, prix sous/au-dessus l'open | Énergie contenue |
| **Casse** | Tous TFs | Prix casse l'open de la bougie de croisement | Explosion simultanée |
| **Cascade** | Tous TFs | Énergie cascade dans les TFs, extrêmes absolus | USD 94, EUR 8 sur M1 |
| **Épuisement** | M5/M15 | Ralentissement, M1 commence à diverger | Contraction ticks |

### 6.2 Lecture horloge

| TF | Rôle |
|-----|------|
| **H4/D1** | Stockent l'énergie — le TF porteur. Plusieurs bougies pour construire le croisement |
| **H1** | Confirme le croisement H4. Structure de session |
| **M15/M5** | Canal de transmission — l'énergie y transite. Quand M15 ralentit, la cascade s'essouffle |
| **M1** | Fenêtres de scalp. Ses extrêmes sont l'aboutissement, pas le signal |
| **Ticks** | Complémentaires. Le tick ne spike pas pour annoncer un pivot — il se contracte juste avant |

### 6.3 Exemple live — Cascade du 17/06

```
H4 bougie N-2 : USD 36.9 (< GBP 44.3)  → Stockage
H4 bougie N-1 : USD 38.3 (< GBP 43.4)  → Stockage
H4 bougie N   : USD 41.0 (> GBP 38.3)  → CROISEMENT validé (open=1.34151)

H4 bougie N+1 : prix casse 1.34151 → -80 pips en 1h
                M1 : USD 92→94, EUR 8, GBP 28
                Bridge en retard (ΔF=+59, disait GBP fort)
```

---

## 7. "On trade quand le marché paie" — définition opérationnelle

Un trade est initié uniquement quand **les 3 conditions sont réunies** :

1. **SDI extrême actif** : au moins une devise en zone extrême (seuil dynamique selon TF×session×devise) sur MTF (H1/H4)
2. **LTF amorce retournement** : LTF commence à diverger de l'extrême (`force_cycle_phase = CROISEMENT` ou `INVERSION`)
3. **Confirmation tick** : ticks confirment la pression (`microstructure_score > 40`, `tick_freq_hz` cohérent, `ctx_align` aligné)

Le marché "paie" quand ces trois signaux convergent. Avant : surveiller.

---

## 8. Lecture multi-TF : MTF (structure) → LTF (confirmation)

```
HTF (H4/D)   → contexte directionnel global — ne pas trader contre
MTF (H1/M30) → structure en cours — zone d'intérêt SDI extrême (seuils dynamiques)
LTF (M15/M5) → confirmation entrée — force_cycle_phase + microstructure
M1           → précision timing (forming bar, velocity intra-bougie)
```

**Règle hiérarchique** :
- HTF définit le biais interdit (ne jamais trader contre H4 fort)
- MTF identifie le contexte — SDI extrême (seuil dynamique) = fenêtre d'intérêt ouverte
- LTF confirme — sans LTF, pas d'entrée même si MTF est parfait
- M1 (option 0 EA) = vélocité intra-bougie en cours de formation

---

## 9. Confirmation tick : force_cycle_phase + ctx_align + microstructure

Trois dimensions de confirmation LTF :

### force_cycle_phase (STEP_13, 300s)

| Phase | Signification | Action |
|-------|--------------|--------|
| `NEUTRE` | Pas de cycle actif | Surveiller |
| `CROISEMENT` | Forces en train de se croiser | Fenêtre ouverte |
| `INVERSION` | Inversion confirmée → boost tick_score **+15** | Signal fort |
| `ANTAGONISME` | Forces opposées sans résolution | Attendre |

### ctx_align (structure_ledger)

| Valeur | Signification | Boost scorer |
|--------|--------------|--------------|
| ≥ +0.34 (aligné) | GBP et USD dans la direction attendue | **+0.10** |
| neutre | Pas de signal cross-devise | 0 |
| ≤ −0.34 (opposé) | Cross-devises contredisent la direction | **−0.20** |

> L'opposition est le signal fort (asymétrique : −0.20 vs +0.10). Corrélation prouvée C2 : +0.149 sur 600+ patterns.

### microstructure_score (pf_tick_confirmation)

- Seuil **40** → WR **65.9%** (restauré après fix TICK_DB, C4/P0)
- Alimenté depuis `data/tick_master.db` (22M ticks GBPUSD)
- Composantes : `tick_rejection`, `tick_momentum`, `tick_freq_hz`, `tick_spread_avg_dp`

---

## 10. Narration multidevise obligatoire

Tout raisonnement sur un signal GBPUSD doit commencer par une phrase du type :
> « GBP est [fort/neutre/faible] parmi les 8 devises. USD est [fort/neutre/faible].
> Le flux dominant va de [X] vers [Y]. La coalition active est [aucune/USD/GBP/commodities]. »

Sans cette phrase, la lecture est partielle.

---

## 11. Hiérarchie de fiabilité des sources

```
Forces MT4 (fiable, toutes minutes) ≥ Bridge forces×tick (fiable si ts < 6min)
> Structure_ledger (calculé chaque 300s) > Patterns détectés
> Ticks MT5 (complémentaire, encore imparfaits) > Scorecard (synthèse)
```

Si ticks MT5 stale → continuer l'analyse sur forces + bridge + structure. Ne pas dégrader
automatiquement en WAIT à cause des seuls ticks.

**Rappel** : le bridge a montré ~3h de retard le 17/06. Toute analyse live doit lire
`force_snapshots_v2` directement (M1/M5/H1) et non dépendre du bridge pour la fraîcheur.

---

## 12. Le flux est une lecture, pas une prédiction

PowerFlow ne prédit pas le prochain tick. Il **perçoit l'état du flux à l'instant** :
- Où va l'argent entre les 8 devises ?
- Quelle est la tension accumulée ?
- Dans quelle phase sommes-nous (accumulation, rupture, extension, fading) ?

Les agents qui « attendent une confirmation tick » avant de valider un signal ratent la nature
du système. La confirmation vient des forces alignées, pas du tick suivant.

---

## 13. Signature Engine C13 — Grammaire de décision

> C13 livré 20/06/2026 (`pf_signature_engine.py`, cron 5min, `signature_log` 6007+ buckets).
> Remplace la terminologie "Chantier 5" désormais obsolète (C7→C13 tous livrés, C14/C15 planifiés).
> ADR-001 : C13 est le **Signature Engine** — fondation des modes d'opération live.

### 13.1 Modes d'opération (ADR-003)

Le `readability_score` calculé par `pf_signature_engine.py` détermine le mode du pipeline :

| Mode | Seuil readability_score | Comportement système | Cible |
|------|------------------------|----------------------|-------|
| **MODE_A** | ≥ 0.70 | Hermes autonome — signal validé, exécution sans frein | C15 |
| **MODE_B** | 0.40 – 0.70 | Dossier trader — signal conditionnel, revue humaine | C14 |
| **NO_TRADE** | < 0.40 | Pipeline bloqué — aucun signal transmis | — |

Règle émergente (STATE.md `I005–I007`) :
- `NO_TRADE` → `quality = 0` (signal annulé)
- `MODE_B` → `quality × 0.85` (signal dégradé)
- `MODE_A` → `quality` inchangée

### 13.2 MRL Dynamique — P50 session (ADR-002)

> MRL = **percentile 50 de session** par TF, recalculé en temps réel.
> Implémenté : `pf_signature_engine.py:199` (`_compute_mrl_dynamic`).

La Moyenne de Retour à la Liquidité (MRL) n'est **pas un seuil fixe** — elle reflète le centre
de gravité réel de la session en cours (médiane statistique par TF × session).

- Recalcul à chaque tick du cron 5min
- `distance_mrl[tf]` = delta_courant − MRL_courant
- Clé de lecture : **plus `|distance_mrl|` est grand, plus le marché est en tension**

### 13.3 Cycle de phase (ADR-004)

Les forces SDI suivent un cycle reproductible à toute échelle :

```
COMPRESSION → RUPTURE → EXTENSION → RETOUR_MRL
    (palier)    (cassure)  (continuation)  (mean-reversion)
```

| Phase | Signal SDI | Comportement GBPUSD | Action |
|-------|-----------|---------------------|--------|
| **COMPRESSION** | `|Δforce| < SEUIL_PALIER` N barres | Range serré, énergie accumulée | Surveiller la rupture |
| **RUPTURE** | Écart vs palier > SEUIL_CASSURE (1.5) | Move directionnel naissant | Évaluer qualification tick |
| **EXTENSION** | Continuation ≥ M_MIN barres même direction | Jambe active | Ride ou skip selon MRL |
| **RETOUR_MRL** | Force > MR_HIGH (80) ou < MR_LOW (20) | Mean-reversion probable | Surveillance REJET §18 |

> `pf_regime_detector.py` → table `regime_snapshots` → pivot `tick_aggregated_5s` (±30s) pour
> qualifier CASSURE : CONFIRMÉE / FAUSSE / INDETERMINEE.

### 13.4 Mapping régime(devise) ↔ phase(paire) + REJET homonyme ⚠️

Le terme **REJET** désigne **deux concepts distincts** dans PowerFlow — ne pas confondre :

| Terme | Source | Définition | Seuil |
|-------|--------|-----------|-------|
| **REJET §9** (contact MRL) | `pf_signature_engine.py` `contact_zone_of()` | `\|distance_mrl\|` > 30 → extrême tendu, retournement probable | distance > `ZONE_EXTREME` |
| **REJET §18** (cinématique régime) | `pf_regime_detector.py` | Force en zone extrême (>MR_HIGH/< MR_LOW) repart violemment | `\|Δforce\|` ≥ 2.0 en zone |

**Mapping régime SDI (par devise) → lecture paire GBPUSD :**

| Régime devise (regime_snapshots) | Phase paire | Setup GBPUSD | Priorité |
|----------------------------------|-------------|--------------|---------|
| GBP=REJET§18 (du haut) + USD=EXTENSION haut | RETOUR_MRL GBP | LONG naissant | Haute |
| USD=REJET§18 (du haut) + GBP=EXTENSION haut | RETOUR_MRL USD | SHORT naissant | Haute |
| GBP=CASSURE CONFIRMÉE haut + USD=PALIER | RUPTURE | LONG directionnel | Modérée |
| GBP=COMPRESSION + USD=COMPRESSION | COMPRESSION paire | NO_TRADE | — |
| Régime FAUSSE ou INDETERMINEE | Ambigu | Attendre confirmation tick | — |

> **Règle** : REJET§18 = vrai setup mean-reversion (priorité haute).
> REJET§9 = tension accumulée → contexte favorable mais pas déclencheur seul.

---

## 14. Le Nœud — convergence multidevise fractale (principe transversal)

> Le nœud à 3 (convergence de `|USD-GBP|`, `|USD-EUR|`, `|GBP-EUR|` vers un minimum commun)
> est un objet de lecture fractal. Son mécanisme est identique à toute échelle de temps.
> Ce qui change avec le TF, c'est la portée temporelle de sa résolution.

Validé sur 3 dates indépendantes (11/05, 16/06, 17/06), 3/3 cascades fortes avec
divergence H4 préexistante. Le nœud H1 le plus serré du 17/06 (d_ge=0.4) a annoncé
un mouvement qui a tenu toute la session (+12h).

---

## 15. RÈGLE TIMEZONE ABSOLUE — source unique UTC

> Décision #152 (18/06/2026). Validé par confrontation DB directe : erreur de
> fusion `bar_time` (broker) + `ts` (UTC) ayant créé un faux décalage +2h.

Dans les DB PowerFlow V8, deux types de timestamp **non interchangeables** :

| Colonne | Fuseau | Source | Usage recommandé |
|---------|--------|--------|------------------|
| `ts` (detected_patterns) | **UTC** | machine (created_at) | **SOURCE UNIQUE** pour toute chronologie de patterns |
| `created_at` (force_snapshots_v2) | **UTC** | machine | **SOURCE UNIQUE** pour la timeline des forces |
| `ts_epoch` | epoch UTC | serveur | calculs internes |
| `bar_time` / `bar_close_time` | **Broker UTC+3** (Tickmill, ADR-005) | MT4/MT5 | Alignement bougies uniquement — **PAS pour dater** |

### Règles absolues

1. **Ne jamais mélanger** les deux fuseaux dans une même timeline. Les mélanger crée un décalage de +2h qui donne l'illusion de "sauts dans le futur" (événements qui semblent se produire après leur vrai moment).
2. **Source unique** pour toute lecture temps réel = `ts` de `detected_patterns` ou `created_at` de `force_snapshots_v2` (tous deux **UTC machine**).
3. **`bar_time` / `bar_close_time` (broker)** utilisé UNIQUEMENT pour aligner avec les bougies MT4/5. Jamais pour dater la séquence d'événements.
4. **Conversion finale uniquement** : heure Paris = UTC+2 en été, broker = UTC+3 (Tickmill, ADR-005 confirmé 20/06). Règle : broker − 3h = UTC.
5. **Requêter SQL** toujours avec `datetime('now', 'utc')` et afficher avec `strftime('%H:%M', ts)` sur la colonne UTC.

### Erreur documentée

Le 18/06/2026, une lecture a mélangé `bar_time` (broker) pour les forces M5 et `ts` (UTC) pour les patterns, créant un bloc temporel "10:55" fictif alors que l'événement réel était à 09:55 UTC. Les patterns et résolutions étaient corrects — seul l'horodatage était décalé. Détecté par vérification DB directe en SQL. Ne pas reproduire.

---

## 16. DOCTRINE DUALE — HTF tendance + LTF scalp (Søn, 29/06/2026)

> Source : session live Søn 29/06, formalisée en doctrine gravée suite au scalp SHORT scalpé serré (entry 1.32445, SL 1.32510, perte -6.5 pips). Validée par `pf_antisignal_check` codé en prod le même jour.

### 16.1 Le principe — pas une vérité, deux lectures

Les **HTF (H4/H1/D1)** = tendance lissée, structure de fond, biais directionnel.
Les **LTF (M1/M5/M15)** = microstructure bruyante, riche en opportunités d'entrée.

On peut **trader la tendance OU le contre** selon niveaux/contexte. Ce sont deux lectures complémentaires, pas mutuellement exclusives. Le système n'impose pas UN seul mode.

### 16.2 Mode A — TENDANCE AGRESSIVE

**Quand l'activer** : HTF trend fort confirmé (D1+H4 alignés même direction).
- Détecteur : `pf_trend_detector.aggregate_regime()` → `AGGRESSIVE_TREND`
- Sortie : `dict(mode='AGGRESSIVE_TREND', htf_alignment=True, htf_strength, confidence, valid_until)`

**Approche d'exécution** :
- TF d'entrée : **M1 / M5** (granularité fine pour capter les replis)
- Pas attendre le cross M30/H1 — on est déjà trend, on cherche replis extrêmes
- **Pyramidage 2-3 lots** sur chaque repli qui confirme la tendance (manager : `pf_pyramid_manager`)
- **Trailing stop ATR-based** (module `pf_atr_trailing`) :
  - Niveau 1 (initial) : SL = entry − 1.5 × ATR(M5)
  - Niveau 2 (BE) : dès que prix > entry + 2 × ATR, SL = entry (break-even)
  - Niveau 3 (locked) : dès que prix > entry + 3 × ATR, SL = prix − 3 × ATR (lock 1 ATR de profit)

**Doctrine §8 (multi-TF) reste valide** : HTF définit le biais, LTF confirme entrée, M1 timing.

### 16.3 Mode B — MEAN-REVERSION LTF

**Quand l'activer** : HTF range ou transition détectée.
- Détecteur : `pf_trend_detector.aggregate_regime()` → `MEAN_REVERSION`

**Approche d'exécution** :
- TF d'entrée : **M5 / M15**
- Single shot en zone extrême (B2 LOW NY, F6 — patterns mean-reversion déjà calibrés)
- Stop **fixe serré** 8-12 pips (zone de range, pas de pyramide)
- Risque antisignal `PINCH_BREAKOUT_STOP_HUNT` (cf §17.1)

### 16.4 Doctrine de choix entre Mode A et Mode B

```python
regime = trend_detector.aggregate_regime(symbol, timeframe='H1')
if regime['mode'] == 'AGGRESSIVE_TREND' and regime['confidence'] >= 0.7:
    # Mode A — pyramide + ATR trailing
elif regime['mode'] == 'MEAN_REVERSION':
    # Mode B — single shot + SL fixe
else:
    # NEUTRAL — pas de trade ou wait
```

Le **moteur de reco dual** est `pf_recommendation_engine_ltf.py` qui charge `calibration_v2.json` et fait le tri.

### 16.5 Doctrine de risque Søn (résumée)

| Mode | Sizing | SL | Pyramide | RR cible |
|---|---|---|---|---|
| **A agressif** | 0.3-0.5 lots base + paliers 0.5/0.3/0.2 | ATR × 1.5 (variable) | Oui 3 max | 1.5 à 3.0 |
| **B mean-reversion** | 0.5-1.0 lots | Fixe serré 8-12 pips | Non | 1.0 à 2.0 |

> Risque : Mode A peut accumuler en cas de pyramide contre-tendance. Limiter `max_pyramid_size_lots = 0.5` total.

### 16.6 Tests du mode A sur 14j backtest

`tests/test_pf_trend_detector.py` (17 tests), `test_pf_pyramid_manager.py` (11), `test_pf_atr_trailing.py` (8) — 36 tests verts sur modules Mode A.

À backtester sur windows_journal 14j avant passage en prod full-auto. Pour l'instant validation manuelle par Søn sur trades live.

---

## 17. ANTISIGNAUX TRANSVERSES (Søn, 29/06/2026)

> Implémenté dans `core/pf_antisignal_check.py` (commit `076df0f` = `6b06dab`, M3-BIS Mode A).
> 4 antisignaux en module autonome appelable par `pf_analyst.py` ou le live pipeline.
> Chaque antisignal retourne un `AntisignalResult {blocked, antisignal_type, score (0-100), narrative, details}`.
> `blocked=True` si `score >= seuil` (50 ou 60 selon l'antisignal).

> ⚠️ **Note historique** : la version 1 (commit `329a6a4`, live 18:30) documentait
> PINCH_COMPRESSION / SL_TOO_TIGHT / FAKE_NEWS_SPIKE / MICROSTRUCTURE_DOWN.
> La version 2 actuelle (M3-BIS, 18:50) remplace ces 4 antisignaux par
> OPPOSITION_HF / SQUEEZE_VOL / MOMENTUM_DIVERG / PINCH_REVERSAL — couverture
> plus large de la doctrine §16 (Mode A tendance ET Mode B mean-reversion).
> La doctrine v1 reste valable qualitativement (SL serré = danger) mais le **code
> de référence** est la v2 ci-dessous.

### 17.1 OPPOSITION_HF — HTF contrarie le trade (Mode A)

**Active quand** : `trade_direction = LONG` ET `d1_regime = TREND_DOWN`, OU symétrique SHORT/TREND_UP.

**Seuil** : `score >= 50` → `blocked=True`. `score = min(100, d1_score × 1.5)`.

**Pourquoi** : entrer tendance (Mode A) contre le D1 = probabilité forte de reversal. D1 est la structure de fond la plus lourde ; si elle s'oppose, on attend.

**API** : `check_opposition_hf(trade_direction, d1_regime, h4_regime, d1_score)`.

### 17.2 SQUEEZE_VOL — volatilité en collapse, breakout imminent mais direction incertaine

**Active quand** : `ATR < 30% de ATR_avg` OU `Bollinger bandwidth < 20% de son avg`.

**Seuil** : `score >= 60` → `blocked=True`. `score = (seuil - ratio) / seuil × 100`.

**Pourquoi** : squeeze = énergie accumulée qui va se libérer, mais **la direction n'est pas décidée**. Entrer avant le breakout = pile ou face. Mieux vaut attendre que le mouvement se confirme.

**API** : `check_squeeze_vol(atr_current, atr_avg, boll_width_ratio)`.

### 17.3 MOMENTUM_DIVERG — prix et momentum en désaccord

**Active quand** :
- Prix `+0.5%` mais `RSI < 45` (divergence bearish), OU
- Prix `-0.5%` mais `RSI > 55` (divergence bullish).

**Seuil** : `score >= 50` → `blocked=True`. `score = |50 - rsi| × 1.5`.

**Pourquoi** : le momentum précède souvent le prix. Un momentum qui s'épuise pendant que le prix monte = signal de retournement probable. MACD histogram en détails pour confirmation optionnelle.

**API** : `check_momentum_diverg(price_change_pct, rsi, macd_histogram)`.

### 17.4 PINCH_REVERSAL — double rejection (mode B, doctrine live Søn)

**Active quand** :
- ≥2 scenes `OPPOSITION` ou `PINCH` dans les 10 dernières fenêtres → `blocked=True` (score `= min(100, 40 + count × 15)`), OU
- `entry` dans 10 pips d'une zone d'appui (`ZONE_A5/A4/F5/F6`) → **warning** (score 45, `blocked=False`).

**Seuil** : `score >= 50` → `blocked=True` (sauf cas zone proximity = warning).

**Pourquoi** : ce antisignal capture le pattern `PINCH_BREAKOUT_STOP_HUNT_REINTEGRATION` observé live Søn 29/06 15:25 UTC (SL serré chassé, -6.5 pips). Double rejection = MM teste une zone, le prix va probablement pivoter.

**API** : `check_pinch_reversal(recent_scenes, current_price, entry_price, zone)`.

### 17.5 check_antisignals agrégateur

```python
from core.pf_antisignal_check import check_antisignals

# Trade direction à tester (LONG ou SHORT), connections DB optionnelles
results = check_antisignals(
    trade_direction='SHORT',
    conn_fresh=conn,       # powerflow_fresh.db (snapshots ATR/RSI/Boll + regimes D1/H4)
    conn_scenes=conn_s,    # scenes.db (recent_scenes pour PINCH_REVERSAL)
)
# results = [AntisignalResult(...), ...] — liste des antisignaux ACTIFS (None filtrés)
blocked = any(r.blocked for r in results)
```

`check_antisignals()` lit automatiquement le snapshot le plus récent (ATR/RSI/Boll), les régimes `structure_ledger` (D1/H4 + score), et les 10 dernières scenes. Si `blocked=True`, `pf_analyst` DOIT downgrader la décision vers WAIT/NO_GO.

> Câblage STEP_27 (analyst decision) à intégrer — voir roadmap P0 Phase C.

### 17.6 Pattern PINCH_BREAKOUT_STOP_HUNT_REINTEGRATION (formalisé live)

> Formalisé en live Søn 29/06 15:25 UTC, scalpé -6.5 pips. Détecteur dédié
> `core/pf_pinch_breakout_detector.py` (~240L) — 6 tests verts (commit `329a6a4`).

6 phases canoniques :

1. **Compression post-cross** : ΔF range serré, forces quasi-égales (range M5 < 10 pips)
2. **Stop hunt** : prix dépasse la borne haute range de 3-5 pips (chasse les SL serrés)
3. **Réintégration** : prix retour SOUS la borne haute en < 2min (faux breakout)
4. **Re-accumulation** : nouveau rally court qui ne dépasse pas la borne
5. **Flush post-sommet** : ΔF s'effondre depuis le pic (>15 pts de chute)
6. **Breakout directionnel** : TRANSITION observée, trade direction possible

**Antisignal associé** : PINCH_REVERSAL §17.4 capture ce pattern via la scène OPPOSITION/PINCH.
**Détecteur standalone** : `pf_pinch_breakout_detector.detect_pinch_phases(symbol)` → timeline 6 phases + `is_pinch_active()` + `is_stop_hunt_likely()`.

Si Phases 1-2 en cours → NE PAS shorter avec SL serré. Attendre Phase 4+ ou trade contre avec sizing réduit.

---

*Document fondateur PowerFlow V8. Mis à jour 17/06/2026 — refonte complète :
SDI coeur du système, comportements fractals (courbure/nœud/synchro/bosses),
coalition pondère les zones, structure du flux, ticks complémentaires.
Comportements documentés de la session live 17/06 (docs/sessions/COMPORTEMENTS_LECTURE_MULTITF_20260617.md).*
*§16 Doctrine duale + §17 Antisignaux transverses ajoutés 29/06/2026 (M3-BIS Mode A, commit `076df0f` = `6b06dab`).*
*Toute évolution doit être validée par une décision numérotée dans STATE.md.*
