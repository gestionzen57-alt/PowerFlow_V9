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
| 9 | Décision et Principes (Régime → Principes → Signal → Décision) | ✅ Terminée — canonisée le 2026-07-05, voir [docs/phases/PHASE9_DECISION.md](phases/PHASE9_DECISION.md) et [CHECKPOINT_2026-07-05_MEGA_V9.md](checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md) |

## Phases restantes

| Phase | Objectif | Priorité | Statut |
|---|---|---|---|
| 10 | Fédération d'agents (multi-analyse) | P1 | ⏳ Planifiée — chantier séparé, ne démarre pas avant stabilisation live de la Phase 9 (voir doctrine de séquencement ci-dessous) |
| 11 | Layer MT5 (microstructure ticks) | P2 | ⏳ Planifiée |
| 12 | Exécution d'ordres | P2 | ⏳ Planifiée |
| 13 | Apprentissage et auto-calibration | P3 | ⏳ Planifiée |

### Phase 9 — Décision et Principes ✅ Terminée
- 27 principes ACTIVE de V8 migrés **tels quels** (`core/v9/principles/*.yaml`, adaptés en
  fonctions pures entrée → bool + confiance), 10 routés en mode ACTIVE, 17 en mode SHADOW
  (journalisés, jamais routés).
- `SignalGenerator` agrège les principes ACTIVE déclenchés en direction + confiance, filtré
  par exploitabilité et régime.
- `DecisionLogger` journalise signal + contexte complet (scène/comportement/fenêtre/
  exploitabilité/régime) + action qualitative (`observer`/`surveiller`/`preparer_entree`/
  `aucune_action`), replayable.
- `RegimeDetector` comble le gap V8 `regime_snapshots` (327k lignes en V8, absent de V9 avant
  cette phase) sur fenêtre glissante.
- **Gap non résolu, reporté** : `zone_diagnostics` créée (`core/v9/zone_db.py`) et **alimentée par ZoneDetector** (commit `db11917`) — 9 des 27 principes débloqués (NODE_BIRTH_FAST, RAW_NODE_BIRTH, POWER_ANGLE_BREAK, ZONE_RETEST, ELASTIC_BREATH, GRAVITY_RESPRING, PRICE_LAG_AT_NODE_BIRTH, COALITION_NODE, ANTAGONIST_NODE).
- **Point ouvert résolu (2026-07-06)** : marquage explicite replay vs live dans chaque décision
  (identifié en Phase 7-8, résolu par l'ajout de la colonne `source_type` dans les 8 tables
  dérivées — voir [DOCTRINE.md](DOCTRINE.md) règle 12 et
  `docs/checkpoints/CHECKPOINT_20260706_V9_SOURCE_TYPE.md`).
- 214 tests au total (139 précédents + 75), tous verts, revérifiés indépendamment à la
  clôture documentaire.

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
| Calibration sur données live | `v9_calibration.py --analyze`/`--principes` sur une session réelle complète, ajuster les seuils de `config.py` (dont les seuils `PROVISIONAL` de régime) | Max — bloquant avant généralisation |
| Multi-paires | Étendre au-delà de GBPUSD (EURUSD, USDJPY, GBPJPY) ; `SceneBuilder` doit agréger cross-paires | Après stabilisation live de la Phase 9 |
| `zone_diagnostics` | **Alimentée par ZoneDetector** (commit `db11917`) — 9/27 principes débloqués. Calibration seuils (COALITION_THRESHOLD, ANTAGONISM_THRESHOLD, PLIURE_THRESHOLD) via `v9_calibration.py` post-stabilisation live | Priorité 2 — calibration live après Phase 9.5 |

## Chantiers futurs distincts — ne pas mélanger maintenant

Trois initiatives sont explicitement **hors périmètre actuel** et ne doivent pas être
entamées ni anticipées pendant que la Phase 9 est en cours de stabilisation live. Chacune
dépend d'un socle plus stable que le précédent :

1. **Phase 10 — Fédération d'agents** (déjà planifiée ci-dessus, P1) : un agent par couche
   cognitive + un arbitre + un risk manager. Ne démarre qu'après calibration live de la
   Phase 9 (voir Leviers ci-dessus).
2. **Architecture globale agents / routing / mémoire avancée** : chantier plus large que la
   seule Phase 10, non scopé dans ce document — orchestration multi-agents généralisée,
   routing dynamique, mémoire fédérée avancée. Distinct de la migration métier Phase 9
   (décision/principes), à ne pas confondre avec elle. Ne sera scopé qu'une fois la Phase 10
   elle-même amorcée.
3. **Skills/agents auto-générés** : chantier encore plus tardif que les deux précédents,
   dépendant d'un socle stable (Phases 9-10 canonisées et calibrées en live). Aucune
   génération automatique de skill/agent ne doit être entreprise avant cette dépendance
   levée (voir [DOCTRINE.md](DOCTRINE.md) — règle de séquencement migration avant
   agentification).

Voir aussi [docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md](checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md)
§« Ce qui ne doit pas être mélangé maintenant ».

## Timeline prévisionnelle (indicative, non contractuelle)

| Période | Contenu |
|---|---|
| Juillet 2026, semaine 1 | Phases 1-8 + orchestrateur live, audit V8, calibration live |
| Juillet 2026, semaine 2 | Phase 9 (décision et principes) terminée et canonisée ; déploiement live à l'ouverture du marché |
| Juillet 2026, semaine 3 | Calibration live des principes/régime, multi-paires, alimentation `zone_diagnostics` |
| Juillet 2026, semaine 4 | Phase 10 (fédération d'agents), premier paper-trading |
| Août 2026 | Phase 11 (MT5), Phase 12 (exécution, paper → réel) |
| Septembre 2026 | Phase 13 (apprentissage), déploiement production, auto-calibration continue |

## Risques connus à surveiller (voir aussi docs/architecture/audit_v8_v9_migration.md)
- Dépendance à l'indicateur SDI propriétaire (MT4 uniquement, pas de fallback identifié).
- Replay vs live : le stale gate (seuils en secondes) est calé pour le live et rejette du
  replay pourtant utile — nécessite un mode réplay distinct ou un bypass documenté.
- Replay vs live marqué dans `decisions` (colonne `source_type`, résolu le 2026-07-06 —
  voir [DOCTRINE.md](DOCTRINE.md) règle 12).
- `zone_diagnostics` **alimentée par ZoneDetector** (commit `db11917`) — 9/27 principes débloqués. Calibration seuils (COALITION_THRESHOLD, ANTAGONISM_THRESHOLD, PLIURE_THRESHOLD) via `v9_calibration.py` post-stabilisation live.
- Latence cumulée : 189,58 ms/snapshot en moyenne, chaîne complète 8 couches (mesuré par
  `regenerate_chain.py` sur 1194 snapshots rejoués, Phase 9) — sous la cible de 200 ms grâce
  au cache process-local du catalogue de principes, à confirmer sur snapshots live réels.
- Calibration actuelle (seuils de régime notamment) basée sur des valeurs `PROVISIONAL`
  portées de V8, pas encore de données live V9 réelles.
