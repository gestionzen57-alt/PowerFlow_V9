# MEMORY_CANON — éléments stables du contexte V9

Synthèse des éléments qui ne changent pas d'une session à l'autre. Renvoie vers les
documents pivots pour le détail — ne duplique jamais leur contenu complet
(`docs/DOC_GOVERNANCE.md` règle 8).

## Doctrine durable (index — détail dans `docs/DOCTRINE.md` et `docs/doctrine/*.md`)
**30 règles immuables** au 2026-07-12 (progression depuis les 19 règles initiales de la
canonisation Phase 9 — détail intégral et à jour dans `docs/DOCTRINE.md`, ne pas dupliquer
ici). Parmi les ajouts notables : règle 28 (Hermes = opérateur git unique, 2026-07-07 ; assouplie 2026-07-14 — délégation du push sur instruction directe de Søn),
règle 29 (lecture scène-complète + zone-type × session), règle 30 (apprentissage
conditionnel WIN/LOSS, seuils progressifs 5/20/50/200).
- Git est la source de vérité, jamais une mémoire de conversation.
- Une seule source de vérité par sujet (pas de doctrine concurrente).
- La migration métier précède l'agentification.
- Autonomie progressive, seulement après stabilité live.
- Aucune dépendance bloquante à un LLM/provider spécifique pour le cœur métier.
- Architecture agents/skills gelée tant que la phase métier en cours n'est pas
  canonisée et stable en live.
- Le code est présumé correct avant la documentation en cas de divergence
  (`docs/DOC_GOVERNANCE.md` §« Règle absolue »).
- Aucune logique d'exécution d'ordre avant la Phase 12 (interdit fondateur).
- MT4 (forces) dicte, MT4 (ticks) confirme, jamais l'inverse (règle 10).

## Décision fondatrice du projet
V9 part d'un dossier vide. Aucune mémoire, skill, convention ou workflow hérité de
V8/Hermes n'est repris implicitement — toute reprise passe par un audit explicite
(voir `docs/architecture/audit_v8_v9_migration.md`).

## Squelette cognitif officiel — 10 couches
Forces(1) → Scènes(2) → Comportements(3) → Fenêtres(4) → Exploitabilité(5) → Régime(6) →
Principes(7) → Signal(8) → Décision(9) — couches 6-9 ajoutées Phase 9, toutes livrées et
fusionnées. Exécution(10) éventuelle = Phase 12, explicitement non ouverte (interdit
fondateur, HITL obligatoire avant tout ordre réel).

## État d'avancement fondamental (au 2026-07-12 — resync Brief R)
- Phases 1 à 9 + 9.5 à 9.10 + 13 + 13.2 terminées et fusionnées sur `feat/v9-foundation-clean`.
- **1018 tests, tous verts** (0 régression, règle 7). Progression depuis 218 tests
  (2026-07-05) : chaque phase a ajouté sa propre couverture, jamais de test supprimé
  sans justification tracée.
- Gouvernance documentaire canonisée (`docs/ARCHITECTURE.md`, `docs/DOCTRINE.md`,
  `docs/LEXIQUE.md`, `docs/NOMENCLATURE.md`, `docs/ROADMAP.md`, `docs/DOC_GOVERNANCE.md`,
  `docs/DOC_REGISTRY.yml`).
- **Gaps historiques résolus** : `zone_diagnostics` alimentée (ZoneDetector + grammaire
  complète, 2026-07-06) ; marquage replay vs live posé (colonne `source_type`, 8 tables
  dérivées, 2026-07-06) ; index manquant `decisions.decision_id` corrigé (Brief O1,
  2026-07-12 — root cause du bloqueur de résolution DYNAMIC) ; colonnes
  `resolution_strategy`/`resolution_details` enfin enregistrées dans le module de
  migration `decision_db.py` (Brief O5, 2026-07-12 — étaient ajoutées par ALTER TABLE
  ad-hoc depuis Phase 13.2 sans jamais être tracées dans le code de migration).
- Phase 10 (fédération d'agents) et Phase 12 (exécution d'ordre réelle) restent
  explicitement gelées — aucune date planifiée, stabilisation live insuffisante.

## Invariants de données stables
- **`paper_trade_idempotency`** (Motion #32, 2026-07-20) : un même
  `(snapshot_id, direction, principes_source)` = une même décision = **un seul**
  paper-trade. Garanti par `UNIQUE INDEX idx_pt_snap_dir_princ` sur `paper_trades`
  + garde applicative `PaperTradeLogger.log_open` (`ON CONFLICT DO NOTHING`,
  renvoie le `trade_id` canonique). Empêche la re-duplication à la ré-résolution
  (cause de l'incident 18-fantômes 2026-07-20). Schéma RÉEL de `paper_trades` :
  `(trade_id PK, snapshot_id, direction, confiance, principes_source, opened_at,
  closed_at, pips_simulated, is_win, risk_go_context)` — **pas** de colonnes
  `principle_name/side/outcome`. Table snapshots réelle = `forces_snapshots`
  (jamais `force_snapshots_v2`).

## Rôles opérationnels stables
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité — ne code pas.
- Claude Code : implémentation structurée, ancrée dans la doctrine existante. Prépare
  chaque livraison (diff, tests, commit message rédigé) mais ne commit/push jamais
  (règle 28 — assouplie 2026-07-14 : sauf délégation explicite de Søn, cf. DOCTRINE.md).
- Hermes : **opérateur git unique** (règle 28, ajoutée 2026-07-07 ; assouplie 2026-07-14 : délégation possible sur motion CEO explicite). Seul rôle habilité
  à `git commit`/`git push`. Support ciblé, itérations légères, expérimentations
  encadrées — jamais de décision de doctrine ou de structure.

## Documents pivots à toujours consulter en premier
`docs/STATE.md`, `docs/CACHE_BOARD.md`, `docs/ROADMAP.md`, `docs/PERPLEXITY.md`,
`docs/DOCTRINE.md`, `docs/DOC_GOVERNANCE.md`.
