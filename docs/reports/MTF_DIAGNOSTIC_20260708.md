# Diagnostic MTF — H4 squelettique + staleness M1/M5

Date : 2026-07-08
Portée : diagnostic uniquement (aucune modification de script — cf. conclusion).
DB analysée : `data/v9_forces.db`, symbole `GBPUSD` (seul symbole présent).

## 1. Résumé exécutif

- **Aucun bug côté Python n'a été trouvé.** `core/v9/capture_server.py` est un
  serveur TCP purement passif (asyncio) : il ne planifie rien, ne filtre rien
  par timeframe, insère (`INSERT OR IGNORE`) exactement ce que l'EA MT4 lui
  envoie. Une recherche exhaustive (`grep -rniE "H4|240|timeframe" scripts/
  core/v9`) ne trouve **aucun scheduler Python** contrôlant la cadence par
  timeframe — la cadence de push est entièrement déterminée côté EA MT4
  (`ea/V9_Sonde_TF.mq4`, référencé dans le docstring de `capture_server.py`
  mais **absent de ce dépôt** — code MQ4 hors périmètre Python).
- H4 (et H1/M30/D1) reçoivent **exactement 1 push par bougie clôturée**
  (vérifié via les deltas de `bar_time`, qui avancent en pas exacts de la
  durée du timeframe). C'est le comportement documenté dans
  `docs/architecture/formats/FORMAT_FORCES.md` pour les timeframes
  "candle-close". Ce n'est **pas un bug** — c'est le comportement attendu
  d'un capteur "1 snapshot par clôture", mais il est **structurellement trop
  grossier** pour une lecture multi-TF intra-bougie sur H4 (une bougie de 4h
  ne produit qu'un seul point).
- **Correction du chiffre fourni dans la tâche** : mesuré sur une journée
  calendaire complète (2026-07-07 00:00–23:59), H4 = **6 snapshots/jour**
  (et non 3), exactement conforme à 24h / 4h = 6 clôtures/jour. H1 = 24/jour
  (1/heure), également exact. Le chiffre "3/jour" ne correspond à aucune
  fenêtre de mesure trouvée dans les données actuelles ; probablement une
  mesure antérieure sur une fenêtre partielle (ex. weekend, marché fermé une
  partie de la période, ou un jour tronqué). Le diagnostic qualitatif du
  ticket ("H4 squelettique, lecture multi-TF impossible") reste valide
  indépendamment de cette correction : 6 points/jour espacés de 4h ne
  permettent aucune lecture intra-bougie.
- **staleness M1 (88.8%) et M5 (70.0%) confirmées** (chiffres exacts mesurés :
  88.8% et 70.0%, cf. §3) mais **pour deux raisons partiellement
  différentes** — voir §3.

## 2. Méthodologie

Requêtes SQL directes sur `data/v9_forces.db` (lecture seule, aucune
modification). Comptages par timeframe, répartition horaire, analyse des
deltas `bar_time` vs `created_at`, comparaison au seuil `STALE_THRESHOLDS_MS`
(`core/v9/config.py`, non modifié — lu uniquement).

## 3. Constats détaillés par timeframe

### Vue d'ensemble (historique complet en base)

| Timeframe | Total snapshots | Stale | % Stale | Cadence observée |
|---|---|---|---|---|
| M15 | 78 030 | 24 864 | 31.9% | Continue, ~2000-3000/h, TOUTE la période |
| M5 | 31 136 | 21 804 | 70.0% | **Bimodale** — voir §3.2 |
| M1 | 3 336 | 2 962 | 88.8% | Constante, exactement ~60/h (1/min) |
| M30 | 314 | 0 | 0.0% | Constante, 1/clôture (2/h) |
| H1 | 259 | 0 | 0.0% | Constante, 1/clôture (24/jour exact) |
| H4 | 214 | 0 | 0.0% | Constante, 1/clôture (6/jour exact) |
| D1 | 202 | 0 | 0.0% | Constante, 1/clôture (1/jour) |

`STALE_THRESHOLDS_MS` (core/v9/config.py, référence, non modifié) :
M1=5s, M5=35s, M15=95s, M30=185s, H1=365s, H4=1450s(~24min), D1=9000s(2.5h).

### 3.1 H4/H1/M30/D1 — comportement candle-close pur, 0% stale

Exemple H4 (10 dernières lignes, `symbol='GBPUSD'`) : les `bar_time`
successifs avancent en pas **exacts de 14400s (4h)**, et chaque `created_at`
suit son `bar_time` de quelques dizaines de secondes à quelques minutes
(latence normale de clôture MT4). Résultat : `age_ms` au moment du push est
toujours très inférieur au seuil (1 450 000 ms) → jamais stale. Idem pour
H1 (pas exact de 3600s), M30, D1. **Ce sous-ensemble se comporte exactement
comme documenté** dans `FORMAT_FORCES.md` §"Candle-close (tableau forces)" :
un point par bougie clôturée, horodaté à la clôture.

**Conséquence pour la lecture multi-TF** : avec seulement 6 points/jour pour
H4 (espacés de 4h), le pipeline ne peut voir H4 qu'à l'instant de chaque
clôture — impossible d'observer l'évolution intra-bougie (tension qui monte,
pliure qui se forme, etc.) que M15 peut voir en continu. C'est la cause
directe de "lecture multi-TF impossible" mentionnée dans le ticket.

### 3.2 M15 — continu tout du long, M5 — changement de régime détecté

**M15** : répartition horaire sur 24h strictement stable, ~1700-3070
push/heure du 2026-07-07 00h au 2026-07-08 14h **sans interruption**.
Sur un échantillon des 200 dernières lignes (12.5 minutes réelles), on
compte seulement **2 valeurs distinctes de `bar_time`** — l'EA republie donc
en continu (haute fréquence, probablement à chaque tick) la bougie M15 *en
cours de formation*, avec le même `bar_time` (open de la bougie) répété des
centaines de fois. Résultat : `age_ms = now - bar_time` croît tout au long
de la vie de la bougie (jusqu'à 900 000 ms) et dépasse le seuil de 95 000 ms
dès les ~95 premières secondes de chaque bougie de 15 min → **la majorité
des pushes intra-bougie sont mécaniquement marqués stale**, alors que la
donnée est en réalité la plus fraîche disponible (le "live tick" de la
bougie en formation). C'est un **problème de sémantique du seuil**, pas une
donnée périmée au sens propre.

**M5** : la répartition horaire révèle un **changement de régime net** le
2026-07-07 vers 15h-16h UTC :
- Avant 15h : ~1700-2250 push/heure (même comportement que M15 ci-dessus,
  continu/haute fréquence — cause probable de l'essentiel du 70% de stale
  mesuré globalement).
- À partir de 16h (2026-07-07T16:00 UTC) jusqu'à aujourd'hui : **exactement
  12 push/heure**, soit 1 par clôture de bougie M5 (60min/5min=12) — bascule
  vers un comportement candle-close pur identique à H1/H4, avec 0% stale
  dans cette fenêtre récente.

Cette transition n'est **pas expliquée par le code de ce dépôt** (aucune
logique de filtrage/rate-limit côté `capture_server.py`). Elle indique un
changement côté EA/terminal MT4 (redémarrage de l'EA sur le graphique M5,
fermeture/réouverture du graphique, crash silencieux repris en mode dégradé,
ou changement de configuration) survenu vers 2026-07-07T15:30-16:00 UTC.
**Hors périmètre Python** — à investiguer côté terminal MT4 (logs EA, pas de
log applicable ici).

### 3.3 M1 — cadence stable 1/min, staleness structurelle

M1 est constant à ~60 push/heure sur toute la période (1 par minute), sans
transition. C'est cohérent avec 1 push par bougie M1 clôturée — **pas** avec
le mode `tick_velocity` continu documenté dans `FORMAT_FORCES.md` (qui
suppose un push quasi instantané à chaque tick, `age_ms` de l'ordre de
quelques centaines de ms). Avec un push unique par minute et un seuil de
5000 ms, toute donnée poussée plus de 5s après l'ouverture de la bougie M1
est mécaniquement stale — ce qui couvre ~55 des 60 secondes de la bougie.
**Même mécanisme de fond que M15** (seuil calibré pour un push quasi-continu
à faible latence, alors que l'EA envoie un point unique par bougie avec
`bar_time` = ouverture de bougie).

### 3.4 Réponse à "même cause ?" (M1 88% / M5 70%)

**Partiellement la même cause, deux manifestations différentes** :
- Le mécanisme sous-jacent commun est un **décalage entre la sémantique de
  `STALE_THRESHOLDS_MS`** (calibré comme si `age_ms` mesurait une latence de
  transmission quasi nulle) **et la réalité de `bar_time`** (souvent
  l'horodatage d'ouverture de la bougie, pas l'horodatage du dernier tick
  réellement traité) — présent sur M1, M5 (avant 16h) et M15.
- Mais la **cause immédiate diffère** : M1 est stale parce que son push
  unique par minute arrive presque toujours après le seuil de 5s ; M5 est
  stale à 70% en moyenne parce que la mesure agrège une période haute
  fréquence (comportement M15-like, très staleness) et une période
  candle-close pure récente (0% stale) — **pas une cause unique et stable
  dans le temps**, contrairement à M1.

## 4. Cause racine (synthèse)

1. **Aucun bug de fréquence côté Python** — confirmé par lecture complète de
   `capture_server.py` (aucune fonction de throttling/scheduling) et
   recherche exhaustive dans `scripts/*.py` et `core/v9/*.py`. La cadence de
   push par timeframe est fixée à 100% côté EA MT4, hors dépôt.
2. Le comportement H4 (candle-close pur, 6/jour) est **conforme à la
   documentation** `FORMAT_FORCES.md`, mais **insuffisant** pour une lecture
   multi-TF intra-bougie — écart entre ce que le format documente
   ("candle-close = 1 point/clôture") et ce dont le pipeline a besoin
   (granularité intra-bougie, comme M15 l'offre déjà).
3. Le staleness M1/M5/M15 provient d'un **décalage sémantique** entre
   `STALE_THRESHOLDS_MS` et la nature de `bar_time` en mode haute-fréquence —
   un problème de calibration (`core/v9/config.py`), **hors périmètre de ce
   chantier** (fichier explicitement protégé).
4. Le comportement M5 a **changé dans le temps** (bascule 2026-07-07
   ~16h UTC) — signal fort d'un événement côté EA/terminal MT4 à
   investiguer côté infrastructure de trading, pas côté ce dépôt.

## 5. Proposition de backfill H4 (documentation seulement, non implémenté)

Objectif : donner à H4 une granularité intra-bougie comparable à M15, sans
toucher `config.py`/`orchestrator.py`/`principle_engine.py` ni au code EA.

**Option retenue à évaluer** : script additif `scripts/v9_h4_backfill.py`
(nouveau fichier, aucune modification de l'existant) qui :
1. Lit en continu les snapshots M15 déjà capturés (haute fréquence, déjà en
   base) pour `symbol=GBPUSD`.
2. Pour chaque snapshot M15 dont le `bar_time` tombe dans une bougie H4 non
   encore couverte par un point synthétique récent (ex. throttle à 1 point
   toutes les ~20-30 min), insère une ligne `forces_snapshots` avec
   `timeframe='H4'`, les 8 forces recopiées du snapshot M15 source, et
   `bar_time` = ouverture de la bougie H4 englobante (pas celle du M15).
3. Marque ces lignes avec un flag distinctif (ex. `source` ou un champ
   dédié si le schéma le permet) pour les distinguer des vrais points de
   clôture EA — **à valider avec l'équipe avant implémentation**, car cela
   modifierait la sémantique de `forces_snapshots` (mélange données EA
   natives / dérivées).

**Alternative (recommandée à plus long terme, hors dépôt)** : côté EA MT4,
aligner le comportement de push H4 (et H1) sur celui de M15 (push à chaque
tick ou à intervalle régulier, pas uniquement à la clôture). Résout le
problème à la source, sans duplication de données ni ambiguïté de
provenance. Nécessite un accès au code `ea/V9_Sonde_TF.mq4` (absent de ce
dépôt).

Ce chantier ne tranche pas entre les deux options — **décision produit à
prendre par l'utilisateur**, la proposition ci-dessus reste au stade
documentaire conformément à la contrainte de session (0 modification de
script si comportement normal côté EA).

## 6. Conclusion

Aucune modification de code n'a été effectuée pour ce chantier — diagnostic
uniquement, conformément à la branche "comportement normal / documenter +
proposer backfill" de la consigne. `pytest` non ré-exécuté pour ce chantier
(aucun fichier de code modifié) ; le run global de la session (859 tests
verts) reste la référence courante après les modifications YAML du
chantier 1.
