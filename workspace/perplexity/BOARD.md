# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. En cas de divergence, `docs/STATE.md`
et `docs/CACHE_BOARD.md` font foi.

## Statut global V9
Chaîne cognitive à 9 couches complète et fusionnée sur `feat/v9-foundation-clean` :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal
→ Décision. Orchestrateur live (`core/v9/orchestrator.py`) opérationnel. Gouvernance
documentaire canonisée (`docs/v9-governance` fusionnée). Outillage opérationnel
(reboot/ouverture marché/reprise de session, « Phase 9.5 ») livré, aucune modification de
`core/v9/*`. **Règle 29** (doctrine §3.1+§3bis+§6+§8 import V8) ajoutée — lecture scène-complète
+ 4 types de zone (naissance / 2e_jambe / continuation / respiration) + pondération
arbiter zone-type×session. **Règle 30** ajoutée 2026-07-07 22h — apprentissage conditionnel
WIN/LOSS, seuils progressifs 5/20/50/200 (jamais par décision arbitraire).

**Phase 13 CEO 2026-07-10** : 4 décisions actées (CONFIANCE_MIN 80→70, arbiter zone_type=neutre
recal -6/-7 pts, YAML SIGNAL_OPEN SHADOW, catalogue 25 ACTIVE + 1 SHADOW = 26).
WR global 97.99% = biais structurel documenté (MFE>0 sur fenêtre 4h ≠ trade rentable).
Bus apprentissage réveillé (224 events/24h, 5 propositions meta-agent).
Architecture MCP recommandée (5 serveurs ciblés anti-V8 monolithique).
**930 tests verts, 0 régression.** HEAD = `9ec113c`. 10 commits H24+1h pushés.

Pipeline état : Phase 9.7 + 9.8 + 9.9 + 9.10-RULE29 + sprint Søn Mode A livrées 2026-07-07.
Audit dette = 0 (F-10 à F-19 résolus). **+26 tests verts sprint** (637 → 663 verts).
**Mode A agentification bornée** : 5 agents chauds (force_reader, scene_builder,
behavior_analyst, gatekeeper, decision_maker) + supervisor + reviewer. **Télémétrie
agents** opérationnelle (`core/v9/agent_telemetry.py` + hook best-effort capture_server),
CLI précision `scripts/v9_agent_precision.py`, préflight VPS `scripts/v9_check_vps.py`.
**Cible VPS** : 4 cores 2.6 GHz / 12 GB RAM (à charge Søn, SDI à installer).

Note historique : 359 verts au 2026-07-06 fin Phase 9.5 (cf.
`docs/checkpoints/CHECKPOINT_20260706_SESSION_FINALE.md`).

## Dernier commit structurant (sprint Søn 2026-07-07 21h → 22h30)
HEAD = `fa79787` — sprint Søn Mode A + télémétrie + VPS-ready + audit V8/V9 YAML +
Règle 30 + DEPRECATED BONUS_CONFLUENCE_MTF.

## Avant sprint Søn (session règle 29, 2026-07-07 17h45 → 20h55)
HEAD était `8a67583` (test window_gate naissance_isolee). Session 14 commits
livrés : `db979da` resync 596, `72f1361` doctrine règle 29, `3170f76`
zone_type + naissance_isolee, `bb5f190` replay_rule29, `47fbfa7` (a)
persistence, `8d12dda` (b) HITL renforcé, `9af7781` (c) arbiter pondération,
`bbfa3b7` tests arbiter, `8a67583` tests window_gate.

**Tests** : **637 → 663 verts** (état 596 → 605 → 637 → 663), 3 xfailed (consolidate fragiles),
1 xpassed. **Règle 7 OK**.
**Pipeline** : port 31685 (serveur actif, PID 42608 ce soir), DB v9_forces.db (2.9 GB, 72K+ snapshots).
**Doctrine** : **30 règles immuables** (règle 28 = Hermes git unique, règle 29 = lecture multi-TF,
règle 30 = apprentissage conditionnel WIN/LOSS).
**Telegram** : heartbeat cron `V9_HeartbeatAlert` toutes les 60min (token Hermes_chezson_bot OK).
**Paper-trade** : orchestrateur testé — 0 trade ouvert (range M5 GBPUSD, comportement attendu).
**Premier trade attendu** : prochain driver macro US majeur = **NFP vendredi 7 août 2026** (1er vendredi du mois, typique UTC 12:30). Entre-temps : aucune news HIGH dans 4h (calendar statique). Marché range post-Fête US, comportement structurellement inerte — V9 fait exactement son travail (99.3% abstention) tant que le marché ne crée pas d'événement `bascule/rupture/extension`.
**Cible VPS** : 4 cores 2.6 GHz / 12 GB RAM, indicateur SDI à charge Søn (hors sprint),
commande `python -m core.v9.capture_server` à lancer côté VPS une fois SDI installé.

Upstream : `origin/feat/v9-foundation-clean` à parité avec HEAD `fa79787` (6 commits
sprint Søn pushés, 0 divergence, working tree clean).

## Phase actuelle
**Phase 9.7 + 9.8 + 9.9 + 9.10-RULE29 livrées 2026-07-07.
Règle 29 active (doctrine + code + tests).
Attente premier paper trade (prochain driver macro US majeur = NFP vendredi 7 août 2026).
Mode A — VEILLE actif.**

- HEAD : `b5cfa99`
- Tests : **596 verts**, 0 échec
- DB live : 7 signaux directionnels GBPUSD 2026-07-07, confiance 80–100, 2 messages Telegram 10:07:49 CEST
- Paper-trade live : 0 trade ouvert (marché range M5, fenêtres non exploitables)
- Conditions pour 1er paper trade : ≥ 2 principes ACTIVE + confiance ≥ 80 + window=exploitable + news_phase ≠ NEWS_SHOCK
- Critères objectifs WIN/LOSS ≥ 20 (règle 25) : **non remplis** — collecte via `scripts/v9_resolve_decision.py` (`b6b722e`)
- Phase 11 (Layer MT5 ticks) **conditionnelle** : 1er paper trade loggé + session London/NY observée

Voir [`docs/checkpoints/CHECKPOINT_20260707_PHASE10.md`](../../docs/checkpoints/CHECKPOINT_20260707_PHASE10.md) pour le détail (signature opérateur + tests live).

## Acquis stabilisation live (2026-07-06)
- Flux EA MT4 live réel confirmé : 7 TF connectés, timestamps qui avancent en temps réel, `is_closed_bar=0`, `validate-ea = VALIDE`.
- `calibrate` et `principles` exécutés sur n≥218 snapshots M5+ purement live.
- `zone_diagnostics` alimenté en live (2 008 lignes, états NEUTRAL/EARLY_EXTREME/ACCUMULATING visibles).
- 9/9 principes `node_rule` ACTIVE désormais déclenchables. `ANTAGONIST_NODE = 0` est un comportement normal de marché (H1 et M5 alignés, pas de divergence).
- Stale M5+ : ~0.6% — excellent.
- Seuils suggérés calibration live : `COALITION_THRESHOLD → 3.73`, `ANTAGONISM_THRESHOLD → 31.31`, `PLIURE_THRESHOLD → 0.0`. **Non appliqués à `config.py`** en attente d'une session live plus longue.
- Le message résiduel "gap zone_diagnostics" dans `v9_calibration.py` est un résidu de code obsolète (non mis à jour après commits `db11917` + `a596f37`). Corrigé en session. Verdict : `ANTAGONIST_NODE` dépend du contexte cross-TF de `forces_snapshots`, pas de `zone_diagnostics`.

## Blocages
Aucun blocage dur identifié. Gaps/anomalies connus, non bloquants :
- ~~`zone_diagnostics` créée mais **non alimentée**~~ → **RÉSOLU** le 2026-07-06 (commits `db11917`, `a596f37`). 9/9 principes `node_rule` ACTIVE déclenchables.
- Marquage replay vs live posé dans les 8 tables dérivées (colonne `source_type`, 2026-07-06). ✅ Résolu.
- ~~Calendrier canonique (`core/v9/market_calendar.py`) ancré sur 22h UTC fixe, incorrect ~8 mois/an pendant la DST US~~ → **RÉSOLU** par commit `e42d81b` (DST-aware via `America/New_York` + `zoneinfo`, 2026-07-07).
- ~~7 documents stales mentionnent encore "zone_diagnostics non alimentée"~~ → **RÉSOLU** par commit `7e56661` (nettoyage 7 docs stales alignés sur la réalité live, 2026-07-07).
- Seuils `config.py` encore `PROVISIONAL` (portés de V8) — gelés jusqu'au run calibration 08h CEST London open (Phase 9.7, commit `539a62e`).

## Next actions (voir aussi `ACTIVE_TASKS.md`)
1. Observation live continue via `python scripts\v9_ops.py watch` et `python scripts\v9_ops.py signals` / `decisions` (session Asie en cours, n>5 000 scènes).
2. ✅ ~~Nettoyage documentaire borné : aligner les 7 documents stales sur la réalité live~~ → FAIT (commit `7e56661`).
3. Décision structurante au matin 08h CEST : appliquer ou non les seuils suggérés (COALITION 5.38, ANTAGONISM 30.53, PLIURE 0.86) — règle de convergence : 3 runs Hermes stables + n>5 000 + WIN/LOSS ≥ 20.
4. Compléter le draft checkpoint Phase 9 → Phase 10 (`docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md`) avec les résultats du run calibration London open.
5. Déclenchement Phase 10 — fédération d'agents — sous condition des 4 critères bloquants (règle doctrine 16/17/19).

## Ce qui est gelé
- **Phase 10 (fédération d'agents)** : planifiée (P1) mais ne démarre pas avant
  stabilisation live confirmée et checkpoint de transition.
- **Architecture globale agents / routing / mémoire avancée** : hors périmètre actuel.
- **Skills/agents auto-générés** : dépend d'un socle Phases 9-10 stable en live.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts — ne pas mélanger maintenant ».

## Ce qui reste avant Phase 10
1. ✅ Flux live confirmé
2. ✅ `validate-ea` valide
3. ✅ `calibrate` + `principles` sur live pur
4. ✅ `zone_diagnostics` alimenté et cohérent
5. ⏳ Seuils `config.py` applicables (après session live plus longue)
6. ✅ Nettoyage documentaire stales (commit `7e56661` + corrections BOARD.md 2026-07-07)
7. ⏳ Checkpoint officiel de transition Phase 9 → Phase 10

## Références pivots (ne pas dupliquer, toujours relire en premier)
- `docs/STATE.md` — détail vivant par phase
- `docs/CACHE_BOARD.md` — tableau de reprise complet
- `docs/ROADMAP.md` — phases restantes et chantiers gelés
- `docs/PERPLEXITY.md` — rôle et responsabilités de Perplexity dans V9
- `docs/DOCTRINE.md` — index doctrine (27 règles immuables au 2026-07-06)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` — outillage reboot/ouverture marché/reprise
- `workspace/perplexity/mini_checkpoints/20260706_084600_live_stabilise.md` — checkpoint live Phase 9
