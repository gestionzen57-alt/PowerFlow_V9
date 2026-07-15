---
name: powerflow-auto-doc
description: "Doctrine d'auto-écriture Opus — MAJ atomique BORD_M3/JOURNAL/STATE/INDEX/CHECKPOINT immédiatement après chaque bloc livré"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, doctrine, auto-doc, governance, atomic-write]
statut: actif
derniere_maj: 2026-07-09
note_chantier: aligne au HEAD b256faa (878 tests, supervision H24 LIVE)
---
# Powerflow Auto Doc

# PowerFlow Auto-Doc

## Rôle
Doctrine d'écriture automatisée des docs de gouvernance. Réflexe immédiat après chaque livraison de code.

## Quand charger
- Fin de chaque sous-tâche (pas fin de session).
- Avant `git commit` : vérifier que la doc est synchronisée.
- Søn dit "documente" ou "trace".

## MAJ atomique obligatoire (5 fichiers)
1. `docs/STATE.md` — décision #N ajoutée dans tableau.
2. `docs/JOURNAL.md` — bloc du jour (1 max/jour) avec liens checkpoints.
3. `docs/index/INDEX_DOCS.md` — ajout nouveau doc actif.
4. `docs/BORD_M3.md` — décision résumée 1 ligne.
5. `docs/checkpoints/CHECKPOINT_YYYY_MM_DD_SLUG.md` — preuve détaillée.

## Workflow
```
[CODE livré] → tests verts → MAJ 5 docs → git add → commit → push
```
**Pas de "je commit après"** — refusé par Søn.

## Format décision dans STATE.md
```markdown
### #158 — Phase 7 récit causal (livré 2026-06-25)
**Contexte** : besoin chaîne causale H4→M5 pour briefing live.
**Livré** : core/pf_scene_timeline.py (260L), 12 tests pytest.
**WR avant/après** : N/A (outillage).
**Prochaine étape** : Phase 8 recalibration.
```

## Format bloc JOURNAL
```markdown
## 2026-06-25 — Phase 7 récit causal + UNKNOWN fix
- 09:00 Fix UNKNOWN=578 (#157) — 5 tests OK
- 14:00 Phase 7 livré — 12 tests OK
- 16:00 Checkpoint CHECKPOINT_2026_06_25_RECIT_CAUSAL.md
```

## Pièges
- Oublier front-matter YAML dans nouveau doc → considéré INACTIF.
- MAJ STATE sans MAJ INDEX → désynchro (cf. `INDEX_DOCS.md` source unique).
- Commit sans MAJ → hook bloque push (workaround: `git pull --no-rebase`).

