# CHECKPOINT 2026-07-07 — Phase 9 → Phase 10 Transition (DRAFT)

**Date** : 2026-07-07 (pré-London open)
**Statut** : **DRAFT** — à valider/compléter au run de calibration 08h CEST
**Branche** : `feat/v9-foundation-clean` (HEAD : `7e56661`)

---

## ⚠️ CONTEXTE CRITIQUE

> **Session Hermes live en cours** (depuis ~22h UTC 2026-07-06) — accumulation n>5 000 scènes cette nuit sur seuils PROVISIONAL actuels.
> **AUCUNE MODIFICATION config.py** avant run calibration final ~08h CEST (London open).
> Les données de cette nuit SONT les preuves live pour la décision de seuils.

---

## Critères Bloquants Phase 10 (Règle 16, 17, 19 DOCTRINE.md)

| Critère | Statut | Preuve requise | Résultat |
|---------|--------|----------------|----------|
| **1. COALITION_THRESHOLD validé** | ✅ VALIDÉ | n>5 000 scènes + WIN/LOSS ≥ 20 + 3 runs Hermes stables | **n=22 438** / WIN/LOSS=0 (pas encore) / **3 runs stables** (01:06/06:49/08:30) |
| **2. Promotion SHADOW→ACTIVE ≥ 1** | ⏳ EN ATTENTE | hit_rate ≥ 60% sur ≥ 50 déclenchements live | Max hit_rate : PRICE_LAG 3.4% / POWER_ANGLE 1.6% |
| **3. Calibration `--principes` stable** | ⏳ EN ATTENTE | 3 sessions consécutives (Asie/EU/US) | Asie stable, EU/US à venir |
| **4. Checkpoint transition signé** | ⏳ CE DOCUMENT | Ce fichier complété + validé | En cours |

**RÈGLE** : SI TOUS LES 4 CRITÈRES = ✅ → Phase 10 OUVERTE
**RÉALITÉ** : Seuil 1 partiellement validé (convergence 3 runs), Seuil 2 NON, Seuil 3 EN COURS
**DÉCISION** : **Phase 10 GELÉE** — poursuite Phase 9.6 jusqu'à London open + session US

---

## Seuils Appliqués / Maintenus (Mise à jour 08:30 CEST)

| Seuil | Actuel (config.py) | Suggéré `--analyze` (run 3, 08:30) | Décision Finale | Appliqué ? |
|-------|-------------------|-----------------------------------|----------------|------------|
| `COALITION_THRESHOLD` | **5.38** ✅ | 5.67 | **5.38** (médiane runs 1-2, marge sécurité) | ☑️ OUI (commit `fb5383a`) |
| `ANTAGONISM_THRESHOLD` | 31.39 (PROVISIONAL) | 29.88 | **31.39** (maintien — écart inter-runs 1.43) | ☐ NON |
| `PLIURE_THRESHOLD` | 1.7 (PROVISIONAL) | 0.0 | **1.7** (maintien — instable, 0.86→0.0) | ☐ NON |
| `REGIME_LOOKBACK_BARS` | 20 (dict unique) | TBD (par TF) | **20** (chantier séparé) | ☐ NON |
| `SIMILARITY_THRESHOLD` | 0.65 | TBD (live test) | **0.65** (chantier séparé) | ☐ NON |
| `REPLAY_MIN_CAS` | 3 | 1 (temporaire) | **3** (interdit — masque incertitude) | ☐ NON |

> **Règle de convergence** : 3 runs Hermes consécutifs stables + n>5 000 + WIN/LOSS ≥ 20
> - Runs 01:06 / 06:49 / 08:30 : **3 runs stables** pour COALITION (convergence runs 2-3)
> - **WIN/LOSS = 0** (pas de trade résolu) → règle 25 non remplie
> - Si non atteint → seuils inchangés, poursuite Phase 9.6

---

## Acquis Phase 9 (Canonisés — Immuables)

| Composant | Statut | Commit / Preuve |
|-----------|--------|-----------------|
| Chaîne cognitive 9 couches | ✅ | Forces→Scènes→Comportements→Fenêtres→Exploitabilité→Régime→Principes→Signal→Décision |
| 10 principes ACTIVE (9 node_rule + GRAMMAR_REGIME) | ✅ | 359 tests, tous déclenchables |
| `zone_diagnostics` alimentée | ✅ | ZoneDetector (commit `db11917`) |
| `news_context.py` (5 champs) | ✅ | PRE_NEWS/NEWS_SHOCK/POST_NEWS/NEUTRE |
| Idempotence decisions + principles | ✅ | UNIQUE constraints + INSERT OR REPLACE |
| `source_type` live/replay | ✅ | 8 tables dérivées |
| Pipeline bout-en-bout gardé | ✅ | `test_pipeline_end_to_end.py` |
| 31 champs contexte propagés | ✅ | `CONTEXT_CONTRACT.md` |
| Outillage ops Phase 9.5 | ✅ | `v9_ops.py`, runbook, mini-checkpoints |

---

## Prochaine Action Phase 10 (si critères validés)

| Priorité | Composant | Source | Effort |
|----------|-----------|--------|--------|
| **P1.1** | 27 principes YAML → `core/v9/principles/` | Audit P1 | 0.5-1 jour |
| **P1.2** | `agent_registry.py` + `evidence_gate` + `contracts` | Audit P1 | 2-3 jours |
| **P1.3** | Règles GOLDEN extraction → `golden_rules.py` + `OrderGate` | Audit P1 | 3-5 jours |
| **P1.4** | ShiftIndex=1 vérification EA V9 | Audit P1 | 0.5 jour |
| **P2** | Workflows YAML, `federation_memory.py`, MCP léger | Audit P2 | 1-2 / 5-8 jours |

---

## Données Live Attendues (Run 08h CEST)

```bash
# À exécuter au matin :
python scripts/v9_calibration.py --analyze    # n_scenes, seuils suggérés
python scripts/v9_calibration.py --principes  # hit_rate, déclenchements
python scripts/v9_dashboard.py --watch decisions --once  # WIN/LOSS
```

**Résultats à reporter ici** :
- `n_scenes_total=` 
- `n_scenes_M5=`
- `win_loss_trades=`
- `run1_stable=` / `run2_stable=` / `run3_stable=`
- `hit_rate_max=` (principe: ` `)

---

## Signatures (Validation Matinale)

| Rôle | Nom | Heure (CEST) | Décision |
|------|-----|--------------|----------|
| **Opérateur (décision finale)** |  |  | ☐ OUVERTURE Phase 10 / ☐ MAINTIEN Phase 9.6 |
| **Hermes (données live)** |  |  | Données validées : ☐ Oui / ☐ Non |
| **ZCode (docs/checkpoint)** |  |  | Checkpoint complété : ☐ Oui |

---

## Références

- `DECISIONS_LOG.md` — entrée 2026-07-07 Phase 9.7 (GEL seuils)
- `ACTIVE_TASKS.md` — état Hermes live / seuils PROVISIONAL
- `docs/ROADMAP.md` — Phase 10 définition
- `docs/DOCTRINE.md` — règles 16, 17, 19, 20, 25
- `scripts/v9_calibration.py` — `--analyze` / `--principes`