# POINT GÉNÉRAL — Tableau de bord du système institutionnel V10 (13/08 21:00 UTC)

> **Mandat CEO (13/08, plein potentiel)** : *"la lecture du marché doit être
> mieux comprise par le système... tu as plein pouvoir."*
>
> Ce document est le **tableau de bord** de la transition du système
> mécanique (delta brut) vers le système institutionnel (lecture de marché
> de Søn). Il liste ce qui est fait, ce qui est branché, ce qui reste à
> injecter, et la vision plein potentiel.

---

## 1. ÉTAT SYSTÈME (vérifié 13/08 21:00)

| Élément | État |
|---|---|
| Tests V10 | ✅ **1380/1380 verts** |
| Commits aujourd'hui | **14** |
| Branche | `feat/zcode-night` |
| HEAD | `5d3ff9a` |
| Edge OVERLAP | ✅ Optimisé (delta≥25, TP=2x/SL=1x), gate PROMOTE, CEO gate GRANTED |
| Cron actif | `v10-edge-overlap-shadow` (*/20 lun-ven) |
| R10 | ✅ Zéro ordre réel (broker non connecté) |

---

## 2. LES 7 PILIERS DE LA LECTURE INSTITUTIONNELLE (ce que Søn a donné)

### Les 7 piliers (extraction complète du brainstorming)

| Pilier | Nom | Source | Document |
|---|---|---|---|
| **1** | CINÉMATIQUE (la courbe avant la valeur) | Søn 12/08 | `DOCTRINE_LECTURE_GBPUSD.md` |
| **2** | IMBRICATION TEMPORELLE (H4 juge, H1 timing, M15 exécution) | Søn 13/08 | `BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md` |
| **3** | COALITION MULTIDEVISE (leader/follower, rupture risk-on) | Søn 13/08 | `BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md` |
| **4** | PERSONNALITÉ DE DEVISE (tempo, véracité, comportement par devise) | Søn 13/08 | `BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` |
| **5** | FRACTALITÉ TEMPORELLE (1min → H4, TF de lisibilité par devise) | Søn 13/08 | `BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` |
| **6** | CYCLES FATMAN (vague Elliott adaptée : naissance/expansion/maturité/épuisement) | Søn 13/08 | `BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` |
| **7** | FORCES PAR TIMEFRAME (échelles propres, pas d'agrégation, croisement + zones extrêmes + double test de rejet + propagation/répulsion) | Søn 13/08 | `LECTURE_FORCES_PAR_TIMEFRAME.md` + `LECTURE_STRATEGIE_CHANGEMENT_PHASE.md` |

---

## 3. CE QUI EST BRANCHÉ DANS LE SYSTÈME (codé et actif)

| Module | Pilier | Ce qu'il fait | Statut |
|---|---|---|---|
| `core/v10/v10_cinematics.py` | **1** | Pics/creux, pente, accélération, divergence force/prix, exhaustion | ✅ Branché dans edge + daily learning + filtre |
| `core/v10/v10_confluence_tf.py` | **2** | Score [0-4] M5+M15+M30+H1, sizing modulé 0.5→1.0 | ✅ Branché dans edge (scan + replay) |
| `core/v10/v10_edge_overlap_filter.py` | **2** | Tag edge_overlap/execution_eligible/exploration_only + cinématique | ✅ Branché dans pipeline live |
| `core/v10/v10_decision_pipeline.py` | Sécurité | Circuit breaker DD + news guard + correlation guard | ✅ Branché (audit 13/08) |
| `scripts/v10_shadow_edge_overlap.py` | **1+2** | Runner edge avec cinématique + confluence + suivi trades shadow | ✅ Actif (cron */20) |
| `scripts/v10_daily_learning.py` | **1** | Apprentissage quotidien avec cinématique | ✅ Actif (manuel, cron à créer) |
| `scripts/v10_edge_overlap_gate.py` | R10 | Gate R10 + CEO gate → executable | ✅ Actif |
| `scripts/v10_edge_scan_sessions.py` | Exploration | Scan multi-fenêtres (Asie/London/Overlap/NY) | ✅ Créé |
| `scripts/v10_force_cinematics.py` | **1** | Lecture courbe GBPUSD (H4/H1) | ✅ Créé (GBPUSD-only) |

---

## 4. CE QUI EST DOCUMENTÉ MAIS PAS ENCORE CODÉ (règles extraites, à injecter)

### Pilier 3 — COALITION MULTIDEVISE (0% codé)

| Règle | Description | Statut |
|---|---|---|
| Leader/follower | Distinguer "GBP mène" (fort en absolu) vs "USD traîne" (faible en absolu) | ⬜ À coder |
| Rupture de coalition | GBP casse la coalition risk-on (AUD continue, GBP retombe) = signal | ⬜ À coder |
| Safe haven | JPY/CHF montent → risk-off → GBPUSD chute (séquence JPY→USD→GBP) | ⬜ À coder |
| Cross-pair | EURGBP en divergence avec GBPUSD = confirmation externe | ⬜ À coder |

### Pilier 4 — PERSONNALITÉ DE DEVISE (0% codé)

| Règle | Description | Statut |
|---|---|---|
| Tempo par devise | Calibrage par devise (seuil, échelle, vitesse de réaction) | ⬜ À coder |
| Véracité par devise | Score de fiabilité (corrélation force→mouvement réel) | ⬜ À coder |
| Comportement de session | Fenêtres PAR DEVISE (AUDUSD en Asie, GBPUSD en Overlap) | ⬜ À coder |

### Pilier 5 — FRACTALITÉ TEMPORELLE (partiel)

| Règle | Description | Statut |
|---|---|---|
| Couche 1min | Timing d'entrée précis (scalp GBPUSD) | ⬜ À coder |
| TF de lisibilité par devise | Paramètre TF par devise (GBPUSD→1min, EURUSD→5min...) | ⬜ À coder |
| Score de confluence M5/M15/M30/H1 | Score [0-4], sizing modulé | ✅ Codé (Pilier 2) |
| **1min dans la confluence** | Ajouter le 1min au score | ⬜ À coder |

### Pilier 6 — CYCLES FATMAN (0% codé)

| Règle | Description | Statut |
|---|---|---|
| Détecteur de vagues | Compter les impulsions/corrections sur la courbe de force | ⬜ À coder |
| Phases du cycle | Naissance → expansion → maturité → épuisement | ⬜ À coder |
| Calibrage par devise | Le cycle est propre à chaque devise | ⬜ À coder |

### Pilier 7 — FORCES PAR TIMEFRAME (0% codé — le plus récent)

| Règle | Description | Statut |
|---|---|---|
| R1 — Calibration par TF | Zones (basse/moyenne/haute/extrême) par percentile, par TF | ⬜ À coder |
| R2 — Lecture par TF | Lire la valeur dans les zones de SON TF | ⬜ À coder |
| R3 — Croisement M5 + zones extrêmes | Croisement M5 significatif si M15/M30 dans zones extrêmes | ⬜ À coder |
| R4 — Double test de rejet de prix | Confirmation par 2 tests de niveau (touche + rebond ×2) | ⬜ À coder |
| R5 — Propagation vs Répulsion | Après croisement : les TF suivent (propagation) ou s'écartent (répulsion) | ⬜ À coder |

### Pilier 6+7 — CHANGEMENT DE PHASE (0% codé)

| Règle | Description | Statut |
|---|---|---|
| Emboîtement H1→H4 | H1 croise avant H4 → anticipation | ⬜ À coder |
| Croisement H4 = changement de phase | GBP haut→bas + USD bas→haut = régime change | ⬜ À coder |
| Trader la nouvelle phase | Vendre extrêmes hauts GBP, acheter extrêmes bas USD | ⬜ À coder |
| Antagonisme = retournement | 2 forces extrêmes simultanées = point de retournement | ⬜ À coder |
| Confirmation TF < | Croisement M15/M5/1min valide le retournement | ⬜ À coder |

---

## 5. LA VISION PLEIN POTENTIEL (reformulation pour le système institutionnel)

### Le système aujourd'hui (mécanique)

```
EDGE OVERLAP (M15 seul)
  delta_forces ≥ 25 → BUY/SELL
  + cinématique (exhaustion/divergence) → filtre BLOCK
  + confluence M5/M15/M30/H1 → sizing modulé
  WR 62.8% (replay), 36.7% (13/08 drift)
```

### Le système institutionnel (plein potentiel)

```
LECTURE DE MARCHÉ (7 piliers intégrés)

  Pilier 7 — FORCES PAR TF
    Chaque TF lu dans son échelle (zones par percentile)
    Croisement M5 + zones extrêmes M15/M30 = retournement possible
    Double test de rejet de prix = confirmation
    Propagation vs Répulsion = trader la nouvelle phase ou le retour

  Pilier 6 — CYCLES FATMAN
    Détecteur de phases : naissance → expansion → maturité → épuisement
    Entrer à la naissance, sortir à la maturité, bloquer à l'épuisement

  Pilier 4 — PERSONNALITÉ DE DEVISE
    Chaque devise a son profil (tempo, véracité, TF de lisibilité)
    GBPUSD → 1min (lisible), EURUSD → 5min, AUDUSD → 15min
    Seuils et fenêtres calibrés PAR DEVISE

  Pilier 5 — FRACTALITÉ TEMPORELLE
    1min → scalp (timing d'entrée précis)
    5min → confirmation
    15min → exécution
    30min → confirmation
    H1 → timing
    H4 → juge (biais directionnel)

  Pilier 1 — CINÉMATIQUE
    La courbe avant la valeur
    Pics → exhaustion, divergence force/prix → piège
    (déjà branché ✅)

  Pilier 2 — IMBRICATION TF
    Score de confluence [0-4], sizing modulé
    (déjà branché ✅)

  Pilier 3 — COALITION MULTIDEVISE
    Leader/follower, rupture risk-on, safe haven JPY/CHF
    Cross-pair confirmation (EURGBP vs GBPUSD)

DÉCISION FINALE :
  Entrée = croisement M5 + zones extrêmes M15/M30 + double test de rejet
    + phase de cycle (naissance/expansion) + confluence TF (sizing)
    + coalition alignée + personnalité de devise respectée
  Sortie = épuisement (cinématique) OU répulsion (forces s'écartent)
    OU propagation complète (tenir) OU antagonisme (retournement)
```

### L'architecture cible

```
COUCHE 0 — MARCHÉ (DB forces_snapshots, chaque TF son échelle)
   ↓
COUCHE 1 — LECTURE PAR TF (Pilier 7)
   Calibration par percentile → zones par TF
   Croisements/décroisements/répulsions par TF
   ↓
COUCHE 2 — CASCADE TEMPORELLE (Pilier 5+2)
   M5 croise → M15 confirme → M30 confirme → H1 juge
   Score de confluence → sizing modulé
   ↓
COUCHE 3 — CYCLES FATMAN (Pilier 6)
   Phase du cycle : naissance/expansion/maturité/épuisement
   Entrer à la naissance, sortir à la maturité
   ↓
COUCHE 4 — PERSONNALITÉ DE DEVISE (Pilier 4)
   Profil par devise (tempo, véracité, TF de lisibilité)
   Calibrage des seuils et fenêtres
   ↓
COUCHE 5 — COALITION MULTIDEVISE (Pilier 3)
   Leader/follower, rupture risk-on, safe haven
   Cross-pair confirmation
   ↓
COUCHE 6 — CINÉMATIQUE (Pilier 1) ✅
   Pics, divergence, exhaustion
   ↓
COUCHE 7 — DÉCISION + GARDE-FOUS ✅
   Edge OVERLAP + circuit breaker + news guard + correlation guard
   R10 : DD max 10%, position max 2%, levier max 5x
```

---

## 6. CE QUI RESTE À FAIRE (par ordre de priorité)

### Priorité 1 — Pilier 7 (forces par TF) — le plus récent, le plus fondamental

Le système ne peut pas lire correctement tant qu'il ne calibre pas les
zones par TF. C'est le prérequis pour TOUS les autres piliers.

- [ ] **R1** — Calibration par TF (percentile par TF sur l'historique)
- [ ] **R2** — Lecture par TF (valeur dans les zones de SON TF)
- [ ] **R3** — Croisement M5 + zones extrêmes M15/M30
- [ ] **R4** — Double test de rejet de prix
- [ ] **R5** — Propagation vs Répulsion

### Priorité 2 — Pilier 6 (cycles Fatman)

Le détecteur de phases (naissance/expansion/maturité/épuisement) est le
cœur de la lecture de Søn. La cinématique actuelle (exhaustion) est le
début — il manque les 3 autres phases.

- [ ] Détecteur de vagues (impulsion/correction sur la courbe de force)
- [ ] Phases du cycle (naissance/expansion/maturité/épuisement)
- [ ] Calibrage par devise

### Priorité 3 — Pilier 4 (personnalité de devise)

Chaque devise a son profil. Le système ne peut pas appliquer le même
seuil à GBP, EUR, AUD. C'est la calibration par devise.

- [ ] Tempo par devise
- [ ] Véracité par devise
- [ ] Comportement de session par devise

### Priorité 4 — Pilier 3 (coalition multidevise)

Le contexte global (qui mène, qui suit, qui s'oppose). C'est la dernière
couche de confirmation.

- [ ] Leader/follower
- [ ] Rupture de coalition
- [ ] Safe haven (JPY/CHF → risk-off)
- [ ] Cross-pair confirmation

### Priorité 5 — Pilier 5 (fractalité 1min)

Le 1min pour le scalp GBPUSD. C'est le laboratoire de Søn.

- [ ] Couche 1min (timing d'entrée)
- [ ] TF de lisibilité par devise

### Infrastructure (en parallèle)

- [ ] Cron `v10-daily-learning` (à créer en nouvelle session)
- [ ] Cron `v10-gbpusd-master-alert` (à créer en nouvelle session)
- [ ] Cron `v10-gbpusd-alert` (à créer en nouvelle session)
- [ ] Broker IBKR (TWS/IB Gateway à lancer pour exécution réelle)

---

## 7. LA DOCTRINE POUR L'INJECTION (principe Søn)

> *"Chaque jour est unique. Il n'y a pas de loi, mais une façon d'exploiter
> et comprendre la réalité du marché."*

Le système ne doit PAS chercher une formule unique. Il doit :
1. **Lire** chaque TF dans son échelle (Pilier 7)
2. **Comprendre** la phase du cycle (Pilier 6)
3. **Respecter** la personnalité de chaque devise (Pilier 4)
4. **Confirmer** par la cascade temporelle (Pilier 5+2)
5. **Contextualiser** par la coalition multidevise (Pilier 3)
6. **Filtrer** par la cinématique (Pilier 1)
7. **Protéger** par R10 (DD max 10%, kill switch)

Chaque règle est testée (benchmark 3 jours) avant adoption. Les règles
qui détériorent sont rejetées (ex: momentum mort en BLOCK). Les règles
qui améliorent sont adoptées (ex: cinématique, confluence).

---

## 8. DOCUMENTS PIVOTS (à lire au démarrage session)

| Document | Rôle |
|---|---|
| `docs/V10/METHODOLOGIE_INJECTION.md` | **LE CONTRAT DE TRAVAIL multi-IA** — à lire EN PREMIER |
| `docs/V10/POINT_GENERAL_INSTITUTIONNEL.md` | **Ce fichier** — tableau de bord |
| `docs/V10/LECTURE_FORCES_PAR_TIMEFRAME.md` | Pilier 7 — le plus récent |
| `docs/V10/LECTURE_STRATEGIE_CHANGEMENT_PHASE.md` | Pilier 6+7 — changement de phase |
| `docs/V10/BRAINSTORMING_FATMAN_DEVISE_FRACTAL.md` | Pilier 4+5 — personnalité + fractalité |
| `docs/V10/BRAINSTORMING_GBPUSD_MATRICE_INSTITUTIONNEL.md` | Pilier 1+2+3 — matrice initiale |
| `docs/V10/DOCTRINE_LECTURE_GBPUSD.md` | Les 7 principes de lecture |
| `docs/V10/DECISION_OVERLAP_VS_SCAN_LARGE.md` | Option C (edge ciblé) |

---

## 9. MÉTHODOLOGIE D'INJECTION (mise à jour 13/08 21:30 — validée Søn)

### La loi

> **Le brainstorming de Søn est la source de vérité. L'implémentation suit,
> ne précède pas.**
>
> - On ne code pas ce qu'on ne comprend pas complètement
> - On ne teste pas ce qu'on a mal interprété
> - On attend que la lecture de Søn soit COMPLÈTE avant d'injecter
> - On injecte UNIQUEMENT les piliers stables et validés

### Les 3 pistes parallèles

```
PISTE A — BRAINSTORMING (Søn ↔ IA)
   Søn donne sa lecture → IA reformule, documente, commit — NE CODE RIEN

PISTE B — IMPLÉMENTATION (seulement les piliers STABLES)
   P1 Cinématique ✅ | P2 Confluence ✅ | P3-P7 : EN ATTENTE du brainstorming

PISTE C — TEST (file d'attente)
   Chaque règle = benchmark 3 jours AVANT adoption
   Les règles qui détériorent = REJETÉES (ex: momentum mort BLOCK)
```

### Ce qu'on peut faire SANS biais (en parallèle)

- **Calibrer les zones par TF (percentile)** — calcul statistique pur ✅ FAIT
  (`core/v10/v10_forces_par_tf.py` — calibrer_zones_tf)
- **Préparer les squelettes de modules P3-P7** ✅ FAIT
  (`v10_personality_devise.py`, `v10_cycles_fatman.py`,
  `v10_coalition_devises.py`, `v10_forces_par_tf.py`, `v10_fractalite_tf.py`)
- **Scanner SHADOW continu** (cron */20) — accumulation de données
- **Daily learning** — track record forward

### Les 20 règles en attente (file d'attente d'injection)

Chaque règle passe par : brainstorming (Søn) → validation → code → test
(benchmark 3 jours) → adoption ou rejet. Voir
`docs/V10/METHODOLOGIE_INJECTION.md` §7 pour la liste complète.

### Travail parallèle (Hermes, Perplexity — git seul)

- Lire METHODOLOGIE_INJECTION.md en premier
- Préparer les squelettes (déjà faits) / calibrer les zones (fait)
- NE PAS inventer de règles de lecture — la source de vérité est Søn
- Commits atomiques + DECISIONS_LOG à jour

---

> **Le système aujourd'hui** : un edge mécanique (delta≥25) avec cinématique
> et confluence — WR 62.8% en replay, 36.7% le 13/08 (drift).
>
> **Le système cible** : un système institutionnel qui lit le marché comme
> Søn — chaque TF dans son échelle, les phases du cycle, la personnalité
> de devise, la cascade temporelle, la coalition multidevise.
>
> **Le chemin** : 5 priorités, 20 règles à injecter, testées une par une
> (benchmark 3 jours), adoptées si elles améliorent, rejetées si elles
> détériorent. Pas de loi fixe — juste l'extraction honnête de ta logique.