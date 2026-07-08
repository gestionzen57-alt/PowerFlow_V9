# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-08 — **Phase 14c : script v9_principle_alert + cron hourly (CEO — angle mort #1 fermé)**.
- **Script `scripts/v9_principle_alert.py`** créé (330 LOC) + tests
  `tests/test_v9_principle_alert.py` (17/17 verts) + wrapper
  `~/.hermes/scripts/v9_principle_alert_hourly.sh` + cron `89454a73f3d4`
  (horaire `0 * * * *`, no-agent, deliver local).
- **5 règles d'alerte** alignées R30 : `BLOCKED_DATA` (resolver KO),
  `SUSPECT_PERFECT` (HR 100% ≥500 résolus = biais haussier), `REGRESSION`
  (HR <60% ≥100 résolus), `INSUFFICIENT_DATA` (promo fraîche <7j <50 trig),
  `RESOLVER_STALE` (ratio résolus/trig <5%, ≥50 trig).
- **Périmètre R8 respecté** : aucune modif `core/v9/config.py`,
  `orchestrator.py`, `principles/*.yaml` → backup MD5 non requis.
- **Tests** : **834 → 851 verts** (+17), 0 régression propre, 4 xfailed
  (pré-existants), 1 xpassed.
- **Découverte immédiate** : GRAMMAR_CONTEXTE déclenche `RESOLVER_STALE`
  (2898 triggers / 21 résolus = 0.7%). Confirme angle mort #3 vivant :
  cron `9c51c8bd1922` (WIN/LESS daemon) en erreur HTTP 402 OpenRouter
  depuis 14:05 UTC, à investiguer prochaine session.
- **Catalogue** : 25 fichiers YAML inchangé (11 ACTIVE + 14 SHADOW).
- **Détails** : DECISIONS_LOG §« Phase 14c ».

2026-07-08 — **Phase 9.10.1 — promotion GRAMMAR_CONTEXTE close + cron daemon + diagnostique Phase 14a** (CEO).
- **GRAMMAR_CONTEXTE PROMU SHADOW→ACTIVE** (Phase 13 close définitive,
  10 → 11 ACTIVE) : `core/v9/config.py` PRINCIPLE_ACTIVE_IDS ligne 210
  ajoute `"GRAMMAR_CONTEXTE"`, YAML `v9_status: SHADOW → ACTIVE`,
  `version: 2 → 3`, `promoted_at: '2026-07-08'`. Critères R25' tous
  remplis (conditions écrites, contexte propagé, décision CEO tracée,
  hit_rate 100% sur 1491 triggers). Backup MD5
  `docs/calibration/backups/2026-07-08_pre_promotion_gc/`.
- **Cron daemon WIN/LOSS** : `cronjob_id=9c51c8bd1922`,
  `*/5 * * * *`, dry-run par défaut avec apply conditionnel sur
  eligible > 0, workdir `D:\Projet\V9`. Filet de sécurité du hook
  orchestrator live.
- **Diagnostic GRAMMAR_PULLBACK** (Phase 14a) : bottleneck identifié
  sur `persistance_confirmee == True` (DORMANT non-propagé, défaut
  `False` toujours). 0/100 triggers sur M5. Refonte YAML
  recommandée Phase 14b (substituer par un champ propagé).
- **v9_phase13_readiness** : enrichi avec `--threshold-pips` (filtre
  hit_rate sur |pips| >= seuil) + `hit_rate_filtered_pct` (anti-bruit
  marché). 13/13 tests verts, verdict global cohérent
  (`PHASE_13_PARTIAL_NO_PROMOTABLE` post-promotion GC, attendu).
- **Tests** : **829 → 834 verts** (+5 : diagnose_shadow_no_trigger
  5/5, phase13 13/13 conservés), 4 xfailed, 1 xpassed, 0 régression.
- **Pipeline live** : UP, port 31685, capture_server PID 37432
  (post-promo rechargé). Hook orchestrator auto-resolve fonctionne
  (les nouvelles décisions seront résolues au fil de l'eau).
- **Détails** :
  `docs/calibration/PHASE_9_10_1_CALIBRATION_20260708.md` +
  DECISIONS_LOG §« PROMOTION SHADOW→ACTIVE : GRAMMAR_CONTEXTE ».

2026-07-08 — **Phase 9.10 WIN/LOSS resolver close** (CEO). **Data flow
WIN/LOSS câblé bout-en-bout** : résolveur prix-based
(`scripts/v9_resolve_decision_auto.py`, 420 LOC, 22 tests), daemon arrière-plan
(`scripts/v9_resolve_decision_auto_daemon.py`, 300 LOC, intervalle 5 min,
log `logs/v9_resolve_daemon.log`), hook non-bloquant dans
`core/v9/orchestrator.py` (batch 50, env var `V9_AUTO_RESOLVE_ENABLED=0` pour
désactiver). Index perf `idx_forces_symbol_timeframe_timestamp` créé sur
`forces_snapshots` (idempotent). **~8360 décisions résolues sur ~8370**
(99.7%), 3 skip lacune data 06-07 14h-22h. Architecture : option A
(résolution directe `decisions.is_win`, court-circuit `paper_trades` qui
n'a jamais été utilisé en prod, 0 ligne). Algorithme : MFE sur fenêtre
`[T+0, T+4h]` (horizon court_terme R29 §3bis), strict `>` pour exclure
l'entry, fallback M15 si TF natif lacunaire. Périmètre R8 respecté :
backup MD5 posé, `config.py`/`principles/*.yaml` intacts. Doctrines
préservées : R8 (étendu validé Søn 2026-07-07), R18 (zéro LLM), R25'
(promotion reste à décision Søn), R30 (resolver alimente hit_rate mais
ne le déclenche pas). Tests : **807 → 829 verts** (+22), 4 xfailed (3
anciens + 1 pré-existant `test_principle_engine` xfail-marked),
1 xpassed, 0 régression propre. Détails dans
`docs/calibration/PHASE9_10_RESOLVER_20260708.md` + DECISIONS_LOG
§« Phase 9.10 WIN/LOSS resolver close ».

2026-07-08 — **Phase 13 + diagnostic ANTAGONIST_NODE** (CEO).
**Phase 13 NON clôturable** (0 WIN/LOSS résolu bloque la promotion) ;
**ANTAGONIST_NODE = INERT_MARKET** (H1/M5 corrélés, pas un bug).
Livré : `scripts/diagnose_antagonist_node.py` (310 LOC, 8 tests) qui
départage BUG_CODE / BUG_YAML / INERT_MARKET — verdict INERT_MARKET.
`scripts/v9_phase13_readiness.py` (290 LOC, 13 tests) qui audite les
15 SHADOW : 12 INERT_NO_CONDITIONS, 2 BLOCKED_NO_TRIGGER
(GRAMMAR_BREAK/PULLBACK), 1 READY_STRUCTURAL (GRAMMAR_CONTEXTE,
655/61589 triggers, candidat #1 promotion). 0 READY_FULL. Verdict
global : **PHASE_13_BLOCKED_NO_WINLOSS** (0 win / 0 loss / 8365 open).
**Bloqueur structurel identifié** : `scripts/v9_resolve_decision.py`
existe mais n'est pas appelé automatiquement (pas de cron, pas de
hook). Tant que ce data flow n'est pas activé, AUCUNE promotion
SHADOW n'est possible. Tests : **786 → 807 verts** (+21). Détails
dans `docs/calibration/PHASE13_DIAGNOSTIC_20260708.md` + entrée
DECISIONS_LOG §« Phase 13 close ».

2026-07-08 — **Phase 9.9 DB hygiene close** (CEO). Maintenance DB exécutée
sur `data/v9_forces.db` : VACUUM 3.74 → 3.58 GB (−154 MB, −4.1%), index
`idx_pe_symbol_timeframe_timestamp` créé sur `principle_evaluations`
(symétrique de `decisions` qui l'avait déjà). Script outillé
`scripts/v9_db_hygiene.py` (340 LOC) avec logique de purge réelle
(SHADOW > 7j + decisions aucune_action > 7j), dry-run par défaut, garde-fou
`--apply` exige `--backup <dir>`. 13/13 tests pytest verts (786 total).
Pipeline live relancé (capture_server PID 35520, port 31685). Backup MD5
dans `docs/calibration/backups/2026-07-08_pre_db_hygiene/`. Détails dans
`workspace/perplexity/memory/DECISIONS_LOG.md` §« Phase 9.9 DB hygiene close ».

2026-07-08 — **Phase 9.8 Phase B livrée** : réalignement doctrinal CHARTE/DOCTRINE
(7 livrables B1-B7, 9 commits — voir `docs/audit/AUDIT_DOCTRINE_REPORT.md` pour l'audit
Phase A qui a motivé ce chantier). Résumé :
- **B1** — `docs/doctrine/CHARTE_COGNITIVE_V9.md` v0.2 : vocabulaire étendu à 19 termes
  (+exploitabilité, principe, signal, décision, arbiter, risk_manager, paper_trade,
  heartbeat), chaîne cognitive scindée en amont immuable (6 couches, Forces→Régime) et
  aval évolutive (4 couches groupées, Principes→Signal / Décision / Arbiter→RiskManager /
  PaperTrade→Heartbeat).
- **B2** — `docs/DOCTRINE.md` : R20 et R25 supprimées et remplacées par R20' (Lecture-first)
  et R25' (Vocabulaire descriptif) ; R27 reformulée (DORMANT justifié, plus de suppression
  automatique) ; R11 reformulée (architecture 9+1 node_rule/grammar). 26 autres règles
  intactes, 30 lignes préservées. 4 entrées `DECISIONS_LOG.md`.
- **B3** — Correctifs mécaniques F0 (checkpoint Telegram : "4 contradictions" → "3 + 5
  tensions"), F1 (GRAMMAR_REGIME.yaml reçoit ses 4 conditions réelles, n'est plus
  structurellement inerte malgré son statut ACTIVE — bug latent `_compute_confidence`
  découvert et corrigé au passage), F2 (docstring `principle_engine.py` : 20→18 principes
  grammar, suppression de la phrase datée auto-contradictoire).
- **B4** — GRAMMAR_BREAK, GRAMMAR_CONTEXTE, GRAMMAR_PULLBACK reçoivent leurs conditions
  réelles (déjà rédigées en note depuis 2026-07-06), restent SHADOW (aucune promotion sans
  décision Søn tracée, règle 25').
- **B5** — GRAMMAR_GRAVITE et GRAMMAR_INVERSION archivés (classe C, `core/v9/principles/
  _archive/`, `ARCHIVE_MANIFEST.md`) — aucune donnée source V9 confirmée. Catalogue actif
  27 → 25 principes (9 node_rule + 16 grammar, 15 SHADOW + 1 ACTIVE).
- **B6** — `docs/audit/AUDIT_R29_MIGRATION_V8.md` : audit A/B/C/D rétrospectif du
  rapatriement DOCTRINE_LECTURE_MARCHE.md V8 (792 lignes) en Règle 29 — classe B confirmée.
- **B7** — `docs/doctrine/ORCHESTRATION_POLICY_V9.md` réaligné sur le Mode A borné réel
  (mapping 7 rôles canoniques ↔ 7 agents, `decision_maker` justifié par la couche Décision
  CHARTE v0.2, `replay-confronter` explicitement reporté Phase 13, exemption Règle 19
  documentée à 3 conditions cumulatives).

**703 → 745 tests verts** (42 tests ajoutés : B1=6, B2=7, B3=6, B4=6+6+6=18 (BREAK/CONTEXTE/
PULLBACK), B5=5, aucun test dédié requis pour B6/B7 — doc pure), **0 régression**, doctrine
toujours 30 règles immuables (4 reformulées : R11, R20', R25', R27).

---

2026-07-08 — **Phase C doctrine realign livrée (worktree isolé), Phase D calibration livrée,
Phase E clôture/merge partiel** : `auto/feat/phase9.8-doctrine-realign` (base
`feat/v9-foundation-clean` @ `07e3eb7`), 7 commits (`800a9e9` R8 lift + `500909a`..`6c5daa8`
C1→C6) + Phase D (calibration 24h/7j, `docs/calibration/COMPARAISON_DOCTRINE_REPLAY.md` :
0 régression hit_rate confirmée sur 27/27 principes, replay 58201 décisions). **733 tests
verts / 3 xfailed / 1 xpassed dans le worktree (703 baseline + 30 nouveaux), 0 régression.**
Découverte d'audit clé : les 17 principes SHADOW→ACTIVE sont tous `kind=grammar` à
`conditions: []` (structurellement non-émetteurs) — ce patch est donc inerte sur les
signaux/décisions déjà produits, seule la visibilité calibration change. **Décision CEO
Phase E (merge partiel)** : la promotion cosmétique 10→27 ACTIVE (C1) est **rejetée** —
audit DB réel confirme 0 trigger historique sur les 17 GRAMMAR_* concernés (1M+ lignes
`principle_evaluations` évaluées pour rien), et la promotion contredit la recommandation
de `COMPARAISON_DOCTRINE_REPLAY.md` (garder les GRAMMAR_* en SHADOW). `PRINCIPLE_ACTIVE_IDS`
reste à 10 (état Phase B). Retenu du worktree : C2 (fallbacks zone_diagnostics), C5
(`--principes` étendu devise×TF×session), C6 (script replay pré/post) ; C3/C4 déjà conformes.
Voir `docs/calibration/AUDIT_DB_20260708.md`, `docs/calibration/COMPARAISON_DOCTRINE_REPLAY.md`
et `DECISIONS_LOG.md` pour le détail.

## Dernière mise à jour
2026-07-08 09:55 CEST — **Phase 9.8 doctrine realign CLOSE (commit `536fba7`)** :
Phase A audit (18 frictions CHARTE/DOCTRINE), Phase B refonte (CHARTE v0.2, 4
règles DOCTRINE reformulées, 4 YAML refactorés, 2 archivés, AUDIT_R29, ORCHESTRATION_POLICY
réaligné), Phase C/D worktree partiel (fallbacks, --principes étendu, replay pré/post),
MERGE PARTIEL retenant 10 ACTIVE / 15 SHADOW après audit DB live confirmant 0 trigger
historique sur les 17 GRAMMAR_*. **773 tests verts (703 → 773, +70), 0 régression**,
doctrine **30 règles** (4 reformulées : R11, R20', R25', R27), pipeline GBPUSD M5/M15
vivante (port 31685), worktree `V9_wt_doctrine_realign` réservé Phase 13.

Phase 9.7 + 9.8 + 9.9 + 9.10-RULE29 livrées 2026-07-07. Pipeline Phase 9
stable live + arbiter + risk_manager + paper_trade_logger + orchestrateur + heartbeat
VPS-READY + **Règle 29 (Doctrine §3.1+§3bis+§6+§8 import V8) + zone_type persistence +
naissance_isolee window + HITL renforcé + pondération arbiter zone-type×session +
Règle 30 (apprentissage conditionnel WIN/LOSS, seuils progressifs 5/20/50/200)**.
**703 tests verts / 3 xfailed / 1 xpassed**, doctrine **30 règles immuables**,
Mode A — VEILLE actif. Pipeline GBPUSD M5/M15/H1/H4/D1 vivant (port 31685, VPS cible :
4 cores 2.6 GHz / 12 GB RAM, SDI en cours d'installation par Søn).

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

## Session sprint Søn 2026-07-07 21h00 → 22h30 (β complet mode autonome)

Suite à demande Søn « je gère l'indicateur SDI et le VPS, occupe-toi du V9 »
(« V9 opérationnel comme je veux et non limitant »), sprint autonome livré
sans autre GO. 6 commits sprint sur `feat/v9-foundation-clean` :

- `22fa492` agents/REGISTRY.py — Mode A 5 chauds + supervisor + reviewer
- `165691c` core/v9/agent_telemetry.py + hook best-effort capture_server
- `15c6845` scripts/v9_agent_precision.py — CLI rapport précision
- `6db9e3b` scripts/v9_check_vps.py — preflight VPS (6 checks)
- `80dc3c5` resync ARCHITECTURE.md (214→663) + DECISIONS_LOG sprint
- `fa79787` audit 11 YAML gap V8/V9 + Règle 30 + BONUS_CONFLUENCE_MTF DEPRECATED

**Bilan** : +26 tests verts (637→663, 0 régression), doctrine 29→30 règles,
0 modif core/v9/business (config.py, orchestrator.py, principles/*.yaml,
arbiter.py intacts), 0 RPC, 0 LLM, 0 MCP, 0 dépendance pip. Anti-fédération
V8 respecté strictement.

**Audit V8/V9 11 YAML manquants** : Perplexity n'a rien écarté d'utile. 5 V6
archivage (mort 2026-04-29), 3 V7 blacklistés (WR 0%), 1 V7 SHADOW audit
requis, 1 V8_NATIVE SHADOW gelé Søn, 1 V7 bug SQL. Verdict : 0 migration
par défaut. Référence : `docs/audit/AUDIT_V8_V9_YAML_GAP_20260707.md`.

**Règle 30 — Apprentissage conditionnel WIN/LOSS** :
- ≥ 5  : lecture décisions possible, 0 recalibrage
- ≥ 20 : feedback loop partielle activable (= v9_agent_precision.py utilisable)
- ≥ 50 : Phase 13 complète activable (recalibrage arbiter zone-type × session)
- ≥ 200 : auto-tune seuils, boucle complètement fermée
- Garde-fous : pas de saut sans DECISIONS_LOG, zéro LLM (règle 18).

**Capacité cible VPS** (4 cores 2.6 GHz / 12 GB RAM, à charge Søn) :
Mode A compatible tout confort. Aucun souci RAM/DB. Le seul objet broker
spécifique = DB 2.9 GB (à ne pas migrer brute, plutôt seed 7 derniers jours).
Indicateur SDI à installer par Søn (charge hors sprint).

**Action immédiate pour Søn** : installer `.mq4` SDI sur VPS MT4,
démarrer `python -m core.v9.capture_server` côté VPS. Le flux arrivera,
télémétrie agents se remplira automatiquement, premier rapport précision
disponible dans 24h via `python scripts/v9_agent_precision.py --window 7`.

## Session Phase 14b CEO — Stale guard PRICE_LAG (2026-07-08 05:35 → 06:10)

Découverte pendant audit live 24h : Tokyo session 2026-07-08 montrait une
dérive 99.6% haussière sur 5778 décisions directionnelles — investigation
a révélé que **PRICE_LAG_AT_NODE_BIRTH** sur-déclenchait de 2-4% à 70-95%
quand forces_snapshot.stale=True. Mécanisme : pf_mid figé + tension_score
ACCUMULATING → 3 conditions YAML restent vraies → trigger systématique
avec confiance 96-100. Risque concret avant FOMC 18:00 UTC.

Commit [`e06f7e3`](https://github.com/gestionzen57-alt/PowerFlow_V9/commit/e06f7e3) :
- Ajout condition `stale == false` en tête du bloc conditions
- 4 tests pytest (`test_price_lag_stale_guard.py`) — verrouillage structurel
  + comportement stale + régression nominal + court-circuit CPU
- 703 verts (699 → 703), 0 régression
- Audit des 8 autres principes ACTIVE : aucun autre affecté
  (POWER_ANGLE/ZONE_RETEST/GRAVITY/NODE_BIRTH_FAST/RAW_NODE_BIRTH/
  COALITION_NODE/ANTAGONIST_NODE/ELASTIC_BREATH/GRAMMAR_REGIME)
- Backup MD5 dans `backups/2026-07-08_pre_stale_guard/`
- Périmètre R8 respecté : principle_engine.py / config.py / orchestrator.py intacts

Référence : DECISIONS_LOG.md §« 2026-07-08 — PRICE_LAG stale guard (Phase 14b CEO) ».

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
