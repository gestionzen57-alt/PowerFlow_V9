# INCIDENTS — journal opérationnel

Journal des incidents opérationnels (bugs marquants, comportements inattendus,
blocages temporaires résolus) pour continuité entre sessions. Ne remplace pas le détail
technique déjà consigné dans les checkpoints (`docs/checkpoints/*.md`) — n'en garde que
le rappel utile à la reprise.

## Format d'entrée
```
### AAAA-MM-JJ — Titre court
- Symptôme :
- Cause :
- Correctif :
- Référence : (commit / checkpoint / doc)
```

## Historique

### 2026-07-05 — Non-idempotence de `regenerate_chain.py`
- Symptôme : un rejeu de `scripts/regenerate_chain.py` a dupliqué en production les
  lignes des tables dérivées (`scenes`/`behaviors`/`windows`/`exploitability`/... —
  2388 lignes au lieu de 1194 attendues).
- Cause : les identifiants (`scene_id`, `behavior_id`, etc.) sont générés avec un
  suffixe aléatoire à chaque appel, sans clé métier protégeant contre un rejeu en
  double (seule `regime_snapshots` avait une contrainte UNIQUE réelle).
- Correctif : ajout de `--replace-derived` (delete ciblé des tables dérivées, jamais
  `forces_snapshots`) et refus par défaut (exit 2) si la DB dérivée n'est pas vide ;
  `--dry-run` pour inspecter sans écrire.
- Référence : commit `c83423e`,
  `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`.
- Action opérateur restante : purger les ~245k lignes dérivées déjà dupliquées dans
  `data/v9_forces.db` via `--replace-derived` (non fait automatiquement).

### 2026-07-05 — Process `capture_server` bloqué sur le port 31685
- Symptôme : un ancien process `capture_server` restait lié au port TCP 31685,
  empêchant le nouveau câblage de l'orchestrateur de prendre effet.
- Cause : process stale non arrêté proprement entre deux itérations.
- Correctif : arrêt manuel puis redémarrage du process.
- Référence : session Phase 9 (branche `feat/v9-foundation-clean`).

### 2026-07-05 — `UnicodeEncodeError` console Windows (cp1252)
- Symptôme : `UnicodeEncodeError` sur des scripts Python affichant caractères accentués
  et séparateurs de type box-drawing.
- Cause : la console Windows utilise le codepage cp1252 par défaut, incompatible avec
  certains caractères UTF-8.
- Correctif : `stream.reconfigure(encoding="utf-8", errors="replace")` sur stdout/stderr
  en début de script, bibliothèque standard uniquement.
- Référence : Phase 8 (`scripts/v9_dashboard.py`, `scripts/v9_calibration.py`,
  `scripts/v9_replay.py`).

### 2026-07-05 — 8 tests `test_behavior_analyzer.py` en échec (pré-existant, non lié à ce chantier)
- Symptôme : `pytest tests/test_behavior_analyzer.py` échoue sur 8 tests (transitions,
  point de rupture, phases, similarité) — reproductible en isolation, sans rapport avec
  le chantier d'automatisation en cours (`scripts/v9_supervisor.py` et consorts,
  aucun fichier `core/v9/*` touché par cette session).
- Cause : non investiguée par cette session (hors périmètre — aucune modification de
  `core/v9/behavior_analyzer.py` autorisée pour ce chantier d'outillage).
- Correctif : aucun (signalement uniquement). Session suivante : investiguer si
  régression réelle ou attente de test obsolète vis-à-vis d'un comportement de
  `core/v9/behavior_analyzer.py` modifié depuis l'écriture du test.
- Référence : branche `feat/v9-foundation-clean`, détecté pendant les tests de
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md`.

### 2026-07-05 — Fusion concurrente de branches de phase
- Symptôme : une session concurrente a fast-forward mergé `feat/v9-phase4-comportements`
  dans `feat/v9-foundation-clean` localement (non poussé), pendant qu'une autre session
  travaillait en parallèle.
- Cause/observation : plusieurs sessions Claude Code peuvent travailler simultanément
  sur des branches de phase différentes du même dépôt.
- Correctif : `git diff --no-index` contre les commits connus des branches sœurs avant
  de supposer qu'un fichier dirty est un nouveau travail — peut être un reliquat
  redondant d'une session concurrente.
- Référence : voir aussi `memory/LESSONS_LEARNED.md`.
