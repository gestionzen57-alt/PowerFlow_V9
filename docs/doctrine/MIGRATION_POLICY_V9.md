# MIGRATION_POLICY_V9.md

## But
Migrer de V8 vers V9 proprement, sans empilement ni dette implicite.

## Principe
V8 est une source d'apprentissage et d'archives.
V9 est la nouvelle base de travail.

## Règle absolue
Rien n'entre dans V9 sans être classé dans une de ces 4 catégories :

### A — Reprendre tel quel
Élément sain, clair, cohérent, encore utile.

### B — Réécrire avant reprise
Élément utile mais pollué par ancienne structure, ancienne stack ou mauvaise formulation.

### C — Archiver
Élément historiquement utile mais non pertinent pour V9.

### D — Re-spécifier depuis zéro
Élément trop confus, trop couplé, ou trop biaisé pour être sauvé.

## Audit obligatoire
Pour chaque élément candidat à migration :
- origine
- utilité
- dette
- dépendances
- place dans la chaîne cognitive
- décision A/B/C/D

## Interdits
- copier-coller massif
- reprise implicite de mémoire
- reprise d'un skill sans audit
- reprise d'un flux technique non documenté

## Ordre recommandé
1. doctrine
2. lexique
3. mémoire
4. structure agents/skills
5. assets
6. scripts
7. éléments métiers sélectionnés

## Critère de succès
La migration est réussie si V9 reste compréhensible sans lire V8.