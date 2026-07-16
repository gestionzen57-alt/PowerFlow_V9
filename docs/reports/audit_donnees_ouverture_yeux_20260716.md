# Audit data-layer — « Ouverture des yeux » (2026-07-16)

> Mission : nettoyer, brancher, ouvrir les sens du système (vélocité, volume,
> multi-paires) et neutraliser le biais NZD. Cœur cognitif sain (1497 tests).
> Ce rapport corrige plusieurs prémisses du brief à la lumière des données réelles.

## Résumé exécutif

| Sens | Prémisse brief | Réalité mesurée | Action livrée |
|---|---|---|---|
| Vélocité | « morte, 0 dans 99% » | **Vivante à 91% sur M1** (tick). Nulle sur candle car la force est **constante intra-bar** (99,2% des M15), pas un bug de calcul. | Fix robustesse `forces_reader` (fallback capture-time) + constat honnête |
| Volume | « absent » | **Capturé à 100%** (`tick_volume`), mais lu par **ZÉRO principe** | Branché dans le contexte + principe SHADOW `VOLUME_CONFIRMATION` |
| NZD | « historique biaisé 99,8% » | **Confirmé** : 655 724/657 284 (99,76%) — artefact **vote-devise pré-fix**, encore ~97%/jour | Vue filtrée non-destructive + script 2 options |
| Multi-paires | « code prêt, EA pas attaché » | **Confirmé** : seul GBPUSD capturé (+1 EURUSD) | Étude corrélation → recommandation 1 paire |

---

## 1. Vélocité — pas morte, myope sur les TF candle

**Mesure (taux de `vitesse` non-nulle par timeframe, GBPUSD) :**

| TF | Snapshots | vitesse ≠ 0 | Taux |
|---|---|---|---|
| M1 (tick) | 6 426 | 5 788 | **90,1%** |
| M30 | 413 | 390 | 94,4% |
| H1 | 310 | 296 | 95,5% |
| H4 | 228 | 213 | 93,4% |
| M5 | 31 729 | 1 588 | 5,0% |
| M15 | 78 229 | 600 | **0,8%** |

Le « 1% » global vient de la **domination du compte de lignes par M15** (78k lignes, ré-échantillonnées à chaque tick sur bougie ouverte).

**Cause racine (diagnostic sur 78 228 paires M15 consécutives) :**
- `bar_time` identique : **99,2%** (ré-échantillonnage intra-bar)
- **`force_gbp` identique : 99,2%** ← le vrai verrou
- capture identique : 3,2%

La force de devise (SDI) **ne change pas** entre deux ré-échantillonnages de la même
bougie ouverte. Quand la force est constante, `vitesse = 0` est **correct**, pas buggé.
La vraie vélocité cinématique vit sur le **tick M1** (91%), qui utilise l'horloge de
capture réelle.

**Livré :** `core/v9/forces_reader.py` — quand `bar_time` n'a pas avancé (`delta_t=0`),
fallback sur le delta de capture réel au lieu de forcer `vitesse=0`. Correctif de
**robustesse** (couvre le cas rare « même bougie, force qui bouge ») + régression testée
(les bougies fermées de replay gardent la base `bar_time`). Sur l'historique existant
l'impact est nul (la force n'y bouge quasiment jamais intra-bar) — c'est attendu.

**KPI brief « >50% non-null » : non atteignable par un patch `forces_reader`** — il est
borné par le modèle de données (force constante intra-bar). La vélocité fiable EST déjà
là, sur M1.

**Next-step recommandé (chantier séparé, calibration marché-ouvert) :** alimenter
`velocite_moyenne` (cinématique, `scene_builder._compute_cinematics`) depuis la dernière
vélocité **tick M1** du symbole quand le snapshot candle est à 0. Non fait ici :
mélangerait l'échelle tick dans la calibration de `VELOCITY_CLIMAX_GUARD` posée le 16/07
(risque de mis-fire) → nécessite sa propre passe de calibration.

## 2. Volume — capturé à 100%, longtemps aveugle

`tick_volume` est rempli sur **100%** des snapshots GBPUSD (toutes TF) depuis l'origine.
Pourtant `principle_engine.py` ne le lisait **jamais** (0 occurrence) : le volume était
invisible pour la couche cognitive.

**Livré :**
- `core/v9/principle_engine.py` (`_load_shared_context`) — dérive un **régime de volume
  relatif** : `volume_ratio` = volume courant / médiane des 100 derniers snapshots
  (même symbole+TF), et `volume_regime` ∈ {HIGH ≥1.5×, NORMAL, LOW ≤0.5×}. Additif R2,
  défensif R6 (None si historique <20 ou volume absent → aucun principe gaté).
- `core/v9/principles/VOLUME_CONFIRMATION.yaml` — **1er principe consommateur de volume**
  (SHADOW). Déclenche sur `volume_regime = HIGH` : distingue une cassure appuyée par la
  participation d'un piège à faible volume. SHADOW par défaut (absent de
  `PRINCIPLE_ACTIVE_IDS`) → observation avant promotion (R25').
- Tests : `test_volume_regime_propagated_to_context`, `test_volume_regime_absent_when_insufficient_history`.

**Limite connue :** le volume intra-bougie est bruité (le `tick_volume` d'une bougie
ouverte croît). Le régime HIGH capte surtout les pics ; le raffinement (volume par bougie
fermée / VWAP) est un chantier séparé.

## 3. NZD — biais confirmé, artefact vote-devise pré-fix

`principle_evaluations` : **655 724 / 657 284 NZD (99,76%)** alors que 100% des snapshots
sont GBPUSD. Les principes cœur (`GRAMMAR_REGIME`, `GRAVITY_RESPRING_NODE`,
`COALITION_NODE`…, tous `currencies: ALL`) tirent ~63-68k fois **sur NZD seul**.

**Ligne temporelle (NZD vs autres devises) :**

| Jour | NZD | Autres |
|---|---|---|
| ≤ 2026-07-14 | 100% | 0 |
| 2026-07-15 (fix) | 46 158 | 726 |
| 2026-07-16 | 30 736 | 855 |

Le fix « vote NZD » du 15/07 fait apparaître les autres devises mais **NZD reste ~97%** :
le vote-devise n'est que **partiellement** corrigé. C'est un **gap résiduel séparé** (dans
la logique d'évaluation), remonté ici mais **non modifié** (R2 : ne pas casser).

**Livré :** `scripts/purge_nzd_20260716.sql` + vue **non-destructive** créée sur la DB
live : `v_principle_evaluations_clean` (exclut NZD). Résultat : **1 587 lignes propres**
sur 657 886 (0,24%).

> ⚠️ **Constat critique :** le dataset cross-devise propre (1 587 lignes) est **lui aussi
> trop maigre** pour un backtest robuste. La purge destructive n'apporterait qu'un
> allègement disque. Le vrai levier est de **finir le fix vote-devise** pour accumuler un
> historique multi-devises réel.

**DÉCISION SØN requise :** Option A (vue, déjà en place, réversible) vs Option B (DELETE
destructif + VACUUM, backup MD5 obligatoire, capture à arrêter). Détail dans le script.
Les `decisions` (67 811 GBPUSD, WR paper 85,6%) ne sont **pas** concernées.

## 4. Audit coalitions

Sur 67 858 scènes, **8,7%** (5 903) portent une coalition détectée (paires de devises
alignées). WR par coalition joint via `decisions.is_win`.

**Top coalitions (fréquence) :** AUD+NZD (680), CAD+USD (504), JPY+USD (474), CHF+EUR
(445), EUR+GBP (371). Leaders répartis uniformément (NZD 1408 … GBP 1134 — pas de leader
dominant).

> ⚠️ **Échantillon résolu par coalition insuffisant** (max ~14 trades résolus, **aucune
> coalition n'atteint 30 résolus**). Le WR-par-coalition et l'identification de coalitions
> « toxiques » **ne sont pas encore statistiquement exploitables**. À réauditer après
> accumulation de trades résolus (59 408 décisions restent non résolues).

## 5. Multi-paires

Voir `docs/reports/etude_multipaires_20260716.md`. Résumé : seul GBPUSD capturé →
recommandation basée sur la **corrélation des 8 forces de devises** (empirique, 78 230
snapshots M15). Reco : **activer USDJPY en premier** (axe JPY le plus décorrélé, pas de
jambe GBP partagée avec GBPUSD).

## Doctrine

- **R2** additif (nouveaux champs/fichier, aucun principe existant modifié)
- **R6** défensif (try/except, dégradation gracieuse, aucun gate sur donnée absente)
- **R7** tests verts (1497 → 1501 passed +1 skip, +4 : 2 vélocité + 2 volume)
- **R8** backup MD5 des fichiers cœur avant modification
- **R18** zéro LLM (heuristiques pures)
- **R25'** `VOLUME_CONFIRMATION` SHADOW par défaut, promotion = motion CEO séparée
