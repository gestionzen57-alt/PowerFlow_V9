# DECISIONS_LOG — journal daté des décisions structurantes

Journal chronologique. Chaque entrée reprend une décision déjà actée côté code/doctrine
(voir `docs/STATE.md` §« Décisions actées » et les checkpoints référencés) — ce journal
n'invente pas de nouvelles décisions, il les indexe pour une reprise rapide côté
continuité multi-provider.

## Format d'entrée
```
### AAAA-MM-JJ — Titre
- Décision :
- Motivation :
- Impact / portée :
- Référence :
```

## Historique

### 2026-07-05 — Extension de la doctrine à 19 règles immuables
- Décision : `docs/DOCTRINE.md` étendu de 13 à 19 règles, ajoutant notamment Git=vérité,
  source unique par sujet, migration métier avant agentification, autonomie progressive
  après stabilité live, pas de dépendance bloquante à un LLM/provider, architecture
  agents/skills gelée tant que la phase métier courante n'est pas canonisée et stable.
- Motivation : cadrer explicitement le séquencement business → agentification avant
  toute reprise de chantier Phase 10+.
- Impact : gèle toute ouverture de la Phase 10 ou d'architecture agentique globale sans
  décision explicite de déblocage.
- Référence : commit `fe6323e`, branche `docs/v9-governance`.

### 2026-07-05 — Clôture de Phase 9 (Décision et Principes)
- Décision : Phase 9 déclarée terminée et canonisée — Régime/Principes/Signal/Décision
  livrés, 214 tests, revérifiés indépendamment.
- Motivation : chaîne cognitive à 8 couches complète, prête pour test live.
- Impact : ouvre le chantier déploiement live à l'ouverture du marché ; `docs/ROADMAP.md`
  mis à jour avec section « Chantiers futurs distincts » séparant explicitement Phase 10
  de l'architecture globale agents.
- Référence : `docs/phases/PHASE9_DECISION.md`,
  `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md`.

### 2026-07-05 — Correctif idempotence `regenerate_chain.py`
- Décision : ajout de `--replace-derived`/`--dry-run` et refus par défaut de rejeu sur
  DB dérivée non vide.
- Motivation : un rejeu antérieur avait dupliqué en production les tables dérivées
  (2388 lignes au lieu de 1194).
- Impact : la purge des ~245k lignes déjà dupliquées reste une action opérateur
  manuelle, non automatisée.
- Référence : commit `c83423e`,
  `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`.

### 2026-07-05 — Outillage d'automatisation opérationnelle (reboot/ouverture marché/reprise)
- Décision : livraison de 4 scripts (`scripts/v9_supervisor.py`, `v9_bootstrap.py`,
  `v9_market_open.py`, `v9_session_resume.py`) et de
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md`, qualifiés « Phase 9.5 » (outillage, pas une
  phase de code métier). Décision de conception : réutilisation telle quelle du gabarit
  de mini-checkpoint déjà défini dans
  `workspace/perplexity/assets/CHECKPOINT_TEMPLATE.md` plutôt que création d'un nouveau
  gabarit, pour respecter `docs/DOC_GOVERNANCE.md` règle 8 (pas de duplication de
  contenu). Fichiers générés dans `workspace/perplexity/mini_checkpoints/`, hors
  `docs/DOC_REGISTRY.yml` par définition de ce gabarit.
- Motivation : réduire la friction manuelle constatée lors du baptême live de V9
  (gestion de port stale, démarrage serveur, checklist T-30/T0, vérification de
  continuité de reprise de session), sans toucher à la logique métier ni ouvrir la
  Phase 10.
- Impact : aucune modification de `core/v9/*`. 40 nouveaux tests (258 au total : 250
  verts, 8 échecs pré-existants et non liés dans `test_behavior_analyzer.py`, signalés
  dans `INCIDENTS.md`, non corrigés — hors périmètre de ce chantier).
- Référence : ce commit (voir message « feat(v9): automatisation reboot machine /
  ouverture marché / reprise de session »), `docs/STATE.md` §« Outillage post-Phase 9 »,
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md`.

### 2026-07-06 — Anomalie DST « Marché : FERMÉ » : correctif observabilité, pas correctif calendrier
- Décision : face au bug documenté (calendrier canonique `core/v9/market_calendar.py`
  ancré sur 22h UTC fixe, incorrect ~8 mois/an pendant la DST US où le marché réel
  ouvre/ferme à 21h UTC), la décision explicite de l'opérateur a été de **ne pas
  modifier `core/v9/market_calendar.py` cette session** et de traiter uniquement
  l'observabilité : `scripts/v9_supervisor.py::market_status_warning()` détecte la
  divergence (calendrier FERMÉ + snapshot récent non-stale) et l'affiche explicitement
  dans `v9_dashboard.py`, `v9_supervisor.py --health`, les mini-checkpoints et le log de
  `v9_market_open.py`.
- Motivation : corriger le calcul canonique rouvrirait une décision Phase 7 canonisée
  (22h UTC documenté et testé) et casserait 7 tests de `tests/test_market_calendar.py`
  qui figent cette hypothèse — hors périmètre Phase 9.5 (outillage, pas relance de
  chantier métier).
- Impact : aucune modification de `core/v9/*`. 11 nouveaux tests, 269 au total (261
  verts, 8 échecs pré-existants inchangés). Gap DST documenté comme chantier futur
  distinct, non bloquant.
- Référence : `workspace/perplexity/INCIDENTS.md` 2026-07-06,
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md` §« Anomalie connue ».

### 2026-07-05 — Création du workspace de continuité Perplexity/multi-provider
- Décision : création de `workspace/perplexity/` (board, tâches actives, template de
  reprise, statut providers, protocole de session, mémoire, backlogs agents/skills
  gelés, incidents, gabarits) sans toucher à `core/v9/` ni ouvrir la Phase 10.
- Motivation : besoin d'un espace léger de continuité opérationnelle distinct des
  documents pivots `docs/`, pour la reprise rapide entre sessions Perplexity et autres
  providers.
- Impact : aucun impact code ; synthèse et renvois vers `docs/` uniquement, pas de
  doctrine concurrente créée.
- Référence : ce commit (voir message « docs: add continuity workspace for perplexity
  and market-open handoff »).
