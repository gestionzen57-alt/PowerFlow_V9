# CHECKPOINT_20260705_V9_PHASE7

## Date
2026-07-05

## Contexte
La chaîne cognitive V9 est complète depuis la fusion précédente (voir
`CHECKPOINT_20260705_V9_CHAIN_COMPLETE.md`), mais aucune donnée réelle n'a
encore circulé dans la chaîne. La Phase 7 prépare le déploiement live :
référentiel temporel complet, outillage de vérification/démarrage/statut du
serveur de capture, validation du format EA en conditions réelles, test
d'intégration live de bout en bout, et guide de déploiement. Branche
`feat/v9-phase7-live-deployment`.

## Livrables

### 1. `core/v9/config.py` — référentiel temporel
Ajout du bloc « Référentiel temporel V9 (Phase 7) » : `BROKER_UTC_OFFSET_HOURS`
(3, Tickmill/FTMO GMT+3, pas de DST broker), `LOCAL_TIMEZONE`
("Europe/Paris"), `MARKET_OPEN_UTC_DAY/HOUR` (dimanche 22h UTC),
`MARKET_CLOSE_UTC_DAY/HOUR` (vendredi 22h UTC). Port de référence
`LISTEN_PORT` basculé sur `31690` (V9 test, le temps de ne pas interrompre
V8 qui occupe `31685` en production) — note explicite dans le commentaire
sur la bascule à opérer pour la production V9 finale.

### 2. `core/v9/market_calendar.py` — `MarketCalendar`
Utilitaires purs (aucune I/O, aucune DB) :
- `is_market_open(timestamp_utc)` : fermé le samedi, fermé dimanche avant
  22h UTC, fermé vendredi à partir de 22h UTC.
- `current_session(timestamp_utc)` : sydney (21h-6h, traverse minuit),
  tokyo (0h-9h), london (7h-16h), new_york (12h-21h),
  overlap_london_ny (12h-16h), ou "closed" si marché fermé. Priorité de
  résolution en cas de chevauchement (du plus spécifique au plus général) :
  overlap_london_ny > london > new_york > tokyo > sydney — ce choix a été
  nécessaire pour satisfaire simultanément les 3 cas de validation fournis
  (10h→london, 14h→overlap_london_ny, 3h→tokyo malgré le chevauchement
  avec sydney à cette heure).
- `next_open(timestamp_utc)` : prochain dimanche 22h UTC strictement après
  le timestamp donné (gère aussi bien un appel marché fermé qu'un appel
  marché ouvert, auquel cas retourne l'ouverture de la semaine suivante).
- `broker_to_utc` / `utc_to_broker` : conversion par offset fixe (3h),
  aucune gestion DST côté broker (Tickmill/FTMO ne changent pas d'heure).
- `paris_to_utc` : conversion via `zoneinfo.ZoneInfo("Europe/Paris")`
  (stdlib Python 3.9+, aucune dépendance externe ajoutée), DST CET/CEST
  géré automatiquement.

### 3. `tests/test_market_calendar.py` — 22 tests
Couvre explicitement les cas de validation fournis dans la mission :
`is_market_open` (samedi 12h UTC → False, dimanche 21h UTC → False,
dimanche 22h UTC → True, vendredi 21h UTC → True, vendredi 23h UTC →
False), `current_session` (10h UTC → london, 14h UTC →
overlap_london_ny, 3h UTC → tokyo), plus `next_open`,
`broker_to_utc`/`utc_to_broker` (aller-retour), `paris_to_utc` (été CEST
UTC+2, hiver CET UTC+1). Les dates de test ont été vérifiées
programmatiquement (`datetime.strftime('%A')`) avant écriture pour éviter
toute erreur de jour de semaine.

### 4. EA MT4 — input `ServerPort`
**Écart découvert en lisant le code existant** : `ea/V9_Sonde_TF.mq4` et
`ea/V9_Sonde_M1.mq4` codaient en dur le port TCP 31685 dans une constante
Winsock packée (`addr[0] = -981794814`), sans aucun input `ServerPort` —
alors que la procédure de déploiement demandée suppose de pouvoir régler
`ServerPort=31690` pour tester V9 sans interrompre V8. Sans ce changement,
la bascule de port décrite dans la mission aurait été impossible à
appliquer depuis les propriétés de l'EA (aurait nécessité une
recompilation à chaque bascule de port).

Correction apportée : ajout d'un input `ServerPort` (défaut `31685`) sur
les deux EA, et d'une fonction `MakeSockAddr0(port)` qui recalcule
dynamiquement l'entier packé (`AF_INET | port en network byte order`) au
lieu de la constante figée. Formule vérifiée arithmétiquement contre
l'ancienne constante (`-981794814` correspond exactement à
`MakeSockAddr0(31685)`). Toute instance déjà compilée doit être
recompilée pour bénéficier de ce nouvel input — point ouvert documenté
plus bas.

`ea/V9_Sonde_README.md` mis à jour : section réseau (paramètre
`ServerPort`, procédure de bascule 31685/31690), section diagnostic
(vérifier `ServerPort` == `LISTEN_PORT`).

### 5. `scripts/deploy_v9.py`
Script autonome (pas de daemon), 4 modes exclusifs :
- `--check` : Python 3.11+, importabilité des 14 modules `core/v9/`,
  existence/création de `data/v9_forces.db` + ses 5 tables (`forces_snapshots`,
  `scenes`, `behaviors`, `windows`, `exploitability`), disponibilité du
  port `31690`, vérification souple (non bloquante, timeout 3s) d'une
  connexion EA entrante.
- `--start` : lance `python -m core.v9.capture_server` en sous-processus,
  écrit un PID file (`logs/v9_capture.pid`), reste au premier plan
  (Ctrl+C ou `--stop` depuis un autre terminal pour arrêter proprement).
- `--status` : compteurs par table (snapshots par timeframe, scènes,
  comportements, fenêtres, évaluations), taux de stale, timestamp + âge du
  dernier snapshot.
- `--stop` : lit le PID file, termine le processus (`taskkill /F` sur
  Windows), nettoie le PID file.

### 6. `scripts/validate_ea_output.py`
Reçoit 1 message TCP EA (`--port` configurable, `--once` seul mode
supporté), puis :
- valide la structure (champs obligatoires, timeframe connu, horodatage
  exploitable, 8 clés `force_*` présentes) ;
- vérifie que les 8 forces sont numériques, non NaN, signale (avertissement
  non bloquant) une valeur exactement à zéro ;
- reconvertit `capture_time` (broker) en UTC via `MarketCalendar.broker_to_utc`
  et le compare au `timestamp` déclaré (tolérance 5s) — détecte un
  `BrokerUTCOffsetHours` mal réglé côté EA ;
- heuristique de plausibilité AUD : AUD doit se situer dans l'intervalle
  [min(EUR,NZD), max(EUR,NZD)] à ±15 unités de force ; sinon avertissement
  « AUD potentiellement inversé », renvoyant vers la procédure de
  diagnostic des buffers SDI (`ea/V9_Sonde_README.md` section 4) sans
  jamais trancher automatiquement ni modifier quoi que ce soit.
- Rapport texte final avec statut global VALIDE/INVALIDE.

Testé avec des messages JSON simulés (payload conforme + payload avec AUD
hors intervalle) : les deux rapports produisent le comportement attendu.

### 7. `scripts/live_integration_test.py`
Attend de nouveaux snapshots non-stale sur la DB de production
(`data/v9_forces.db`, **lecture seule**), copie chaque snapshot détecté
vers une DB de test dédiée (`data/v9_live_test.db` par défaut, recréée à
chaque lancement sauf `--keep-db`), puis fait traverser la chaîne complète
(`SceneBuilder.build_scene` + `_write_scene_to_db` →
`BehaviorAnalyzer.analyze_scene` → `WindowGate.evaluate_behavior` →
`ExploitabilityEvaluator.evaluate_window`) sur cette DB de test. Mesure le
temps de traitement par couche (`time.perf_counter`), accumule les
erreurs par couche sans interrompre le traitement des snapshots suivants,
et conserve le premier comportement/fenêtre/évaluation produits pour le
rapport final (qualification + confiance, statut de fenêtre, statut
d'exploitabilité).

Point d'implémentation notable : le dict retourné par
`BehaviorAnalyzer.analyze_scene` imbrique `qualification` et
`confiance_qualification` sous la clé `"comportement"` (pas au niveau
racine) — repéré et corrigé pendant les tests manuels du script (accès via
`behavior["comportement"]["qualification"]`).

Testé de bout en bout avec un snapshot simulé inséré dans une DB de
production temporaire pendant l'exécution du script (poll 1s) : la chaîne
complète s'exécute sans erreur, produit une scène, un comportement
(qualification "maintien", confiance 40), une fenêtre (statut "absente")
et une évaluation (statut "non_exploitable"). La DB de production n'a
jamais été modifiée par le script (vérifié : seules des lectures
`SELECT`).

### 8. `docs/deployment/V9_DEPLOYMENT_GUIDE.md`
Guide de déploiement complet : pré-requis, référentiel temporel, 5 étapes
(compilation EA, déploiement MT4, démarrage serveur Python, validation
sonde, test d'intégration live), table de diagnostic, rappel des limites
de portée (aucune exécution d'ordre, aucune calibration automatique).

## Validation
`python -m pytest tests/ -v` → **118 passed** (96 précédents + 22
nouveaux pour `test_market_calendar.py`), aucune régression.

Tous les scripts testés manuellement en conditions simulées (marché
fermé au moment de la session — le vrai test contre le marché réel reste
à faire à l'ouverture, voir « Prochaine étape ») :
- `deploy_v9.py --check` : toutes les vérifications bloquantes passent.
- `deploy_v9.py --status` : compteurs corrects (0 partout sur DB vide).
- `deploy_v9.py --stop` : gère correctement l'absence de PID file.
- `validate_ea_output.py --once` : rapport correct sur payload valide et
  sur payload avec AUD suspect.
- `live_integration_test.py --duration` : chaîne complète exécutée avec
  succès sur un snapshot simulé inséré en cours d'exécution.

Toutes les données de test simulées (DB de production temporaire,
snapshots factices) ont été supprimées après validation — `data/*.db` est
de toute façon exclu du dépôt par `.gitignore`.

## Points ouverts (non bloquants)
- Les `.ex4` compilés déjà présents dans `ea/` datent d'avant l'ajout de
  l'input `ServerPort` — recompilation requise avant tout déploiement
  réel (voir `docs/deployment/V9_DEPLOYMENT_GUIDE.md` étape 1).
- Calibration des seuils heuristiques (`core/v9/config.py`) toujours non
  validée sur données réelles — objectif du test d'intégration live à
  l'ouverture du marché.
- Validation terrain de la sonde EA sur données de marché réelles : reste
  à faire (nécessite le marché ouvert).
- `data/replay_outcomes.json` reste un fichier optionnel vide, sans
  source de production réelle tant que la couche Exécution éventuelle
  n'existe pas.
- Décision de périmètre pour la couche Exécution éventuelle : toujours
  hors périmètre de cette phase, à trancher séparément.

## Statut
**PHASE 7 TERMINÉE.** Déploiement live et test d'intégration préparés :
référentiel temporel complet, 4 scripts autonomes de déploiement/validation,
guide de déploiement, EA mis à jour pour supporter un port de test sans
toucher à V8. 118 tests verts.

## Prochaine étape
Déploiement live à l'ouverture du marché (dimanche 23h Paris / 22h UTC) :
suivre `docs/deployment/V9_DEPLOYMENT_GUIDE.md` du début à la fin
(compilation EA, déploiement MT4, démarrage serveur, validation sonde,
test d'intégration live), puis calibrer les seuils heuristiques sur les
observations réelles obtenues.
