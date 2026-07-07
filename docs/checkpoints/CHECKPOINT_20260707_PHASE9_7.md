# CHECKPOINT — Phase 9.7 livrée (Paper-Trade Simulator, sous-phase de Phase 10)
_2026-07-07 10h54 CEST — re-badgé 2026-07-07 | Hermes (implémentation) + Perplexity (doctrine)_

---

## Contexte

Phase 10 (Paper-Trade simulator) autorisée le 2026-07-07 10h08 CEST
(voir [`docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md`](CHECKPOINT_20260707_PHASE9_TO_PHASE10.md))
en mode dégradé — règle 25 (WIN/LOSS ≥ 20) différée, période de grâce
accordée par l'opérateur pour faire tourner le simulateur en parallèle
de la collecte WIN/LOSS via `scripts/v9_resolve_decision.py`.

Périmètre Phase 10 (défini par l'opérateur, voir checkpoint Phase 9→10) :
- `core/v9/arbiter.py` — consolidation des décisions par snapshot
- `core/v9/risk_manager.py` — filtre 5 règles bloquantes
- Table `paper_trades` + `core/v9/paper_trade_logger.py` — saisie simulation
- `scripts/v9_paper_trade_run.py` — orchestrateur bout-en-bout

---

## Livrables Phase 10

| Commit | Livrable |
|--------|----------|
| `134205e` | `core/v9/arbiter.py` — consolidation décisions (lecture seule) |
| `71007d7` | `core/v9/risk_manager.py` — 5 règles bloquantes (go/no-go) |
| `83b6098` | `core/v9/paper_trade_logger.py` + table `paper_trades` + `paper_trades_db.py` |
| `aa5c365` | `scripts/v9_paper_trade_run.py` — orchestrateur Arbiter → Risk → Paper |
| `21f6c82` | `workspace/perplexity/memory/memory.md` + `exchange.md` |

(Chantiers antérieurs utiles : `a303057` validate-coherence.py, `b6b722e`
is_win/résolution, `52ee778` checkpoint Phase 9→10, `5fc39c5` GAP-001.)

## Tests : 489 verts, 0 régression

- **Arbiter** : 14 tests (consolidation, plafond < 2 principes, lecture seule)
- **RiskManager** : 18 tests (5 règles bloquantes, ordre évaluation, constantes)
- **PaperTradeLogger** : 17 tests (log_open/close, idempotence, WIN/LOSS)
- **PaperTradeRun** : 14 tests (dry-run, idempotence snapshot+direction, mixed outcomes)
- **Suite globale** : 489 verts (était 359 au checkpoint Phase 9 2026-07-05, 426 au checkpoint Phase 9→10 ce matin)

---

## Workflow opérationnel

```
scripts/v9_paper_trade_run.py
   ↓
Arbiter.consolidate(snapshot_id)         ← lit table decisions (lecture seule)
   ↓                                       filtre source_type='live' direction != 'neutre'
fetch_context_for_snapshot()              ← window_status + news_phase
   ↓                                       depuis decisions.contexte_complet_json
RiskManager.evaluate()                    ← 5 règles bloquantes
   ↓ si go=True
is_trade_already_open()                   ← idempotence (snapshot_id + direction)
   ↓ si False
PaperTradeLogger.log_open()               ← INSERT paper_trades
```

## Test live réalisé — 2026-07-07 10h50 CEST

```
$ python scripts/v9_paper_trade_run.py --dry-run

⏭ Ignoré — confiance insuffisante (74)  ×7
⏭ Ignoré — fenêtre non exploitable      ×3
------------------------------------------------------------
10 snapshots analysés — 0 trades ouverts (10 ignorés)
```

**Diagnostic** :
- 7 décisions ont 1 seul principe actif → Arbiter plafonne confiance à 74 → RiskManager bloque (règle 2 : confiance < 80)
- 3 décisions ont ≥ 2 principes mais `window.statut='absente'` → RiskManager bloque (règle 4 : fenêtre non exploitable)
- Marché GBPUSD M5 actuellement en **range** → peu de fenêtres exploitables et peu de principes multiples activés simultanément

**Filtre fonctionne correctement — aucun seuil modifié.** Le comportement "0 trade ouvert" est attendu en phase range M5.

---

## Comportement attendu avant premier paper trade

Conditions **toutes réunies** :
- ≥ 2 principes ACTIVE déclenchés simultanément sur un même snapshot
- Confiance arbitrée ≥ 80 (post-plafond si nb_principes ≥ 2)
- `window_status` = `'exploitable'` (donc hors range M5)
- `news_phase` ≠ `'NEWS_SHOCK'`

Probabilité d'occurrence :
- Plus élevée sur **M15/H1** que M5 (volatilité suffisante pour casser le range)
- Plus élevée en **session Londres (07-10 UTC) ou New York (12-15 UTC)** (overlay de liquidité)

Estimation : 1er paper trade attendu dans les **24-72h** sous session Londres/NY sur M15.

---

## Gaps non bloquants (rappel)

- **GAP-001** : 7 décisions orphelines (signal_id introuvable, pré-fix `8697d84`) → [`docs/architecture/GAPS_RESIDUELS.md`](../architecture/GAPS_RESIDUELS.md) gap #8
- **Check 4 stale** : 3442 rangées `source_type='live'` datées >24h — historique J-1 normal (validate-coherence `a303057`)
- **WIN/LOSS = 0** : aucune décision résolue à ce jour — collecte via `scripts/v9_resolve_decision.py` (livré `b6b722e`)

---

## Prochaine phase autorisée

### Phase 11 — Layer MT5 (microstructure ticks)

**Condition de déblocage** :
- ✅ 1+ paper trade loggé (permet d'avoir au moins 1 WIN/LOSS pour calibrer)
- ✅ 1+ session London/NY observée avec window exploitable M15/H1

**Périmètre anticipé** (non démarré — voir `docs/ROADMAP.md`) :
- `core/v9/tick_reader.py` — lecture ticks MT5 (densité, déséquilibre bid/ask)
- `core/v9/microstructure.py` — couche 10 validant le signal à l'échelle tick
- Bridge MT4 (forces) ↔ MT5 (ticks) — règle 10 doctrine (MT4 dicte, MT5 confirme)

### Hors périmètre Phase 10 (rappels doctrine)

- ❌ **Phase 12** — exécution d'ordre réelle (interdit fondateur, HITL requise)
- ❌ **Phase 13** — agentique globale / federation (gelée par règle 22)
- ⚠️ **Phase 11** amorcée par `scripts/v9_scoring.py` (calcul hit rate par principe)
  en parallèle de la collecte WIN/LOSS — ne nécessite pas de paper trade pour
  tourner, mais produira des résultats plus significatifs dès qu'on aura ≥ 5 décisions résolues

---

## Signature

| Rôle | Nom | Date / Heure (CEST) | Décision |
|------|-----|---------------------|----------|
| Implémentation | Hermes | 2026-07-07 10h54 | ✅ Arbiter + RiskManager + PaperTradeLogger + orchestrateur livrés et testés |
| Doctrine / Coordination | Perplexity | 2026-07-07 | ✅ Cohérence documentaire vérifiée |
| Opérateur (CEO) | Søn | 2026-07-07 | ✅ **Phase 10 livrée** · ⏳ **Phase 11 planifiée (conditionnelle au 1er paper trade)** |

---

## Références

- `docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md` — transition Phase 9 → Phase 10
- `docs/architecture/GAPS_RESIDUELS.md` — gaps résiduels P1-P3
- `workspace/perplexity/memory/memory.md` — mémoire persistante projet
- `workspace/perplexity/exchange.md` — bus de coordination Hermes ↔ Zcode
- `workspace/perplexity/GAPS_RESIDUELS.md` — alias workspace du canonique
- `scripts/validate-coherence.py` (`a303057`) — gardien DB live
- `scripts/v9_resolve_decision.py` (`b6b722e`) — saisie WIN/LOSS manuelle
- `scripts/v9_telegram_notifier.py` (`4fde966`) — alertes live confiance > 65