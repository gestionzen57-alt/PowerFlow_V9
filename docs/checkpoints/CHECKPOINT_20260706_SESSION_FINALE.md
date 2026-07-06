# CHECKPOINT 2026-07-06 — Session Finale Phase 9.5

**Date** : 2026-07-06 (fin de journée)
**Branche** : `feat/v9-foundation-clean` (HEAD : `74d4b16`)
**Tests** : **359 verts** (zéro régression)
**DB** : `data/v9_forces.db` — 582 MB, 3 UNIQUE constraints, idempotence complète

---

## Résumé des livraisons de la journée (4 sessions successives)

| Session | Chantier | Commit | Tests |
|---------|----------|--------|-------|
| **S1** | NewsContext (calendrier économique pur) | `05f8232` + `f278a1e` | 354 |
| **S2** | Pipeline bout-en-bout + Idempotence decisions | `85b40fe` + `3d42b6c` | 359 |
| **S3** | YAML news-aware (4 principes) | `a87d88f` | 359 |
| **S4** | DORMANT P2 → PROPAGÉ (4 champs) | `f4c3c13` | 359 |
| **S5** | AGENT.md racine V9 + audits | `74d4b16` | 359 |

---

## État courant — Phase 9.5 TERMINÉE

### Chaîne cognitive complète (9 couches)
```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité
       → Régime → Principes → Signal → Décision
```

### Métriques clés
- **Principes** : 10 ACTIVE (9 `node_rule` + `GRAMMAR_REGIME`) / 17 SHADOW
- **Contexte propagé** : **31 champs** (CONTEXT_CONTRACT.md)
- **NewsContext** : 5 champs actifs (`news_phase`, `news_distance_min`, `news_importance`, `news_session_clean`, `news_type`)
- **Signal live** : 3 `preparer_entree` GBPUSD M5 haussière conf 80-100 (2026-07-06 14:35 UTC)
- **Décisions** : 3957 total (3 directionnelles live, 2658 `aucune_action` live, 1296 replay)

### Seuils calibrés (config.py)
| Seuil | Valeur | Statut | Base |
|-------|--------|--------|------|
| `ANTAGONISM_THRESHOLD` | 31.39 | **CALIBRÉ** | P80, n=218 M5+ live |
| `COALITION_THRESHOLD` | 5.0 | **PROVISIONAL** | Suggéré 5.33 (n=3957) / 3.96 (n=1708) |
| `PLIURE_THRESHOLD` | 1.7 | **CALIBRÉ** | P90 pente réelle, n=1454 M5+ |
| `REGIME_LOOKBACK_BARS` | 20 | PORTÉ V8 | P3 (non recalibré) |
| `SIMILARITY_THRESHOLD` | 0.65 | PORTÉ V8 | P3 (non recalibré) |
| `REPLAY_MIN_CAS` | 3 | MALUS live | P3 → temp 1 recommandé |

### Calibration `--principes` (n=3306 évaluations ACTIVE)
| Principe | Hit Rate | Décl. | Statut |
|----------|----------|-------|--------|
| POWER_ANGLE_BREAK | 1.1% | 38 | ACTIVE |
| PRICE_LAG_AT_NODE_BIRTH | 3.6% | 120 | ACTIVE |
| ZONE_RETEST | 1.6% | 54 | ACTIVE |
| COALITION_NODE | 1.5% | 48 | ACTIVE |
| NODE_BIRTH_FAST | 0.6% | 20 | ACTIVE |
| RAW_NODE_BIRTH | 0.6% | 20 | ACTIVE |
| GRAVITY_RESPRING_NODE | 0.4% | 13 | ACTIVE |
| ANTAGONIST_NODE | 0.0% | 0 | ACTIVE (aligné H1/M5) |
| ELASTIC_BREATH | 0.0% | 0 | ACTIVE |

**Verdict** : Aucune promotion SHADOW→ACTIVE possible (règle 25 : hit_rate ≥ 60% sur ≥ 50 décl.)

---

## Chantiers clos aujourd'hui

### 1. **COALITION_THRESHOLD audit + calibration**
- Analyse `--analyze` : suggéré **5.33** (P20, n=3957 scènes live)
- Précédent suggéré 3.96 remplacé
- **Décision** : maintien à 5.0 PROVISIONAL (règle 25 : attendre n>5000 + WIN/LOSS)
- 3 décisions directionnelles live seulement — insuffisant pour validation

### 2. **Inventaire migration V8→V9** (audit MIGRATION_POLICY_V9.md)
| Priorité | Composants | Effort | Statut |
|----------|------------|--------|--------|
| **P1** | 27 principes YAML, agent_registry, evidence_gate, règles GOLDEN, ShiftIndex EA | ~6-11j | **À faire** |
| **P2** | zone_diagnostics, workflows YAML, MT5 ticks, structure_ledger | ~15-25j | **Décision produit** |
| **P3** | Doublons versionnés, dashboard_*, scheduler_*, telegram_*, monolithe MCP | — | **Archiver** |

**Gaps critiques V8→V9 identifiés** :
- `zone_diagnostics` (36k lignes) — aucun équivalent V9
- `detected_patterns.resolution_pips` / `is_win` — retour trade réel absent V9
- `regime_snapshots` (327k lignes) — absent V9
- `structure_ledger` multi-TF SQL typé — remplacé par JSON V9

---

## Documents mis à jour (cette session)

| Fichier | Modification |
|---------|--------------|
| `AGENT.md` | Réécrit complet : état Phase 9.5, seuils, doctrine, chantiers, rituel démarrage |
| `docs/STATE.md` | Chantiers nettoyés (COALITION_THRESHOLD, migration inventory cochés) |
| `workspace/perplexity/ACTIVE_TASKS.md` | Sessions 4-5 cochées, COALITION_THRESHOLD + migration ajoutés |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | 2 nouvelles entrées (COALITION_THRESHOLD + migration inventory) |
| `docs/architecture/CONTEXT_CONTRACT.md` | 4 champs P2 reclassés DORMANT→PROPAGÉ + news CONSOMMÉ |
| `core/v9/principles/GRAMMAR_CONTEXTE.yaml` | Notes enrichies (contexte_temporel_fenetre) |
| `core/v9/principles/GRAMMAR_PULLBACK.yaml` | Notes enrichies (point_de_rupture_declencheur, variante) |
| `core/v9/principles/GRAMMAR_REGIME.yaml` | Notes enrichies (contexte_temporel_fenetre, point_de_rupture) |
| `core/v9/principle_engine.py` | 4 fallbacks + 4 injections P2 DORMANT + coalition_news_allow |

---

## Git — Commits de la session

```
74d4b16  docs: AGENT.md racine V9 — état courant Phase 9.5
f4c3c13  feat(v9): session 5 — DORMANT P2 promus PROPAGÉ (4 champs) + GRAMMAR notes
a87d88f  feat(v9): session 4 — YAML news-aware (4 principes)
3d42b6c  fix(v9): decision — idempotence par snapshot_id (dédup rejeu)
85b40fe  test(v9): pipeline end-to-end — snapshot → signal → décision (gardien permanent)
... (commits antérieurs S1-S2)
```

**Branche propre** : `feat/v9-foundation-clean` up-to-date avec `origin`

---

## Prochaines actions (ordre de priorité)

1. **Observation live continue** — sessions Asie/Europe/US
   - `python scripts/v9_dashboard.py --watch decisions --once`
   - `python scripts/v9_calibration.py --principes` (matin/aprèm)

2. **Calibration `--principes` à ~500 scènes** post-tuning YAML (news-aware + P2 DORMANT)

3. **COALITION_THRESHOLD** — réévaluer à n>5000 scènes + WIN/LOSS enregistrés

4. **Inventaire migration V8→V9 — exécution P1** :
   - Porter 27 principes YAML → V9 `core/v9/principles/` (déjà fait pour 10 ACTIVE, 17 SHADOW restants)
   - `agent_registry.py` + `evidence_gate` → V9 (Phase 10 fédération)
   - Extraire règles GOLDEN de `pf_mt5_bridge_v2.py`
   - Vérifier ShiftIndex=1 dans EA V9

5. **Promotion SHADOW→ACTIVE** — décision sur hit_rate live (règle 25)

6. **Nettoyage documentaire stales** — 7 docs mentionnent encore "zone_diagnostics non alimentée"

---

## Rituel de fermeture session validé
- [x] `git pull` + `pytest tests/ -q` → 359 verts
- [x] Périmètre explicité et livré complet (4 sessions = 4 livraisons)
- [x] Tests verts (zéro régression)
- [x] `CONTEXT_CONTRACT.md` mis à jour (nouveaux champs tracés)
- [x] Principes YAML consommateurs mis à jour (règle 23)
- [x] Commits atomiques (1 par unité logique)
- [x] `DECISIONS_LOG.md` — 1 entrée par décision structurante
- [x] `STATE.md` à jour
- [x] `git push origin feat/v9-foundation-clean`

---

**Fin de session 2026-07-06 — Phase 9.5 canonisée et stable en live**