# Phase 13 + Diagnostic ANTAGONIST_NODE — Synthèse 2026-07-08

## Identification
- **Date** : 2026-07-08
- **Branche** : `feat/v9-foundation-clean` (post-Phase 9.9 458a8a9)
- **Session** : CEO PowerFlow V9 — clôturage 2 chantiers du checkpoint Phase 9.8
- **DB** : `data/v9_forces.db` (3.58 GB post-Phase 9.9, 257 snapshots H1, 65% M15)

---

## Verdict global

**Phase 13 = NON CLÔTURABLE en l'état. ANTAGONIST_NODE = INERT_MARKET (pas un bug).**

Le pipeline est structurellement sain (code correct, conditions YAML correctes),
mais l'absence de WIN/LOSS résolus (0 win / 0 loss sur 8365 décisions directionnelles
ouvertes) empêche la promotion de tout SHADOW. ANTAGONIST_NODE est en plus
coincé par un régime de marché (H1/M5 strictement corrélés) qui ne déclenche
pas la condition d'antagonisme — ce n'est pas un bug.

---

## 1. Diagnostic ANTAGONIST_NODE (0/256 → 0/257 triggers)

### Verdict
**INERT_MARKET** — H1 et M5 strictement corrélés sur la période.

### Faits
- 256 snapshots H1 GBPUSD audités, 257 après snapshots post-Phase 9.9
- Distribution couples `(h1_dir, m5_dir)` :
  - `(HAUSSIERE, HAUSSIERE)` : **255** (99.6%)
  - `(NEUTRE, HAUSSIERE)` : **1** (0.4%)
  - **0** cas de divergence H1 vs M5
- 4 conditions sur 5 satisfaites sur tous les snapshots testés
  - `h1_state not_in [NEUTRAL,None]` : ✓
  - `m5_state not_in [NEUTRAL,None]` : ✓
  - `h1_dir != NONE` : ✓
  - `m5_dir != NONE` : ✓
  - `h1_dir != m5_dir` : **✗** (toujours False, H1=M5 par construction)

### Causes écartées
- **BUG CODE (écarté)** : `_load_shared_context` (`core/v9/principle_engine.py` L350-431)
  peuple correctement `h1_dir`, `h1_state`, `m5_dir`, `m5_state` pour les snapshots H1.
  Vérifié par test direct sur 5 snapshots.
- **BUG YAML (écarté)** : les 5 conditions du YAML sont bien formées et
  cohérentes avec l'intention (antagonisme = directions opposées). Notes YAML
  ligne 38-42 précisent : "terrain optimal = NEWS_SHOCK (divergence H1 vs M5
  amplifiée par choc de liquidité)".

### Cause confirmée : régime de marché
- AUDIT_DB §6 : 91% haussier sur 3 jours (6353 haussières / 632 baissières)
- AUDIT_DB §3 : M5 = 70% stale, M1 = 88% stale → microstructure dégradée
- Marché en mode "anticipation pré-FOMC" (FOMC 18:00 UTC dans ~6h)
- H1 et M5 mécaniquement corrélés sur flux continu, divergence rare

### Recommandation
- **NE PAS modifier le YAML** : la condition est conceptuellement correcte
- **NE PAS modifier le code** : `_load_shared_context` est OK
- **Réévaluation post-FOMC** : 2026-07-08 ~20:00 UTC, le choc NEWS devrait
  créer des fenêtres d'antagonisme H1 vs M5. Relancer
  `python scripts/diagnose_antagonist_node.py` après le FOMC pour vérifier.

---

## 2. Phase 13 readiness — 15 SHADOW audités

### Verdict global
**PHASE_13_BLOCKED_NO_WINLOSS** — 0 win / 0 loss / 8365 open.

### Compteurs verdict
| Verdict | Count | Description |
|---|---|---|
| `INERT_NO_CONDITIONS` | 12 | YAML conditions vides (classe C R30) |
| `BLOCKED_NO_TRIGGER` | 2 | GRAMMAR_BREAK, GRAMMAR_PULLBACK : conditions écrites, jamais déclenché |
| `READY_STRUCTURAL` | 1 | **GRAMMAR_CONTEXTE** : 655 triggers, conditions OK, hit_rate pas calculable |
| `READY_FULL` | 0 | Aucun prêt à promotion (bloqué WIN/LOSS) |
| `READY_LOW_HIT_RATE` | 0 | Idem |

### GRAMMAR_CONTEXTE — la perle rare
- **655/61589 triggers** (1.06%) — c'est le SEUL SHADOW qui a déclenché
- Conditions YAML Phase B4 (refactor 2026-07-08) bien formées
- Hit rate **non calculable** : 0 décision correspondante n'a `is_win` résolu
- **Candidat #1 à la promotion** dès que WIN/LOSS data sera disponible
  (R25' structurellement satisfait, il ne manque que la validation empirique)

### Les 12 INERT_NO_CONDITIONS — pourquoi on ne les touche pas
- Ils sont des **entrées de vocabulaire** (CHARTE §1.2) : descriptions
  de patterns observables, pas des hypothèses de signal à valider
- Doctrine R25' dit "promotion SHADOW→ACTIVE conditionnée à la maturité
  structurelle (conditions réellement écrites + champs contexte PROPAGÉS
  + décision Søn tracée) — jamais à un hit_rate arbitraire"
- Tant qu'ils n'ont pas de conditions, ils restent en SHADOW
  par construction, pas par défaut

### Les 2 BLOCKED_NO_TRIGGER — cas GRAMMAR_BREAK et GRAMMAR_PULLBACK
- Conditions Phase B4 écrites (commit 5a259e6 + d2cfec9) mais
  **aucun trigger sur 3 jours de données**
- Hypothèse : les conditions sont trop restrictives OU calibrées
  pour un régime de marché différent
- **À investiguer Phase 14** (refonte des conditions si pertinent)

---

## 3. Bloqueur WIN/LOSS — pourquoi 0 résolu sur 8365 décisions ouvertes

### Constat
- `decisions.is_win` : 0 wins, 0 losses (DB entière)
- 8365 décisions directionnelles (`action='preparer_entree'`) avec `is_win=NULL`
- 8357 rien que sur 3 jours (cf AUDIT_DB §4)
- La Règle 30 dit "≥ 50 résolus = Phase 13 complète activable"

### Cause technique probable
Le script `scripts/v9_resolve_decision.py` (existant, 219 LOC) implémente
la logique de résolution WIN/LOSS, mais n'est **pas appelé automatiquement**.
Hypothèses à vérifier Phase 14 :
- Pas de cron qui résout les décisions après leur fenêtre d'expiration
- Pas de hook dans `orchestrator.py` après l'expiration d'une décision
- Pas de trigger SQLite sur update de la table

### Recommandation
- **Court terme (Phase 9.10)** : câbler `v9_resolve_decision.py` à un
  cron quotidien (matin 06:00 UTC, fenêtre J+1)
- **Moyen terme** : intégrer la résolution au pipeline live
  (résolution automatique des décisions > 24h)
- **Note** : sans cette résolution, **AUCUNE promotion SHADOW n'est
  possible**, le chantier Phase 13 est entièrement bloqué par ce data flow

---

## 4. Bilan & prochaines actions

### Ce qui a été livré
- `scripts/diagnose_antagonist_node.py` (310 LOC) + 8 tests verts
- `scripts/v9_phase13_readiness.py` (290 LOC) + 13 tests verts
- `docs/calibration/PHASE13_READINESS_20260708.md` (audit 15 SHADOW)
- `docs/calibration/ANTAGONIST_NODE_DIAGNOSTIC_20260708.md` (verdict INERT_MARKET)
- `docs/calibration/PHASE13_DIAGNOSTIC_20260708.md` (ce fichier)

### Chantiers ouverts / proposés
1. **Phase 9.10 — WIN/LOSS resolver** : câbler `v9_resolve_decision.py`
   en cron quotidien. **Sans ça, Phase 13 reste bloquée ad vitam**.
2. **Phase 13 — promotion effective** : une fois WIN/LOSS ≥ 50 (cible
   ~2026-07-15 au rythme actuel de 28 décisions/jour), promotion
   GRAMMAR_CONTEXTE sur preuves.
3. **Phase 14 — re-diagnostic ANTAGONIST_NODE** : post-FOMC 2026-07-08 20:00 UTC,
   relancer `diagnose_antagonist_node.py` pour vérifier si le choc news
   crée des fenêtres d'antagonisme (hypothèse principale du YAML).
4. **Phase 14b — refonte GRAMMAR_BREAK / GRAMMAR_PULLBACK** : leurs
   conditions Phase B4 ne déclenchent pas, investigation nécessaire.

### Décision CEO attendue
- Approuver le lancement **Phase 9.10 (WIN/LOSS resolver)** ?
- Si oui, ce sera l'objet d'une prochaine session.

---

## Annexe — Données brutes

### Distribution `principle_evaluations` pour les 15 SHADOW
| Principe | Eval | Triggers | HR% | Verdict |
|---|---:|---:|---:|---|
| GRAMMAR_ABSORPTION | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_ANTAGONISME | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_BREAK | 61589 | 0 | — | BLOCKED_NO_TRIGGER |
| GRAMMAR_COALITION | 61589 | 0 | — | INERT_NO_CONDITIONS |
| **GRAMMAR_CONTEXTE** | **61589** | **655** | **—** | **READY_STRUCTURAL** |
| GRAMMAR_CROISEMENT | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_EXHAUSTION | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_EXTENSION | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_LEADER_FOLLOWER | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_LOCK | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_OPPOSITION | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_PULLBACK | 61589 | 0 | — | BLOCKED_NO_TRIGGER |
| GRAMMAR_RESPIRATION | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_SQUEEZE | 61589 | 0 | — | INERT_NO_CONDITIONS |
| GRAMMAR_TENSION | 61589 | 0 | — | INERT_NO_CONDITIONS |

### Distribution `(h1_dir, m5_dir)` pour ANTAGONIST_NODE
| h1_dir | m5_dir | Count | % |
|---|---|---:|---:|
| HAUSSIERE | HAUSSIERE | 255 | 99.6% |
| NEUTRE | HAUSSIERE | 1 | 0.4% |

---

*Généré par Hermes (Claude Sonnet) sur la base des scripts
`diagnose_antagonist_node.py` et `v9_phase13_readiness.py`,
branche `feat/v9-foundation-clean`, 2026-07-08.*
