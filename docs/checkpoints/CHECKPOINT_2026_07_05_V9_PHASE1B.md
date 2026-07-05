# CHECKPOINT_2026_07_05_V9_PHASE1B

## Contexte
Session parallèle B (Phase 1B) : définir les formats JSON et interfaces des
couches aval du système cognitif V9 — Comportements, Fenêtres,
Exploitabilité — sans coder aucun module métier ni introduire de logique
d'exécution d'ordre. Travail mené en isolation sur la branche
`feat/v9-phase1-formats-aval`, via un worktree dédié, pendant qu'une session
parallèle (A) travaillait simultanément sur `feat/v9-phase1-formats-amont`
dans le répertoire de travail principal `D:\Projet\V9`.

## Décisions prises
- Les 3 formats respectent strictement l'ordre cognitif officiel
  (Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution
  éventuelle) et référencent chacun explicitement leur couche amont
  immédiate.
- Le vocabulaire natif de `docs/lexicon/LEXICON_V9.md` est utilisé comme
  seule source de termes (force, scène, comportement, fenêtre, zone,
  coalition, antagonisme, cinématique, orchestration, replay,
  exploitabilité).
- Enum `comportement.qualification` fixé à 12 valeurs (maintien, bascule,
  lutte_forces, contraction, extension, tension, rupture, reequilibrage,
  annulation, preparation_ouverture_fenetre, seconde_bosse,
  rotation_leadership) — aucune extension sans révision du lexique.
- Règle explicite « pas de fenêtre est une réponse valide » et « pas de
  fausse fenêtre sans comportement confirmé » codifiées dans
  `FORMAT_FENETRES.md`.
- Règle explicite « jamais sans validation des couches amont » et
  « l'absence d'exploitabilité est une réponse valide » codifiées dans
  `FORMAT_EXPLOITABILITE.md`.
- Aucun champ d'exécution (taille de position, prix d'ordre, routage
  broker) dans aucun des 3 formats — hors périmètre strict de cette session.

## Livrables
- `docs/architecture/formats/FORMAT_COMPORTEMENTS.md`
- `docs/architecture/formats/FORMAT_FENETRES.md`
- `docs/architecture/formats/FORMAT_EXPLOITABILITE.md`
- `docs/STATE.md` mis à jour
- `docs/CACHE_BOARD.md` mis à jour

Chaque document contient : structure JSON champ par champ (types,
contraintes, obligatoire/optionnel), enums documentés (code JSON + libellé
natif), règles explicites de gouvernance de la couche, et au moins un
exemple JSON complet et syntaxiquement validé (5 blocs JSON au total,
validés via `json.loads`).

## Ce qui est explicitement refusé
- Toute logique d'exécution d'ordre dans ces 3 formats.
- Toute référence à V8 (formats conçus natifs V9).
- Toute fenêtre ou exploitabilité positive sans confirmation de la couche
  amont correspondante (règles de gate explicites dans chaque doc).

## Note d'isolation de session
La branche de départ `feat/v9-phase1-formats-amont` portait des
modifications non commitées d'une session parallèle active
(`docs/architecture/IMPLEMENTATION_ROADMAP_V9.md`, +488/-52). Pour éviter
tout risque de collision (changement de HEAD partagé dans le même
répertoire de travail), cette session a créé un worktree Git isolé
(`git worktree add ... -b feat/v9-phase1-formats-aval <commit HEAD>`) plutôt
que de basculer de branche dans le répertoire partagé. Aucun fichier de la
session A n'a été lu depuis son état non commité, ni modifié.

## Prochaine marche
- Faire relire les 3 formats par la session en charge du squelette agentique
  (Phase 2 — orchestrator / behavior-analyst / window-gate /
  replay-confronter) avant toute implémentation Python.
- Vérifier si un format Scène formel existe déjà (couche amont de
  Comportements) ; sinon, le spécifier en priorité pour fermer la chaîne
  Forces → Scènes → Comportements.
- Fusionner `feat/v9-phase1-formats-aval` avec `feat/v9-phase1-formats-amont`
  (ou vers la branche par défaut) une fois les deux chantiers parallèles
  clos, en arbitrant les éventuels conflits sur les documents partagés
  (STATE.md, CACHE_BOARD.md, IMPLEMENTATION_ROADMAP_V9.md).

## Risque principal
Divergence entre les formats aval définis ici et le contenu en cours
d'écriture côté amont (roadmap, doctrine) sur la branche parallèle, non
visible depuis cette session car non commité au moment de l'exécution.

## Contre-mesure
Ce checkpoint documente explicitement le point de départ (commit HEAD) et
le mécanisme d'isolation utilisé, pour permettre une fusion propre et
auditable des deux chantiers parallèles.
