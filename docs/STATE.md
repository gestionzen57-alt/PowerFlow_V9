# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-06 — Session Coalition Intelligence (Tâches A+B+C + Anomalies #1-#4 + Gouvernance CONTEXT_CONTRACT)

## Session Coalition Intelligence (2026-07-06) — enrichissement cognitif + gouvernance propagation

Session livrée sur `feat/v9-foundation-clean` (6 commits + push, rebase propre).
**339 tests verts, zéro régression.**

### Tâche A — Coalition Intelligence
`core/v9/scene_builder.py` — `_detect_coalitions` enrichi de 3 métriques :
- `age_bars` : continuité arrière (break au premier trou de composition)
- `intensite_trend` : delta vs moyenne des 3 dernières apparitions (montante/stable/declinante)
- `stabilite` : ratio de présence sur la fenêtre d'historique
Pattern `prev_forces` respecté : historique passé en paramètre, jamais lu directement depuis la DB.

### Tâche B — RiskMeter
`core/v9/risk_meter.py` (nouveau module pur, aucune connexion DB) :
- `assess(coalitions, directions, mtf_emboitement)` → dict 8 clés
- Sentiments : RISK_ON / RISK_OFF / MIXTE / NEUTRE
- Confidence : base 40 +20 opposition +15 age>=5 +10 stab>=0.7 +10 trend montante +5 MTF
- `risk_assessment_json` ajouté dans `scenes` DB (ALTER TABLE rétrocompatible)
- 5 champs injectés dans `_load_shared_context` :
  risk_sentiment, risk_confidence, risk_on_score, risk_off_score, persistance_confirmee

### Tâche C — coalition_mtf_score + rotation
`_detect_mtf_confluences` enrichi dans scene_builder :
- `coalition_mtf_score` (int) : nb TF où la coalition dominante est présente
- `coalition_mtf_depth` (str) : TF le plus large confirmé (D1>H4>H1>M30>M15>M5)
5 champs injectés dans `_load_shared_context` :
coalition_mtf_score, coalition_mtf_depth, coalition_rotation_detectee,
coalition_rotation_ancien_leader, coalition_rotation_nouveau_leader

### Anomalie #1 — similarite_score dans confiance_qualification
Bonus post-calcul dans `analyze_scene` :
+15 si similarite_score >= 0.85, +8 si >= 0.70, sinon 0. Plafond 100.

### Anomalie #2 — coalition_composition_sim dans _similarity
Nouvelle pondération : 0.30 jaccard + 0.20 same_tf + 0.20 same_phase + 0.15 cinématique + 0.15 coalition_composition_sim.
Helper `_dominant_coalition_set` : Jaccard sur devises de la coalition dominante. Fallback 0.5.

### Anomalie #3 — bascule_equilibre.sens dans le contexte
3 nouveaux champs dans `_load_shared_context` :
bascule_detectee (bool), bascule_devise_dominante (str|None), bascule_intensite (float).
Fallbacks False/None/0.0 si scene_row absent.

### Anomalie #4 — contexte_temporel dans le contexte
4 nouveaux champs dans `_load_shared_context` :
session_marche (london/new_york/asie/sydney/overlap/inconnu),
heure_utc (int|None), jour_semaine (0=lundi..4=vendredi), marche_ouvert (bool).

### Gouvernance — CONTEXT_CONTRACT.md + test_context_propagation.py
`docs/architecture/CONTEXT_CONTRACT.md` (nouveau) : contrat vivant, 7 couches, 80+ champs,
statut PROPAGÉ ou DORMANT (justifié), 9 métriques DORMANT P2/P3 listées explicitement.
`tests/test_context_propagation.py` (nouveau) : gardien automatique, 4 tests
(présence champs PROPAGÉS, non-None chaîne complète, fallbacks, cohérence déclaration).
**Règle doctrine ajoutée** : toute métrique ajoutée doit être tracée dans CONTEXT_CONTRACT.md.

### Tests et commits
339 passed (318 baseline + 21 nouveaux).
Commits : cd50cd7 / 4ebf86a / 24c0653 / 4d6cf53 / 44c8ae4 / 6648d27

---

## Correctif Phase 9.5 (2026-07-06) — observabilité du statut marché (anomalie DST US)
Anomalie constatée : `scripts/v9_dashboard.py` peut afficher « Marché : FERMÉ » alors que
le pipeline reçoit des snapshots frais. Cause : `market_calendar.py` ancre sur 22h UTC fixe
(EST), incorrect pendant DST US (21h UTC). Décision : ne pas modifier `market_calendar.py`
(rouvrirait Phase 7 canonisée). Correctif limité à l'observabilité via `market_status_warning()`.
Aucune modification de `core/v9/*`. 269 tests verts post-correctif.
Détail : `workspace/perplexity/INCIDENTS.md`, `docs/deployment/V9_AUTOMATION_RUNBOOK.md`.

## Statut
PHASE 9 TERMINÉE — couche Décision et Principes (2026-07-05).
Chaîne cognitive : Forces → Scènes → Comportements → Fenêtres → Exploitabilité →
Régime → Principes → Signal → Décision.
27 principes YAML (10 ACTIVE / 17 SHADOW), latence moyenne 189ms/snapshot.
Voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE9.md`.

## Correctif post-Phase 9 (2026-07-05) — idempotence regenerate_chain.py
`--replace-derived` (delete ciblé tables dérivées) + `--dry-run`. 218 tests verts.
Voir `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`.

## Outillage post-Phase 9 (2026-07-05) — automatisation
`v9_supervisor.py`, `v9_bootstrap.py`, `v9_market_open.py`, `v9_session_resume.py`.
Doc : `docs/deployment/V9_AUTOMATION_RUNBOOK.md`. 40 nouveaux tests verts.

## Gouvernance documentaire (docs/v9-governance)
Arborescence canonique : ARCHITECTURE.md, DOCTRINE.md, LEXIQUE.md, NOMENCLATURE.md,
ROADMAP.md, DOC_GOVERNANCE.md, DOC_REGISTRY.yml. Outillage : `tools/doc_sync.py`,
`.github/workflows/doc-freshness.yml`. Aucun code modifié.

## PHASES 1→8 TERMINÉES
Voir checkpoints dans `docs/checkpoints/`.
Phase 8 : monitoring/calibration/replay. Phase 7 : déploiement live.
Phases 1-6 : chaîne cognitive complète (Forces → Exploitabilité).

## Décisions actées
- V9 part dans un dossier vide. GitHub est la source de vérité.
- V8 : source de migration curée uniquement.
- Squelette cognitif : Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision.
- Documents pivots avant tout chantier de code.
- **Nouvelle (2026-07-06)** : toute métrique ajoutée doit être tracée dans
  `docs/architecture/CONTEXT_CONTRACT.md` (PROPAGÉ ou DORMANT justifié).
  `tests/test_context_propagation.py` est le gardien automatique.

## Métriques DORMANT — prochaines vagues
Détail complet : `docs/architecture/CONTEXT_CONTRACT.md`.

P2 (prochaine session post-calibration live) :
- `contexte_temporel.fenetre` (ouverture/mi-session/cloture)
- `point_de_rupture.declencheur`
- `variante_de_comportement_connu` — à lire dans WindowGate

P3 (après stabilisation live) :
- `cinematique.rotation_force.*`
- `confluences_mtf.cascades_temporelles`
- `zone.structure`, `zone.niveau`
- `risk_assessment.dominant_bloc`
- `behavior.singularites_locales`
- `vitesse` par devise (EA MT4, 8 colonnes)

## Objectif immédiat
**Observation live + calibration** sur données réelles.
Suivre `docs/deployment/V9_DEPLOYMENT_GUIDE.md`.
Après stabilisation : révision des 27 principes YAML pour exploiter les 13 nouveaux
champs du contexte (coalition_mtf_score, risk_sentiment, bascule_devise_dominante,
session_marche, coalition_rotation_detectee…).

## Chantiers en file
1. **Observation live** — `scripts/v9_dashboard.py --watch decisions`
2. **Calibration** seuils — `scripts/v9_calibration.py --analyze`
3. **Révision principes YAML** — 27 principes à enrichir avec les 13 nouveaux champs
4. **Métriques DORMANT P2** — contexte_temporel.fenetre + declencheur + variante
5. AGENT.md racine V9
6. Inventaire de migration V8 → V9

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code / Hermes / MiniMax : implémentation selon périmètre assigné

## Règle d'or
Aucune implémentation structurante sans ancrage explicite dans la doctrine V9.
Toute nouvelle métrique tracée dans CONTEXT_CONTRACT.md avant ou à la livraison.
