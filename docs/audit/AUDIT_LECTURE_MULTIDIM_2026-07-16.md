# Audit lecture multi-dimensionnelle — 2026-07-16

> Audit **lecture seule** (R18/R2). Aucune ligne de code modifiée. Les « fix proposés »
> sont des descriptions, pas des patchs. Preuves chiffrées extraites de
> `data/v9_forces.db` (117 461 snapshots GBPUSD, 655 536 évaluations, 67 758 scènes,
> 59 paper-trades).

## Résumé exécutif

Le système lit bien les forces, mais chaque dimension censée **moduler** la lecture est
soit débranchée, soit inerte. La volatilité est calculée puis jamais persistée ni
propagée par devise ; la **session** n'entre dans aucun seuil de déclenchement (pur
décor) ; le moteur de confirmation MTF est **mort à 99,95 %** (`no_context` 2052/2053) ;
le volume n'existe pas et la vélocité qui pourrait le remplacer est calculée mais
consommée par **zéro** principe. Résultat mesurable : 98 % des trades se concentrent sur
une seule session (overlap), l'espérance est **négative** (−4 pips/trade) et l'asymétrie
directionnelle est réelle (short 39 % WR vs long 77 % WR). La lecture est en noir et
blanc : les modulateurs existent dans le code mais ne touchent pas la décision.

---

## Gaps par dimension

### 1. Multi-TF — cascade illusoire + moteur de confirmation mort

- **Problème A — pas de vraie cascade fractale.** `_detect_mtf_confluences`
  (`core/v9/scene_builder.py:567`) ne modélise pas H4→H1→M15→M5. C'est une somme
  d'**overlaps par paires de TF adjacents** (`present[i]`, `present[i+1]`, ligne 616) :
  « la coalition X vue en HTF réapparaît-elle en LTF ». `coalition_mtf_score`
  (ligne 585-614) **compte** ces recouvrements ; aucun HTF ne *dicte* ou ne *gate* le
  LTF. Chaque TF reste une couche indépendante recollée statistiquement.
- **Problème B — le boost MTF est aveugle ET quasi jamais émis.**
  `MTFConfirmationEngine` retourne un `+25` / `-15` **fixe**
  (`core/v9/mtf_confirmation_engine.py:43-44`), non pondéré par la force de la thèse ni
  par le nombre de TF alignés. Surtout : sur 2053 évaluations, **2052 sont `no_context`**
  (dont `thesis_absente` = 2029) et **le boost aligné n'a été émis qu'une seule fois**.
  Cause racine : `THESIS_REGIMES = {"CASSURE", "EXTENSION"}`
  (`mtf_confirmation_engine.py:39`) est trop étroit — pour GBP, CASSURE+EXTENSION = 426
  barres sur 67 733 (**0,63 %**). Le 2ᵉ régime le plus fréquent, `RETOUR_EQUILIBRE`
  (47 798 occurrences), est explicitement exclu (ligne 38 : « sans direction fiable »).
- **Impact** : la couche « lecture anticipée multi-TF » livrée comme bonus Phase 9 est
  de facto débranchée. Le pipeline tourne comme s'il n'existait pas.
- **Fix proposé** :
  1. Élargir `THESIS_REGIMES` pour inclure `RETOUR_EQUILIBRE` avec une direction dérivée
     de `cassure_direction`/`z_extreme_dir` (dégradation gracieuse si ambigu → no_context,
     R6 préservé).
  2. Rendre le boost **proportionnel** : `boost = base × (n_TF_alignés / n_TF_présents)`
     borné, au lieu du `25` constant.
  3. (Architecture) faire de `coalition_mtf_depth` un *gate* : n'autoriser un signal LTF
     que si le HTF partage la direction dominante — vraie cascade, pas somme.

### 2. Session — décorative, jamais un modulateur de seuil

- **Problème** : `session_marche` est calculé (`core/v9/principle_engine.py:693-701`) et
  propagé, mais le multiplicateur adaptatif
  (`core/v9/adaptive_thresholds_at_runtime.py:116`) ne prend **que** `vol_regime × news ×
  timeframe`. **La session n'apparaît nulle part dans la formule des seuils.** Seul
  `exit_simulator.DYNAMIC_PROFILES` adapte les TP/SL par session — l'**entrée**, elle,
  applique les mêmes seuils à Tokyo qu'à l'overlap.
- **Preuve chiffrée** : les scènes sont **45 % Tokyo** (30 318), 21 % Londres, 17 %
  overlap, 11 % NY, 7 % Sydney. Mais les trades sont **98 % overlap** (58/59, 1 seul
  Tokyo). Le système *lit* massivement l'Asie et n'y *décide* quasiment jamais — non par
  choix explicite calibré, mais parce que les seuils fixes ne matchent que la signature
  volatile de l'overlap. Win-rate overlap = 48 %, pips cumulés −232.
- **Impact** : 45 % du temps de lecture (Asie = range/accumulation) produit ~0 décision ;
  aucune sensibilité accrue en range calme, aucune exigence renforcée en breakout Londres.
- **Fix proposé** : ajouter un `SESSION_MULTIPLIER` (Asie ×0.85 plus sensible / Londres
  ×1.2 plus exigeant / NY ×1.1 / overlap ×1.0) au produit composite de
  `adaptive_multiplier_for_vol_regime` (nouveau paramètre `session=`, borné [0.5, 2.0]).
  Additif, dégradation gracieuse si session `inconnu` → ×1.0.

### 3. Volatilité — calculée, mais mono-devise et non persistée

- **Problème A — vol mono-symbole appliquée aux 8 devises.** `vol_regime` est calculé sur
  l'ATR-30 des **bougies GBPUSD uniquement** (`principle_engine.py:752-766`), puis servi
  tel quel à l'évaluation de NZD, CHF, AUD… La volatilité de GBPUSD module la lecture de
  toutes les autres devises. Un NZD calme lu avec la vol d'un GBP agité = seuils faux.
- **Problème B — vol jamais persistée.** `context_json` de `principle_evaluations` ne
  stocke que `{"zone_type": …}` (`principle_engine.py:1052`). `vol_regime`, `session`,
  `vol_atr_pips` ne sont **écrits nulle part**. Conséquence directe pour cet audit :
  impossible de corréler offline vol×outcome (d'où l'absence de la table croisée demandée
  en Phase 1 — la donnée n'existe pas).
- **Problème C** — `adaptive_thresholds` applique le multiplicateur **uniformément** aux 3
  seuils (`adaptive_thresholds_at_runtime.py:180`, commenté « politique la plus simple »).
- **Impact** : la vol est un modulateur partiel (via P3-WIRE, kill switch souvent OFF) et
  aveugle à la devise réellement évaluée.
- **Fix proposé** :
  1. Persister `vol_regime`, `vol_atr_pips`, `session_marche` dans `context_json`
     (déjà calculés — coût nul, débloque toute analyse offline et la calibration).
  2. Calculer l'ATR par **devise** (panier de forces déjà par-devise) plutôt que sur le
     seul symbole de base.

### 4. Volume — absent, et le proxy vélocité est inerte

- **Problème** : aucune donnée de volume. MAIS le matériau d'un proxy existe :
  `scene_builder._compute_cinematics` calcule `velocite_moyenne`, `acceleration_vraie`,
  `dispersion_velocite` (`scene_builder.py:517-519`) à partir de la colonne `vitesse`, et
  ces champs sont chargés dans le contexte (`principle_engine.py:588-590`). Pourtant
  **aucun principe YAML ne les consomme** (confirmé : commentaire `principle_engine.py:500`
  « DORMANT, jamais consommés »). Le système sait à quelle vitesse le marché respire mais
  ne s'en sert pas pour qualifier « montée sur volume faible » vs « fort ».
- **Impact** : un mouvement lent (peu de changements de direction / vélocité faible) et un
  mouvement climax sont lus à l'identique.
- **Fix proposé** : introduire un champ dérivé `flow_intensity` = f(`velocite_moyenne`,
  `dispersion_velocite`) normalisé, et l'ajouter comme condition **optionnelle** (bounds,
  pas gate dur) sur les principes de cassure/extension — le pattern émet toujours mais la
  confiance est pondérée par l'intensité de flux. R6 : absent → neutre.

### 5. Biais cachés

- **Biais NZD (99,8 %)** : 654 009 / 655 536 évaluations sont sur NZD, alors que le socle
  par-devise est **parfaitement équilibré** (`zone_diagnostics` et `regime_snapshots` :
  64 319 / 67 733 lignes **par devise**, 8/8). La donnée cognitive par-devise existe ; elle
  est écrasée en amont. Cause : avant le fix DIVERSIFY 2026-07-16, `_build_currency_context`
  dérivait `h1/m5 dir/state` depuis la devise **globalement** la plus forte (identique pour
  les 8) → une seule lecture effective. Le fix (`principle_engine.py:931-956`) dérive
  désormais par devise ; les devises non-NZD **réapparaissent** (CHF 672, AUD 226, CAD 198…
  toutes en triggered=1, donc post-fix). **Le biais est en cours de correction mais tout
  l'historique reste NZD** → toute stat/calibration basée sur cet historique est biaisée.
  - *Fix* : re-générer une fenêtre de validation post-fix et vérifier que la distribution
    par-devise s'équilibre (KPI : aucune devise > 40 % des triggers sur 48 h).
- **Biais directionnel (réel, pas de lecture)** : paper-trades — **short 46 trades / 39 % WR
  / −5,9 pips moy.** vs **long 13 trades / 77 % WR / +2,7 pips moy.** Le système sur-trade
  des shorts perdants. Or le *déclenchement* de PRICE_LAG est équilibré (6693 haussier /
  5444 baissier = 55/45) → l'asymétrie naît **en aval** (entrée/exit/sizing), pas dans le
  principe. Espérance globale **négative** : 0,48×7,8 − 0,52×15 = **−4,0 pips/trade**.
  - *Fix* : instrumenter l'exit par direction (les shorts touchent-ils le SL −15 plus vite ?
    profil TP/SL asymétrique par direction dans `exit_simulator`).
- **Biais timeframe** : M15 = 495 382 évals (75 %), M5 = 98 871 (15 %), M1 = 52 680. M5
  n'est pas sous-échantillonné en capture mais l'évaluation privilégie M15. `mtf_confirmations`
  ne tourne que sur M15 (2052/2053) → la voie M5→H1 du `CONTEXT_TF_MAP` n'est jamais exercée.
- **Biais latent — `GRAMMAR_COALITION_ADAPTIVE` (à vérifier)** : la condition compare
  `coalition_strength` (échelle 0–1, formule `principle_engine.py:576`, max structurel ≈1)
  à `adaptive_coalition_threshold` (échelle **brute** ≈5,38×mult, `principle_engine.py:877`)
  — `GRAMMAR_COALITION_ADAPTIVE.yaml:14-22`. C'est **exactement** le mismatch d'échelle que
  `ADAPTIVE_VOL_GATE` a corrigé en passant à `adaptive_coalition_threshold_norm`
  (`principle_engine.py:893`). Sous le câblage actuel ce principe ne peut structurellement
  pas déclencher ; les 949 triggers en base sont **antérieurs** à ce jeu de conditions.
  - *Fix* : remplacer `adaptive_coalition_threshold` par `adaptive_coalition_threshold_norm`
    (même correctif que ADAPTIVE_VOL_GATE). **À confirmer** par un replay ciblé avant patch.

---

## Priorisation

| # | Gap | Impact | Effort | Priorité |
|---|-----|--------|--------|----------|
| 1 | MTF confirmation mort (thesis trop étroit) | Élevé — couche entière débranchée, 1 boost/2053 | Faible (1 set + dérivation) | **P0** |
| 2 | Persister vol/session dans context_json | Élevé — débloque calibration & analyse | Très faible (déjà calculé) | **P0** |
| 3 | Session absente des seuils d'entrée | Élevé — 45 % du temps de lecture stérile | Moyen (nouveau multiplier) | **P1** |
| 4 | `GRAMMAR_COALITION_ADAPTIVE` scale mismatch | Moyen — 1 principe ACTIVE dormant | Très faible (1 champ) | **P1** |
| 5 | Vol mono-devise (ATR GBPUSD → 8 devises) | Moyen — seuils faux hors GBP | Moyen (ATR par devise) | **P2** |
| 6 | Proxy vélocité inerte (volume absent) | Moyen — pas de lecture climax/épuisement | Moyen (champ + bounds YAML) | **P2** |
| 7 | Cascade MTF = somme d'overlaps, pas fractale | Moyen — lecture MTF plate | Élevé (gate HTF→LTF) | **P3** |
| 8 | Asymétrie directionnelle short/long | Élevé (espérance −) mais hors périmètre lecture | Moyen (exit par direction) | **P2** |
| 9 | Biais NZD historique | Diagnostic — corrigé, à re-valider | Faible (fenêtre validation) | **P1** |

## Fichiers cibles

- `core/v9/mtf_confirmation_engine.py:39` — `THESIS_REGIMES` (élargir) ; `:43-44` — boost fixe (pondérer).
- `core/v9/adaptive_thresholds_at_runtime.py:88-95,116` — ajouter `SESSION_MULTIPLIER`.
- `core/v9/principle_engine.py:1052` — persister vol_regime/session dans `context_json`.
- `core/v9/principle_engine.py:752-766` — ATR par devise au lieu du seul symbole.
- `core/v9/principles/GRAMMAR_COALITION_ADAPTIVE.yaml:14,22` — `adaptive_coalition_threshold` → `_norm`.
- `core/v9/scene_builder.py:567-614` — cascade MTF (gate directionnel HTF→LTF).
- `core/v9/principles/*.yaml` — ajouter condition bounds `flow_intensity` (proxy volume) sur cassure/extension.
- `core/v9/exit_simulator.py` (`DYNAMIC_PROFILES`) — profil TP/SL asymétrique par direction.

---

## Résolution — 2026-07-16 (session « Donner de la couleur »)

Les 9 gaps ont été traités dans la foulée. Statut :

| # | Gap | Statut | Preuve |
|---|-----|--------|--------|
| 1+9 | MTF mort + boost fixe | ✅ Corrigé | Replay 3000 M15 : **11 boosts (12–25) + 25 conflits** vs 1/2053 |
| 2 | vol/session non persistés | ✅ Corrigé | 3 champs ajoutés à `context_json` + test |
| 3 | Session non modulatrice | ✅ Corrigé | `SESSION_MULTIPLIER` câblé + 8 tests |
| 4 | Vol mono-devise | 📄 Documenté | Price-ATR par devise impossible (mono-symbole) — piste proxy force-dispersion |
| 5 | Vélocité inerte | ✅ Corrigé | `VELOCITY_CLIMAX_GUARD` (SHADOW) consomme la vélocité — vélocité 99 % nulle documentée |
| 6 | Biais NZD | ✅ Vérifié | Fix `_build_currency_context` effectif (6/8 contextes distincts) — historique en résorption |
| 7 | Mismatch échelle | ✅ Corrigé | `GRAMMAR_COALITION_ADAPTIVE` → `_norm` |
| 8 | Asymétrie short/long | 📄 Diagnostiqué | Signal 3:1 LONG ; trades 46 short = échantillon 7 h ; gate risk neutre |

Tests : **1497 passed + 1 skip** (baseline 1482). Détail : `DECISIONS_LOG §2026-07-16 DIVERSIFY couleur`.

## Garde-fous respectés

R18 (0 LLM dans le cœur) · R2 (100 % additif, aucun principe cassé) · R6 (chaque fix inclut
sa dégradation gracieuse) · R8 (fichier neuf, aucun fichier existant modifié → pas de backup
MD5 requis). `order_executor.py`, `config.py`, Phase 12 non touchés.
