# STATE — PowerFlow V10

**Pointeur exécutif actif — mis à jour :** 2026-08-07 12:18 CEST  
**Branche / HEAD :** `feat/v9-foundation-clean`  
**Validation courante :** `python -m pytest tests/test_v10_*.py -q` → **1172 passed**, 3 warnings `sklearn` attendus.

> Source canonique détail : `docs/V10/STATE.md`  
> Gouvernance fraîcheur documentaire : `docs/V10/DOCUMENT_STATUS.md`

---

## 🟢 État opérationnel actuel

| Composant | État | Notes |
|---|---|---|
| Tests V10 | ✅ 1172/1172 verts | Vérifié 2026-08-05 |
| Tests suite complète | ⚠️ 5421/5437 | 15 V9 rouges pré-existants + 1 |
| Capture server | ✅ port 31685 LISTENING | ~1 min fraîcheur |
| DB v9_forces.db | ✅ 259 540+ snapshots | |
| Orchestrateur | ✅ 2 workers alive | 0 crash |
| MT5 bridge | ✅ Tickmill paper-only | |
| Cron boucle décision | ✅ Sprint 15 actif | 30 min polling |
| Boucle auto-recalibration | ✅ Sprint 7 actif | verdict HOLD |
| Exécution réelle | ❌ DÉSACTIVÉE | paper_only=True hard-codé |

---

## 🚀 Prochaines étapes prioritaires (CEO-level)

1. **[P1] Calibration live Fatman Phase A** — comparer FatmanCalculator vs indicateur visuel (critère : 10 signaux alignés)
2. **[P1] Promotion RL SHADOW→ACTIVE** — 100 trades paper, gates : WR≥50 / Sharpe≥0.3 / DD≤50p / consistency≥75%
3. **[P2] Validation signaux live Sprint 14-15** — tenir 2-3 jours consécutifs
4. **[P3] Nettoyage 15 tests V9 rouges** — mandat Søn requis, V9 verrouillé
5. **[P3] Nettoyer V9_EXECUTION_ENABLED=1** — résidu V9 dans config, 0 consommateur V10

---

## ⚠️ Dettes techniques actives

Voir `docs/DEBT_TRACKER.md` pour le registre complet avec propriétaires et deadlines.

**Top 3 critiques :**
- 15 tests V9 rouges (pré-existants, hors périmètre V10)
- `V9_EXECUTION_ENABLED=1` résidu dans `config/v9_kill_switches.env`
- `docs/V10/CACHE_BOARD.md` obsolète (692 tests, HEAD 40ed93a)

---

## 🏆 Jalons V10 livrés

| Sprint | Livrable | Date |
|---|---|---|
| Sprint 1-3 | HMM régimes + SMC public + ICT OTE | Juin 2026 |
| Sprint 4 | Filter compositor + GARCH + Wyckoff | Juin 2026 |
| Sprint 5 | Gate final public_filters + error learner | Juin 2026 |
| Sprint 6 | Night report + shadow — verdict HOLD | Juillet 2026 |
| Sprint 7 | Auto-recalibrator R8 (REVERT conservateur) | Juillet 2026 |
| Sprint 8 | Cron nocturne auto | Juillet 2026 |
| Sprint 9 | Net exposure + doubles opposées | Juillet 2026 |
| Sprint 10 | Risk shield R10 gates unifiés | Juillet 2026 |
| Sprint 11 | Risk dashboard net exposure par devise | Juillet 2026 |
| Sprint 12 | Démo composition publique live | Juillet 2026 |
| Sprint 13 | Decision pipeline + bouclier R10 | Août 2026 |
| Sprint 14 | Live decision polling bars → régimes HMM | Août 2026 |
| Sprint 15 | Cron boucle décision live 30min | Août 2026 |
| Phase 12 | Contexte fractal 7 TF + cinématique M1/M5 | Août 2026 |
| Bug fix R9 | Safe Haven flip inversé — commit `885a851` | Août 2026 |
| Cognitive Continuum | Mémoire V9 read-only + Cortex + RAG | Août 2026 |

---

## 📚 Liens essentiels

- [`docs/SOUL.md`](docs/SOUL.md) — Vision système + pipeline + modules
- [`docs/LEVIER_HUB.md`](docs/LEVIER_HUB.md) — 19 leviers L1-L19 avec poids et ΔWR
- [`docs/PIPELINE_MAP.md`](docs/PIPELINE_MAP.md) — Pipeline ASCII + fail-open R6
- [`docs/AGENT_PROMPT_MASTER.md`](docs/AGENT_PROMPT_MASTER.md) — Prompt universel agent IA
- [`docs/SESSION_RITUEL.md`](docs/SESSION_RITUEL.md) — Rituel démarrage/fin session
- [`docs/DEBT_TRACKER.md`](docs/DEBT_TRACKER.md) — Registre dettes techniques
- [`docs/DECISIONS_LOG.md`](docs/DECISIONS_LOG.md) — Journal décisions structurantes
- [`docs/ZCODE_MISSION.md`](docs/ZCODE_MISSION.md) — Mission brief Zcode (prête à coller)
- [`docs/V10/STATE.md`](docs/V10/STATE.md) — Détail technique Sprint 1-15
