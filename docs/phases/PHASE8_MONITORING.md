# PHASE 8 — Monitoring

## Statut
✅ Terminée, branche `feat/v9-phase8-monitoring`, worktree `D:\Projet\V9_wt_monitoring`.

## Objectif
Outiller l'observation temps réel, la calibration et le replay — toujours en lecture seule
stricte sur `data/v9_forces.db`.

## Livrables
- `scripts/v9_dashboard.py` — dashboard terminal temps réel : statut marché/session (`MarketCalendar`), tableau des forces du dernier snapshot par TF, badges stale, compteurs par couche, blocs détaillés dernier comportement/fenêtre/exploitabilité. CLI `--interval N` (défaut 5), `--once`, `--watch comportements|fenetres`. Couleurs ANSI brutes (pas de `rich`/`colorama`), UTF-8 forcé sur stdout/stderr (évite `UnicodeEncodeError` en console Windows cp1252)
- `scripts/v9_calibration.py` — `--stats`, `--export csv|json` (dump vers `output/`, ajouté à `.gitignore`), `--analyze` (distributions + suggestions de seuils `COALITION_THRESHOLD`/`ANTAGONISM_THRESHOLD`/`PLIURE_THRESHOLD`/`STALE_THRESHOLDS_MS`, jamais appliquées automatiquement)
- `scripts/v9_replay.py` — `--list`, `--show <id>`, `--compare <id1> <id2>` (score de similarité heuristique documenté), `--search key=value`
- `tests/test_dashboard.py` — 21 tests
- `.gitignore` — ajout de `output/`

## Décisions notables
- Aucune logique d'exécution d'ordre, aucune écriture DB par les 3 scripts, aucune modification automatique de `config.py`.
- Suggestions de calibration basées sur des proxys observables (écart de force brut entre paires de devises) plutôt que sur une ré-implémentation exacte de la logique interne de `scene_builder.py`.

## Tests
21 tests (`test_dashboard.py`), portant le total à 139 (tous verts).

## Voir aussi
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE8.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE8.md)
