# exchange.md — Bus de coordination V9
_Dernière mise à jour : 2026-07-07 22h30 CEST_

## Session courante
- session_id   : 20260707_sprint_son_mode_a
- source_agent : Hermes
- status       : TERMINÉ

## Dernière tâche complétée
- task         : SPRINT SØN MODE A (β complet) + checkpoint + resync docs
- target_agent : Søn (CEO)
- outputs      : [docs/STATE.md, docs/ARCHITECTURE.md, docs/DOCTRINE.md, docs/audit/AUDIT_V8_V9_YAML_GAP_20260707.md, workspace/perplexity/BOARD.md, ACTIVE_TASKS.md, exchange.md, JOURNAL.md, DECISIONS_LOG.md]
- status       : TERMINÉ — 6 commits sprint Søn livrés + 1 commit clôture checkpoint
- next_action  : MODE A — VEILLE ; attente action Søn (installer SDI sur VPS, lancer capture_server) → premier rapport télémétrie dans 24h

## File d'attente (post-sprint Søn)
- [x] **Sprint Søn Mode A** — Hermes (6 commits : REGISTRY, telemetry, CLI precision, VPS preflight, doc resync, audit+R30)
- [x] **Chantier Règle 30** — Hermes (`fa79787`, doctrine WIN/LOSS progressif)
- [x] **Audit 11 YAML V8/V9 gap** — Hermes (livré par la négative, 0 migration par défaut)
- [ ] **Action Søn VPS** — Søn (installer SDI, lancer daemon)
- [ ] **Premier rapport télémétrie** — attendu 24h après démarrage VPS
- [ ] **Premier paper trade** — attend prochain driver macro US (NFP vendredi 7 août 2026)
- [ ] **WIN/LOSS ≥ 20** — déclenche Règle 30 feedback loop partielle
- [ ] **WIN/LOSS ≥ 50** — déclenche Phase 13 complète
- [ ] **Phase 11 (MT5)** — gelée par décision Søn 2026-07-07 14:58
- [ ] **Tests consolidation in-memory** — Phase 13 (refactor arbiter.py nécessaire)

## Handoffs récents (2026-07-07)
- `8697d84` → `15e632c` — fix signal currency gap (live GBPUSD M15)
- `4fde966` → `2b9bbf9` — telegram notifier décision actée
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