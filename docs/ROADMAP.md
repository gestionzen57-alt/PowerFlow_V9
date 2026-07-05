# ROADMAP — PowerFlow V9

## Statut
Reprend le plan de [docs/v9_processus_complet.md](v9_processus_complet.md) §3, §6, §7.
Pour l'état détaillé et à jour des phases déjà livrées, voir [docs/STATE.md](STATE.md)
(source de vérité vivante, mise à jour à chaque phase). Ce document couvre les phases
**restantes** (9-13) et leur séquencement prévisionnel.

## Phases terminées (résumé — détail dans STATE.md et docs/phases/)

| Phase | Construction | Statut |
|---|---|---|
| 1 | Formats de données (6 fichiers JSON) | ✅ Terminée |
| 2 | Forces (EA MT4 + capture TCP + DB + stale gate) | ✅ Terminée |
| 3 | Scènes (`scene_builder.py`, coalitions/antagonismes) | ✅ Terminée |
| 4 | Comportements (`behavior_analyzer.py`, 12 qualifications) | ✅ Terminée |
| 5 | Fenêtres (`window_gate.py`, 6 statuts) | ✅ Terminée |
| 6 | Exploitabilité (`exploitability_evaluator.py`, 5 niveaux) | ✅ Terminée |
| 7 | Déploiement live (EA `ServerPort`, `market_calendar.py`, scripts de déploiement) | ✅ Terminée |
| 8 | Monitoring (dashboard, calibration, replay — tous lecture seule) | ✅ Terminée |
| + | Orchestrateur live (chaîne automatique événementielle) | ✅ Terminée |

## Phases restantes

| Phase | Objectif | Priorité | Statut |
|---|---|---|---|
| 9 | Décision et Principes (signaux) | P0 | 🔄 En cours (session concurrente, voir [docs/phases/PHASE9_DECISION.md](phases/PHASE9_DECISION.md)) |
| 10 | Fédération d'agents (multi-analyse) | P1 | ⏳ Planifiée |
| 11 | Layer MT5 (microstructure ticks) | P2 | ⏳ Planifiée |
| 12 | Exécution d'ordres | P2 | ⏳ Planifiée |
| 13 | Apprentissage et auto-calibration | P3 | ⏳ Planifiée |

### Phase 9 — Décision et Principes
- Migrer (adapter, pas copier) les 27 principes ACTIVE de V8 (`core/v9/principles/*.yaml`)
  vers le modèle V9 : chaque principe = fonction pure (entrée → bool + confiance).
- Commencer par les 5-10 principes les plus significatifs plutôt que les 27 d'un coup.
- Un signal agrège plusieurs principes en direction + confiance.
- Une décision = signal + contexte complet (scène/comportement/fenêtre/exploitabilité) +
  action recommandée, journalisée pour confrontation ultérieure (`decision_logger.py`).
- Marquer explicitement replay vs live dans chaque décision (point ouvert identifié en
  Phase 7-8, non encore résolu — voir [DOCTRINE.md](DOCTRINE.md) règle 12).

### Phase 10 — Fédération d'agents
- Un agent par couche cognitive (scene agent, behavior agent, etc.).
- Un agent arbitre qui consolide les lectures.
- Un agent risk manager qui filtre les décisions avant toute action.
- Premier paper-trading une fois la fédération en place.

### Phase 11 — Layer MT5 (microstructure)
- Lecture des ticks en temps réel (au-delà de GBPUSD si multi-paires activé en amont).
- Détection de micro-patterns (absorption, rejet, accélération).
- Principe directeur : **MT4 (forces) dicte, MT5 (ticks) confirme** — jamais l'inverse
  (voir [DOCTRINE.md](DOCTRINE.md) règle 10).

### Phase 12 — Exécution d'ordres
- Passage de paper-trading à exécution réelle, seulement après stabilisation des Phases 9-11.
- Aucune logique d'exécution avant cette phase (interdit fondateur, voir AGENT.md).

### Phase 13 — Apprentissage et auto-calibration
- Logger le résultat de chaque signal/décision (gagnant/perdant/neutre).
- Comparer prédictions vs réalité, ajuster automatiquement les seuils des principes.
- Identifier les principes les plus performants (base pour un futur scoring de principes).

## Leviers transverses (non liés à une phase unique)

| Levier | Description | Priorité |
|---|---|---|
| Calibration sur données live | `v9_calibration.py --analyze` sur une session réelle complète, ajuster les seuils de `config.py` | Max — bloquant avant généralisation |
| Multi-paires | Étendre au-delà de GBPUSD (EURUSD, USDJPY, GBPJPY) ; `SceneBuilder` doit agréger cross-paires | Après stabilisation Phase 9 |

## Timeline prévisionnelle (indicative, non contractuelle)

| Période | Contenu |
|---|---|
| Juillet 2026, semaine 1 | Phases 1-8 + orchestrateur live, audit V8, calibration live |
| Juillet 2026, semaine 2 | Phase 9 (décision et principes), migration des 10 premiers principes V8 |
| Juillet 2026, semaine 3 | Calibration live des principes, multi-paires, dashboard `--signals` |
| Juillet 2026, semaine 4 | Phase 10 (fédération d'agents), premier paper-trading |
| Août 2026 | Phase 11 (MT5), Phase 12 (exécution, paper → réel) |
| Septembre 2026 | Phase 13 (apprentissage), déploiement production, auto-calibration continue |

## Risques connus à surveiller (voir aussi docs/architecture/audit_v8_v9_migration.md)
- Dépendance à l'indicateur SDI propriétaire (MT4 uniquement, pas de fallback identifié).
- Réplay vs live : le stale gate (seuils en secondes) est calé pour le live et rejette du
  replay pourtant utile — nécessite un mode réplay distinct ou un bypass documenté.
- Latence cumulée : 148 ms/snapshot en chaîne complète (Phases 1-8) ; l'ajout de ~27
  principes (Phase 9) pourrait porter le total à 200 ms+ — à mesurer.
- Calibration actuelle basée sur des valeurs par défaut, pas encore de données live réelles.
