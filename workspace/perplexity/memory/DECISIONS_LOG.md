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
