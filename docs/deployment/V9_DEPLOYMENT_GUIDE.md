# V9_DEPLOYMENT_GUIDE — Déploiement live PowerFlow V9 (Phase 7)

## Rôle de ce document

Ce guide décrit la procédure complète pour brancher la chaîne cognitive V9
(Forces → Scènes → Comportements → Fenêtres → Exploitabilité) sur des
données de marché réelles, à l'ouverture du marché Forex. Il ne couvre
aucune logique de trading ni d'exécution d'ordre — la couche Exécution
éventuelle reste hors périmètre (voir `docs/STATE.md`).

Le marché Forex ouvre dimanche 23h00 Paris (22h00 UTC, 01h00 broker
GMT+3 lundi) et ferme vendredi 23h00 Paris (22h00 UTC). Voir
`core/v9/market_calendar.py` pour les utilitaires de calendrier.

## Pré-requis

- MT4 Tickmill installé et configuré (serveur en GMT+3, Tickmill ou FTMO MT5 équivalent).
- Indicateur `SDI TCSWL 600+` chargé et fonctionnel (MT4 uniquement).
- Python 3.11+ installé, dépendances standard (aucune dépendance externe
  ajoutée par la Phase 7 — `zoneinfo` fait partie de la stdlib).
- Dépôt V9 cloné sur `D:\Projet\V9`.

## Référentiel temporel (rappel)

- Les timestamps stockés en DB (`forces_snapshots.timestamp`, `created_at`,
  etc.) sont **toujours en UTC** (ISO 8601).
- L'EA MT4 envoie `bar_time` / `server_time` / `capture_time` en heure
  broker (GMT+3, Tickmill/FTMO) ; la conversion vers UTC est faite côté EA
  (`ToISO8601UTC`, paramètre `BrokerUTCOffsetHours`) avant tout envoi TCP.
- `core/v9/market_calendar.py` (`MarketCalendar`) centralise les
  conversions broker ↔ UTC ↔ Paris et la détection d'ouverture de marché /
  session active, côté Python.

## Étape 1 — Compilation de l'EA

1. Ouvrir MetaEditor (F4 depuis MT4, ou directement).
2. Copier `ea/V9_Sonde_TF.mq4` et `ea/V9_Sonde_M1.mq4` dans `MQL4/Experts/`
   du terminal MT4 cible.
3. Compiler chaque fichier (F7).
4. Vérifier dans l'onglet "Erreurs" : 0 erreur attendu (les avertissements
   sur variables non utilisées sont sans conséquence).

**Nouveauté Phase 7** : les deux EA exposent désormais un input
`ServerPort` (au lieu d'un port TCP figé dans le code). Toute instance
existante compilée avant cette phase doit être recompilée pour bénéficier
de ce paramètre.

## Étape 2 — Déploiement de l'EA sur MT4

Pour chaque timeframe (M1, M5, M15, M30, H1, H4, D1) :

1. Glisser `ea/V9_Sonde_TF.mq4` sur le chart correspondant (sauf M1, voir
   ci-dessous).
2. Dans les inputs de l'EA :
   - `ServerPort` = `31690` (test V9, le temps de valider sans interrompre
     V8) — repasser à `31685` uniquement pour la production V9 finale,
     après arrêt de V8.
   - `BrokerUTCOffsetHours` = `3` (Tickmill/FTMO, GMT+3 — à re-vérifier à
     chaque changement d'heure été/hiver broker).
   - `ShiftIndex` = `1` (candle-close, M5..D1).
   - `RefreshSeconds` = `1`.
3. Vérifier le smiley vert (EA actif) en bas à droite du chart.

Pour **M1**, utiliser `ea/V9_Sonde_M1.mq4` à la place (mode tick, pas de
`ShiftIndex`/`RefreshSeconds` — voir `ea/V9_Sonde_README.md`), avec le même
`ServerPort`.

## Étape 3 — Démarrage du serveur Python

```powershell
cd D:\Projet\V9
python scripts\v9_ops.py check
python scripts\v9_ops.py start
```

Ou via le point d'entrée unique (équivalent) :

```powershell
python scripts\v9_ops.py boot
```

`--check` vérifie : la présence/création de `data/v9_forces.db` et de ses 5
tables (`forces_snapshots`, `scenes`, `behaviors`, `windows`,
`exploitability`), la disponibilité du port `31685`, Python 3.11+, et
l'importabilité de tous les modules `core/v9/`. Il tente aussi une
vérification souple (non bloquante) d'une connexion EA entrante.

`--start` lance `core/v9/capture_server.py` en sous-processus (écoute sur
`core.v9.config.LISTEN_PORT`, soit `31685`), journalise dans
`logs/v9_capture.log`, et reste au premier plan (Ctrl+C pour arrêter).

**Équivalent PowerShell** pour le suivi des logs en temps réel :

```powershell
Get-Content -Path D:\Projet\V9\logs\v9_capture.log -Wait -Tail 20
```

Ou via le point d'entrée unique :

```powershell
python scripts\v9_ops.py log
```

## Étape 4 — Validation de la sonde EA

Dans un second terminal, pendant que le serveur tourne (ou avant, le script
écoute lui-même le port le temps de recevoir un message) :

```powershell
python scripts\v9_ops.py validate-ea
```

Vérifier dans le rapport :
1. Les 8 forces (`force_usd` ... `force_nzd`) sont reçues.
2. Aucune n'est à `0` ou `NaN` de façon persistante.
3. Le timestamp UTC déclaré correspond bien à `capture_time` (broker)
   converti — un écart suspect indique un mauvais `BrokerUTCOffsetHours`
   sur l'EA.
4. Le champ « Plausibilité AUD » ne signale pas d'inversion (AUD hors de
   l'intervalle EUR/NZD) — sinon, voir `ea/V9_Sonde_README.md` section 4
   (diagnostic buffers SDI), sans jamais modifier le code de l'EA.

Puis :

```powershell
python scripts\v9_ops.py status
```

Vérifier les compteurs par timeframe, le taux de stale, et l'âge du
dernier snapshot reçu.

## Étape 5 — Test d'intégration live

Attendre l'ouverture du marché (dimanche 23h Paris / 22h UTC), puis, le
serveur de capture tournant (`--start`) :

```powershell
python scripts/live_integration_test.py --duration 300
```

Ce test **ne modifie jamais** `data/v9_forces.db` (lecture seule) : chaque
nouveau snapshot non-stale est copié dans une DB de test séparée
(`data/v9_live_test.db` par défaut, recréée à chaque lancement sauf
`--keep-db`), sur laquelle la chaîne complète (`SceneBuilder` →
`BehaviorAnalyzer` → `WindowGate` → `ExploitabilityEvaluator`) est
exécutée.

Vérifier dans le rapport final :
1. La chaîne complète fonctionne sans erreur bloquante.
2. Le premier comportement qualifié (qualification + confiance).
3. Le premier statut de fenêtre.
4. Le premier statut d'exploitabilité.
5. Les temps moyens par couche (indicatif de performance, pas de
   calibration).

## Diagnostic

| Symptôme | Vérification |
|---|---|
| Pas de données reçues | Port (`ServerPort` EA == `LISTEN_PORT` 31685 Python), pare-feu Windows, EA actif (smiley vert), un seul process écoutant sur le port |
| Forces à 0 ou NaN | L'indicateur `SDI TCSWL 600+` est-il bien chargé et calculé sur le chart ? Voir `ea/V9_Sonde_README.md` section 3 |
| AUD suspect (hors intervalle EUR/NZD) | `ea/V9_Sonde_README.md` section 4 — procédure de diagnostic des buffers SDI, ajuster uniquement les inputs `BufIdx_*`, jamais le code |
| Beaucoup de `stale` | Vérifier la connexion MT4 (déconnexion serveur), et `BrokerUTCOffsetHours` (un décalage horaire faux fausse le calcul d'âge du snapshot) |
| `deploy_v9.py --stop` ne trouve rien | Le PID file (`logs/v9_capture.pid`) n'existe que si `--start` a été lancé depuis cette machine et n'a pas déjà été arrêté proprement. Utiliser `python scripts\v9_ops.py stop` (alias) ou `taskkill /F /PID <pid>` en dernier recours |

## Ce que cette phase ne fait pas

- Aucune logique d'exécution d'ordre.
- Aucune calibration automatique des seuils heuristiques (Scènes,
  Comportements, Fenêtres, Exploitabilité) — `core/v9/config.py` reste la
  source de vérité, à ajuster manuellement sur la base des observations du
  test d'intégration live.
- Aucune référence à V8 au-delà du partage temporaire du port `31685` en
  production (V9 utilise `31690` le temps du test).
