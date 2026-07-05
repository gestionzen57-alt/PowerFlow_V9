# CHECKPOINT_20260705_V9_PHASE2B

## Contexte
Phase 2B : construire le serveur de capture Python pour la couche Forces
de PowerFlow V9 — from scratch, sans reprendre le code V8
(`D:\Projet\V8\core\capture_forces.py`), qui n'a ni STALE_GATE, ni
calcul de vélocité, ni transformation vers un format de sortie
documenté. Travail mené sur la branche `feat/v9-phase2-python-capture`,
directement dans `D:\Projet\V9` (pas de worktree séparé : aucune autre
session n'était détectée comme active sur ce répertoire au démarrage).

## Livrables
- `core/v9/__init__.py` — package vide
- `core/v9/config.py` — configuration centrale (DB_PATH, ports, devises,
  timeframes, seuils STALE_GATE, constantes de calibration ForcesReader)
- `core/v9/stale_gate.py` — `StaleGate.check_freshness()`, jamais bloquant
  à l'insertion, log warning + compteur stale par timeframe
- `core/v9/forces_reader.py` — `ForcesReader.transform()` : validation des
  champs obligatoires, calcul des champs dérivés, application du
  STALE_GATE, état mémoire `{(devise, timeframe): last_force}`
- `core/v9/capture_server.py` — serveur TCP asyncio port 31685, `--status`,
  `--once`, stats received/inserted/stale/errors, logging structuré
- `core/v9/db_schema.py` — table `forces_snapshots` (WAL, busy_timeout 30s,
  index sur `(timeframe, bar_time)`)
- `tests/test_stale_gate.py` (7 tests), `tests/test_forces_reader.py` (8 tests)
  — 15 tests, tous verts (`python -m pytest tests/ -v`)
- `.gitignore` — exclut `data/*.db*` et `logs/*.log` (jamais commités)

## Décisions de design (non explicitement tranchées par le prompt)

### 1. Seuils STALE_GATE : écart assumé avec FORMAT_FORCES.md
Le prompt de mission donnait des seuils différents de ceux déjà publiés
dans `FORMAT_FORCES.md` (ex : H4 = 1 450 000 ms / 24 min ici, contre
900 000 ms / 15 min dans le format documenté ; D1 = 9 000 000 ms / 2h30
ici, contre 3 600 000 ms / 1h dans le format documenté). **Les seuils du
prompt ont été appliqués tels quels dans `config.py`**, car explicites et
plus récents dans l'ordre des instructions. Ceci crée une divergence
documentaire à trancher : soit `FORMAT_FORCES.md` doit être mis à jour
pour refléter ces seuils élargis, soit `config.py` doit revenir aux
seuils d'origine. **Point ouvert pour la prochaine session.**

### 2. Décomposition symbole → devise de base / contrepartie
La sonde EA (`ea/V9_Sonde_TF.mq4`, déjà présente dans le repo bien que
hors périmètre de cette session) tourne « 1 instance par timeframe sur
un symbole donné » et transmet un message contenant les 8 forces
simultanément (`force_usd`, `force_gbp`, ... `force_nzd`) pour ce
symbole/timeframe/bougie. Le schéma DB demandé (`forces_snapshots`) a des
colonnes singulières `direction`/`vitesse`/`croisement_*` par ligne — donc
par message, pas par devise. Décision : le `symbol` reçu (ex: `GBPUSD`)
est décomposé en devise de base (`GBP`) et devise de contrepartie
(`USD`) ; les champs `direction`, `vitesse`, `croisement`,
`recroisement`, `rejet_repulsion` de la ligne décrivent la devise de
base, ce qui correspond à la lecture naturelle du graphique observé par
la sonde. Les 8 forces (colonnes `force_*`) sont toujours stockées
intégralement, et l'état mémoire `{(devise, timeframe): last_force}` est
mis à jour pour les 8 devises à chaque message (pas seulement la base),
pour permettre plus tard des croisements entre devises non liées au
symbole observé.

### 3. `compression_extension` — métrique de bougie, pas de devise
Ce champ compare l'amplitude (max - min) des 8 forces du message courant
à une moyenne mobile (fenêtre configurable, `COMPRESSION_WINDOW_BARS=10`)
des amplitudes précédentes pour ce timeframe. C'est une métrique de
« tension du panier de devises », indépendante de la devise de base.

### 4. M1 (tick/vélocité)
Aucune sonde EA M1 n'existe encore dans ce repo (mentionnée en commentaire
dans `V9_Sonde_TF.mq4` comme `V9_Sonde_M1.mq4`, à écrire). `ForcesReader`
suppose que le message M1 aura la même forme que le message candle-close
(mêmes 8 clés `force_*`, `symbol`, `timeframe="M1"`, `capture_time`), sans
`bar_time` significatif. `direction`/`vitesse` sont calculés de la même
façon (delta_force / delta_time), et `format_forces_entry` produit une
entrée alignée sur le schéma `m1[]` de `FORMAT_FORCES.md` (mode
`tick_velocity`, `vitesse_tick`, `nb_ticks_fenetre` compté sur une fenêtre
glissante de `stale_threshold_ms`). **À revalider dès que
`V9_Sonde_M1.mq4` sera écrit.**

### 5. `recroisement` et `rejet_repulsion` — fenêtres de calibration
- `recroisement` : un croisement est comparé aux `RECROISEMENT_LOOKBACK_BARS`
  (5) croisements précédents pour la même paire (base, quote, timeframe) ;
  si un croisement de direction opposée est trouvé, `recroisement_detecte=True`.
- `rejet_repulsion` : rebond détecté si la valeur précédente de la devise
  de base était un extrême local sur `REJET_EXTREME_WINDOW_BARS` (10)
  bougies et que le rebond dépasse `REJET_MIN_REBOUND` (5.0, unités de
  force). Ces constantes sont non calibrées sur données réelles — à
  ajuster une fois des snapshots réels capturés.

## Ce qui a été explicitement refusé / évité
- Aucune reprise de code V8 (relu à titre de référence uniquement, pour
  identifier les bugs connus : décalage horaire broker non appliqué,
  absence de STALE_GATE, absence de transformation de format).
- Aucune logique de trading, aucun calcul d'exploitabilité.
- Aucune suppression de donnée stale : `stale=True` est toujours inséré,
  jamais bloqué (doctrine FREE-FIRST), conformément à `STALE_GATE`
  décrit dans `FORMAT_FORCES.md`.
- Le port TCP 31685 réel n'a pas été testé en conditions réelles dans
  cette session car un processus tiers (probablement le serveur V8 de
  production) l'occupait déjà sur cette machine (PID 7792, `pythonw.exe`).
  Validation faite sur un port de test alternatif (31686/31687) avec le
  même code (`capture_server.handle_client`, `run_server`), en couvrant :
  réception JSON valide, JSON invalide, champ manquant, message stale,
  mode `--once`, `--status` sur DB vide et DB peuplée.

## Validation effectuée
- `python -m pytest tests/ -v` → 15 passed
- `python -m core.v9.capture_server --status` sur DB absente → message
  propre, pas de crash
- Serveur TCP démarré sur port de test (31686/31687), message JSON réel
  (forme exacte de `ea/V9_Sonde_TF.mq4`) envoyé et inséré correctement,
  y compris un message volontairement stale (`stale=True` inséré, jamais
  rejeté)
- Mode `--once` confirmé : reçoit exactement 1 message puis `run_server`
  retourne proprement
- `ForcesReader.to_snapshot()` produit un JSON conforme à la structure de
  `FORMAT_FORCES.md` (schema_version, snapshot_id, timestamp, source,
  freshness, forces[]/m1[])

## Prochaine marche
1. Trancher l'écart de seuils STALE_GATE entre ce livrable et
   `FORMAT_FORCES.md` (point ouvert n°1 ci-dessus).
2. Brancher un chart MT4 réel avec `ea/V9_Sonde_TF.mq4` sur
   `capture_server.py` pour une validation de bout en bout (le port 31685
   de production devra être libéré ou le déploiement V9 fait sur une
   machine/port distinct tant que V8 tourne encore).
3. Écrire `V9_Sonde_M1.mq4` et revalider les hypothèses de forme du
   message M1 dans `forces_reader.py`.
4. Calibrer `REJET_MIN_REBOUND`, `REJET_EXTREME_WINDOW_BARS`,
   `COMPRESSION_WINDOW_BARS`, `EXTENSION_RATIO`, `COMPRESSION_RATIO` sur
   des données réelles une fois capturées.
5. Engager la Phase 3 — Couche Scènes (lecteur réel), qui consomme les
   snapshots validés de `forces_snapshots` selon `MEMORY_CONTRACT.md`.

## Risque principal
Les constantes de calibration (seuils de rejet, fenêtres de recroisement,
ratios de compression/extension) sont des valeurs de départ raisonnables
mais non calibrées empiriquement. Un premier lot de données réelles
capturées via la sonde EA sera nécessaire avant de considérer ces
détections comme fiables pour la couche Scènes.
