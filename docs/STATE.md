# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-07 20h55 CEST — **Phase 9.7 + 9.8 + 9.9 + 9.10-RULE29 livrées**. Pipeline Phase 9
stable live + arbiter + risk_manager + paper_trade_logger + orchestrateur + heartbeat
VPS-READY + **Règle 29 (Doctrine §3.1+§3bis+§6+§8 import V8) + zone_type persistence +
naissance_isolee window + HITL renforcé + pondération arbiter zone-type×session**.
**637 tests verts, 0 échec**, 3 xfailed (consolidate fragiles, chantier Phase 13),
1 xpassed. Détail bilan : `docs/checkpoints/CHECKPOINT_20260707_RULE29.md` + 14 commits
livrés cette session. Doctrine **29 règles immuables** (règle 29 ajoutée). Mode A —
VEILLE actif. Pipeline GBPUSD M5/M15/H1/H4/D1 vivant (port 31685, 50K+ snapshots/24h).

Commits structurants session règle 29 (2026-07-07 17h45 → 20h55) :
- `db979da` resync test count 596
- `72f1361` doctrine règle 29 (import V8 §3.1+§3bis+§6+§8)
- `3170f76` rule 29 zone_type lecture + naissance_isolee window (DOCTRINE §29)
- `bb5f190` replay_rule29 script — lecture zone_type sur behaviors passés
- `57d02ff` DECISIONS_LOG entrée replay_rule29 livraison
- `a9c15f2` JOURNAL entrée 19h00 — bilan règle 29
- `47fbfa7` rule 29 (a) — zone_type persistence
- `8d12dda` rule 29 (b) — HITL renforcé naissance_isolee
- `9174017` DECISIONS_LOG bilan (a)+(b)+(c) annulé
- `9af7781` rule 29 (c) — arbiter pondération (retry après relecture)
- `d9478ae` DECISIONS_LOG retry (c) réussi
- `bbfa3b7` test rule 29 dédiés (26 tests = 23 pass + 3 xfail)
- `8a67583` test window_gate naissance_isolee (6/6 verts)
- (à venir) early return fix arbiter + checkpoint RULE29

Bilan global session 2026-07-07 : **30+ commits**, Phase 9 finalisée (dette = 0
audit 10/10 F résolu), Phase 9.7/9.8/9.9 livrées, **Règle 29 importée**.

Commits structurants 2026-07-07 (matin) : `cd9b629` (mem0 archive), `4aa4fd3`
(heartbeat + Phase 9.8), `1996fa2`/`55d0070` (FABLE 1+2 inspiration), `4ac3863`
(C-1/C-2/C-3 consolidation), `0d438bf` (audit dette), `54930b3` (C-5b tests v9_ops),
`3604b8b` (C-5a YAML status), `b02b43a` (F-3 tests calibration+replay),
`371c696` (doctrine règle 28), `8028898` (README resync).

## Phase actuelle
**Phase 9.7 + 9.8 livrées 2026-07-07. Attente premier paper trade (London/NY open).
Phase 10 (fédération d'agents) planifiée — gelée par doctrine.**

Phase 9.7 = paper-trade simulator (Arbiter + RiskManager + PaperTradeLogger +
orchestrateur `v9_paper_trade_run.py`). Sous-phase de Phase 10 (pré-requis
simulation avant paper-trading), **distincte de la Phase 10 doctrine**
(fédération d'agents — voir `docs/ROADMAP.md`). Tous les modules sont livrés,
testés et fonctionnent en dry-run. Le filtre bloque correctement les
paper-trades sur marché range M5 (fenêtres non exploitables) — comportement
attendu.

Conditions pour le premier paper trade :
- ≥ 2 principes ACTIVE déclenchés simultanément
- confiance arbitrée ≥ 80 (post-plafond)
- window_status = exploitable
- news_phase ≠ NEWS_SHOCK

Phase 11 (Layer MT5 ticks) est planifiée mais **conditionnelle** au premier
paper trade loggé + ≥ 1 session London/NY observée avec window exploitable
M15/H1. Voir [`docs/checkpoints/CHECKPOINT_20260707_PHASE10.md`](checkpoints/CHECKPOINT_20260707_PHASE10.md).

## Statut opérationnel actuel

```
Forces → Scènes → Comportements → Fenêtres → Exploitabilité
       → Régime → Principes → Signal → Décision
       → [Phase 9.7] Arbiter → RiskManager → PaperTradeLogger
       → [Phase 9.8] Heartbeat (port 31685 + DB freshness + Telegram)

✅ Bout-en-bout fonctionnel
✅ 3 signaux haussiers GBPUSD conf 80-100 produits en live
✅ 596 tests verts (règle 7)
✅ 10/10 principes ACTIVE débloqués
✅ 31 champs contexte propagés (26 précédents + 5 news)
✅ Contexte news actif : news_phase PRE_NEWS/NEWS_SHOCK/POST_NEWS/NEUTRE
✅ Arbiter + RiskManager + PaperTradeLogger opérationnels
✅ Orchestrateur v9_paper_trade_run.py testé live
✅ v9_scoring.py prêt (en attente WIN/LOSS)
```

---

## Session NewsContext (2026-07-06 — session 2)

Commits [`05f8232`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/05f8232) + [`f278a1e`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/f278a1e6c9e224acef6277576a97db225b99e0ed) | **354 tests verts** (+7).

### Philosophie inscrite dans le code
```
# Le système ne trade pas les news. Il lit les flux de liquidité
# qui les précèdent et la réorganisation des coalitions qui suit.
# La news est un repère temporel. Les forces sont la réalité.
# — Perplexity, architecte externe V9, 2026-07-06
```

### Module créé : core/v9/news_context.py
- Module pur : aucune I/O DB, aucun import orchestrateur
- Interface : `NewsContext().assess(utc_dt)` → dict 5 champs
- Calendrier statique : `data/economic_calendar.json` (7 règles : NFP, ISM_PMI, CPI_US, FOMC_RATE, FOMC_MINUTES, GDP_US, RETAIL_SALES_US)
- Prio multi-news : distance min puis importance HIGH > MEDIUM > LOW
- Tolérance ±3 min sur heure typique

### 5 champs PROPAGÉS (injectés EN DERNIER dans _load_shared_context)
```
news_type          : str | None    # "NFP" / "ISM_PMI" / "CPI_US" / "FOMC_RATE" / None
news_phase         : str           # "PRE_NEWS" / "NEWS_SHOCK" / "POST_NEWS" / "NEUTRE"
news_distance_min  : int | None    # >0=futur, <0=passée, None si NEUTRE
news_importance    : str           # "HIGH" / "MEDIUM" / "LOW" / "NEUTRE"
news_session_clean : bool          # True = aucune news HIGH dans 90 prochaines min
```

### Placement doctrine respecté
Injection après TOUS les `context.update()` existants —
leçon bug ANTAGONIST_NODE (ne jamais écraser un bloc `update()` antérieur).

### Tests : tests/test_news_context.py (7 tests)
- test_news_context_pre_news_45min_avant
- test_news_context_shock_5min_apres
- test_news_context_post_news_30min_apres
- test_news_context_neutre_hors_fenetre
- test_news_context_clean_session_sans_news_proche
- test_news_context_fallback_calendar_vide
- test_news_context_champs_propages_dans_shared_context

---

## Session Pipeline bout-en-bout gardien + Idempotence decisions (2026-07-06 — session 3)

Commits [`85b40fe`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/85b40fe) + [`3d42b6c`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/3d42b6c) | **359 tests verts** (+4 vs session 2).

2 chantiers conjoints pour fermer les irritants structurels apparus session 2 :

### Chantier A — `tests/test_pipeline_end_to_end.py`
Test d'intégration bout-en-bout qui aurait détecté les 5 bugs silencieux du 2026-07-06 (fallbacks cross-TF, REGIMES_INADEQUATS, window=absente, principes quote perdus, `_load_signal ORDER BY`).

Trajet : `forces_snapshots` → `SceneBuilder.build_scene()` (réel) → `behaviors`/`windows`/`exploitability` injectés (heuristique single-snapshot instable) → `zone_diagnostics`/`regime_snapshots`/`principle_evaluations` injectés (multi-snapshot) → `SignalGenerator.generate()` (réel) → `DecisionLogger.log()` (réel) → `decisions`.

Assertions :
- `signal.direction IS NOT NULL AND != 'neutre'`
- `decision.direction IS NOT NULL AND confiance > 0`
- `contexte_complet` peuplé (scene+behavior+window+exploitability+principles)
- `decision.signal_id == signal.signal_id`

Reproductibilité : DB tmp, timestamps figés 2026-07-05T17:00Z, aucun `datetime.now()` non mocké. 0 dépendance à `data/v9_forces.db`.

### Chantier B — Idempotence decisions par snapshot_id
Bug : `decision_id = timestamp + uuid` changeait à chaque `.log()` → `INSERT OR REPLACE` créait une nouvelle rangée à chaque rejeu (3697 → 3960 sur 3 snapshots rejoués session 2).

Fix 2 volets dans `core/v9/decision_logger.py` :
1. `decision_id = uuid5(snapshot_id).hex[:12]` — déterministe par snapshot_id.
2. `_write_to_db()` : pré-check `_action_quality()` (preparer_entree=3 > surveiller=2 > observer=1 > aucune_action=0). Skip si ancien ≥ nouveau.

3 tests ajoutés (`test_decision_idempotent_same_snapshot_no_duplicate`, `test_decision_replaces_nondirectional_with_directional`, `test_decision_keeps_best_on_multiple_replay`).

Validation live : `dec_df961c3f104b` stable sur 3 appels `.log(v9-GBPUSD-M5-1783354200-016028)`. 5 décisions directionnelles sur la DB live (3 créées session 2 + 2 nouvelles).

### Périmètre strict respecté
- ✅ Modif `core/v9/decision_logger.py` + ajout `tests/test_pipeline_end_to_end.py` + 3 tests.
- ❌ Aucun contact avec YAML principes, `config.py`, ou `orchestrator.py` structure globale.
- ✅ Décision `DECISIONS_LOG.md` 2026-07-06 — Pipeline bout-en-bout gardien + Idempotence decisions.

---

## Session Déblocage pipeline signaux (2026-07-06)

Commit [`c7bc76b`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/c7bc76b36e8b5e4ca2a0bacbc3b836484f9749d3) | **347 tests verts**.
3 goulets d'étranglement corrigés :
1. `REGIMES_INADEQUATS` contenait NEUTRE — rejeté
2. `_determine_status` toujours `non_exploitable` sur `window=absente` — fixé
3. Principes perdus si `raison_absence != None` + re-évaluation in-memory — fixé

Impact : 0 → 3 signaux haussiers GBPUSD conf 80-100.

---

## Session ANTAGONIST_NODE (2026-07-06)

Commit [`7466f01`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/7466f0186e9bcd8a78a32ee8e18d3fbc52bc1da7) | **347 tests verts** (+4).
Bug fallback cross-TF écrasant `h1_state/h1_dir/m5_state/m5_dir` par None après `context.update()`.
10/10 principes ACTIVE techniquement débloqués.

---

## Session Calibration Live + Tuning YAML (2026-07-06)

**343 tests verts**. 3 commits : `046b285` / `35939aa` / `ecc056b`.
2245 snapshots / 1708 scènes / 0 signaux (pré-déblocage pipeline).
8 YAML enrichis avec 13 nouveaux champs contexte. `config.py` inchangé.
`DOCTRINE.md` 19 → 27 règles. Commit [`2a970cf`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/2a970cf98551c62f2506e20e6699b53d27432763).

---

## Session Coalition Intelligence (2026-07-06)

**339 tests verts**. 13 champs contexte + CONTEXT_CONTRACT.md + gardien auto.
Commits : cd50cd7 / 4ebf86a / 24c0653 / 4d6cf53 / 44c8ae4 / 6648d27

---

## Correctif Phase 9.5 (2026-07-06) — observabilité DST US
Correctif `market_status_warning()`. `core/v9/*` inchangé. 269 tests verts.

## Phase 9 TERMINÉE (2026-07-05)
Chaîne cognitive complète. 27 principes YAML (10 ACTIVE / 17 SHADOW).
Voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE9.md`.

## PHASES 1→8 TERMINÉES
Voir `docs/checkpoints/`.

---

## Décisions actées
- V9 from scratch. GitHub = source de vérité. V8 = migration curée.
- CONTEXT_CONTRACT.md + test_context_propagation.py = gardien de propagation.
- DOCTRINE.md 27 règles (calibration-first, sessions, YAML, fallbacks).
- COALITION_THRESHOLD → reporté à n>5000 scènes + WIN/LOSS.
- news_context.py : la news = repère temporel, jamais déclencheur.
- Tout fallback dans `_load_shared_context` TOUJOURS placé AVANT ou après
  son `context.update()` selon sa logique — jamais l'inverser.

## Objectif immédiat
**Observer les premiers signaux post-ISM PMI avec news_context actif.**
Lancer après 16h Paris :
```
python scripts/v9_dashboard.py --watch decisions --once
python scripts/v9_calibration.py --principes
```
Suivre : ANTAGONIST_NODE se déclenche-t-il sur NEWS_SHOCK ISM PMI ?
Suivre : POWER_ANGLE_BREAK_TO_PRICE_IMPACT sur POST_NEWS ?

## Chantiers en file
1. **Calibration --principes** — relancer à ~500 scènes post-tuning YAML news-aware
2. **COALITION_THRESHOLD** — réévaluer à n>5000 scènes + WIN/LOSS (actuel 5.0, suggéré calibration 5.33, 3.96 antérieur)
3. **Promotion SHADOW→ACTIVE** — décision sur base hit_rate live (règle 25)
4. AGENT.md racine V9 — ✅ FAIT
5. **Inventaire migration V8→V9** — audit selon MIGRATION_POLICY_V9.md ✅ FAIT

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code / Hermes / MiniMax : implémentation selon périmètre assigné

## Règle d'or
Aucune implémentation structurante sans ancrage explicite dans la doctrine V9.
Toute métrique ajoutée tracée dans CONTEXT_CONTRACT.md.
Tout fallback dans `_load_shared_context` — ordre respecté par rapport aux `context.update()`.
