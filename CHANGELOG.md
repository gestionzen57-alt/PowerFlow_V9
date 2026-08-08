# CHANGELOG — PowerFlow V10

> Ce fichier est un journal des changements majeurs par sprint/phase.
> Source de vérité tests : `pytest tests/` sur `feat/v9-foundation-clean`.

---

## [Sprint 24] — 2026-08-08 (Perplexity GitHub MCP — No-limit CEO)

### Ajouté
- `conftest.py` racine : skip automatique des 15 tests V9 rouges à la collection pytest (mandat CEO P3)
- `tests/conftest_v9_skip.py` : liste officielle + docstring mandat CEO
- `tests/pytest_v9_skip.ini` : marker `v9_red`
- `docs/V10/P3_NETTOYAGE_V9.md` : audit complet 15 tests V9 skippés
- `docs/V10/SPRINT_24_ROADMAP.md` : backlog Sprint 24 complet (6 tâches)
- `docs/V10/RL_PROMOTION_TRACKER.md` : tracker SHADOW→ACTIVE (gates, historique, plan)
- `docs/V10/RL_FAIL_ANALYSIS_S24.md` : analyse détaillée échecs EURUSD+USDJPY
- `docs/V10/SPRINT_24_SCRIPTS.md` : doc scripts générés
- `docs/V10/DOCUMENT_STATUS.md` : hiérarchie de vérité mise à jour
- `scripts/v10_metrics_dashboard.py` : dashboard CEO live (WR, RL, edges, gates)
- `scripts/v10_rl_shadow_rerun.py` : re-run shadow ciblé EURUSD+USDJPY
- `scripts/v10_walkforward_30d.py` : walk-forward 30j EURUSD M30 (verdict GO/NO-GO)
- `scripts/v10_s24_batch.py` : orchestrateur batch CEO (3 étapes chainées)
- `scripts/v10_sprint_report.py` : rapport Telegram hebdo CEO (Markdown)
- `scripts/v10_rl_fail_analysis.py` : analyse patterns échec shadow (session, streak, action)
- `scripts/v10_night_cron_s24.sh` : cron nocturne étendu 11 étapes (S23 + sprint_report + rl_fail)
- `.github/workflows/v10_ci.yml` : CI GitHub Actions (tests V10 + lint ruff, skip V9 rouges)
- `docs/V10/CACHE_BOARD.md` : statut P3 exécuté, Sprint 24 init
- `docs/V10/STATE.md` : P3 intégré, roadmap S24, HEAD mis à jour
- `ZCODE_RESUME_PROMPT.md` : mis à jour Sprint 24 + Perplexity MCP

### Corrigé
- `nonexistent_xyz.db` supprimé (fichier vide artefact — R9 nettoyage)

### Tests
- **1310/1310 verts** — inchangé
- **15 tests V9 rouges** → skippés automatiquement (conftest.py racine)

---

## [Phase 19] — 2026-08-08 (ZCode)
- Fix watchdog JPY : seuils ×100 pour paires *JPY
- Watchdog HEALTHY (exit 0)

## [Phase 18] — 2026-08-08 (ZCode)
- Cron nocturne 10 étapes complet
- Night report : 9 731 signaux, NY +18.14pts
- Replay batch : 17 960 trades, 8 edges ≥50%

## [Phase 17] — 2026-08-08 (ZCode)
- RL SHADOW 100 trades × 4 paires : 2/4 gates (GBPUSD ✅ AUDUSD ✅)

## [Phase 16] — 2026-08-07 (ZCode)
- Calibration live Fatman : 10/10 VALID, alignement 86.7/100

## [Phases 13-15] — 2026-08-07 (ZCode)
- Wyckoff Gate + LiquidityMap + Behavior Context Gate

## [Cognitive Continuum] — 2026-08-06 (Hermes)
- 11 phases : 78 652 comportements, COHERENT, 0 orphelin

## [Sprints 1-23] — 2026-08-05 (Hermes/ZCode)
- Pipeline complet V10 : 1310 tests, crons, Telegram, RL, dashboard

## [Audit ZCode] — 2026-08-05
- Bug Safe Haven flip inversé réparé
- Doublon v10_strategy_layers réconcilié
