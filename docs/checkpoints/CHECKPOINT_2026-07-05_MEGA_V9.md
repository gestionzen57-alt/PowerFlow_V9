# CHECKPOINT_2026-07-05_MEGA_V9

<!-- Nomenclature : mega-checkpoint transversal (plusieurs phases + gouvernance documentaire),
distinct des checkpoints de phase unique (`CHECKPOINT_{YYYYMMDD}_V9_{NOM_COURT}.md`). Nommé
avec la date ISO à tirets pour se distinguer visuellement d'un checkpoint de phase — voir
note dans docs/NOMENCLATURE.md. -->

## Date
2026-07-05

## Contexte

Ce mega-checkpoint consolide l'état de PowerFlow V9 après quatre chantiers convergents menés
le même jour, sur le même dépôt, par des sessions distinctes partageant le même répertoire de
travail (`D:\Projet\V9`) :

1. **Audit V8→V9** (`docs/architecture/audit_v8_v9_migration.md`, branche source
   `audit/v8-to-v9-migration` sur le dépôt V8) — inventaire complet de ce qui est repris,
   adapté, archivé ou re-spécifié.
2. **Phase 9 — Décision et Principes** (branche `feat/v9-foundation-clean`, commit `a233abb`
   pour le code, complété en working tree ensuite) — extension de la chaîne cognitive avec
   Régime, Principes, Signal, Décision.
3. **Gouvernance documentaire** (branche `docs/v9-governance`, commit `dc26d8e`) — arborescence
   canonique `docs/`, registre de documents, outillage de fraîcheur CI.
4. **Ce mega-checkpoint** — clôture documentaire de la Phase 9 (le placeholder
   `docs/phases/PHASE9_DECISION.md` rédigé pendant que la phase était encore en cours est
   remplacé), mise en cohérence de `docs/ROADMAP.md`, `docs/DOCTRINE.md`, `docs/ARCHITECTURE.md`,
   `docs/LEXIQUE.md`/`docs/lexicon/LEXICON_V9.md`, `docs/DOC_REGISTRY.yml`, `docs/CACHE_BOARD.md`,
   `README.md`, `AGENT.md`.

**Règle appliquée pour ce chantier** : le Git courant (working tree + historique) est la
source de vérité, jamais une hypothèse héritée de V8 ou d'un prompt antérieur (voir
[DOCTRINE.md](../DOCTRINE.md) règle 14). Tous les chiffres cités ci-dessous ont été
revérifiés contre le code réel le 2026-07-05 (`python -m pytest tests/ -q` → **214 tests,
tous verts** ; comptage direct de `core/v9/principles/*.yaml` → 27 fichiers ; lecture directe
de `config.PRINCIPLE_ACTIVE_IDS` → 10 entrées). Aucun module métier n'a été modifié par ce
chantier — seules la documentation et la gouvernance ont été touchées (voir « Fichiers
modifiés » en fin de document).

---

## 1. État global du repo

| Axe | État |
|---|---|
| Branche de référence | `feat/v9-foundation-clean` |
| Branche de ce chantier | `docs/v9-governance` |
| Chaîne cognitive | 8 couches : Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision |
| Tests | **214, tous verts** (139 Phases 1-8 + 75 Phase 9) |
| Outillage live | Déploiement (Phase 7), monitoring/calibration/replay (Phase 8), orchestrateur événementiel — tous prêts |
| Gouvernance documentaire | Arborescence canonique posée, CI de fraîcheur active (`doc-freshness.yml`), registre `DOC_REGISTRY.yml` à jour |
| Audit V8→V9 | Livré, intégré dans `docs/architecture/audit_v8_v9_migration.md`, référencé depuis `DOCTRINE.md`, `ROADMAP.md`, `PHASE9_DECISION.md` |

## 2. Phases terminées

| Phase | Contenu | Tests |
|---|---|---|
| 1 | 6 formats JSON (Forces, Scènes, Comportements, Fenêtres, Exploitabilité, contrat mémoire) | — |
| 2 | Forces : EA MT4 (`V9_Sonde_TF`/`V9_Sonde_M1`) + capture TCP + `forces_snapshots` + STALE_GATE | 15 |
| 3 | Scènes : `SceneBuilder`, coalitions/antagonismes/cinématique | 13 |
| 4 | Comportements : `BehaviorAnalyzer`, 12 qualifications | 21 |
| 5 | Fenêtres : `WindowGate`, 6 statuts | 20 |
| 6 | Exploitabilité : `ExploitabilityEvaluator`, 5 niveaux | 26 |
| 7 | Déploiement live : `market_calendar.py`, scripts de déploiement, EA `ServerPort` | 22 |
| 8 | Monitoring : dashboard/calibration/replay, tous lecture seule | 21 |
| 9 | Décision et Principes : Régime/Principes/Signal/Décision | 75 |
| + | Orchestrateur événementiel live (`run_chain`), anti-replay, régénération de chaîne | — |

Total : **214 tests, tous verts**, chaîne complète rejouée sans erreur sur 1194 snapshots
non-stale (latence moyenne 189,58 ms/snapshot, chaîne 8 couches).

## 3. État réel de la Phase 9

Phase 9 **fonctionnellement terminée et vérifiée** (214 tests verts, chaîne rejouée sans
erreur). Ce qui était encore vrai au moment où le placeholder `PHASE9_DECISION.md` a été
rédigé (« en cours, session concurrente ») ne l'est plus : la session Phase 9 a complété son
travail dans le même répertoire de travail pendant que ce chantier de gouvernance avançait en
parallèle, et a documenté son résultat dans `docs/STATE.md` (journal détaillé, non modifié par
ce chantier pour éviter tout conflit d'édition — voir sa note de coordination explicite).

Ce chantier de gouvernance :
- a **revérifié indépendamment** les chiffres annoncés dans `STATE.md` (tests, comptage de
  principes, ACTIVE IDs, usage de `zone_db`) plutôt que de les recopier aveuglément (conforme
  à [DOC_GOVERNANCE.md](../DOC_GOVERNANCE.md) : « le code est la source de vérité, pas la doc ») ;
- a **remplacé le placeholder** `docs/phases/PHASE9_DECISION.md` par son contenu de clôture ;
- a **retiré les mentions « Phase 9, en cours »** devenues obsolètes dans `ARCHITECTURE.md`,
  `LEXIQUE.md`, `lexicon/LEXICON_V9.md`, `DOCTRINE.md`, `ROADMAP.md`, `DOC_REGISTRY.yml` ;
- n'a **rien modifié dans `core/v9/`** ni dans `docs/STATE.md` (propriété de la session Phase 9).

Ce qui est en place : `RegimeDetector` (machine à états sur fenêtre glissante), `PrincipleEngine`
(27 grammaires YAML migrées, 10 ACTIVE/17 SHADOW), `SignalGenerator` (vote majoritaire filtré),
`DecisionLogger` (action qualitative + contexte replayable), `zone_db.py` (schéma créé).

Ce qui reste non idempotent / non résolu :
- **`zone_diagnostics` non alimentée** — table créée, aucun détecteur ne l'écrit. 9 des 27
  principes (dont `ZONE_RETEST`, qui fait pourtant partie des 10 ACTIVE) ne se déclenchent
  jamais. Dégradation gracieuse confirmée par les tests, jamais une erreur.
- **Replay vs live non marqué** dans `decisions` (doctrine règle 12, point ouvert depuis
  Phase 7-8, non traité par cette phase).
- **`regime_snapshots.cassure_type`** toujours `INDETERMINEE` (pas de couche tick en V9).
- **Seuils de régime `PROVISIONAL`** — portés de V8 sans recalibration sur données V9 réelles.

Ce qui est prêt pour le market open : la chaîne complète (8 couches) tourne sans erreur sur
données rejouées, l'orchestrateur événementiel est actif (`config.ENABLE_CHAIN`), le dashboard
expose `--watch signals`/`--watch decisions`.

Ce qui doit être observé ce soir en live :
- Fréquence de déclenchement réelle des 10 principes ACTIVE (ne pas confondre l'absence de
  déclenchement de `ZONE_RETEST` avec une régression — c'est le gap `zone_diagnostics`,
  attendu).
- Latence réelle par snapshot (comparer aux 189,58 ms mesurés en replay).
- Cohérence des actions qualitatives de `decisions` avec la scène/comportement/fenêtre source.
- Comportement du `StaleGate` en conditions live réelles (le mode replay bypasse certains
  seuils, point de vigilance déjà documenté dans `ROADMAP.md`).

## 4. Apports de l'audit V8→V9

Voir [docs/architecture/audit_v8_v9_migration.md](../architecture/audit_v8_v9_migration.md)
pour le détail complet (déjà à sa place canonique dans l'arborescence V9, aucun déplacement
nécessaire). Synthèse :

- **Périmètre** : 1361 fichiers Python V8 hors venvs, ~115 bases SQLite, inventoriés par
  cluster (préfixe de nom) plutôt que ligne à ligne (volume non lisible exhaustivement).
- **Verdict global** : la chaîne cognitive V9 (Phases 1-9) est un **sur-ensemble net et plus
  propre** de `force_snapshots_v2`/`detected_patterns` côté V8 — moins de tables, JSON typé
  par couche, un seul emplacement de tests (`tests/`), pas de doublons versionnés (`_v2`...`_v9`).
- **Gaps réels confirmés** (aucun équivalent V9, indépendamment de la Phase 9) :
  `zone_diagnostics` (36 808 lignes en V8 — origine du gap Phase 9 ci-dessus),
  `structure_ledger` (multi-TF SQL typé, recouvert partiellement par `scenes.confluences_mtf_json`),
  couche microstructure MT5 (4,2 Go de ticks, 15 modules de détection).
- **Priorité 1 déjà exploitée par la Phase 9** : les 27 principes YAML — l'audit les qualifiait
  de « plus haut ratio valeur/effort de tout l'audit » ; c'est exactement ce qui a été migré.
- **Priorité 1 non encore exploitée** : `agent_registry.py` + `federation_evidence_gate.py`
  (routage LLM free-first, gate déterministe) — pertinent pour la Phase 10 (fédération
  d'agents), **pas pour maintenant** (voir §7).
- **Priorité 2 (peut attendre)** : `zone_diagnostics` (5-8j), workflows YAML fédération (1-2j
  après Phase 10), couche MT5 tick (10-15j, décision produit à trancher explicitement).
- **Dette à ne jamais reproduire** : suffixes `_v2`.../`_v9` sans suppression, sprawl de bases
  SQLite, tables créées jamais alimentées, tests fragmentés sur 3 emplacements, divergence
  doc/code non testée automatiquement — **V9 a justement construit `doc-freshness.yml` pour
  éviter ce dernier point**, la leçon explicite de l'audit (§7 dernier paragraphe).

## 5. Ce qui est migré

| Élément V8 | Statut V9 |
|---|---|
| Capture forces (`force_snapshots_v2`) | ✅ Repris et étendu (`forces_snapshots`, direction/vitesse/croisement/rejet/compression) |
| 27 principes YAML | ✅ Migrés tels quels (`core/v9/principles/*.yaml`), 10 ACTIVE/17 SHADOW |
| Machine à états régime (`pf_regime_detector.py`) | ✅ Portée sur fenêtre glissante (`regime_detector.py`) |
| EA Sonde (bug ShiftIndex, décalage horaire) | ✅ Corrigés par construction (`V9_Sonde_TF`/`V9_Sonde_M1`, `BrokerUTCOffsetHours`) |
| Dashboard / calibration / replay | ✅ Reconstruits plus simples (`v9_dashboard.py`, `v9_calibration.py`, `v9_replay.py`) |

## 6. Ce qui est encore un gap

| Gap | Origine | Effort estimé | Statut |
|---|---|---|---|
| `zone_diagnostics` non alimentée | Audit §6, confirmé Phase 9 | 5-8 jours | Non planifié, non bloquant |
| Replay vs live non marqué dans `decisions` | Doctrine règle 12, ouvert depuis Phase 7-8 | Non estimé | Non planifié |
| Fédération d'agents / `agent_registry.py` | Audit §4, Priorité 1 | 2-3 jours | Phase 10, non démarrée (voir §7) |
| Couche MT5 tick/microstructure | Audit §5 | 10-15 jours | Phase 11, décision produit à trancher |
| `structure_ledger` (multi-TF SQL typé) | Audit §6 | Non estimé | À réévaluer seulement si JSON insuffisant en pratique |
| Règles GOLDEN d'exécution (`pf_mt5_bridge_v2.py`) | Audit §7 | 3-5 jours | Phase 12, hors périmètre actuel |

## 7. Décisions prises (ce chantier de gouvernance)

- **Clôturer documentairement la Phase 9** maintenant, parce que sa propre session a déclaré
  le travail terminé dans `STATE.md` et que la revérification indépendante (214 tests, 27
  principes, 10 ACTIVE) confirme cette déclaration — satisfait la précondition de
  [DOC_GOVERNANCE.md](../DOC_GOVERNANCE.md) règle 9 (« code non modifiable depuis une autre
  session, mais un checkpoint de clôture peut être écrit une fois la phase terminée »).
- **Ne pas toucher `docs/STATE.md`** : propriété du journal de la session Phase 9, déjà
  correct et détaillé, toute réécriture risquerait un conflit d'édition sur le même fichier
  partagé.
- **Ne pas toucher aux modules `core/v9/*.py`, `tests/*.py`, `core/v9/principles/*.yaml`,
  `memory/memory_temp.md`** : lecture seule stricte, conforme au périmètre « documentation et
  gouvernance uniquement » de ce chantier.
- **Étendre `docs/DOCTRINE.md` de 13 à 19 règles** plutôt que de créer un nouveau document de
  doctrine parallèle — préserve la source unique (règle 15, nouvellement ajoutée) plutôt que
  de dupliquer.
- **Ne pas déplacer `docs/architecture/audit_v8_v9_migration.md`** : déjà à sa place
  canonique (arborescence posée par le chantier de gouvernance précédent), aucune action
  nécessaire.
- **Ne pas fusionner `docs/architecture/IMPLEMENTATION_ROADMAP_V9.md`** (marqué `stale` dans
  `DOC_REGISTRY.yml`) avec `docs/ROADMAP.md` dans ce chantier — laissé en l'état pour éviter
  de toucher un document potentiellement encore référencé ailleurs, décision déjà actée par
  le chantier de gouvernance précédent et reconduite ici.

## 8. Risques ouverts

- **Dépendance SDI propriétaire** (MT4 uniquement, pas de fallback) — inchangé depuis l'audit.
- **Réplay vs live** : StaleGate calé pour le live peut rejeter du replay utile — mode réplay
  distinct non implémenté.
- **`zone_diagnostics`** : 9/27 principes dégradés tant que non alimentée — pas une erreur,
  mais un vrai manque à observer.
- **Seuils `PROVISIONAL`** (régime notamment) — non recalibrés sur données V9 réelles.
- **Latence** : 189,58 ms/snapshot mesuré en replay sur 1194 snapshots ; à confirmer sur
  snapshots live réels (charge réseau, EA réels, non simulée).
- **Fichier `memory/memory_temp.md`** : diff de +475 146 lignes constaté dans le working tree
  au moment de ce chantier — journal de travail de la session Phase 9, hors périmètre de ce
  chantier, signalé ici pour information mais non traité (voir [MEMORY_POLICY_V9.md](../doctrine/MEMORY_POLICY_V9.md) : `memory_temp.md` ne doit pas devenir une décharge permanente — à
  surveiller par la session qui le possède).

## 9. Doctrine de séquencement

Rappel consolidé (formalisé dans `DOCTRINE.md` règles 14-19 et `ROADMAP.md` §« Chantiers
futurs distincts ») :

1. Le Git courant est la source de vérité — jamais une mémoire de session ou un état V8 supposé.
2. Une seule source de vérité par sujet — en cas de divergence, synthèse et renvoi, jamais duplication.
3. **Migration métier avant agentification** : Phase 9 (décision/principes/régime) devait être
   canonisée avant tout chantier d'architecture agentique généralisée. C'est chose faite par
   ce mega-checkpoint — la Phase 10 (fédération d'agents) peut désormais être *planifiée* dans
   `ROADMAP.md`, mais ne doit pas être *démarrée* avant stabilisation live de la Phase 9
   (point 4).
4. **Autonomie progressive seulement après stabilité démontrée en live** — pas par anticipation
   documentaire ni par confiance dans des tests replay seuls.
5. **Pas de dépendance bloquante à un provider/modèle LLM** pour le cœur cognitif critique
   (Forces→Décision) — confirmé structurellement : aucun appel LLM dans `core/v9/` à ce jour.
6. **Le chantier « architecture globale agents/routing/mémoire avancée »** et **le chantier
   « skills/agents auto-générés »** restent gelés tant que la phase métier en cours n'est pas
   canonisée (fait, ce mega-checkpoint) **et** stabilisée en live (pas encore fait — market
   open à venir).

## 10. Ce qui ne doit PAS être mélangé maintenant

- **Ne pas démarrer la Phase 10** (fédération d'agents) avant observation live de la Phase 9 —
  même si l'audit a identifié `agent_registry.py`/`federation_evidence_gate.py` comme
  « récupérables en 2-3 jours », ce n'est pas une raison de commencer maintenant.
- **Ne pas confondre** la migration métier Phase 9 (décision/principes, terminée) avec le
  chantier futur « architecture globale agents/routing/mémoire avancée » (non scopé, non
  démarré) — ce sont deux sujets distincts, à ne jamais documenter dans le même paragraphe
  sans cette distinction explicite.
- **Ne pas anticiper** la génération automatique de skills/agents (dossiers `skills/` et
  `agents/` du repo, actuellement de simples README placeholders) tant que les Phases 9-10 ne
  sont pas toutes deux stabilisées en live.
- **Ne pas rouvrir le chantier `zone_diagnostics`** en urgence ce soir — c'est un gap connu,
  documenté, non bloquant pour le market open ; le traiter en pleine analyse (5-8j estimés),
  pas en correctif de dernière minute.
- **Ne pas modifier `docs/STATE.md`** depuis une autre session tant qu'une session y écrit
  activement — règle de coordination déjà observée par ce chantier, à reconduire.

## 11. Rappel — architecture agents/skills future (chantier séparé)

Ce mega-checkpoint **ne scope pas** l'architecture globale agents/routing/mémoire avancée, ni
la génération automatique de skills/agents. Ces deux chantiers sont explicitement mentionnés
ici uniquement pour acter qu'ils **restent hors périmètre** et **dépendent d'un socle stable**
(Phases 9-10 canonisées et calibrées en live) avant d'être scopés à leur tour. Voir
`docs/ROADMAP.md` §« Chantiers futurs distincts » et `docs/DOCTRINE.md` règles 16, 17, 19 pour
la formalisation de cette dépendance.

## 12. Fichiers modifiés par ce chantier (documentation et gouvernance uniquement)

- `docs/phases/PHASE9_DECISION.md` — placeholder remplacé par le contenu de clôture
- `docs/ROADMAP.md` — Phase 9 marquée terminée, section « Chantiers futurs distincts » ajoutée
- `docs/DOCTRINE.md` — règles 11/12 mises à jour, règles 14-19 ajoutées
- `docs/ARCHITECTURE.md` — modules Phase 9 déplacés vers la table stable, mentions « en cours » retirées
- `docs/LEXIQUE.md` / `docs/lexicon/LEXICON_V9.md` — mentions « Phase 9, en cours » retirées ou précisées
- `docs/DOC_REGISTRY.yml` — statut `PHASE9_DECISION.md` (placeholder → active), entrée ajoutée pour ce checkpoint
- `docs/CACHE_BOARD.md` — état global, chantiers actifs, prochaines actions, références pivots mis à jour
- `README.md` — table de statut (139 → 214 tests, ligne Phase 9), arborescence `core/v9/`, rituel de lecture Niveau 4, renvois « 13 règles » → « 19 règles »
- `AGENT.md` — renvoi « 13 règles » → « 19 règles »
- `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md` — ce fichier

Aucun fichier de `core/v9/`, `tests/`, `core/v9/principles/`, `scripts/`, `ea/`, ni
`memory/memory_temp.md` n'a été modifié.

## 13. Validation

- [x] Tests : `python -m pytest tests/ -q` → 214 passed (vérifié par ce chantier, aucune régression)
- [x] `docs/DOC_REGISTRY.yml` mis à jour (statut Phase 9 + nouvelle entrée checkpoint)
- [x] `docs/phases/PHASE9_DECISION.md` mis à jour (clôture)
- [ ] `docs/STATE.md` — volontairement non modifié (propriété de la session Phase 9, voir §7)

## 14. Prochaine étape

Déploiement live à l'ouverture du marché (voir `docs/deployment/V9_DEPLOYMENT_GUIDE.md` et
`docs/ROADMAP.md` §Timeline). Observer via `scripts/v9_dashboard.py --watch signals`/
`--watch decisions`. Ne pas démarrer la Phase 10 avant retour d'observation live de la
Phase 9.
