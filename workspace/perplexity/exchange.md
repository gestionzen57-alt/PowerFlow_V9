# exchange.md — Bus de coordination V9
_Dernière mise à jour : 2026-07-07 10h08 CEST_

## Session courante
- session_id   : 20260707_phase10_open
- source_agent : Hermes
- status       : EN_COURS

## Dernière tâche complétée
- task         : Chantier Phase 10 — arbiter + risk_manager + paper_trades
- target_agent : Zcode (handoff post-implementation)
- outputs      : [commit `134205e`, `71007d7`, `83b6098`]
- status       : TERMINÉ — 49 tests verts ajoutés (14+18+17)
- next_action  : push origin + validate-coherence.py live check

## File d'attente
- [x] **Push origin feat/v9-foundation-clean** — Hermes (`f6a5aa5..9e3c351`, 10 commits)
- [x] **Chantier A — arbiter.py** — Hermes (`134205e`, 14 tests)
- [x] **Chantier B — risk_manager.py** — Hermes (`71007d7`, 18 tests)
- [x] **Chantier C — paper_trades + logger** — Hermes (`83b6098`, 17 tests)
- [x] **Chantier D — memory.md + exchange.md** — Hermes (ce brief)
- [ ] Cron telegram notifier persistant — Zcode (session dédiée)
- [ ] WIN/LOSS ≥ 20 (règle 25 doctrine) — collecte via `scripts/v9_resolve_decision.py`
- [ ] Phase 11 (multi-paires) — gelée jusqu'à WIN/LOSS ≥ 50

## Handoffs récents (2026-07-07)
- `8697d84` → `15e632c` — fix signal currency gap (live GBPUSD M15)
- `4fde966` → `2b9bbf9` — telegram notifier décision actée
- `b6b722e` → `a303057` — is_win/résolution → validate-coherence
- `5fc39c5` → `52ee778` — GAP-001 → checkpoint Phase 9→10
- `134205e` → `71007d7` → `83b6098` — Phase 10 (arbiter + risk + paper)

## Protocole de mise à jour
Hermes met à jour `exchange.md` :
- à chaque tâche complétée (`status → TERMINÉ`)
- à chaque nouvelle tâche démarrée (`status → EN_COURS`)
- à chaque handoff vers Zcode (`target_agent → Zcode`)
Zcode lit `exchange.md` en début de mission pour contexte.

## Lecture rapide (≤ 2 minutes)
1. **HEAD** : `9e3c351` (avant push) → après push des 4 derniers commits Phase 10 :
   `134205e` (arbiter) → `71007d7` (risk) → `83b6098` (paper)
2. **Tests** : 426 → **475 verts** (cible atteinte : +49)
3. **Pipeline live** : 7 signaux GBPUSD baissiers 2026-07-07, 2 messages
   Telegram 10:07:49 CEST, GAP-001 archivé
4. **Phase 10 ouverte** : arbiter (consolidation) → risk_manager (filtre) →
   PaperTradeLogger (saisie) — workflow complet implémenté et testé

## Référence pivot
- `workspace/perplexity/memory/memory.md` — mémoire persistante
- `workspace/perplexity/GAPS_RESIDUELS.md` — gaps résiduels archivés
- `workspace/perplexity/BOARD.md` — état opérationnel courant
- `docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md` — transition
- `workspace/perplexity/DECISIONS_LOG.md` — journal décisions datées