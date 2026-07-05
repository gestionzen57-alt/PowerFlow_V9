# CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT

## Date
2026-07-05

## Contexte
Post-clôture Phase 9 (branche `feat/v9-foundation-clean`), avant observation live du
marché. Risque opérationnel identifié : `scripts/regenerate_chain.py` n'était pas
idempotent — rejouer la chaîne cognitive sur une DB déjà peuplée dupliquait
silencieusement `scenes`/`behaviors`/`windows`/`exploitability`. Un `--dry-run` sur
`data/v9_forces.db` a confirmé le bug déjà matérialisé en production : ces quatre
tables comptaient 2388 lignes (= 2×1194) contre 1194 pour `signals`/`decisions` et
9552 (= 8×1194) pour `regime_snapshots` — preuve d'un rejeu antérieur partiellement
dupliqué. Ce checkpoint corrige la cause racine et sécurise le rejeu avant l'ouverture
du marché.

## Cause racine
`scene_id`, `behavior_id`, `window_id`, `exploitability_id`, `signal_id`,
`decision_id` et `evaluation_id` (`principle_evaluations`) sont tous générés avec un
suffixe aléatoire (`uuid.uuid4().hex[:6]`) à chaque appel de
`orchestrator.run_chain()`. Aucune de ces tables ne porte de contrainte UNIQUE liée au
snapshot source (`forces_snapshot_ref`/`scene_id_ref`/`behavior_id`/`window_id`/
`snapshot_id`) — seule `regime_snapshots` en a une (`UNIQUE(forces_snapshot_ref,
currency)`), ce qui la rend déjà idempotente via son `INSERT OR REPLACE`. Pour toutes
les autres, `INSERT OR IGNORE`/`INSERT OR REPLACE` porte sur l'ID généré aléatoirement,
qui ne collisionne jamais avec un rejeu précédent : chaque rejeu ajoute donc un jeu
complet de nouvelles lignes au lieu de remplacer ou ignorer les anciennes.

## Stratégie retenue
Introduire des clés métier + upsert dans sept modules de couche (`scene_db.py`,
`behavior_db.py`, `window_db.py`, `exploitability_db.py`, `signal_db.py`,
`decision_db.py`, `principle_db.py`) aurait été le fix le plus général, mais c'est un
chantier transverse touchant l'architecture de chaque couche cognitive — hors
périmètre de cette correction ciblée. Stratégie retenue à la place, confinée à
`scripts/regenerate_chain.py` :
- **Suppression ciblée + régénération complète** (`--replace-derived`) : vide les
  tables dérivées dans l'ordre `decisions → signals → principle_evaluations →
  regime_snapshots → exploitability → windows → behaviors → scenes`, jamais
  `forces_snapshots` (source) ni `principles` (catalogue YAML, pas un événement par
  snapshot), puis rejoue `run_chain` sur tous les snapshots non-stale.
- **Refus explicite par défaut** : si une seule table dérivée contient déjà des
  lignes et qu'aucun flag n'est passé, le script refuse (exit 2) plutôt que de
  dupliquer silencieusement — impose une décision explicite de l'opérateur.
- **`--dry-run`** : rapporte l'état des tables dérivées et ce qui serait fait, sans
  aucune écriture.

## Livrables

### 1. `scripts/regenerate_chain.py`
Ajout de `--replace-derived`, `--dry-run`, refus par défaut (exit code 2) si la DB
dérivée n'est pas vide. `main()` accepte désormais `argv`/`db_path`/`memory_dir` en
paramètres (au lieu de constantes figées) pour rester testable. Comportement de rejeu
normal (DB vide, premier run) inchangé.

### 2. `tests/test_regenerate_chain.py`
4 nouveaux tests : premier run sur DB vide peuple toutes les couches ; second run sans
flag refuse et ne modifie rien ; `--replace-derived` régénère sans doublons (comptes
identiques avant/après) ; `--dry-run` n'écrit jamais (DB vide ou déjà peuplée).

## Décisions de design assumées
- Pas de retouche aux schémas/écritures des sept modules de couche : le risque de
  régression sur la Phase 9 (tests, formats, orchestrateur) dépassait le bénéfice pour
  une correction ciblée sur le seul script de rejeu.
- Le refus par défaut s'applique dès qu'UNE SEULE table dérivée contient des lignes,
  même partiellement peuplée (état ambigu) — jamais de tentative de complétion
  partielle silencieuse.
- `principles` (catalogue) et `forces_snapshots` (source) ne sont jamais vidés, même
  avec `--replace-derived`.

## Écarts assumés vis-à-vis de la doctrine ou des formats
Aucun — le format de sortie de chaque couche (`FORMAT_*.md`) est inchangé, seul le
script de rejeu est modifié.

## Points ouverts
- La non-idempotence structurelle (absence de clé métier + upsert) reste présente
  dans `scene_db.py`/`behavior_db.py`/`window_db.py`/`exploitability_db.py`/
  `signal_db.py`/`decision_db.py`/`principle_db.py` : `capture_server.py` en
  production n'est pas concerné (un événement live = un seul appel `run_chain` par
  snapshot, jamais de rejeu), mais tout futur outil de rejeu/replay devra soit
  réutiliser `regenerate_chain.py --replace-derived`, soit répéter la même prudence.
- `data/v9_forces.db` contient encore la duplication historique (2388 au lieu de 1194
  pour scenes/behaviors/windows/exploitability) tant que `--replace-derived` n'a pas
  été exécuté manuellement par l'opérateur sur la DB de production (action destructive
  volontairement non automatisée par cette session).

## Validation
- [x] Tests : `pytest tests/ -q` — 218 tests, tous verts (214 précédents + 4 nouveaux)
- [x] `docs/STATE.md` mis à jour (note additive, Phase 9 non réécrite)
- [x] `docs/DOC_REGISTRY.yml` mis à jour (ce checkpoint)
- [ ] Doc de couche (`docs/phases/PHASEn_*.md`) — non applicable, correction d'outillage

## Prochaine étape
Exécuter `python scripts/regenerate_chain.py --replace-derived` sur `data/v9_forces.db`
avant l'ouverture du marché pour purger la duplication historique et repartir d'un état
propre — action laissée à l'opérateur (suppression de ~245k lignes dérivées,
confirmation explicite requise).
