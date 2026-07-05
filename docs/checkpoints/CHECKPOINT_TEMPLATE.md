# CHECKPOINT_{YYYYMMDD}_V9_{NOM_COURT}

<!--
Gabarit de checkpoint. Copier ce fichier vers
docs/checkpoints/CHECKPOINT_{YYYYMMDD}_V9_{NOM_COURT}.md et remplir chaque section.
Un checkpoint est obligatoire à la clôture de chaque phase (voir DOC_GOVERNANCE.md).
Supprimer ce commentaire avant de committer le checkpoint rempli.
-->

## Date
{YYYY-MM-DD}

## Contexte
Pourquoi ce checkpoint existe : quelle phase/branche/worktree, quel était l'état avant,
quel manque ou objectif a motivé ce travail. 2-4 phrases, factuel.

## Livrables

### 1. `chemin/vers/fichier_1.py`
Rôle, fonctions/classes clés, décisions de design notables. Un sous-titre par livrable
significatif (module, table DB, script, doc).

### 2. `chemin/vers/fichier_2.py`
...

### N. `tests/test_xxx.py`
Nombre de tests, ce qu'ils couvrent, total cumulé de tests du repo après ce checkpoint.

## Décisions de design assumées
Choix qui méritent d'être tracés (pourquoi cette heuristique plutôt qu'une autre, pourquoi
ce seuil, pourquoi cette dépendance/déréférence entre couches). Une puce par décision.

## Écarts assumés vis-à-vis de la doctrine ou des formats
Si un format (`docs/architecture/formats/FORMAT_*.md`) ou une règle de doctrine n'a pas été
respecté à la lettre, le dire explicitement ici avec la justification — jamais silencieusement.

## Points ouverts
Ce qui reste non résolu, non bloquant pour clore ce checkpoint mais à traiter plus tard.
Préciser si le point est levé à une fusion/checkpoint ultérieur (et lequel, une fois connu).

## Validation
- [ ] Tests : `pytest` — X tests, tous verts (préciser le delta vs checkpoint précédent)
- [ ] `docs/STATE.md` mis à jour
- [ ] `docs/DOC_REGISTRY.yml` mis à jour si un nouveau document a été créé
- [ ] Doc de couche (`docs/phases/PHASEn_*.md`) créée ou mise à jour si pertinent

## Prochaine étape
Ce qui suit immédiatement ce checkpoint (référencer `docs/ROADMAP.md` si applicable).
