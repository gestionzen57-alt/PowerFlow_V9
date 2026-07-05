# V9_AUTOMATION_RUNBOOK — Automatisation opérationnelle PowerFlow V9

## Rôle de ce document

Ce runbook documente l'outillage d'automatisation qui réduit la friction manuelle au
reboot machine, à l'ouverture marché et à la reprise de session. Il **complète**
`docs/deployment/V9_DEPLOYMENT_GUIDE.md` (procédure de déploiement complète, incluant
compilation/déploiement EA — hors périmètre de cet outillage) et
`workspace/perplexity/assets/MARKET_OPEN_TEMPLATE.md` (checklist d'observation
temporelle T-30/T0/T+15/T+60) sans les dupliquer : ce document décrit uniquement les
scripts eux-mêmes et comment ils s'articulent avec les procédures déjà existantes.

**Ce que cet outillage ne fait pas** (rappel de périmètre) :
- Aucune modification de `core/v9/*` (logique métier de la chaîne cognitive).
- Aucune logique d'exécution d'ordre (interdit fondateur avant Phase 12).
- Aucune ouverture de la Phase 10 (fédération d'agents).
- Aucun LLM requis pour fonctionner — stdlib Python uniquement, aucune dépendance
  externe ajoutée.

## Vue d'ensemble des 4 scripts

| Script | Mode | Rôle |
|---|---|---|
| `scripts/v9_supervisor.py` | `--health` (+ dispatch `--boot`/`--market-open`/`--resume`) | Bibliothèque partagée et point d'entrée unique. Health snapshot immédiat. |
| `scripts/v9_bootstrap.py` | `--boot` | Procédure de reboot machine : checks bloquants, port stale, démarrage serveur. |
| `scripts/v9_market_open.py` | `--market-open` | Automatise T-30/T0 de `MARKET_OPEN_TEMPLATE.md` + plausibilité AUD + taux de stale. |
| `scripts/v9_session_resume.py` | `--resume` | Automatise la vérification mécanique de `REPRISE_TEMPLATE_CLAUDE.md`. |

Les trois scripts `v9_bootstrap.py` / `v9_market_open.py` / `v9_session_resume.py` sont
utilisables indépendamment, ou via le point d'entrée unique `v9_supervisor.py` :

```powershell
python scripts/v9_supervisor.py --health
python scripts/v9_supervisor.py --boot
python scripts/v9_supervisor.py --market-open
python scripts/v9_supervisor.py --resume
```

`v9_market_open.py` réutilise la séquence de `v9_bootstrap.run_boot()` (pas de
duplication de la logique port/serveur) avant d'ajouter ses vérifications propres à
l'ouverture marché.

## `scripts/v9_supervisor.py` — bibliothèque partagée

Fournit, réutilisé par les 3 autres scripts :
- **Gestion de port stale** (`ensure_port_free`) : distingue un port occupé par notre
  propre serveur de capture (suivi par `logs/v9_capture.pid`, jamais touché) d'un
  process stale sans PID file correspondant (incident récurrent, voir
  `workspace/perplexity/INCIDENTS.md` 2026-07-05 « Process `capture_server` bloqué sur
  le port 31685 ») — celui-ci est arrêté automatiquement (`taskkill` sur Windows).
- **Démarrage du serveur de capture en arrière-plan** (`start_capture_server_background`) :
  variante non bloquante de `deploy_v9.py --start`, écrit le même PID file — donc
  `deploy_v9.py --status`/`--stop` restent utilisables pour piloter ce process.
- **Health snapshot** (`read_health_snapshot`) : réutilise telles quelles les
  vérifications bloquantes de `scripts/deploy_v9.py` (`check_python_version`,
  `check_modules_importable`, `check_db`), ajoute l'état du port, du serveur, du
  calendrier marché (`core/v9/market_calendar.py`) et les compteurs DB.
- **Génération de mini-checkpoint** (`generate_mini_checkpoint`) — voir section dédiée
  ci-dessous.
- **Logging partagé** (`setup_logging`) : un seul fichier `logs/v9_ops.log` (distinct de
  `logs/v9_capture.log`, propre au serveur de capture), format horodaté, console UTF-8
  reconfigurée pour éviter l'`UnicodeEncodeError` cp1252 déjà documenté (voir
  `workspace/perplexity/INCIDENTS.md`).

## `scripts/v9_bootstrap.py --boot`

Automatise l'étape 3 de `V9_DEPLOYMENT_GUIDE.md` et le §T-30 de
`MARKET_OPEN_TEMPLATE.md` :
1. Vérifications bloquantes (Python 3.11+, modules `core/v9/` importables, DB + 5 tables).
2. Libération du port d'écoute si un process stale l'occupe.
3. Démarrage du serveur de capture en arrière-plan (sauf s'il tourne déjà, ou
   `--skip-start`).
4. Observation initiale (health snapshot post-démarrage).
5. Mini-checkpoint automatique (kind=`boot`).

```powershell
python scripts/v9_bootstrap.py --boot              # sequence complete
python scripts/v9_bootstrap.py --boot --dry-run    # verifications seules, aucun demarrage
python scripts/v9_bootstrap.py --boot --skip-start # ne demarre pas le serveur meme inactif
```

Code de sortie : `0` succès, `1` échec bloquant (checks, port non libérable, serveur ne
répond pas après démarrage).

## `scripts/v9_market_open.py --market-open`

Automatise la partie mécanique de `MARKET_OPEN_TEMPLATE.md` T-30/T0 :
1. Statut calendrier marché (avertissement non bloquant si le marché est fermé —
   permet une préparation avant l'heure réelle d'ouverture).
2. Séquence `v9_bootstrap.run_boot()` (checks/port/serveur).
3. Plausibilité AUD (doit rester entre EUR et NZD ± 15 unités par défaut,
   `--aud-tolerance` pour ajuster — détecte une inversion de buffer SDI, voir
   `ea/V9_Sonde_README.md` section 4).
4. Taux de stale sur `forces_snapshots`.
5. Mini-checkpoint automatique (kind=`market_open`), sections T-30/T0 pré-remplies.

```powershell
python scripts/v9_market_open.py --market-open
python scripts/v9_market_open.py --market-open --aud-tolerance 20
```

**Ce que ce script ne remplace pas** : `scripts/validate_ea_output.py` (validation
détaillée de la sonde EA) et `scripts/live_integration_test.py` (test d'intégration
complet sur DB de test dédiée) restent à lancer manuellement en complément, ainsi que
les observations T+15/T+60 de `MARKET_OPEN_TEMPLATE.md` (`v9_dashboard.py --watch ...`,
`v9_calibration.py --stats`), qui exigent d'attendre le temps réel écoulé et un
jugement humain — le mini-checkpoint généré liste explicitement ces suites dans sa
section « Suite ».

## `scripts/v9_session_resume.py --resume`

Automatise la vérification mécanique de
`workspace/perplexity/REPRISE_TEMPLATE_CLAUDE.md` :
1. Existence des documents de continuité, dans l'ordre imposé (`BOARD.md`,
   `docs/CACHE_BOARD.md`, `docs/STATE.md`, `ACTIVE_TASKS.md`,
   `memory/DECISIONS_LOG.md`).
2. Détection des checkpoints référencés par `docs/STATE.md` mais absents du dépôt
   (rupture de continuité au sens du gabarit de reprise).
3. État git (branche, dernier commit, `git log --oneline -10`, working tree propre ou non).
4. Health snapshot système.
5. Mini-checkpoint automatique (kind=`resume`), sauf `--no-checkpoint`.

```powershell
python scripts/v9_session_resume.py --resume
python scripts/v9_session_resume.py --resume --no-checkpoint
```

Code de sortie : `0` continuité mécanique intacte, `2` rupture détectée (fichier
manquant ou checkpoint référencé introuvable — reconstruire l'état depuis `git` avant
de poursuivre, ne rien deviner, conformément à `REPRISE_TEMPLATE_CLAUDE.md`).

**Ce script ne lit ni n'interprète le contenu métier** des documents de continuité
(aucun LLM requis) — seulement leur présence et les références de fichiers qu'ils
contiennent. La lecture/synthèse de fond reste la responsabilité de l'opérateur ou de
la session Claude qui reprend le travail.

## Mini-checkpoint automatique — décision de réutilisation du gabarit existant

Aucun nouveau gabarit n'a été créé : `generate_mini_checkpoint()` remplit
**telles quelles** les 5 sections du gabarit déjà défini dans
`workspace/perplexity/assets/CHECKPOINT_TEMPLATE.md` §« Mini-checkpoint (usage
workspace uniquement) » (Contexte / Observé / Écart vs attendu / Action immédiate /
Suite), pour respecter `docs/DOC_GOVERNANCE.md` règle 8 (pas de duplication de contenu
entre documents). Les fichiers générés sont écrits dans
`workspace/perplexity/mini_checkpoints/{horodatage}_{kind}.md` (jamais dans
`docs/checkpoints/`, réservé aux checkpoints de phase officiels) et n'ont pas besoin
d'entrée dans `docs/DOC_REGISTRY.yml`, conformément à la règle de portée du gabarit
source.

Les sections auto-remplies (`Observé`) sont des faits bruts (health snapshot, git,
plausibilité AUD, taux de stale) — jamais d'interprétation. Les sections qui exigent un
jugement humain (`Action immédiate`, `Suite` dans le cas général) restent au format
« à compléter par l'opérateur » quand aucune anomalie mécanique n'a été détectée.
Rappel de la règle de bascule du gabarit source : si un mini-checkpoint révèle une
décision structurante ou un correctif de fond, il ne reste pas dans le workspace — il
déclenche un vrai checkpoint de phase (`docs/checkpoints/CHECKPOINT_TEMPLATE.md`) et
une mise à jour de `docs/STATE.md`.

L'opérateur reste responsable d'archiver ou de purger périodiquement
`workspace/perplexity/mini_checkpoints/` (aucune rotation automatique — ce n'est pas un
répertoire de logs).

## Diagnostic

| Symptôme | Vérification |
|---|---|
| `--boot` échoue à l'étape « verifications bloquantes » | Voir le détail imprimé (repris de `deploy_v9.py --check`) — Python/modules/DB |
| Port non libérable (`ensure_port_free` renvoie `False`) | `find_pid_on_port` n'a pas trouvé de PID (plateforme non-Windows, ou parsing `netstat` en échec) — vérifier manuellement avec `netstat -ano \| findstr :31685` |
| Serveur démarré mais `is_server_running()` renvoie faux juste après | Vérifier `logs/v9_capture.log` — le process a pu crasher immédiatement (import, port déjà repris entre-temps) |
| `--market-open` signale un AUD hors intervalle | Voir `ea/V9_Sonde_README.md` section 4 (diagnostic buffers SDI) — ne jamais modifier le code de l'EA |
| `--resume` renvoie exit code 2 | Un fichier de continuité ou un checkpoint référencé par `STATE.md` est absent — reconstruire l'état depuis `git log`/`git status` avant de poursuivre, ne rien deviner |
| Caractères accentués mal affichés dans la console | Cosmétique (encodage terminal Windows/cp1252) — les fichiers écrits sur disque (logs, mini-checkpoints) restent en UTF-8 correct |

## Tests

`tests/test_v9_supervisor.py`, `tests/test_v9_bootstrap.py`, `tests/test_v9_market_open.py`,
`tests/test_v9_session_resume.py` — fonctions pures et orchestration mockée (aucun test
ne démarre un vrai serveur de capture, ne tue un vrai process, ni ne touche
`data/v9_forces.db`/`logs/v9_capture.pid` réels).
