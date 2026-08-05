# V10 STATE — État du pipeline cognitif V10

**Dernière mise à jour** : 2026-08-05 (~09:00 UTC) — ZCode (mandat CEO)
**Branche active** : `feat/v9-foundation-clean`
**HEAD courant** : Phase 32 Currency Behavior (à committer sur 6255d55)

---

## ✅ Phases livrées

### Phase 32 — Currency Behavior (2026-08-05, ZCode)
- `core/v10/v10_currency_behavior.py` — 5 couches : observation,
  comportement (états/coalitions/leadership/régimes/lead-lag), fidélité
  (linéaire + extrême P90/P10), apprentissage (calibration R8 + drift
  + réversibilité), expression (narratives V1/V2 + behavior_context)
- 43 tests verts (cumul V10 : **774/774**, zéro régression)
- `scripts/v10_currency_behavior_demo.py` + rapport JSON + rapport MD
- **Découvertes R9** : corrélation linéaire forces→prix ≈ 0 MAIS WR
  65-90% aux queues P90/P10 → GBPUSD + AUDUSD RELIABLE, USDJPY DÉGRADÉE
  (exclue du gate R10). Régime SAFE_HAVEN calibré (59.9/38.6).
- Réversibilité totale : `apply_behavior_config` / `reset_behavior_config`
  / `get_behavior_state` (jamais bloqué par un choix)

### Phases antérieures (résumé)
- Phases 1-31 Edge Fund (commits `b1c3b98` → `40ed93a`) + Phase 28b
  (étapes 1-4, commits `21225cf` → `6255d55`) : 731 tests → 774
- Cœur cognitif V10 (Phases E-F) : v10_force/structure/context/orchestrator
- Phase A-D institutionnelles + Edge Fund Quantique Phases 1-3

---

## 📊 État live (2026-08-05 ~08:00 UTC)

| Élément | État |
|---|---|
| Capture server | ✅ port 31685 LISTENING (PID 18344) |
| DB forces_snapshots | 257 395+ lignes, fraîcheur ~1 min |
| Tests V10 | **774/774 verts** |
| HEAD | 6255d55 + Phase 32 (à committer) |
| Régime marché (calibré) | SAFE_HAVEN — lecture recalibrée |

---

## 🔄 Prochaines étapes (suggérées CEO)

| Phase | Contenu | Statut |
|---|---|---|
| 32.2 | Table stats comportementales par (devise, TF, session, état) → R4 | À valider |
| 32.3 | Branchement `behavior_context` dans signal orchestrator | À valider |
| 32.4 | Watchdog rotation de régime (alerte SAFE_HAVEN↔RISK_ON) | À valider |
| 20++ | Reconstruction forces natives V10 (TA lecture) | À valider |
| 25+ | Validation 100 trades paper (cible Sharpe ≥ 0.5) | À valider |
| 28+ | Promotion RL SHADOW→ACTIVE si 100 trades ≥ 4 gates | À valider |

---

## 🎯 Doctrine V10 respectée

R1-AGIR ✅ · R2 additif pur (0 import core/v9/) ✅ · R3 INVENTER ✅
(fidélité extrême découverte sur données réelles) · R5 CoT ✅ ·
R6 fail-open ✅ · R7 tests verts 774/774 ✅ · R8 auto-calibration ✅ ·
R9 audit honnête (corr ≈ 0 documentée) ✅ · R10 capital protégé ✅

## 🔗 Liens

- Rapport Phase 32 : `docs/V10/V10_PHASE_32_CURRENCY_BEHAVIOR_REPORT.md`
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
