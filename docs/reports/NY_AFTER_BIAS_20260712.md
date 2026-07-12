# Analyse du biais New York / After — Brief O4 (2026-07-12)

**Périmètre** : analyse pure, lecture seule. Aucune modification de `core/v9/*`, aucun seuil, aucun YAML. Recalcul indépendant sur les prix bruts (`forces_snapshots`), pas sur les labels déjà écrits en DB.

Données brutes complètes : `docs/reports/NY_AFTER_BIAS_RAW_20260712.json`.
Script (jetable, réutilisable) : `scripts/v9_analyze_ny_after_bias.py`.

Population analysée : 1296 décisions `preparer_entree` en session New York (802) ou After (494), 1295 avec prix futurs disponibles (1 sans donnée).

## Question centrale

Le WR NY 29.6% / After 20.6% (sous stratégie TP10/SL15, cf. STATE.md Phase 13.2) est-il :
- **(a)** un biais de période (échantillon haussier, les sessions US concentrent les retournements de cette fenêtre précise) ;
- **(b)** un défaut structurel de lecture (la microstructure NY invalide les principes V9) ;
- **(c)** un mélange quantifiable des deux ?

**Verdict : (c), avec un dosage différent par session.** New York est dominé par (a)+une composante structurelle de volatilité ; After montre un signal supplémentaire compatible avec (b), mais qui reste largement expliqué par (a) une fois le contexte de drift pris en compte (voir §4).

## 1. Distribution direction × session × résultat

Le catalogue de principes génère une proportion de signaux **baissiers** très supérieure à sa moyenne globale, précisément dans les deux sessions à problème :

| Session | % baissière | % haussière | WR baissière (MFE) | WR haussière (MFE) |
|---|---|---|---|---|
| Asie | 2.0% | 98.0% | 55.5% | 96.2% |
| London | 92.1% | 7.9% | 71.5% | 46.0% |
| Overlap | 51.7% | 48.3% | 75.0% | 49.1% |
| **New York** | **81.0%** | 19.0% | 93.5% | 94.7% |
| **After** | **75.5%** | 24.5% | 66.8% | 99.2% |

Globalement (tous `preparer_entree`), la répartition est 68.4% haussière / 31.6% baissière. New York et After sont les **deux seules sessions où le signal bascule majoritairement baissier**, dans un marché dont l'audit antérieur (backlog W1/R1) documente un drift haussier ~91% sur la période. C'est une divergence structurelle nette entre le régime détecté par les principes en fin de journée US et le régime réel du marché — **explique une bonne partie du déficit de WR sous stratégie directionnelle réelle** (TP/SL), même si sous MFE pur (sans stop) le WR reste élevé des deux côtés (voir §3-4 pour la raison).

## 2. WR par principe × session

`PRICE_LAG_AT_NODE_BIRTH` (dominant, ~90% des triggers) : 93.0% WR (MFE) en NY contre 73.4% en After — écart cohérent avec le §4 (After montre un vrai déficit directionnel, pas seulement de la volatilité). Les autres principes (`POWER_ANGLE_BREAK_TO_PRICE_IMPACT`, `ZONE_RETEST`, `GRAVITY_RESPRING_NODE`) suivent la même hiérarchie NY > After sans qu'aucun ne se détache comme porteur spécifique des pertes — le problème n'est pas concentré sur un principe isolé, il est **sessionnel**.

## 3. MFE/MAE par session — le discriminant clé

| Session | MFE moyen | MAE moyen | Lecture |
|---|---|---|---|
| New York | 8.6 pips | **16.9 pips** | Excursion adverse > SL=15 en moyenne — le SL est touché avant que le mouvement favorable (modeste, 8.6 pips) ne se matérialise |
| After | 4.8 pips | **25.6 pips** | Excursion adverse massive, mouvement favorable faible — profil le plus défavorable des 5 sessions |

**0% des cas** où MFE > 10 pips ont fini perdants sous MFE_ONLY (normal — MFE_ONLY n'a pas de stop). La perte sous TP/SL vient entièrement de l'ordre d'arrivée des prix : l'adverse arrive **avant** le favorable. C'est un problème de **volatilité/chronologie**, pas un problème de signal en soi pour New York — le SL=15 est structurellement trop juste pour l'amplitude MAE ~17 pips typique de cette session.

## 4. Pattern de retournement — le discriminant décisif

| Session | WR réel (MFE, direction prise) | WR si direction inversée (MFE) | Écart |
|---|---|---|---|
| New York | 93.8% | 93.6% | **≈0** — aucun avantage à inverser |
| After | 74.7% | **99.6%** | **+24.9 pts** — écart massif |

**New York** : inverser la direction ne change rien (93.8% vs 93.6%). Sous MFE pur, le marché finit par bouger favorablement dans les deux sens quasiment tout le temps — il n'y a **pas de signal directionnel exploitable ni erroné** ici, c'est de la volatilité bidirectionnelle (whipsaw), cohérent avec le §3 (SL touché par bruit, pas par tendance adverse réelle).

**After** : écart de 25 points. C'est le signal le plus fort de cette analyse. Deux lectures possibles :
- Lecture (b) — défaut structurel : le principe lit mal la microstructure After et pointe la mauvaise direction.
- Lecture (a) — biais de période : 75.5% des signaux After sont baissiers (§1) dans un marché à drift haussier documenté ~91% sur la période ; un signal baissier a mécaniquement plus de mal à trouver une excursion favorable dans un marché qui monte, et le signal inverse (haussier) en profite d'autant.

Les deux lectures ne sont pas exclusives et je ne peux pas les départager avec les données actuelles (il faudrait le drift réel minute par minute de la fenêtre After sur la période, pas seulement le WR haussière/baissière agrégé). **Ceci est documenté comme diagnostic ouvert, PAS comme stratégie d'inversion** — inverser un signal sur la seule base d'un WR historique sur 494 décisions d'une unique période à fort drift serait un surapprentissage classique, hors doctrine sans décision structurante séparée.

## 5. Contrefactuel TP=3/SL=15

| Session | WR | Total pips | Pips/trade |
|---|---|---|---|
| New York TP3/SL15 | 83.4% | -337.2 | **-0.4** |
| New York TP10/SL15 (actuel = SKIP) | 29.6% | -5996.1 | -7.5 |
| After TP3/SL15 | 24.5% | -5361.6 | -10.9 |
| After TP10/SL15 (actuel = SKIP) | 20.6% | -5255.6 | -10.6 |

TP3/SL15 améliore radicalement le WR affiché en New York (29.6% → 83.4%) mais reste **légèrement négatif en pips** (-0.4/trade) même avant prise en compte d'un spread réel NY souvent > 0.5 pip (session généralement plus liquide que After mais avec des pics de volatilité sur news US) — donc pas clairement viable en l'état, sensible au spread réel. Pour After, TP3/SL15 est nettement pire (-10.9/trade) — confirme qu'aucun ajustement de TP/SL ne sauve cette session, cohérent avec le §4 (le problème n'est pas la granularité du TP mais la direction/l'ordre des prix).

## Verdict motivé

- **New York** : dominé par **(a)+une composante de volatilité structurelle** — signaux majoritairement baissiers à contre-tendance d'un marché haussier (§1), combiné à un profil MAE (16.9) qui dépasse le SL=15 en moyenne (§3), sans avantage à l'inversion (§4). Pas un défaut de lecture des principes, plutôt un environnement où le couple (direction-biaisée + volatilité) rend toute résolution directionnelle avec TP/SL fixe structurellement difficile.
- **After** : **mélange (a)/(b) non départagé** — écart de retournement le plus fort de l'analyse (+24.9 pts), compatible avec un vrai défaut de lecture OU avec le même biais de période amplifié par un MAE encore plus extrême (25.6 pips). Aucun TP/SL testé n'est profitable.

## Recommandation

**Maintien du SKIP (statu quo) pour New York et After.**

Aucune des alternatives testées n'est clairement profitable :
- TP3/SL15 New York : quasi break-even (-0.4 pips/trade) mais **négatif**, et sensible à un spread réel probablement > 0.5 pip sur cette session — pas assez de marge pour justifier un passage en SHADOW dès maintenant.
- TP3/SL15 After : nettement négatif (-10.9 pips/trade) — à exclure.
- Filtre par principe : aucun principe ne se détache comme porteur spécifique des pertes (§2) — un filtre par principe n'aurait pas de levier ici, le problème est sessionnel, pas principiel.

**Proposition pour décision Søn** (rien n'est appliqué) : si un futur audit confirme que le drift haussier de la période s'atténue (marché plus équilibré), ré-évaluer TP3/SL15 New York en SHADOW-observation — c'est la seule variante qui s'approche du seuil de viabilité. After ne présente aucune configuration testée qui justifie une réévaluation à court terme.
