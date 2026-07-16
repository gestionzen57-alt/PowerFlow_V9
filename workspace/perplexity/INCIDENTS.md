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

### 2026-07-16 — Taux stale M1/M5 élevés = artefact historique (NON-INCIDENT, diagnostic)
- Symptôme : audit global signale M1 stale 50.0 %, M5 stale 68.9 %, M15 31.8 %
  (M30/H1/H4/D1 = 0 %). Suspicion d'un seuil `STALE_THRESHOLDS_MS` trop court
  pour M1/M5 ou d'un flux EA insuffisant.
- Diagnostic (requêtes `data/v9_forces.db`) :
  - Les % globaux sont dominés par un **burst historique** les **2026-07-07/08**.
    Ce jour-là M5 a capté **28 343 snapshots** (76.4 % stale) contre ~300/jour en
    régime normal — soit ~90 % de tous les snapshots M5 de la base. M1 07-07/08 :
    95–99 % stale. Ce volume ~100× la normale = reconnexion EA en rafale / rejeu
    de données à timestamps anciens, pas un régime nominal.
  - **Flux live sain** : sur les dernières 24 h, M1 = 1.6 %, M5 = 2.1 %, M15 = 0.7 %
    stale ; sur les 2 dernières heures M1 = 0.57 %, M5 = 0.7 %. Depuis le 2026-07-14
    tous les TF sont < 3 % stale avec le **même** seuil.
- Cause : pollution d'agrégat par l'incident de capture du 07-07/08. **Ni un problème
  de seuil, ni un problème de flux actuel.**
- Correctif : **aucune modification de code**. Le seuil M5=35 s / M1=5 s est
  correctement calibré — le baisser masquerait la vraie péremption lors d'incidents
  réels (doctrine FREE-FIRST : marquer, jamais cacher). Action de suivi éventuelle :
  purge/segmentation des snapshots 07-07/08 si l'on veut des agrégats représentatifs
  du régime nominal (hors périmètre de cette session).
- Référence : session 2026-07-16, `docs/DECISIONS_LOG.md` (Chantier A) ;
  `core/v9/config.py::STALE_THRESHOLDS_MS`.

### 2026-07-05 — Non-idempotence de `regenerate_chain.py` (RÉSOLU)
- Symptôme : un rejeu de `scripts/regenerate_chain.py` a dupliqué en production les
  lignes des tables dérivées (`scenes`/`behaviors`/`windows`/`exploitability`/... —
  2388 lignes au lieu de 1194 attendues).
- Cause : les identifiants (`scene_id`, `behavior_id`, etc.) sont générés avec un
  suffixe aléatoire à chaque appel, sans clé métier protégeant contre un rejeu en
  double (seule `regime_snapshots` avait une contrainte UNIQUE réelle).
- Correctif : ajout de `--replace-derived` (delete ciblé des tables dérivées, jamais
  `forces_snapshots`) et refus par défaut (exit 2) si la DB dérivée n'est pas vide ;
  `--dry-run` pour inspecter sans écrire.
- Purge exécutée le 2026-07-06 : 262 812 lignes dupliquées supprimées, 1 296 snapshots
  régénérés proprement (0 erreur, latence moyenne 248.50ms).
- Référence : commit `c83423e`,
  `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`.

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

### 2026-07-06 — 8 tests `test_behavior_analyzer.py` en échec (RÉSOLU)
- Symptôme : `pytest tests/test_behavior_analyzer.py` échouait sur 8 tests (transitions,
  point de rupture, phases, similarité) — reproductible en isolation.
- Cause : le timestamp du comportement utilisait `datetime.now()` au lieu du timestamp
  de la scène source. `_load_behavior_history` filtre par `timestamp < scene.timestamp`,
  donc les comportements précédents n'étaient jamais retrouvés, rendant toutes les
  transitions/comparaisons muettes.
- Correctif : `behavior_analyzer.py` ligne 281 — `datetime.now(timezone.utc).isoformat()`
  remplacé par `scene.timestamp`. 269 tests, tous verts.
- Référence : commit `eec353c`.

### 2026-07-06 — Dashboard affiche « Marché : FERMÉ » pendant que le live tourne (bug DST US)
- Symptôme : `scripts/v9_dashboard.py` peut afficher « Marché : FERMÉ » (et
  `scripts/v9_supervisor.py --health` / mini-checkpoints afficher `Marche : FERME`) alors
  que le pipeline de capture reçoit réellement des snapshots frais.
- Cause : `core/v9/market_calendar.py` ancre l'ouverture/fermeture sur **22h UTC fixe**
  (`config.py` : `MARKET_OPEN_UTC_HOUR`/`MARKET_CLOSE_UTC_HOUR`), calibré sur l'heure
  d'hiver US (EST, UTC-5). Le marché forex réel ouvre/ferme à 17h heure de New York,
  soit **21h UTC pendant la période DST US** (~mi-mars à début novembre, EDT UTC-4).
  Chaque dimanche/vendredi en DST, il existe donc une fenêtre 21h-22h UTC où
  `is_market_open()` répond FERMÉ à tort. Reproduit :
  `MarketCalendar.is_market_open(2026-07-05 21:30 UTC)` → `False` alors que le marché
  réel est déjà ouvert (17h30 EDT New York).
- Correctif appliqué (Phase 9.5, observabilité uniquement — **le calendrier canonique
  n'a pas été modifié**, décision explicite) : `scripts/v9_supervisor.py` expose
  `market_status_warning()`, qui compare le statut canonique à la fraîcheur du dernier
  `forces_snapshots` (non-stale, âge < 90s). Si le calendrier dit FERMÉ mais qu'une
  activité live récente est détectée, un avertissement explicite apparaît dans
  `v9_dashboard.py`, `v9_supervisor.py --health`, les mini-checkpoints (`--boot`/
  `--market-open`/`--resume`) et le log de `v9_market_open.py`. 11 nouveaux tests
  (`tests/test_v9_supervisor.py`, `tests/test_dashboard.py`), 269 tests au total :
  261 verts, 8 échecs pré-existants inchangés (voir entrée ci-dessous).
- Action non faite (hors périmètre, décision utilisateur) : corriger le calcul canonique
  lui-même (ex. ancrer `is_market_open`/`next_open` sur `America/New_York` via
  `zoneinfo`, DST-safe par construction, comme `paris_to_utc`). Casserait 7 tests de
  `tests/test_market_calendar.py` qui figent l'hypothèse 22h UTC fixe et rouvrirait une
  décision Phase 7 canonisée — chantier dédié recommandé, hors Phase 9.5.
- Référence : `docs/deployment/V9_AUTOMATION_RUNBOOK.md` §« Anomalie connue »,
  branche `feat/v9-foundation-clean`.

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
