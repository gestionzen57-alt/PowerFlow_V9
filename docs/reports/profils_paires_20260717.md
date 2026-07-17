# Profils par paire — Diagnostic 2026-07-17

**Source** : lecture seule `data/v9_forces.db` (5,2 GB, 23 tables).
**Périmètre** : 6 paires, ~131K snapshots total, 8707 décisions résolues.
**Statut** : rapport exploratoire. Aucune décision de seuils n'est proposée
sans motion CEO explicite (R25' strict). Toutes les valeurs sont des
observations factuelles.

## 1. Seuils calibrés (depuis `scenes.coalitions_json` + `cinematique_json`)

| Paire     |   N    | Coal P50 | Coal P90 | Pliure P50 (détectées) | Pliure P90 |
|-----------|-------:|---------:|---------:|-----------------------:|-----------:|
| GBPUSD    | 11312  |     49.5 |     71.1 |                   5.25 |      15.59 |
| USDJPY    |  1470  |     47.3 |     71.9 |                   3.87 |      11.65 |
| USDCAD    |  1264  |     47.5 |     70.6 |                   4.28 |      14.83 |
| USDCHF    |  1312  |     48.8 |     74.6 |                   4.87 |      21.35 |
| EURUSD    |  1046  |     50.3 |     74.2 |                   4.32 |      40.40 |
| AUDUSD    |   212  |     50.1 |     73.3 |                   5.95 |      10.10 |

**Lecture** :
- **Coalitions** : distribution quasi-identique entre paires (P50 ~ 47-50, P90 ~ 70-75). L'écart max est < 3 unités sur la médiane. → Le seuil `COALITION_THRESHOLD ≈ 5.38` (config.py) opère sur une échelle différente (force spécifique, pas ratio d'alignement — chaque paire a son référentiel de 8 devises propres).
- **Pliures** : P50 entre 3.87 (USDJPY, conservative) et 5.95 (AUDUSD, plus heurtée). P90 entre 11.65 (USDJPY) et 40.40 (EURUSD — large queue). → GBPUSD P90=15.59 est central.
- **Antagonismes** : `antagonismes_json` quasi systématiquement `[]` sur les scènes échantillonnées (1 coalition unique / pas d'antagonisme détecté). Le détecteur produit peu d'antagonismes en régime constant. Le seuil `ANTAGONISM_THRESHOLD = 31.39` est calibré sur une minorité de scènes.

## 2. Forces moyennes par devise (8 colonnes `force_*`)

| Paire    |   N    |  USD  | GBP | EUR  | JPY  | CAD  | CHF  | AUD  | NZD  | vitesse |
|----------|-------:|------:|----:|-----:|-----:|-----:|-----:|-----:|-----:|--------:|
| GBPUSD   | 119006 | 52.0  |46.7 |49.0  |50.2  |53.4  |51.2  |45.9  |49.2  |  -0.000 |
| USDJPY   |   2133 | 49.2  |47.4 |47.1  |47.4  |49.1  |48.6  |49.2  |47.2  |  -0.033 |
| USDCAD   |   1722 | 49.4  |48.5 |47.9  |47.2  |49.8  |48.6  |48.2  |48.0  |  -0.047 |
| USDCHF   |   1641 | 50.9  |49.8 |48.3  |48.7  |51.7  |48.3  |48.7  |48.4  |  -0.034 |
| EURUSD   |   1804 | 51.5  |48.1 |47.7  |49.6  |51.4  |47.8  |49.5  |48.7  |  -0.008 |
| AUDUSD   |    446 | 49.0  |45.3 |49.3  |44.2  |50.2  |51.9  |50.3  |49.2  |  -0.073 |

**Lecture** :
- **GBPUSD écrase** par le volume (n=119006 vs 1000-2000 pour les autres). Toutes les autres paires sont des add-ons récents (< 3 jours).
- **Toutes les forces sont autour de 45-53** (régime constant des dernières 24h). Pas de déséquilibre extrême.
- **Vitesse** : signal faible (autour de 0). AUDUSD légèrement plus heurtée (-0.073). Cohérent avec P50 pliure 5.95.

## 3. Distribution globale par session (toutes paires confondues)

| Session     |    N   |  WR%   | Paires représentées            |
|-------------|-------:|-------:|--------------------------------|
| asie        |   6222 |  94.4% | EUR, GBP, CAD, CHF, JPY        |
| london      |   1978 |  68.8% | toutes (6/6)                   |
| new_york    |    207 |   0.0% | GBPUSD uniquement              |
| overlap     |    215 |  63.7% | GBPUSD uniquement              |
| after       |     85 |   0.0% | GBPUSD uniquement              |

**Lecture critique** :
- **L'Asie cumule 6222 trades (72% du total résolu)** principalement avant le Brief O4 (15/07). Le **WR global 85% est massivement gonflé** par cette queue historique.
- **new_york et after WR=0%** mais ce sont des sessions **structurellement blacklistées** par O4 (depuis 15/07). Les n=207+85 trades qui y figurent sont **résiduels pré-O4** (avant que `_is_session_tradable()` ne les bloque).
- **london a toutes les 6 paires** (sample varié) — session qui généralise le mieux la multi-paire.

## 4. WR par paire × session (granulaire)

| Paire    | asie | london | NY | overlap | after |
|----------|-----:|-------:|---:|--------:|------:|
| GBPUSD   | 95.0% (n=6135) | 69.3% (n=1918) | 0% (n=207) | 63.7% (n=215) | 0% (n=85) |
| USDJPY   | 42.9% (n=21) | 77.8% (n=18) | — | — | — |
| USDCAD   | 18.8% (n=16) | 0% (n=3) | — | — | — |
| USDCHF   | 73.1% (n=26) | 44.4% (n=9) | — | — | — |
| EURUSD   | 37.5% (n=24) | 61.5% (n=13) | — | — | — |
| AUDUSD   | — | 29.4% (n=17) | — | — | — |

## 5. PIPS cumulés par paire (résolus)

| Paire    |   N   | WR   | Pips total | Avg/trade |
|----------|------:|----:|-----------:|----------:|
| GBPUSD   | 8560  | 85.3% |  +46785.9 |   +5.47 |
| USDCHF   |   35  | 65.7% |     +99.9 |   +2.85 |
| USDJPY   |   39  | 59.0% |     -57.5 |   -1.47 |
| EURUSD   |   37  | 45.9% |     -42.8 |   -1.16 |
| AUDUSD   |   17  | 29.4% |     -14.8 |   -0.87 |
| USDCAD   |   19  | 15.8% |     -58.6 |   -3.08 |

## 6. Recommandations (lecture seule, à valider par Søn lundi)

### USDCAD : WR=15.8%, -58.6 pips (n=19)
- **Constat** : pire ratio de la cohorte. Petit échantillon, mais **2 sessions asie à 18.8%** ne justifient pas le risque pris.
- **Option A (conservatrice)** : blacklister USDCAD tant que n < 50 Londres résolu. Lecture : le moteur continue de calculer, mais `paper_risk_manager.evaluate()` force `go=False`.
- **Option B (calibration)** : doubler le seuil COALITION sur USDCAD (P90 local = 70.6, donc seuil adaptatif à 8.0 au lieu de 5.38). Plus de trades, mais WR non garanti.
- **Recommandation privilégiée** : Option A. Risque asymétrique (n petit, espérance déjà -3 pips/trade).

### AUDUSD : WR=29.4%, -14.8 pips (n=17), 446 snapshots
- **Constat** : tout neuf (< 48h), seul sample london disponible. WR mauvais mais n petit. La vélocité -0.073 (la plus heurtée) signale une volatilité atypique.
- **Recommandation** : **observer jusqu'à n ≥ 50 Londres résolu**. Ne pas toucher aux seuils. Monitoring serré dimanche/lundi.

### USDJPY : WR=59.0%, -57.5 pips (n=39)
- **Constat** : WR correct mais **pips total négatif** = SL > TP. Le profil statique (TP=8 SL=15, RR=0.53) est sous-optimal pour JPY qui a des swings > 30 pips.
- **Recommandation** : laisser le **DynamicRiskManager APPLY** travailler (RR dynamique 1.63 quand phase trend/coalition HTF). Sur 2110 signaux DRM dynamiques déjà émis, USDJPY doit converger.

### EURUSD : WR=45.9%, -42.8 pips (n=37)
- **Constat** : EUR et GBP historiquement très corrélés. WR européen (londres n=13, 61.5%) en progression.
- **Recommandation** : pas de décision immédiate. À observer avec AUDUSD (mêmes sessions Londres en croissance).

### USDCHF : WR=65.7%, +99.9 pips (n=35)
- **Constat** : seul add-on clairement positif (pips total > 0). Spread CHF/faible volatilité = bon profil pour le moteur actuel.
- **Recommandation** : **profiter**, pas de tuning nécessaire.

### GBPUSD : WR=85.3% mais n=8560 (97% de l'effectif)
- **Constat** : ASIE pré-O4 WR=95% tire le global vers le haut. Le pipeline actuel fonctionne, le WR baissera mécaniquement quand les trades asie/post-O4 entreront dans la fenêtre résolue.
- **Recommandation** : **aucune action**. Le Brief O4 a déjà corrigé le biais NY/After (sessions structurellement perdantes).

## 7. Conclusion pour décision CEO lundi

**Question stratégique** : « Faut-il des profils par paire ou les seuils GBPUSD sont-ils universels ? »

**Réponse empirique** :
1. **Seuils de coalition** : distribution quasi-uniforme (P50 ~ 48-50 sur les 5 paires historiques, AUDUSD = 50.1 à 212 obs). Pas de signal fort pour des profils par paire.
2. **Pliures** : dispersion plus nette (P90 USDJPY=11.65 vs EURUSD=40.40). Profil par paire JUSTIFIÉ pour la pliure uniquement. Effort : 1 patch config.py + 1 test (mécanique).
3. **Blacklist par session** : déjà fait via Brief O4 (NY/After). Pas de blacklist par paire nécessaire sauf USDCAD.

**Recommandation globale** : 
- **Court terme (lundi)** : blacklister USDCAD tant que n<50 Londres résolu. Observer AUDUSD. Rien d'autre.
- **Moyen terme (post-n=200 par paire)** : recalibrer `PLIURE_THRESHOLD` par paire (5 profils). Effort ~2h.
- **Pas de tuning COALITION/ANTAGONISM par paire** : les distributions sont trop homogènes, le gain est marginal.

## 8. Garde-fous

- **R8** : aucune modification de `core/v9/*`, `config.py`, `order_executor.py`. Rapport lecture seule.
- **R18** : zéro LLM (rapport écrit en bash + Python stdlib).
- **R6** : tous les queries SQL ont un fallback (renvoient 0 / vide si erreur).
- **R25'** : aucune proposition de tuning de seuil n'est appliquée sans motion CEO.
