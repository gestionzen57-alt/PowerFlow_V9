# exchange.md — Bus de coordination V9
_Dernière mise à jour : 2026-07-07 10h08 CEST_

## Session courante
- session_id   : 20260707_resync_docs_actives_rule29
- source_agent : Hermes
- status       : TERMINÉ

## Dernière tâche complétée
- task         : RESYNC DOCS ACTIVES (bilan complet + mise à jour de tout)
- target_agent : Søn (CEO)
- outputs      : [docs/STATE.md, workspace/perplexity/BOARD.md, exchange.md, ACTIVE_TASKS.md, memory.md, JOURNAL.md, DECISIONS_LOG.md, docs/checkpoints/CHECKPOINT_20260707_RULE29.md (nouveau)]
- status       : TERMINÉ — Règle 29 + 14 commits livraison + checkpoint dédié
- next_action  : MODE A — VEILLE ; observation live jusqu'au prochain NFP (vendredi 7 août 2026)

## File d'attente (post-RULE29)
- [x] **Chantier doctrine règle 29** — Hermes (`72f1361`, 72 lignes DOCTRINE.md)
- [x] **Chantier code règle 29** — Hermes (`3170f76`, _detect_zone_type + naissance_isolee whitelist + promotion conditionnelle)
- [x] **Chantier tests dédiés règle 29** — Hermes (`bbfa3b7` 26 tests, `8a67583` 6 tests window_gate)
- [x] **Rapatriement doctrine V8 lecture multi-TF** — Hermes (`memory/DOCTRINE_LECTURE_MARCHE.md`, 792 lignes)
- [x] **Chantier (a) zone_type persistence** — Hermes (`47fbfa7`)
- [x] **Chantier (b) HITL renforcé naissance_isolee** — Hermes (`8d12dda`)
- [x] **Chantier (c) arbiter pondération (retry après relecture 147 LOC)** — Hermes (`9af7781`)
- [ ] **Test consolidation in-memory** — Phase 13 (refactor arbiter.py nécessaire)
- [ ] **Premier paper trade** — attend prochain driver macro US (NFP vendredi 7 août 2026)
- [ ] **v9_scoring alimentation** — attend WIN/LOSS via `v9_resolve_decision.py`
- [ ] **Phase 11 (MT5)** — gelée par décision Søn 2026-07-07 14:58
- [ ] **WIN/LOSS ≥ 50 (règle 25 indicative)** — collecte via scripts/v9_resolve_decision.py

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