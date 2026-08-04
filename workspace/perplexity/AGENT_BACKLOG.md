# AGENT_BACKLOG — idées agents, V10 unlocked

> **🚨 V10 doctrine (2026-08-04 05:00 UTC)** : V9 verrouillé → V10 libre.
> CEO mandate : "il ne faut plus de limitation au contraire, tu peux
> inventer trouver des choses sans restriction, un systeme intelligent
> et auto-apprentissage". Le backlog Phase 10 (fédération agents) est
> **dégelé** par V10 R1-AGIR. CEO mandate Go max.
> Voir `AGENTS.md` §DOCTRINE V10 + `docs/V10/V10_PLAN_REPARALETTRAGE.md`.

**Ce fichier est un backlog de notes, pas un chantier.** Rien ici ne doit être démarré
avant que `docs/ROADMAP.md` §« Chantiers futurs distincts » ne lève explicitement le gel
de la Phase 10 (fédération d'agents) et de l'architecture globale agents/routing/mémoire
avancée. Le collecter ici sert uniquement à ne pas perdre les idées entre sessions.

## Statut
🟢 **DEGELÉ par V10 doctrine** (CEO mandate 2026-08-04 05:00 UTC) —
V10 R1-AGIR autorise l'expérimentation agents/routing/mémoire avancée
sans permission CEO préalable. R10 reste le seul garde-fou (capital).
Démarrage Phase 10 maintenant possible si Søn mandate Phase A V10.

## Squelette déjà existant dans le repo (structure seulement, pas de logique fédérée)
`agents/` contient déjà des dossiers README-only, posés en amont sans logique active :
- `agents/orchestrator/`
- `agents/force-reader/`
- `agents/scene-builder/`
- `agents/behavior-analyst/`
- `agents/window-gate/`
- `agents/reviewer/`

Ces README ne doivent pas être interprétés comme un début d'implémentation de la
Phase 10 — vérifier leur contenu réel avant toute supposition (ils peuvent être de
simples placeholders).

## Idées collectées (à ré-évaluer seulement après déblocage Phase 10)
- Un agent par couche cognitive (scene agent, behavior agent, window agent,
  exploitability agent, regime/principle agent) — cf. `docs/ROADMAP.md` §Phase 10.
- Un agent arbitre consolidant les lectures inter-couches.
- Un agent risk manager filtrant les décisions avant toute action (paper-trading
  d'abord, jamais d'exécution réelle avant Phase 12).

## Règle de sortie du gel
Ne retirer une idée de ce backlog vers un vrai chantier que sur décision explicite
consignée dans `memory/DECISIONS_LOG.md`, avec référence à la calibration live de la
Phase 9 ayant justifié le déblocage.


## Phase 14 — Nettoyage données mortes (CEO quant sprint nuit 2026-07-08 00h25)

**Origine** : audit CEO Søn 23h20 CEST 2026-07-07 — DB 2.9→3.1 GB sur 3h, pas de
doublon, croissance linéaire. Mais 70 % du volume = données mortes identifiées.

**Dette quantifiée** :
- `zone_diagnostics` (364 528 rows × 25 cols + 2 JSON) : 0 consommateur downstream
- `principle_evaluations` lignes v9_status='SHADOW' (~800K rows × 66%) : jamais routées
- `principle_evaluations.context_json` : {} hardcodé sur 1.2M rows (~60 MB gaspillés)
- `behaviors.point_de_rupture_*` : flag=0 à 100% (propriété morte, jamais déclenchée)
- `scenes.coalitions_json`, `behaviors.ecarts_json`, `behaviors.singularites_locales_json` :
  écrits jamais lus downstream

**Stratégie retenue par Søn — exécution en 2 temps** :

### Phase 14a — Cleanup minimal (1 sprint 2-3h)
Sprint à tête reposée, pas ce soir :
1. Feature flag `V9_DISABLE_ZONE_DIAGNOSTICS=1` : bypass `zone_detector.detect()`
   dans orchestrator.ROI immédiat −25% DB si activé. 1 commit, 0 risque.
2. Filtre SHADOW : `V9_DISABLE_SHADOW_EVAL=1` bloque l'écriture en DB des 17
   principes SHADOW. ROI −45% si activé. 1 commit.
3. Patch `context_json` : ne pas écrire la chaîne JSON si zone_type == "indetermine"
   ou absent. ROI −5%. 1 commit.
4. VACUUM final.

### Phase 14b — Migration DuckDB (1 sprint futur)
Une fois Phase 14a appliquée : DB cible ~1 GB. Migration DuckDB = −55 à −70%
supplémentaire (compression columnare). 1-2 sprints à tête reposée.

**ROI cumulé** : DB actuelle 3.1 GB → cible Phase 14a+b ~0.6 GB (compression −80%).

**Risque** : 1 sprint borné, 0 modif core/v9/business gelé SAUF feature flag.
Pas de fusion SQL ou DuckDB tant que Phase 14a pas validée.

**Statut** : 🔒 Gelé — pas d'exécution ce soir (règle 28 + signal Søn fatigue 00h25 CEST).

---

## Phase 14a — Cleanup minimal V9 (kill switch données mortes)
(initiative CEO quant Søn — voir ci-dessus)

**Livrable attendu quand Søn donne GO (à tête reposée)** :
- 3 commits max (règle 22)
- Migration SQL back-compat possible via VACUUM optionnel
- DECISIONS_LOG entrée dédiée
- Tests verts (≥ 691 préservés)
- Push origin uniquement quand Søn OK

**Statut** : 🟡 BACKLOG (priorité P1 selon Søn)
