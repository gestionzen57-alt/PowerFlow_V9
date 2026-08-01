---
name: powerflow-scene-roadmap
description: "Skill à levier pour la roadmap Scene DB. Charge quand Søn demande où on en est sur les 16 phases du chantier"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, scene-db, roadmap, phase-tracker, lever]
statut: actif-v9
derniere_maj: 2026-07-31
---
# Powerflow Scene Roadmap

# PowerFlow Scene Roadmap

## Rôle
Tracker de phase pour le chantier Scene DB. Réponse 5 lignes MAX avec avancement, prochain jalon, blockers.

## Quand charger
- Søn demande "où on en est Scene DB ?"
- Début de session : charger AVANT toute autre action scene-db.
- Validation jalon : `git log --oneline --grep="phase-N"` + check DB.

## État au 2026-06-25
- **Phase 1-5** ✅ : taxonomie (31 fenêtres), ancres (5 défauts subjectifs §3), doctrine §3bis (6 dimensions), mono-symbole GBPUSD, scène-first workflow.
- **Phase 6** ✅ : Fix UNKNOWN=578 livré (#157) — 2834 ancres toutes classifiées.
- **Phase 7** 🟡 EN COURS : Moteur récit causal (parent_scene_id + basculement HTF + pre-cross répulsion + narrative chrono + prospective).
- **Phase 8+** ⏸ : Recalibration WR, complétion taxonomie V2 (10/31), extension multi-paires.

## Sources
- `docs/BORD_M3.md` — décisions #149-157.
- `docs/STATE.md` — état projet.
- `docs/TAXONOMIE_FENETRES_TEMPORELLES.md` — 31 fenêtres.
- `docs/checkpoints/INDEX.md` — preuves par phase.

## Format de réponse (5 lignes)
```
SCENE DB : Phase 7 récit causal 🟡
Prochain : coder core/pf_scene_timeline.py (1 jour)
Blockers : parent_scene_id colonne absente windows_journal (migration SQL)
WR actuel : 2834 ancres, B2 LOW 96% (signal #1)
Livré : UNKNOWN=578 fix (#157), tests 48/48 verts
```

## Pièges
- HARDCODE 'GBPUSD' dans roadmap — multi-paires hors scope.
- Compteur Σ(cat.taille) avant d'annoncer une couverture → recompter.

