# Audit d'impact multi-paires — Brief Q4 (2026-07-13)

Étape 0 du Brief Q4 (mandat série Q1→Q5, 2026-07-12) : lister tout ce qui suppose
GBPUSD/une seule paire dans le dépôt, AVANT tout changement de code. Contrainte
dure : le comportement GBPUSD doit rester strictement inchangé.

## Verdict global

Le pipeline V9 est **déjà construit de façon largement symbol-agnostique** — bien
plus que le mandat initial ne le supposait (qui envisageait une "extension de
SceneBuilder pour agrégation cross-paires" comme le gros du travail). Un seul bug
réel a été trouvé, dans `core/v9/exit_simulator.py` : le multiplicateur pips était
codé en dur à 10000 (4 décimales), faux pour les paires cotées en JPY (2
décimales). Corrigé, voir DECISIONS_LOG §Brief Q4.

## Détail par composant

### 1. `core/v9/config.py` — SAFE, rien à restructurer
Aucune constante `SYMBOL`/`PAIRS` hardcodée. `symbol` a toujours été un champ
libre (aucune liste blanche). Un registre informatif `SUPPORTED_SYMBOLS` a été
ajouté (additif, ne change aucun comportement existant) pour la validation
dashboard/scripts futurs.

### 2. Chaîne perceptuelle (`scene_builder.py`, `forces_reader.py`, `signal_generator.py`) — SAFE
`SceneBuilder` prend `symbol` en paramètre de requête à chaque appel SQL
(`f.symbol = ?`, `_load_coalition_history(symbol, timeframe, ...)`, etc.) — il
traite déjà n'importe quel symbole présent dans les snapshots qu'on lui passe,
sans hypothèse GBPUSD codée en dur. `forces_reader.py`/`signal_generator.py`
documentent la convention "direction lue sur la devise de BASE du symbole"
(GBP pour GBPUSD, EUR pour EURUSD, etc.) — déjà générique par construction.
**Aucun changement de code nécessaire.**

### 3. Schéma DB (`core/v9/db_schema.py`) — SAFE, risque signalé au mandat NON confirmé
Le mandat signalait spécifiquement "UNIQUE index bar_time" comme risque à
vérifier. Vérifié : `idx_unique_closed_bar` est un index composite
`(symbol, timeframe, bar_time)` — `symbol` fait déjà partie de la clé
d'unicité. Deux paires avec le même `bar_time` ne collisionnent pas.
**Aucun changement nécessaire.**

### 4. `principles/*.yaml` (26 fichiers, 25 ACTIVE) — SAFE
Recherche de toute référence à un symbole/devise spécifique dans les
`condition` des YAML : aucune. Les 2 seules occurrences de "GBP" trouvées
(`GRAMMAR_ABSORPTION.yaml`, `GRAMMAR_EXHAUSTION.yaml`) sont des commentaires de
documentation historique (héritage V8 `z_gbp`), pas des conditions — la
logique réelle lit `z_current`/`zone_diagnostics` (champs génériques dérivés de
la devise de BASE du symbole courant, quel qu'il soit). La règle du mandat
("un principe lit les forces, pas le symbole") est déjà respectée par
construction. **Aucun changement nécessaire, aucune duplication à faire.**

### 5. EA MT4 (`ea/V9_Sonde_M1.mq4`, `ea/V9_Sonde_TF.mq4`) — SAFE, déploiement = action opérateur
`g_symbol = (RefSymbol == "") ? Symbol() : RefSymbol;` — l'EA utilise déjà le
symbole natif du graphique MT4 sur lequel il est attaché (`Symbol()`), avec un
override optionnel. **Aucune modification de code EA nécessaire** pour émettre
EURUSD/USDJPY/GBPJPY : il suffit d'attacher une instance de l'EA à un graphique
de chacune de ces paires dans le terminal MT4. C'est une **action opérateur**
(attacher l'EA à 3 graphiques supplémentaires), hors périmètre autopilot de ce
brief — non tentée, aucun terminal MT4 live touché.

### 6. `core/v9/exit_simulator.py` — BUG RÉEL, corrigé
`PIPS_MULTIPLIER = 10000` codé en dur, utilisé pour convertir tout écart de
prix en pips (`price_to_pips()`, TP/SL/trailing en unités de prix). Pour les
paires cotées en JPY (pip = 0.01, pas 0.0001), ce multiplicateur aurait produit
des comptages de pips 100× trop élevés et des seuils TP/SL 100× trop serrés en
prix réel — silencieusement faux, sans erreur.

**Correction** : `pips_multiplier_for_symbol(symbol)` (nouveau) retourne 100
pour `{"USDJPY", "GBPJPY"}`, 10000 sinon (y compris `None`/`"GBPUSD"`/
`"EURUSD"` — défaut historique). `ExitSimulator.__init__` accepte un paramètre
`symbol` optionnel (mot-clé, défaut `None`) qui détermine
`self._pips_multiplier`. **Tout appelant existant (aucun des 8 sites d'appel
actuels ne passe `symbol`) obtient exactement `10000`, comportement
strictement identique à avant.** Preuve empirique (pas seulement théorique) :
`tests/test_exit_simulator_multi_pair.py` charge la version du fichier
sauvegardée AVANT modification (backup R8 MD5,
`docs/calibration/backups/2026-07-13_multi_pair_q4/exit_simulator.py.bak`) et
compare ses résultats à la version actuelle sur 7 scénarios (toutes les
stratégies : TP_SL, TRAILING, TIME_BASED, MFE_ONLY, DYNAMIC×2) — pips,
exit_reason, MFE, MAE, bars_held, is_win identiques bit-à-bit dans tous les cas.

### 7. `core/v9/paper_risk_manager.py` — commentaire imprécis, pas un bug fonctionnel
`pip_value = 10.0  # $10 par pip pour 1 lot standard GBPUSD` — le commentaire
cite GBPUSD spécifiquement mais la valeur (10$/pip pour 1 lot standard en
compte USD) reste une approximation raisonnable pour EURUSD également ; pour
les paires JPY la valeur exacte dépend du taux USDJPY courant (~1000¥/pip/lot,
converti ≈ mais pas exactement 10$ selon le taux). **Non corrigé dans ce
brief** — approximation déjà en place pour GBPUSD, le sizing paper reste
indicatif (R22, hors périmètre : un calcul de pip_value dynamique par taux de
change serait un chantier distinct, pas un correctif de régression).

### 8. `scripts/v9_market_report.py` — gap connu, non bloquant
`WHERE symbol = 'GBPUSD'` codé en dur dans la requête de rapport. Script de
reporting opérationnel (pas le chemin cognitif/décision), continuerait à ne
reporter que GBPUSD si d'autres paires sont ajoutées côté EA. **Non modifié
dans ce brief** (R22, hors périmètre strict de Q4 — un rapport multi-paires
serait un chantier dédié) ; documenté ici pour qu'un futur brief le retrouve
facilement plutôt que de le redécouvrir.

### 9. `scripts/v9_dashboard_web.py` (Brief Q3) — SAFE
Aucune des requêtes `dashboard_queries.py` ne filtre par symbole — `/`,
`/review`, `/trades`, `/calibration` afficheraient déjà les décisions/trades de
toutes les paires si elles existaient en DB. **Aucun changement nécessaire.**

## Ce qui N'A PAS été fait dans ce brief (R22, hors périmètre)

- Attacher l'EA à des graphiques EURUSD/USDJPY/GBPJPY réels (action opérateur MT4).
- Corriger `scripts/v9_market_report.py` pour être multi-paires (gap connu,
  documenté ci-dessus, script de reporting non critique).
- Calcul dynamique de `pip_value` par taux de change dans
  `paper_risk_manager.py` (approximation existante conservée telle quelle).
- Aucune donnée réelle EURUSD/USDJPY/GBPJPY n'existe en base à ce jour (l'EA
  n'émet que GBPUSD) — ce brief prépare le pipeline à les recevoir
  correctement le jour où l'opérateur les active, il ne peut pas les tester
  end-to-end sur des données live faute de flux existant.
