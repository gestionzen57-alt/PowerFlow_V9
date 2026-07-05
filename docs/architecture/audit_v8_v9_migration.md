# Audit V8 → V9 — Migration Cognitive PowerFlow

**Date** : 2026-07-05
**Auteur** : Claude (architecte externe, audit sur branche `audit/v8-to-v9-migration`)
**Portée** : `D:\Projet\V8` (lecture seule) comparé à `D:\Projet\V9` (`feat/v9-foundation-clean`, commit `a233abb`)

## Méthode et limites

V8 contient **1361 fichiers Python hors venvs** (708 dans `core/`, 496 dans `scripts/`, 55 dans `tests/`)
et **~115 bases SQLite** (dont doublons de backup). Une lecture ligne-à-ligne exhaustive des 1361
fichiers n'est pas réalisable dans cet audit. La méthode a donc été :

1. Inventaire complet par taille/date (`Get-ChildItem` / `find`) — exhaustif, pas d'échantillonnage.
2. Groupement par préfixe de nom (`pf_*`, `run_*`, `dashboard_*`, `mcp_*`, `telegram_*`, etc.) pour
   identifier les clusters fonctionnels et les doublons versionnés.
3. Lecture de code source réelle (pas seulement docs) pour les modules cités explicitement dans la
   demande : fédération, principes, workflows, EA MQ4/MQ5, bridge MT5, schémas DB.
4. Introspection SQLite directe (`sqlite3` en lecture seule) du schéma **et** du volume réel de
   chaque table sur la base de production active (`core/powerflow_fresh.db`, modifiée aujourd'hui).
5. Comparaison ligne à ligne avec le schéma V9 actuel (`data/v9_forces.db` : `forces_snapshots`,
   `scenes`, `behaviors`, `windows`, `exploitability`).

Là où un fichier individuel n'a pas été ouvert (la majorité des 609 fichiers `core/*.py` hors des
modules cités ci-dessus), le classement [RÉCUPÉRABLE]/[ADAPTER]/[OBSOLÈTE]/[RECONSTRUIRE] est donné
**au niveau du cluster**, avec la taille et le rôle déduits du nom, de l'emplacement, et — quand
disponible — de `docs/architecture/ARCHITECTURE.md` / `docs/NOMENCLATURE.md`. Les divergences entre
la doc et le code trouvées au passage sont signalées explicitement (section 7).

---

## 1. Inventaire des modules V8

### 1.1 Vue d'ensemble par répertoire

| Répertoire | Fichiers .py | Rôle | Statut global |
|---|---|---|---|
| `core/` | 708 | Cœur logique métier : détecteurs, moteurs, dashboards, MCP server, run_*_once wrappers | Mixte — voir 1.2 |
| `scripts/` | 496 | Scripts opérationnels : tests (88), pf_* (66), cron runners, migrations, sync | Mixte — beaucoup de scripts one-off |
| `tests/` | 55 | Suite de tests V8 | Partiellement pertinent (voir 1.4) |
| `federation/` | 12 | Fédération d'agents LLM (registry, gateway, memory, scorecard) | **RÉCUPÉRABLE** (logique), **ADAPTER** (infra) |
| `principles/` | 39 (37 YAML + 2 py) | Grammaire de principes de trading (27 ACTIVE) | **RÉCUPÉRABLE** |
| `workflows/` | 7 YAML | Orchestration de workflows (battle_plan, federated_analysis, etc.) | **ADAPTER** |
| `ea/` | ~30 fichiers MQ4/MQ5 + .set | EA MetaTrader (capture forces, bridge MT5, ordres) | **RÉCUPÉRABLE** (déjà en partie migré vers V9) |
| `orders/` | 3 fichiers (pending.csv, pending_SENT.csv, JSON) | Exécution d'ordres MT5 en cours | **RECONSTRUIRE** pour V9 (phase future) |
| `research/`, `archive/`, `core/legacy/`, `core/archive/`, `federation/_archive*` | — | Code et DBs explicitement archivés | **OBSOLÈTE** |
| `mcp_comite/` | 2 | Serveur MCP "comité" alternatif | À examiner au cas par cas — probablement **OBSOLÈTE**/doublon de `powerflow_mcp_server.py` |
| `output/` | 499 fichiers (non-.py en majorité : JSON, rapports, dashboards) | Artefacts générés | **OBSOLÈTE** (régénérable) |

### 1.2 `core/` — 708 fichiers, clusters principaux

Le répertoire `core/` n'a pas de sous-structure (tout est à plat), avec un préfixe de nommage qui
sert de convention de facto :

| Préfixe | Nb fichiers | Contenu | Statut |
|---|---|---|---|
| `pf_*` | 319 | Détecteurs/moteurs métier (anchor, battlefield, zone, tick, scene, temporal, cascade, gravity...) | **ADAPTER au cas par cas** — logique de détection SDI valable, mais couplée à l'ancien schéma DB |
| `run_*` | 117 | Wrappers "_once" exécutés en cron pour déclencher un module `pf_*` | **OBSOLÈTE en tant que pattern** — V9 utilise un orchestrateur événementiel (`orchestrator.py`) et non des crons `_once` indépendants |
| `dashboard_*` | 26 | Normalisation/injection de cartes dashboard | **OBSOLÈTE** — V9 a `v9_dashboard.py` (Phase 8), architecture différente |
| `mcp_*` | 17 | Outils MCP (kpi, hot, live, rag, learning, workflow engine) | **ADAPTER** — logique de query réutilisable si un MCP server est reconstruit pour V9 |
| `analyst_*` | 15 | Mémoire/apprentissage de l'analyste (calibration, pattern, sequence, zone, HTF, node) | **RECONSTRUIRE** — logique intéressante mais fortement couplée à `analyst_memory.db` (150 Mo, schéma ad hoc) |
| `telegram_*` | 8 (+ doublons `_v01`, `_v01_1`, `_v01_2`, `_v6`) | Alerting Telegram | **OBSOLÈTE** — hors périmètre V9 actuel (pas de couche notification) |
| `tick_*` | 7 | Patterns microstructure ticks (patterns_composite, patterns_core, patterns_elite, microstructure) | **ADAPTER** — pertinent si V9 réintroduit une couche tick (voir section 5) |
| `scheduler_*` | 5 | Scheduler unifié (45 Ko `scheduler_unified.py`) | **OBSOLÈTE** — remplacé par le modèle événementiel V9 (insert → chaîne cognitive automatique) |
| `cockpit_*` | 5 | Cockpit terminal/agentic | **OBSOLÈTE** |
| `config_*` | 3 | Config V8 (`config_v8.py`, `config_paths.py`, `config_t009_flags.py`) | **OBSOLÈTE** (V9 a son propre `config.py`) |

**Doublons versionnés non nettoyés** (dette technique à ne PAS porter) :
- `pf_anchor_detector.py` + `_v2` à `_v9` → **9 versions coexistantes** du même détecteur
- `pf_price_verdict_v5_3.py`, `_v5_5.py`, `_v5_6.py` → 3 versions
- `telegram_trader_alert_v01.py`, `_v01_1.py`, `_v01_2.py` + `telegram_v6.py` / `telegram_timing_v6.py`
- `pf_lab_engine.py` (67 Ko) vs `pf_lab_engine_v72.py` (49 Ko) — deux moteurs de lab coexistants
- `run_battlefield_radar_once.py` / `_v02.py`, `run_weekly_agent_scan.py` / `_v02` / `_v03`
- `resolve_patterns.py` / `resolve_patterns_v2.py`

Ce pattern (créer `_v2`, `_v3`... sans supprimer les versions précédentes) est la dette technique
la plus visible du repo. **Ne pas reproduire dans V9** — le modèle worktree/branche déjà en place
sur V9 (une session = un worktree = une branche = un merge propre) évite structurellement ce
problème.

**Fichiers monolithiques massifs** (candidats "à ne pas récupérer tels quels") :
- `core/powerflow_mcp_server.py` — **430 934 octets** (~430 Ko), MCP server monolithique tout-en-un (le README fédération y référence "119 tools")
- `core/pf_temporal_node_state.py` — 102 Ko
- `core/detect_patterns.py` — 131 Ko
- `core/pf_lab_engine.py` — 67 Ko
- `core/pf_t009_sequence_summarizer.py` — 66 Ko
- `core/broadcast_briefing.py` — 47 Ko

Ces fichiers concentrent une logique métier réelle et testée en production (le SDI, la détection de
patterns) mais leur taille et leur couplage les rendent **inadaptables tels quels** — la valeur est
dans l'algorithme, pas dans le fichier. Recommandation : extraire la logique de détection utile
(ex. règles de coalition, seuils SDI ≥75/≤25) vers des modules V9 neufs et petits, pas porter le
fichier.

### 1.3 `scripts/` — 496 fichiers

- 88 fichiers `test_*.py` (à distinguer de `tests/`, 55 fichiers — double emplacement de tests, lui-même un signe de dette)
- 66 `pf_*.py`, 15 `run_*.py`, 12 `mcp_*.py`, 8 `resolve_*.py`, 8 `import_*.py`, 7 `replay_*.py`,
  7 `enrich_*.py`, 7 `backtest_*.py`, 6 `tick_*.py`, 6 `migrate_*.py`, 6 `discord_*.py`,
  6 `backfill_*.py`
- Sous-dossiers `batch/`, `chantier1/`, `chantier2/`, `dev/`, `hooks/`, `migration/`, `shell/` —
  noms qui suggèrent des chantiers ponctuels non nettoyés après clôture

**Statut** : majoritairement **OBSOLÈTE** en tant qu'ensemble (scripts one-off, cron wrappers,
migrations one-shot déjà appliquées). Quelques scripts individuels à examiner si besoin précis
(ex. `scripts/resolve_federation_outcomes.py`, cité dans `FEDERATION_README.md` comme resolver
différé actif — **RÉCUPÉRABLE** si la fédération est migrée).

### 1.4 Tests

- `tests/` : 55 fichiers
- `core/test_*.py` : 5 fichiers (`test_cascade_engine.py`, `test_cross_symbol_validation.py`,
  `test_p2_boost.py`, `test_session_overlay.py`, `test_wavelet_density.py`)
- `scripts/test_*.py` : 88 fichiers

Trois emplacements de tests différents (`tests/`, `core/`, `scripts/`) sans convention unique —
contraste avec V9 qui a un seul `tests/` avec 139 tests verts et une chaîne CI implicite claire
(Phases 1-9). **Ne pas porter la fragmentation** ; si des tests V8 sont récupérés, les re-heberger
sous `V9/tests/`.

### 1.5 État du dépôt au moment de l'audit

Le dépôt V8 a un **système live en cours d'exécution** pendant cet audit : `git status` montre des
modifications non commitées dans `cache/flash.json`, `cache/hermes.json`, `docs/STATE.md`,
`docs/papertrade_journal.md`, `scripts/live_pipeline_loop.py`, etc. — cohérent avec les crons Windows
Task Scheduler actifs décrits dans `agent_registry.py` (`ORCHESTRATED_SCRIPTS`). Ces fichiers n'ont
**pas été modifiés ni committés** par cet audit (contrainte "ne pas modifier V8" respectée) ; seul
`docs/audit_v8_v9_migration.md` est ajouté.

---

## 2. Base de données V8

### 2.1 Sprawl de fichiers `.db`

V8 a **~115 fichiers `.db`** répartis sur `core/`, `data/`, `federation/`, `output/`, `logs/`,
racine, et 3 dossiers de backup (`data/backups_20260701/`, `data/backups_20260704/`,
`data/old db powerflow/`). Beaucoup sont vides (0 octet) ou clairement abandonnés. Les bases
volumineuses actives :

| Fichier | Taille | Dernière écriture | Rôle |
|---|---|---|---|
| `data/tick_master.db` | **4,2 Go** | 2026-07-02 | Ticks bruts GBPUSD (tick_stream, tick_aggregated_5s) |
| `data/tick_master_v2.db` | 807 Mo | 2026-07-03 | v2 du même rôle — doublon actif |
| `data/old db powerflow/powerflow_fresh old.db` | 486 Mo | archive | Ancienne version, déjà archivée |
| `core/powerflow_fresh.db` | 152 Mo | **2026-07-05 (aujourd'hui, live)** | **Base de production principale** — 55 tables |
| `data/analyst_memory.db` | 150 Mo | 2026-07-05 (live) | Mémoire d'apprentissage de l'analyste |
| `data/backups_20260704/powerflow_fresh.db` | 150 Mo | backup | Snapshot |
| `data/histdata_replay.db` | 332 Mo | 2026-06-30 | Données de replay historique |
| `core/scenes.db` | 42 Mo | 2026-07-04 | Scènes V8 (à ne pas confondre avec `scenes` de V9) |
| `core/papertrade.db` | 54 Mo | 2026-07-03 (live) | Paper trading |
| `data/mem0_local.db` | 49 Ko | — | Mémoire mem0 locale |

`data/v9_forces.db` **existe déjà dans l'arborescence V8** (0 octet, créé 2026-07-05 07:01) — signe
que le port TCP 31685 partagé entre V8 et V9 (déjà documenté côté V9) a laissé une trace côté V8
également ; à surveiller pour éviter toute confusion de chemin entre les deux repos.

### 2.2 Schéma complet — base de production (`core/powerflow_fresh.db`, 55 tables)

Tables avec volume (au 2026-07-05) :

| Table | Lignes | Table | Lignes |
|---|---|---|---|
| `regime_snapshots` | 327 112 | `scene_detection_log` | 12 361 |
| `force_snapshots_v2` | 53 249 | `signature_log` | 8 678 |
| `rotation_multidevise` | 39 756 | `decision_log` | 7 442 |
| `zone_diagnostics` | 36 808 | `antagonism_log` | 6 432 |
| `gravity_log` | 30 484 | `detected_patterns` | 5 565 |
| `time_compression_events` | 22 578 | `structure_ledger` | 5 299 |
| `tick_force_minute` | 24 789 | `coalition_log` | 2 727 |
| `bridge_forces_tick` / `cinematic_metrics` | 13 964 chacune | `fractal_coherence_log` | 2 736 |
| `triple_cross_cascade` | 2 691 | `tick_context_enriched` | 2 721 |
| `scene_journal` | 848 | `cerebras_verdicts` | 560 |

38 tables au total ont des données ; 17 sont vides (`agent_memory`, `analyst_log`, `backtest_results`,
`compression_metrics`, `elite_patterns`, `learned_rules`, `learner_proposals`, `position_status_log`,
`principles_registry`, `quota_log`, `sequence_log`, `daily_stats`, etc.) — code écrit mais jamais
alimenté en production, ou fonctionnalité abandonnée en cours de route.

**Schémas des tables citées dans la demande** (extraits `CREATE TABLE` réels, pas la doc) :

- **`force_snapshots_v2`** (53 249 lignes) : `id, created_at, symbol, timeframe, bar_time,
  bar_close_time, server_time, capture_time, is_closed_bar, open/high/low/close, tick_volume,
  spread_points/price/pips, bid, ask, mid, force_aud/gbp/jpy/usd/cad/eur/chf/nzd, source_id,
  bridge_version, tick_freq_hz, tick_marche_paie, tick_absorption, tick_freq_surge`
- **`detected_patterns`** (5 565 lignes) : `id, ts, ts_epoch, symbol, pattern_type, pattern_name,
  confidence, price, delta_f, force_gbp/usd, h4_gbp/usd, h1_gbp/usd, details, resolution_ts,
  resolution_direction, resolution_pips, resolved, is_win, resolution_label, sequence_id`
- **`structure_ledger`** (5 299 lignes, clé `(ts, symbol)`) : empile D1/W1/H4/H1/M30/M15/M5 avec
  gbp/usd/regime/score par TF, `velocity`, `inertia_min`, `coalition_strength`, `leader_devise`,
  `total_score`, `verdict`, `bridge_verdict`, `zone_extreme_score`, `bloc_eu/sh/com`, `session*`
- **`time_compression_events`** (22 578 lignes) : `ts_minute, event_type, timeframes, band_pips,
  ticks_in_lock, center_price, break_price, delta_force, force_regime, compression_subtype,
  tick_count, tick_freq_hz, ...` avec `UNIQUE(ts_minute, timeframes, event_type)`
- **`zone_diagnostics`** (36 808 lignes) : `logged_at, symbol, timeframe, currency, state, zone_level,
  z_current, z_extreme_dir, bars_in_extreme, pullback_count, absorbed_pullback_count,
  depth_slope/acceleration, absorption_factor, tension_score, context_score, profile_name,
  rank_position/total/duration_bars, context_tags_json, raw_diagnosis_json, ...`

### 2.3 Comparaison avec le schéma V9 (`data/v9_forces.db`)

V9 a **6 tables** (`forces_snapshots`, `scenes`, `behaviors`, `windows`, `exploitability`,
`sqlite_sequence`), toutes vides à ce stade (base fraîchement créée) mais au schéma stabilisé sur
139 tests. Comparaison :

| V8 | V9 | Verdict |
|---|---|---|
| `force_snapshots_v2` | `forces_snapshots` | **Repris et étendu** — V9 ajoute `direction`, `vitesse`, `croisement_detecte/partenaire/direction`, `recroisement_detecte/contexte`, `rejet_repulsion_detecte/intensite`, `compression_extension_etat/intensite`, `stale`, `age_ms` — c'est un vrai raffinement, pas juste un renommage. V9 **n'a pas** encore `spread_pips`, `tick_freq_hz`, `tick_marche_paie`, `tick_absorption`, `tick_freq_surge` de V8 — à évaluer si utile |
| `detected_patterns` | *(absent — remplacé par `windows` + `exploitability`)* | Remplacement conceptuel assumé (cf. tableau gap section 6) — mais V8 a une notion de `resolution_pips` / `is_win` (issue de trade réelle) qui n'existe dans aucune table V9 actuelle |
| `structure_ledger` | *(absent — partiellement recouvert par `scenes.confluences_mtf_json` et `contexte_temporel_json`)* | Le multi-TF D1→M5 de `structure_ledger` est plus riche (verdict, coalition_strength, leader_devise numériques) que les champs JSON non structurés de `scenes` — à surveiller si l'exploitation par requête SQL est nécessaire côté V9 |
| `time_compression_events` | *(absent — recouvert conceptuellement par `forces_snapshots.compression_extension_etat`)* | V8 a un event log dédié (append-only, dédupliqué par `UNIQUE(ts_minute,...)`) alors que V9 a un champ d'état sur le snapshot — ce sont deux modélisations différentes (event log vs état courant), pas un simple renommage |
| `zone_diagnostics` | *(absent)* | Aucun équivalent V9 actuel. `zone_diagnostics` porte la logique de zones extrêmes (pullback, absorption, tension) très utilisée par le SDI (règle "SDI ≥75/≤25 = retournement"). **Gap réel à combler**, cf. section 6 |
| `scene_journal` (narratif texte) | `scenes` (JSON structuré) | V9 est structurellement supérieur (JSON typé vs texte libre) — ne pas reporter le format V8 |
| `regime_snapshots` (327k lignes) | *(absent)* | Le plus gros volume de données V8, aucun équivalent structurel côté V9 |
| `rotation_multidevise`, `gravity_log`, `coalition_log` | *(partiellement recouverts par `scenes.coalitions_json`)* | Logique de coalition/rotation multidevise existe en V8 sous forme de tables dédiées, en V9 sous forme de JSON embarqué dans `scenes` — cohérent avec l'architecture V9 "5 couches" mais perd la requêtabilité SQL directe |

**Constat clé** : la couche `forces_snapshots` de V9 est un **sur-ensemble net et amélioré** de
`force_snapshots_v2`. En revanche, tout ce qui en V8 vivait dans des tables analytiques dédiées
(`zone_diagnostics`, `structure_ledger`, `regime_snapshots`, `time_compression_events`) est en V9
soit absent, soit compressé dans des champs JSON à l'intérieur de `scenes`/`behaviors`. C'est un
choix d'architecture cohérent (moins de tables, plus de JSON typé par couche), mais il faut confirmer
que rien d'important n'est perdu — en particulier `zone_diagnostics` (pas d'équivalent, même
partiel) et la traçabilité `resolution_pips`/`is_win` de `detected_patterns` (retour réel de trade,
absent de `windows`/`exploitability`).

---

## 3. Indicateur SDI (MQ4)

### 3.1 État du code

L'indicateur **source** "SDI TCSWL 600+" (celui appelé via `iCustom(sym, tf, "SDI TCSWL 600+", buffer, shift)`)
**n'est pas présent dans le dépôt** — ni en `.mq4` ni en `.ex4`. Il tourne dans MT4/MT5 comme
indicateur compilé installé séparément (hors repo). Seuls les **consommateurs** de l'indicateur sont
dans `ea/` :

- `ea/SDI_Diagnostic.mq4` (97 lignes) — dump manuel des 8 buffers pour diagnostic
- `ea/SDI_Diagnostic_EA.mq4` (87 lignes) — variante EA du diagnostic
- `ea/EA_PowerFlow_V8_Sonde_TF.mq4` (242 lignes) — capteur multi-timeframe (celui avec le bug corrigé, voir 3.3)
- `ea/EA_PowerFlow_V8_UniversalSonde.mq4` (329 lignes) — capteur multi-devise
- `ea/EA_PowerFlow_V7_UniversalSonde_FINAL.mq4` — version V7, toujours en usage parallèle

**Gap identifié** : le code source de l'indicateur SDI lui-même est absent du repo Git — seul le
binaire compilé tourne dans MT4/MT5. Si l'indicateur doit être modifié un jour, il faudra le
retrouver ou le redévelopper à partir de sa spécification (8 buffers = 8 devises).

### 3.2 Buffers lus (confirmé par lecture de code, `EA_PowerFlow_V8_Sonde_TF.mq4:105-116`)

```
buffer 0 = AUD   buffer 4 = CAD
buffer 1 = GBP   buffer 5 = EUR
buffer 2 = JPY   buffer 6 = CHF
buffer 3 = USD   buffer 7 = NZD
```

8 devises confirmées. Timeframes lus (multi-TF, capteur `Sonde_TF`) : le fichier tourne un chart par
TF (M1/M5/M15/M30/H1/H4 confirmés dans `PROCEDURE_SHIFTINDEX_2026_06_30.md`, +D1/W1 visibles dans
`structure_ledger`) — soit l'ensemble des **7 timeframes** cité dans la demande utilisateur
(cohérent avec `structure_ledger` qui a des colonnes `d1_/w1_/h4_/h1_/m30_/m15_/m5_`).

### 3.3 Bug connu — EA 5min qui lisait mal les buffers

Confirmé par `ea/PROCEDURE_SHIFTINDEX_2026_06_30.md` et le code actuel :

- **Cause** : `EA_PowerFlow_V8_Sonde_TF.mq4` avait `ShiftIndex=0` par défaut (lit la bougie **en
  cours**, non fermée) au lieu de `1` (bougie fermée). Résultat : `is_closed_bar=false`
  systématiquement dans le flux JSON envoyé en DB, ce qui dégradait silencieusement 5 scripts Python
  en aval (`rotation_multidevise`, 3× `analyst_*_learning`, `pf_anchor_detector`) — ils consommaient
  des valeurs de bougie non stabilisées.
- **Fix appliqué le 2026-06-30 05:55 UTC** : ligne 28 du fichier, `ShiftIndex` par défaut passé de
  `0` à `1`, avec commentaire explicite dans le code (`"default 1, aligne V7 + coherence
  force_snapshots_v2.is_closed_bar"`) — **vérifié présent dans le code actuel** (ligne 28 lue
  directement).
- **Filet de sécurité désactivé** : un cron `*/5 * * * *` qui rétro-propageait `is_closed_bar=1` a
  été désactivé dans `core/scheduler_unified_config.json` après validation du fix — cohérent avec le
  message utilisateur ("EA 5min qui lisait mal les buffers → valeurs décalées").
- **Reste à faire côté V8** (documenté dans la procédure, pas vérifié par cet audit car il s'agit
  d'action manuelle MT5, hors code) : appliquer `ShiftIndex=1` sur chaque chart MT5 ouvert
  (l'input par défaut ne s'applique qu'aux nouveaux attachements d'EA, pas aux instances déjà
  tournantes) et créer les `.set` files `MT4 V8 1 min.set` / `MT4 V8 HTF.set` correspondants.
- **Pertinence V9** : le mémo de session V9 (Phase 7) confirme que les fichiers `ea/V9_Sonde_M1.mq4`
  et `ea/V9_Sonde_TF.mq4` sont les héritiers directs de ces EA V8, avec un port TCP 31685 codé en dur
  et **partagé avec V8 en production** — point de vigilance opérationnel déjà noté côté V9.

---

## 4. Architecture de fédération V8

### 4.1 Agents — 13 agents réels (pas les noms cités dans la demande initiale)

`federation/agent_registry.py` (1020 lignes) définit **13 agents canoniques** dans le dict `AGENTS` :
`hermes_scan`, `hermes_quant`, `hermes_validate`, `hermes_chairman`, `hermes_code`, `hermes_research`,
`hermes_free1` à `hermes_free5`, `hermes_code_premium`, `hermes_deep_analyst` — plus 2 alias
backward-compat (`hermes_cerebras`→`hermes_validate`, `hermes_opus`→`hermes_chairman`).

Les noms `hermes_analyst` cités dans la demande initiale ne correspondent à aucun agent réel du
registre — probablement une confusion avec `hermes_deep_analyst` ou `analyst_*` (les modules
d'apprentissage `core/analyst_*.py`, sans lien direct avec la fédération LLM).

Routage : `free_first` (Groq/OpenRouter/Nous gratuits par défaut), avec `hermes_code_premium`
(Claude Sonnet 4) en **opt-in strict, jamais routé automatiquement**. Le fichier contient un
historique de migrations de providers (Groq → OpenRouter → NVIDIA/Nous) visible dans les
commentaires, signe d'une fédération qui a beaucoup itéré sur le coût/performance des modèles.

### 4.2 Workflows YAML (7 fichiers)

`workflows/battle_plan.yaml`, `federated_analysis.yaml`, `daily_briefing.yaml`,
`session_opening_battle_plan.yaml`, `session_review.yaml`, `signal_check.yaml`,
`auto_sync_docs.yaml`. Exemple lu (`battle_plan.yaml`) : orchestre `charging_state` →
`hermes_scan` (analyse microstructure) → `run_battle_plan` (chairman ou fallback heuristique),
avec sortie vers `docs/checkpoints/battle_plan_live.md`. Logique déclarative simple (steps +
depends_on), portable telle quelle vers un nouveau moteur de workflow.

### 4.3 Principes (39 fichiers = 37 YAML + 2 py)

Confirmé par comptage direct des statuts YAML :

- **27 ACTIVE** (`status: active` × 24 + `status: ACTIVE` × 3) — correspond exactement au chiffre
  cité dans la demande
- **9 DEPRECATED**
- **2 SHADOW** (dont un avec commentaire explicite `# JAMAIS ACTIVE sans gate Sön — 3 cas seulement`)

**Aucun fichier `shadow_gate.py` ou `shadow_gate.yaml` trouvé** dans tout le repo (recherche
exhaustive `grep -ri shadow_gate`) — confirme "shadow_gate supprimé" tel que cité dans la demande.
Le principe le plus riche (`principles/GRAMMAR_*.yaml`, 15 fichiers) forme une vraie grammaire de
lecture de marché (absorption, antagonisme, break, coalition, croisement, exhaustion, extension,
gravité, inversion, leader/follower, lock, opposition, pullback, régime, respiration, squeeze,
tension) — c'est la définition formalisée de "comportements" que V9 vise à formaliser dans sa
couche `behaviors`.

### 4.4 Pertinence pour V9

| Composant | Pertinence | Commentaire |
|---|---|---|
| `agent_registry.py` (config agents/fallbacks/quotas) | **RÉCUPÉRABLE** | Logique de routage free-first + fallback chains est directement réutilisable, indépendante du schéma DB |
| `federation_evidence_gate.py`, `federation_contracts.py` | **RÉCUPÉRABLE** | Gate déterministe avant synthèse — bon pattern pour éviter les hallucinations de synthèse |
| `federation_memory.py` (schéma 25 colonnes) | **ADAPTER** | Le concept (mémoire structurée + `query_memory`/`memory_summary`) est bon ; le schéma doit être aligné sur les tables V9 (scenes/behaviors/windows) plutôt que sur `bridge_verdict`/`patterns_seen` V8 |
| `orchestrator_router.py` (hot-reload routing) | **RÉCUPÉRABLE** | Pattern découplé utile |
| `gateway_server.py` (FastMCP port 8765) | **ADAPTER** | Dépend de `powerflow_mcp_server.py` (430 Ko monolithique) côté V8 — à reconstruire léger pour V9 |
| 27 principes YAML (grammaire) | **RÉCUPÉRABLE tel quel** | Ce sont des règles déclaratives indépendantes du code — portables directement comme grammaire de la couche `behaviors` V9 |
| Workflows YAML | **ADAPTER** | Structure `steps/depends_on` réutilisable ; les `tool:` référencés (`get_charging_state`, `run_battle_plan`) doivent être ré-implémentés côté V9 |

---

## 5. Couche MT5 (tick layer)

### 5.1 Bridge MT5 → Python

Deux générations coexistent :
- `core/pf_mt5_bridge.py` (8,3 Ko) — legacy
- `core/pf_mt5_bridge_v2.py` (48,9 Ko, **actif** — modifie `orders/pending.csv`, lit
  `output/bridge_verdict_{symbol}.json`, écrit dans `output/trade_log.db`)

`pf_mt5_bridge_v2.py` implémente une vraie stratégie d'exécution en production : règles "GOLDEN"
(WR historique 61.1%) — USDJPY (60%) + GBPUSD (40%), LONG uniquement, sessions ASIA+NY, SL=15/TP=20,
volume 0.01 lot. C'est un **système de trading réel avec règles métier dures codées en Python**, pas
juste un connecteur technique.

Côté EA : `ea/MT5_PowerFlow_Bridge.mq5` / `_v2.mq5` (571 lignes, + README dédié),
`ea/PowerFlow_V8_Socket_EA.mq5`, `ea/T009_TickRecorder_MT5.mq5` (recorder de ticks bruts).

### 5.2 Lecture de ticks GBPUSD

`data/tick_master.db` (4,2 Go, table `tick_stream` + `tick_aggregated_5s` + `scalp_observations`) et
`data/tick_master_v2.db` (807 Mo) — deux générations actives simultanément, la v2 n'ayant
apparemment pas encore remplacé la v1 (les deux ont été écrites début juillet 2026).

### 5.3 Microstructure

`core/tick_patterns_microstructure.py`, `core/tick_patterns_core.py`, `core/tick_patterns_elite.py`,
`core/tick_patterns_composite.py`, `core/pf_order_flow_proxy_lite.py`, `core/pf_cvd_tracker.py`,
`core/pf_iceberg_detector.py` — cluster de détection microstructure sur ticks bruts (absorption,
iceberg, CVD, order flow proxy). Alimente `microstructure_scores` (181 lignes) et
`tick_context_enriched` (2 721 lignes) en DB.

### 5.4 Pertinence pour V9

V9 n'a **aucune couche tick actuellement** (capture forces uniquement, cf. `forces_snapshots`). La
couche microstructure V8 est significative (4,2 Go de données, ~15 modules de détection) mais
**fortement couplée** à `tick_master.db` et aux scripts `run_tick_*_once.py`. C'est une décision
produit, pas seulement technique : réintroduire les ticks dans V9 signifie relancer un flux de
données à très haut débit (vs le rythme "snapshot par bougie fermée" actuel de V9). **À décider
explicitement avec l'utilisateur** avant tout portage (cf. gap table, ligne "MT5 ticks").

---

## 6. Gap analysis V8 → V9

| Domaine | V8 | V9 | Action |
|---|---|---|---|
| Capture forces | `capture_forces.py` + EA → `force_snapshots_v2` (53k lignes) | TCP→SQLite (`forces_snapshots`, schéma étendu) | ✅ Fait — V9 est un sur-ensemble |
| Chaîne cognitive | Fragmentée (609 fichiers `core/`, couplage fort) | Unifiée 5 couches (forces→scenes→behaviors→windows→exploitability), 139 tests | ✅ Fait |
| Fédération agents | Active, 13 agents, gateway FastMCP, workflows YAML | Absente | À migrer (agent_registry + evidence_gate en priorité, cf. 7) |
| Principes | 27 ACTIVE (grammaire YAML) | Absents | À intégrer tel quel — zéro dépendance code |
| Replay | Bootstrap memory (`replay_results/`, ad hoc par run) | `v9_replay.py`, read-only, testé | ✅ Fait — V9 supérieur |
| Dashboard | 26 modules `dashboard_*` + `dashboard_server.py` | `v9_dashboard.py` | ✅ Fait — V9 est plus simple/maintenable |
| Calibration | Manuelle (`pf_calibration_*`, `analyst_calibration_report.py`) | `v9_calibration.py` | ✅ Fait |
| MT5 ticks | Bridge v2 actif + `tick_master.db` 4,2 Go + 15 détecteurs microstructure | Absent | À décider (voir 5.4) — impact volumétrie/latence significatif |
| Orders | `pf_mt5_bridge_v2.py` (règles GOLDEN actives, WR 61.1%) + `orders/pending.csv` | Absent | Phase future — logique de règles ("GOLDEN") récupérable, infra (CSV↔EA) à reconstruire |
| Patterns détectés | `detected_patterns` (5 565 lignes, avec `resolution_pips`/`is_win` réel) | `windows` + `exploitability` | Remplacé conceptuellement — **vérifier que le retour de trade réel (`is_win`, `resolution_pips`) a un équivalent V9**, sinon gap de mesure de performance |
| Zones extrêmes | `zone_diagnostics` (36 808 lignes — pullback, absorption, tension, rank) | Absent | **Gap non couvert** — aucune table ni champ JSON V9 équivalent identifié |
| Structure multi-TF | `structure_ledger` (5 299 lignes, D1→M5 typé SQL) | `scenes.confluences_mtf_json` (JSON libre) | Changement de modélisation (SQL typé → JSON) — requêtabilité perdue, à évaluer si nécessaire |
| Régimes de forces | `regime_snapshots` (327k lignes — le plus gros volume V8) | Absent | Gap non couvert, mais recouvrable partiellement par `forces_snapshots.compression_extension_etat` |
| Microstructure tick | 15 modules (`tick_patterns_*`, `pf_iceberg_detector`, `pf_cvd_tracker`) | Absent | Lié à la décision "MT5 ticks" ci-dessus |

---

## 7. Recommandations de migration

### Priorité 1 — à migrer immédiatement (haute valeur, faible couplage DB)

1. **27 principes YAML** (`principles/*.yaml`) — zéro dépendance code, portage direct comme grammaire
   de la couche `behaviors` V9. C'est le plus haut ratio valeur/effort de tout l'audit.
2. **`agent_registry.py` + `federation_evidence_gate.py` + `federation_contracts.py`** — logique de
   routage free-first, fallback chains, gate déterministe. Découplée du schéma DB V8, adaptable en
   quelques jours.
3. **Règles "GOLDEN" de `pf_mt5_bridge_v2.py`** (WR 61.1%, sessions, SL/TP, symboles) — c'est la
   seule stratégie d'exécution avec un historique de performance réel documenté dans le repo. À
   extraire du fichier (ne pas porter les 48,9 Ko tels quels) avant la phase Orders de V9.
4. **Correction ShiftIndex EA** — s'assurer que les EA V9 (`V9_Sonde_M1.mq4`, `V9_Sonde_TF.mq4`)
   héritent bien du fix `ShiftIndex=1` (déjà probable vu leur filiation directe, à vérifier
   explicitement dans leur code).

### Priorité 2 — peut attendre

1. **`zone_diagnostics`** (logique de zones extrêmes/pullback/absorption) — gap réel identifié en
   section 6, mais pas bloquant tant que la couche `behaviors`/`windows` V9 n'a pas démontré un
   besoin explicite de cette granularité.
2. **Workflows YAML** (`battle_plan.yaml`, `federated_analysis.yaml`) — portables une fois la
   fédération migrée (dépendance sur P1.2).
3. **Couche MT5 tick/microstructure** — décision produit à trancher explicitement (volumétrie 4,2 Go,
   15 modules) avant tout effort de portage.
4. **`structure_ledger`** (multi-TF SQL typé) — à réévaluer seulement si les requêtes JSON sur
   `scenes` s'avèrent insuffisantes en pratique.
5. **Orders / exécution MT5** (`orders/pending.csv` + EA côté MT5) — déjà noté "Phase future" par
   l'utilisateur ; dépend de P1.3 (règles GOLDEN) et de la couche `exploitability` V9 stabilisée.

### Priorité 3 — obsolète (legacy V6/V7, ne pas porter)

1. Tous les doublons versionnés non nettoyés : `pf_anchor_detector_v2` à `_v9` (9 versions),
   `pf_price_verdict_v5_3/5_5/5_6`, `telegram_trader_alert_v01/_v01_1/_v01_2`, `pf_lab_engine` vs
   `_v72`, `run_battlefield_radar_once` vs `_v02`, `run_weekly_agent_scan` vs `_v02/_v03`.
2. Le cluster `dashboard_*` (26 fichiers) et `scheduler_*` (5 fichiers, dont `scheduler_unified.py`
   45 Ko) — modèle cron/dashboard remplacé par l'orchestrateur événementiel V9.
3. Le cluster `telegram_*` (8+ fichiers) — hors périmètre V9 actuel.
4. `core/legacy/`, `core/archive/`, `federation/_archive/`, `federation/_archive_2026_06_21/`,
   `archive/` (108 Mo), `OLD/` — déjà explicitement archivés par l'équipe V8 elle-même.
5. Toutes les DB de backup/doublon (`data/backups_20260701/`, `data/backups_20260704/`,
   `data/old db powerflow/`, `data/tick_master_v2.db` tant que `tick_master.db` original coexiste
   sans clarté sur laquelle fait foi).
6. Le monolithe `core/powerflow_mcp_server.py` (430 Ko) tel quel — reconstruire un serveur MCP V9
   minimal plutôt que porter/refactorer ce fichier.

### Dette technique à ne PAS porter dans V9

- **Le pattern `_v2`/`_v3`.../`_v9` en suffixe de fichier** sans suppression des versions
  précédentes — 8+ occurrences répertoriées. V9 évite déjà ce piège via le modèle
  worktree-par-phase + merge propre ; il faut le maintenir strictement.
- **Duplication de tests sur 3 emplacements** (`tests/`, `core/test_*.py`, `scripts/test_*.py`).
- **Sprawl de bases SQLite** (~115 fichiers `.db`, dont beaucoup vides ou dupliqués) — V9 doit
  rester sur une base unique (`v9_forces.db`) et ne créer une nouvelle base que pour une raison
  architecturale explicite (comme documenté pour les phases 3-6).
- **Tables créées mais jamais alimentées** (17 tables vides sur 55 dans `powerflow_fresh.db`) —
  signe de fonctionnalités commencées puis abandonnées ; ne pas répliquer le réflexe "créer la
  table au cas où".
- **Divergence doc/code observée** : `FEDERATION_README.md` documente "5 agents canoniques" et un
  routage Groq (`llama-4-scout`, `llama-3.3-70b`) dans son tableau "Profils agents", alors que
  `agent_registry.py` (code réel, à jour) définit **13 agents** routés en free-first
  OpenRouter/Nous/NVIDIA — le README n'a pas suivi la dernière migration de providers. **Leçon pour
  V9** : si une doc de fédération est écrite, la lier par test automatisé au code (comme V9 le fait
  déjà pour `STATE.md`/`CACHE_BOARD.md` à chaque fin de session).

---

## 8. Estimation d'effort par composant

| Composant | Effort estimé | Justification |
|---|---|---|
| Principes YAML → V9 | **0,5–1 jour** | Copie directe + validation format contre `behaviors` |
| `agent_registry.py` + evidence gate → V9 | **2–3 jours** | Portage config + tests, sans dépendance DB |
| Workflows YAML → V9 | **1–2 jours** | Une fois fédération migrée ; ré-implémenter les `tool:` référencés |
| Règles GOLDEN (exécution) → V9 Orders | **3–5 jours** | Extraction logique + intégration avec `exploitability`, tests sur historique WR |
| `zone_diagnostics` (si retenu) → V9 | **5–8 jours** | Nouvelle table/couche, logique pullback/absorption à réécrire proprement (pas porter le fichier) |
| MT5 tick/microstructure (si retenu) | **10–15 jours** | Nouvelle capture haut-débit, 15 modules de détection à sélectionner/réécrire, volumétrie à gérer |
| Serveur MCP V9 minimal (si besoin fédération/dashboard externes) | **5–8 jours** | Reconstruction légère plutôt que portage de `powerflow_mcp_server.py` (430 Ko) |
| Nettoyage/archivage V8 (hors scope V9 mais recommandé) | **1–2 jours** | Marquer/déplacer les doublons versionnés et DB obsolètes identifiés en section 7 |

**Total P1 (priorité immédiate)** : ~6–11 jours.
**Total P1+P2 (sans MT5 ticks)** : ~15–25 jours.
**Avec MT5 ticks (P2 complet)** : ~25–40 jours.
