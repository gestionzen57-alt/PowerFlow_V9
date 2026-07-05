# PHASE 1 — Formats

## Statut
✅ Terminée et fusionnée sur `feat/v9-foundation-clean`.

## Objectif
Spécifier les formats JSON des 5 couches cognitives et le contrat de mémoire associé,
avant tout code — architecture avant implémentation (doctrine).

## Livrables
- `docs/architecture/formats/FORMAT_FORCES.md` — format de sortie couche Forces (8 devises, 7 timeframes dont M1 séparé, STALE_GATE)
- `docs/architecture/formats/FORMAT_SCENES.md` — format de sortie couche Scènes (zone, coalitions, antagonismes, cinématique locale, confluences MTF)
- `docs/architecture/formats/MEMORY_CONTRACT.md` — contrat de mémoire Forces ↔ Scènes (cycle hypothèse → validation/rejet)
- `docs/architecture/formats/FORMAT_COMPORTEMENTS.md`
- `docs/architecture/formats/FORMAT_FENETRES.md`
- `docs/architecture/formats/FORMAT_EXPLOITABILITE.md`

## Décisions notables
- Produits en deux sessions parallèles (A : formats amont Forces/Scènes/mémoire ; B : formats aval Comportements/Fenêtres/Exploitabilité).
- Revue CEO des 6 formats : fond validé, 3 corrections identifiées (scene_source de Comportements, `schema_version` manquant sur les 3 formats amont, contrat mémoire non étendu aux couches aval) — appliquées sur `fix/v9-phase1-review` puis fusionnées.

## Tests
13 blocs JSON valides (pas de tests unitaires Python à ce stade — Phase 1 est purement spécification).

## Voir aussi
[docs/checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1A.md](../checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1A.md),
[docs/checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1B.md](../checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1B.md),
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE1_COMPLETE.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE1_COMPLETE.md)
