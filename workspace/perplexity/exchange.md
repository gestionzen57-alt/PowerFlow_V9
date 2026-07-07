# exchange.md — Bus de coordination V9
_Dernière mise à jour : 2026-07-07 10h08 CEST_

## Session courante
- session_id   : 20260707_phase10_cloture
- source_agent : Hermes
- status       : EN_COURS

## Dernière tâche complétée
- task         : Clôture Phase 10 + checkpoint + scoring
- target_agent : Zcode (handoff post-implementation)
- outputs      : [commit `134205e`, `71007d7`, `83b6098`, `aa5c365`, `5f70b3d`, `b5cfa99`]
- status       : TERMINÉ — 49 + 12 tests verts ajoutés (Phase 10 + scoring)
- next_action  : push origin + wait London/NY for first paper trade

## File d'attente
- [x] **Push origin feat/v9-foundation-clean** — Hermes (3 pushs : étape 0 → `9e3c351`, chantiers A-D → `21f6c82`, paper_trade_run → `aa5c365`)
- [x] **Chantier A — arbiter.py** — Hermes (`134205e`, 14 tests)
- [x] **Chantier B — risk_manager.py** — Hermes (`71007d7`, 18 tests)
- [x] **Chantier C — paper_trades + logger** — Hermes (`83b6098`, 17 tests)
- [x] **Chantier D — memory.md + exchange.md** — Hermes (`21f6c82`)
- [x] **Orchestrateur paper_trade_run.py** — Hermes (`aa5c365`, 14 tests)
- [x] **Checkpoint Phase 10** — Hermes (`5f70b3d`)
- [x] **v9_scoring.py — hit rate par principe** — Hermes (`b5cfa99`, 12 tests)
- [ ] Cron telegram notifier persistant — Zcode (session dédiée)
- [ ] **Premier paper trade** — attend session London/NY sur M15/H1
- [ ] **v9_scoring alimentation** — attend WIN/LOSS via `v9_resolve_decision.py`
- [ ] Phase 11 (Layer MT5 ticks) — conditionnelle au 1er paper trade
- [ ] WIN/LOSS ≥ 20 (règle 25 doctrine) — collecte via `scripts/v9_resolve_decision.py`

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
2. **Tests** : 426 → 475 → 501 → 588 → **596 verts** (F-11/F-13/F-15/F-17/F-19 livrés 2026-07-07 fin d'après-midi)
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