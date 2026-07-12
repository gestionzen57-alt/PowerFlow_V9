# exchange.md — Bus de coordination V9
_Dernière mise à jour : 2026-07-13 ~01:30 UTC_

## Session courante
- session_id   : 20260713_autopilot_ceo_p1_p6
- source_agent : Hermes (CEO orchestreur)
- status       : PARTIELLEMENT LIVRÉ — 9 commits, 4 chantiers P2/P3/P4/P5 reportés

## Dernière tâche complétée
- task         : Série Autopilot CEO 2026-07-13 (P1+P6 + Fix HITL + consolidation docs)
- target_agent : Søn (CEO) — push R28 (Hermes opérateur git unique, jamais auto-push)
- outputs      : 9 commits sur `feat/v9-foundation-clean` —
  `9592ce3` P6 vol_regime module, `331382f` P1 DYNAMIC signal rec,
  `6cf75d4` autopilot_status doc, `ade60e1` fix HITL test,
  `9aa7d08` consolidation post-Autopilot (STATE+BOARD+ACTIVE_TASKS+JOURNAL),
  `0b29280` CACHE_BOARD resync, `96232dd` ROADMAP doctrine 28→30,
  `ee084f1` DOC_REGISTRY enrichi, `3b9f7fe` LEXIQUE+LEXICON.
- status       : 1114 verts + 2 skipped + 0 fail. 0 régression Autopilot.
- next_action  : Suite CEO — P3 (Adaptive Thresholds 8-12h, prioritaire HAUTE)
  > P4 (Event Calendar 6-8h) > P5 (Long-term memory 4-6h) >
  P2 (Shadow mode parallèle 16-24h, J+2). Décision Brief O4 « biais
  New York/After » en attente (bloque activation effective de P1).

## File d'attente (post-série Autopilot)
- [x] **P6 vol_regime** — livré 13/07 ~00:55 (commit `9592ce3`)
- [x] **P1 DYNAMIC signal** — livré 13/07 ~01:05 (commit `331382f`, INEFFET j/Q O4)
- [x] **Fix HITL test HITL_HIGH=80** — livré 13/07 ~01:15 (commit `ade60e1`)
- [x] **Consolidation docs** — livré 13/07 ~01:30 (5 commits docs)
- [ ] **Décision Brief O4** — Søn (politique New York/After : exclusion / re-calibration scale)
- [ ] **P3 Adaptive Thresholds** — Hermes (8-12h, prioritaire)
- [ ] **P4 Event Calendar dynamique** — Hermes (6-8h)
- [ ] **P5 Long-term memory** — Hermes (4-6h, behavior_analyzer.load_history(limit=500))
- [ ] **Fixer 15 fails pré-existants test_telegram_notifier.py** — chantier Telegram
- [ ] **Push des 9 commits Autopilot** — Søn (R28 = Hermes opérateur git unique)
- [ ] **Activation effective P1** (post-décision O4) — patch `v9_resolve_decision_auto.py`
- [ ] **Action Søn VPS** — Søn (installer SDI, lancer daemon) — pré-existant
- [ ] **Premier paper trade** — post-O4 décision

## Handoffs récents (2026-07-13)
- `9592ce3` → `331382f` → `6cf75d4` → `ade60e1` → `9aa7d08` →
  `0b29280` → `96232dd` → `ee084f1` → `3b9f7fe` — Série Autopilot CEO
  complète (4 code + 5 docs). R28 push en attente Søn.
- `b6b722e` → `a303057` — is_win/résolution → validate-coherence
- `5fc39c5` → `52ee778` — GAP-001 → checkpoint Phase 9→10
- `134205e` → `71007d7` → `83b6098` — Phase 10 (arbiter + risk + paper)
- `db979da` → `...` → `8a67583` — Règle 29 (14 commits)
- `22fa492` → `...` → `fa79787` — Sprint Søn Mode A (6 commits)
- `80dc3c5` → ... — Resync sprint (commit resync ARCHITECTURE + DECISIONS_LOG)
- `fa79787` — Règle 30 + audit YAML gap + DEPRECATED BONUS

## Protocole de mise à jour
Hermes met à jour `exchange.md` :
- à chaque tâche complétée (`status → TERMINÉ`)
- à chaque nouvelle tâche démarrée (`status → EN_COURS`)
- à chaque handoff vers Zcode (`target_agent → Zcode`)
Zcode lit `exchange.md` en début de mission pour contexte.

## Lecture rapide (≤ 2 minutes)
1. **HEAD** : `fa79787` — sprint Søn Mode A + Règle 30 + audit V8/V9 YAML
   (pushé, parité origin, working tree clean)
2. **Tests** : **663 verts** (sprint Søn +26 vs baseline 637), 3 xfailed, 1 xpassed
3. **Pipeline live** : 72K+ snapshots M5 GBPUSD, 419 décisions directionnelles jour,
   PID 42608 capture_server vivant 9h43+ uptime
4. **Doctrine** : **30 règles immuables** (ajout Règle 30 apprentissage conditionnel WIN/LOSS)
5. **Phase 10 ouverte** : arbiter (consolidation) → risk_manager (filtre) →
   PaperTradeLogger (saisie) — workflow complet implémenté et testé
6. **Cible VPS** : 4 cores 2.6 GHz / 12 GB RAM, SDI à installer par Søn

## Référence pivot
- `workspace/perplexity/memory/memory.md` — mémoire persistante
- `workspace/perplexity/GAPS_RESIDUELS.md` — gaps résiduels archivés
- `workspace/perplexity/BOARD.md` — état opérationnel courant
- `docs/checkpoints/CHECKPOINT_20260707_RULE29.md` — transition
- `workspace/perplexity/DECISIONS_LOG.md` — journal décisions datées
- `docs/audit/AUDIT_V8_V9_YAML_GAP_20260707.md` — audit 11 YAML gap sprint Søn