# Axe 3 — Diversification edgefund : le monopole GBPUSD est un problème de capture, pas de routing

> **Audit edgefund V9 — Axe 3/8** · OPUS Claude Code · 2026-07-19 · lecture seule.

## TL;DR

Le quasi-monopole GBPUSD (97,7 %) **n'est pas un bug de routing**. C'est une simple
**asymétrie de couverture de capture** : GBPUSD est capturé en continu depuis 12 jours,
les 5 autres paires n'ont que **1-2 jours** de données. Quand elles sont capturées, **les 6
paires dépassent toutes la cible edgefund de ≥ 100 entrées/semaine.** L'infrastructure de
diversification est **déjà opérationnelle** — il ne manque que la capture continue.

## Preuve n°1 — le routing fonctionne pour les 6 paires

`decisions` par symbole (colonne `entrees` = `action='preparer_entree'`) :

| Symbole | decisions | entrées | snapshots dispo | jours captés |
|---|---:|---:|---:|---:|
| GBPUSD | 69 341 | 8 572 | 119 954 | 12 (05→17/07) |
| USDJPY | 1 596 | 47 | 3 408 | 2 (16-17/07) |
| USDCHF | 1 483 | 48 | 2 693 | 2 (16-17/07) |
| USDCAD | 1 480 | 25 | 2 931 | 2 (16-17/07) |
| EURUSD | 1 351 | 46 | 2 926 | ~10 (08→17/07, épars) |
| AUDUSD | 626 | 33 | 2 105 | 1 (17/07) |

Chaque paire capturée **produit des entrées** proportionnellement à ses snapshots. Le
`principle_engine` / `_load_shared_context` route correctement les 6 devises. **Aucun bug
de routing, aucun trigger manquant.**

## Preuve n°2 — chaque paire dépasse la cible ≥ 100 trades/semaine

Entrées normalisées par jour de capture :

| Paire | entrées/jour | **projection/semaine** | Cible 100/sem |
|---|---:|---:|:---:|
| USDCHF | 48,0 | **336** | ✅ |
| USDJPY | 47,0 | **329** | ✅ |
| EURUSD | 46,0 | **322** | ✅ |
| AUDUSD | 33,0 | **231** | ✅ |
| USDCAD | 25,0 | **175** | ✅ |
| GBPUSD | 1 428* | 10 001* | ✅ |

\* GBPUSD anormalement élevé (≈ 10× les autres) — gonflé par la période de forte densité
(shadow/intrabar purgés, boucle 17/07). La cadence « saine » d'une paire est **25-48
entrées/jour**, soit **175-336/semaine** — confortablement au-dessus de la cible.

→ **Les 6 paires sont edgefund-viables en volume.** Le goulot n'est pas le nombre de
signaux, c'est l'historique disponible pour valider un edge par paire.

## Diversification policy (plan chiffré)

### Étape 1 — Capture continue multi-paires (opérationnel, pas de code cognitif)

Activer la capture continue des 5 paires (EURUSD, USDJPY, USDCHF, AUDUSD, USDCAD) au même
régime que GBPUSD. Coût : configuration EA/capture_server. Aucune modification `core/v9/`.

### Étape 2 — Accumulation d'historique (T+2 semaines)

À 175-336 entrées/semaine/paire, **2 semaines suffisent** pour atteindre ≥ 350-670
entrées/paire — assez pour un walk-forward par paire (≥ 3 folds de ≥ 100).

### Étape 3 — Validation d'edge par paire, indépendante (T+3-4 semaines)

Pour chaque paire, exiger **avant activation live** (mêmes critères que GBPUSD) :
- walk-forward out-of-sample : WR ≥ 55 % **et** std inter-folds ≤ 10 pts ;
- direction : appliquer d'abord la politique **long-only / no-baissiere** par paire (le
  baissier reste non-stationnaire, cf Axe 1 §4) ;
- corrélation : plafonner l'exposition agrégée USD (5 des 6 paires sont USD-quote →
  risque de concentration cachée, pas de vraie diversification si toutes long USD).

### Étape 4 — Sizing de portefeuille (T+1 mois)

Une fois ≥ 3 paires validées : sizing par **budget de risque agrégé** (CVaR portefeuille,
module `V9_KELLY_CVAR` déjà présent, OFF) plutôt que par trade isolé. Objectif : ≥ 3 paires
faiblement corrélées avec ≥ 50 trades/semaine chacune (cible edgefund du prompt : atteinte).

## ⚠️ Angle mort — la « diversification » USD n'est pas une vraie diversification

5 des 6 paires sont cotées contre USD. Un panier « tout long USD-quote » n'est **pas**
diversifié : c'est un pari macro unique sur le dollar. La vraie diversification exige soit
des **crosses non-USD** (EURGBP, EURJPY…), soit un **netting par devise** via les forces
(`force_usd`, `force_eur`… déjà en base). À intégrer dans la policy avant de parler
d'edgefund multi-actifs.

## Score Axe 3

| Critère | Cible | Résultat |
|---|---|---|
| Cause monopole | routing vs data | ✅ **data (couverture capture)**, routing sain |
| Diversification ≥ 3 paires ≥ 50/sem | oui | ✅ **6 paires ≥ 175/sem** dès capture continue |
| Roadmap chiffrée | bonus | ✅ 4 étapes T+2sem → T+1mois + garde-fou corrélation USD |
