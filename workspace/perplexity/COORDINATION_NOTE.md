# NOTE DE COORDINATION — Session ZCode ↔ Hermes
## 2026-07-14 ~18:45 UTC — Resync Hermes

### Contexte
Søn en vacances, actif via VPS. Motion CEO « fait ce qu'il faut et continue les activation ».
**Fable hors service** (pas de crédit) — ZCode et Hermes continuent en parallèle sur
`feat/v9-foundation-clean`. Session Søn parallèle à venir via ZCode (à coordonner ici).

### État actuel (2026-07-14 ~18:45 UTC)

| Action | Statut | Qui | Détail |
|--------|--------|-----|--------|
- **A1** `V9_TRADER_MINI_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **A2** `V9_AUTO_CALIBRATOR_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P2** `V9_SHADOW_MODE_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P3-WIRE** `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED` | ✅ ON | ZCode+Hermes | Activé 14/07 commit `ac26c3a` (motion CEO priorité 3) — §2.4 DECISIONS_LOG 15/07 |
| **B+C+D** Audits | ✅ Fait | ZCode | DB 1.56GB, 9516 résolues, gate R30 PASS |
| **DB restoration** | ✅ Fait | Hermes | Commit `2ab07f3` (DB drainée → restaurée) |
| **Wrapper kill switches** | ✅ Fait | Hermes | Commit `2ab07f3` (loader .py + .bat + conftest) |
| **P1-RESOLVE** | ✅ Fait | ZCode | `resolve_one()` lit `signals.exit_strategy_recommended` — 3 nouveaux tests, 36/36 verts |
| **SHADOW-EXPAND** | 🔄 En cours | ZCode | Étendre shadow_evaluator à trader_mini_weigher + auto_calibrator |
| **P3-CONSUME** | ✅ **LIVRÉ 2026-07-14 18:55 UTC** | Hermes | 3 commits distants `f13c10f`/`eb1e7b9`/`01c2b9d`. 27 _ADAPTIVE générés (1 P3-CONSUME + 26 P3-CONSUME-EXTEND), tests 1303 verts. |
| **P3-CONSUME-EXTEND — CLOS** | ✅ **CLOSED 2026-07-15** | Hermes | §2.2 DECISIONS_LOG — bilan, baseline 1307 verts (ajd +4), tous SHADOW. Promotion ACTIVE = motion CEO distincte. |
| **Boucle apprentissage** | ✅ **Activée** | Hermes | Cron `V9_LearningLoop` installé Ready (18:43 UTC). Arbitrage §2.1 15/07 : 5 PENDING → 2 APPROVED (`cf7955b1be08` haussière, `49f65b2cb806` baissière) + 3 REJECTED (doublons). 0 PENDING. |
| **Resync docs** | ✅ Fait | Hermes | Commit `f94d2a9` + `48ea826` + `f13c10f` + `eb1e7b9` + `01c2b9d` — 5 docs resyncés + CHANGELOG étendu |
| **TP_SL P3-D1** | ❌ **CLOSED-OBSOLETE 2026-07-15** | — | §2.3 DECISIONS_LOG — 0 cas TP_SL depuis P1-RESOLVE. Tâche historique neutralisée. |
| **Phase 14 SPECIFIQUE** | ✅ **LIVRÉ 2026-07-15 05:25 UTC** | Hermes | §3 DECISIONS_LOG — `b7bfc98` poussé origin. Module `learning_offset_applier` + wire-up arbiter + CLI + 23 tests. Kill switch `V9_LEARNING_OFFSET_ENABLED` OFF par défaut, activation = motion CEO distincte. |
| **Phase 14.2 fix the 5-** | ✅ **LIVRÉ 2026-07-15 05:50 UTC** | Hermes | §4 DECISIONS_LOG — `2249fd9` poussé origin. Cache TTL 60s + bornes asymétriques (haussiere [0.85, 1.20] / baissiere [0.80, 1.10]) + kill switch ON par défaut (motion CEO §3.6 §1) + `v9_calibrate_offsets.py` grid search + 37 tests verts. |
| **Push** | ✅ **PUSHÉ 2026-07-15 05:05 UTC** | Hermes | PAT fourni par Søn via chat (modèle mémoire). `ac26c3a..f4e1798` → origin/feat/v9-foundation-clean. A redemander par session (credential store bash non persistant). |
| **Phase 14 push** | ✅ **PUSHÉ 2026-07-15 05:25 UTC** | Hermes | `587ca7c..b7bfc98` → origin/feat/v9-foundation-clean. Suite à motion CEO « fait la phase 14 et tout ». |
| **E** `V9_EXECUTION_ENABLED` | ❌ REFUSÉ | — | Interdit fondateur |
| **WIRE activation** | ✅ **FAIT 14/07** | ZCode+Hermes | cf. ligne P3-WIRE — activation = `ac26c3a` |
| **Arbitrage 5 propositions learning_loop** | ✅ **FAIT 2026-07-15 05:00 UTC** | Hermes | §2.1 DECISIONS_LOG — meilleur haussier + meilleur baissier 30j APPROVED, 3 doublons REJECTED. |

### Hand-off mis à jour

**Fable hors service** (pas de crédit). P3-CONSUME-EXTEND **repris par Hermes**
(mandat CEO « fait ce qu'il faut »). Fable 5 = clos sans livraison.

**ZCode en parallèle** : continue SHADOW-EXPAND sur sa session, livre ses commits
sur `feat/v9-foundation-clean` sans marcher sur P3-CONSUME-EXTEND (périmètre Hermes).

---

## 2026-07-20 ~23h45 UTC — Push Phase 2+3+3' (motion CEO 'go r28' reçue)

### Contexte
Søn motion CEO explicite 23:35 UTC : « go r28 » + « go max toute la nuit pas de limite Go ».
Push Phase 1 (commit `0d5e81c`) suivi de Phase 2 (commit `6ab0076`) et Phase 3+3' (`4bcb282` + `1cff80d`).

### Périmètre livré (pushés origin)
- Phase 1 — `0d5e81c` : câblage shadow Phase E (R25' strict)
- Phase 2 — `6ab0076` : CLI rapport edge uplift (`v9_meta_strategy_report.py`)
- Phase 3 — `4bcb282` : simulation replay (`v9_meta_strategy_simulation.py`) + verdict factuel
- Phase 3' — `1cff80d` : heuristic phase + --force-meta diagnostic

### Vérification empirique live
5000 décisions 30j sur `data/v9_forces.db` (lecture seule) :
```
WR legacy  : 81.10%
WR meta    : 81.10%
PF legacy  : 6.72
PF meta    : 6.72
Verdict    : RED_NO_UPLIFT
```
Cause : `principle_scores` n'a pas de colonne `strategy` → meta optimizer
tombe en fallback conservateur TP_SL sur tous les segments testés.
**Verdict R25' strict respecté : pas de câblage runtime.**

### Chantier de fond à ouvrir
Ajouter colonne `strategy` à `principle_scores` (motion CEO future distincte).
Avec 332 lignes actuelles et la table `paper_trades` résolue (4817 trades),
on peut dériver WR/PF/dd_ratio par (principle, strategy) et brancher
réellement le meta optimizer. Effort estimé : 4-6h, dépend de disponibilité
Claude/Opus pour la migration.

### Garde-fous respectés
- Motion #18 REGIME non-active, code intact.
- Phase 12 EXECUTION OFF, jamais touché.
- Constantes doctrine intouchées.
- Legacy runtime JAMAIS écrasé (R25' strict, tests `test_recommend_shadow_*`).
- Push conditionnel R28 appliqué sur motion CEO explicite.
- 5 commits atomiques, 92 tests verts cumulés (Phase E).
- Aucune régression globale (2426 → 2518 tests verts cumulés session).

### Anti-régression
- pytest tests/test_v9_meta_strategy_*.py → 23+20+34 = 77 tests verts cumulés.
- 3 fails globaux pré-existants (motion #32 en cours), aucun nouveau fail.
- 12 skipped vestigiaux + 2 xfail + 1 xpass (inchangés).

### Périmètre gelé (inchangé)
- Phase 10/12/13, R28 push sans mandat, exécution ordres réelle.

### Référence
- Branche : `feat/v9-resolve-drift-loop-20260720` (HEAD `1cff80d`).
- Brief nuit : `workspace/perplexity/PROMPT_CLAUDE_CODE_PHASE_E_NUIT_20260720.md`.
- Skill : `claude-code-overnight-session`.
- Mémoire : entrée consolidée 2026-07-20 (motion CEO AUTO-PILOTE + faux modèle nuit).

---

## 2026-07-20 ~23h00 UTC — Session nuit AUTO-PILOTE Phase E (Hermes foreground)

### Contexte
Søn motion CEO 2026-07-20 ~23h UTC : « tu vas optimiser toute la nuit avec claude
et claude opus, voit tout ». Tentative wrapper `claude -p "<brief>"` background :
**faux modèle nuit** (Claude Sonnet CLI = 1 tour puis exit, pas de loop). Skill
`claude-code-overnight-session` créé pour documenter le piège + 3 vrais patterns
(A foreground / B sous-agents / C Opus API + Python loop).

### Périmètre Hermes (cette nuit)
- ✅ Skill `claude-code-overnight-session` créé (périmètre `~/AppData/Local/hermes/skills/`).
- ✅ Mémoire mise à jour : pattern faux modèle documenté.
- ✅ Phase 1 livrée (foreground, R25' strict) :
  - `core/v9/v9_meta_strategy_shadow.py` (NEW, ~300 LOC) — kill switch `V9_META_STRATEGY_SHADOW_ENABLED=0` défaut.
  - `tests/test_v9_meta_strategy_shadow.py` (NEW, 23 tests verts).
  - Backup R8 `docs/calibration/backups/2026-07-21_meta_strategy_wire/` (4 fichiers, MD5).
  - `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-20 23h35 UTC.
- ⏸ Phase 2 (CLI rapport) + Phase 3 (validation edge uplift) = lundi.
- ⏸ Phase 4 (câblage runtime) = motion CEO distincte après uplift mesuré.

### Garde-fous respectés
- Motion #18 (REGIME_TIMEFRAME_OVERRIDES) NON ACTIF, code intact.
- Phase 12 (V9_EXECUTION_ENABLED) OFF, jamais touché.
- Constantes doctrine intouchées.
- Legacy runtime JAMAIS écrasé (R25' strict, tests `test_recommend_shadow_*`).
- Aucun push sans motion CEO explicite « go r28 ».

### Anti-régression
- 2426 tests passed (+23 nouveaux verts).
- 3 fails pré-existants (motion #32 en cours, non liés).
- 12 skipped vestigiaux + 2 xfail + 1 xpass.
- Aucune pollution working tree hors modules V9 cibles.

### Périmètre gelé (inchangé)
- Phase 10/12/13, R28 push sans mandat, exécution ordres réelle.

### Référence
- Brief nuit : `workspace/perplexity/PROMPT_CLAUDE_CODE_PHASE_E_NUIT_20260720.md`
- Session state : `logs/nuit_20260720/session_state.json`
- Skill : `claude-code-overnight-session` (créé cette session)

---

## 2026-07-18 ~23:25 UTC — Resync Hermes post-journée

### Contexte
Søn en vacances, actif via Telegram + chat. **Journée dense** (3 sessions CEO via
Claude/Opus/ZCode/Hermes en parallèle). Motion CEO §17h45 : « reformuler en
exploitant pleinement » / « prompt puissant [...] je copie colle » / « c'est
une autre philosophie » / « go et continue » — qui a déclenché :

1. **Chantiers A/B/C** livrés par Opus, commit `fbca486` (~19h35 UTC) :
   A = regime gate primaire (`V9_REGIME_GATE_ENABLED=0`),
   B = CVaR sizing institutionnel (`V9_KELLY_CVAR_ENABLED=0`),
   C = CVD tick-level MT4 (`V9_CVD_ENABLED=0`).
2. **Notifier Telegram dynamique** livré, commit `66bca85` (~21h30 UTC) :
   system prompt remplacé par `_format_system_state_prompt()` (état réel),
   `_route_data_intent()` mapping intention → slash commande, `reply_markup`
   (claviers inline). Tests : 12/12 verts (`test_telegram_notifier_interactive.py`).
3. **Refresh `data/strategy_pole/`** (auto-calibrator post-commit) :
   commit `a4acfac` (~21h35 UTC) — métadonnées `last_updated`/`generated_at`.
4. **Prompt Opus audit edgefund** livré (motion §17h45 du brief « lis tous les
   documents pour le contexte, fait le bilan et propose pour opus un audit
   complet pour optimisation edgefund ») :
   `workspace/perplexity/PROMPT_OPUS_AUDIT_EDGEFUND_20260718.md`. **Statut :
   À VALIDER motion CEO avant lancement.** Ne s'auto-exécute pas.

### État actuel (2026-07-18 ~23:25 UTC)

| Action | Statut | Qui | Détail |
|--------|--------|-----|--------|
| Chantiers A/B/C (regime/CVaR/CVD) | ✅ Poussé `fbca486` | Opus | kill switches OFF défaut, 41 tests verts |
| Notifier dynamique + prompt Opus | ✅ Poussé `66bca85` | Hermes | 12 tests verts interactif Telegram |
| Refresh data/strategy_pole | ✅ Poussé `a4acfac` | Hermes | chore, métadonnées uniquement |
| Audit working tree anti-régression | ✅ Clean | Hermes | grep `execution_enabled|circuit_breakers` → 2 matches lecture seule sur statut |
| Push origin | ✅ À jour | Hermes | `a4acfac` sur `feat/v9-foundation-clean` |
| Sync docs (AUTO:STATE) | ✅ Fait | Hermes | 23:24 UTC, 3 fichiers régénérés (STATE/CACHE_BOARD/AGENT.md) |
| Notifier prompt Opus à lancer | ⏸ En attente | CEO | motion §17h45 « valide lancement » → audit hedge fund |

### Périmètre Hermes (cette session)
- ✅ Push initial (motion CEO §17h15 « go r28 » = push direct)
- ✅ Audit working tree pré-push (R28)
- ✅ Sync docs (`v9_sync_state.py`, run réel)
- 🔄 Entrées DECISIONS_LOG §2026-07-18 « Notifier dynamique » (R26 rattrapage)
- 🔄 BOARD.md resync (était bloqué à 14h18 CEST, capture server mort ce matin)

### Périmètre ZCode (session parallèle Opus)
- Chantiers A/B/C livrés (commit `fbca486`)

### Périmètre Claude Code (Opus direct)
- Chantiers A/B/C — implémentation + tests + COMMIT_REF=`fbca486`

### Périmètre gelé (inchangé)
- Phase 10 (fédération agents) — gel
- Phase 12 (exécution réelle) — interdit fondateur
- Exécution prompts auto — CEO explicite avant tout déclenchement

### Référence
- Dernier commit distant : `a4acfac` (refresh data/strategy_pole)
- HEAD origin : `feat/v9-foundation-clean` à jour
- Tests : **non re-canon** ce sync (run complet ~7 min, hors scope rapide)
- DECISIONS_LOG : entrée notifier dynamique à ajouter (R26 rattrapage session)
- Motion CEO §17h45 = « reformuler en exploitant pleinement » +
  « prompt puissant [...] je copie colle » + « c'est une autre philosophie » +
  « go et continue » (mode AUTO-PILOTE, périmètre autorisé : notifier + prompt Opus)

### Anti-régression commit `66bca85`
- Grep `execution_enabled|MAX_OPEN_TRADES|circuit_breakers|SIMULATION` :
  2 hits lecture seule sur `ks.execution_enabled` dans l'affichage statut
  du notifier. **Aucune activation.**
- Aucun fichier `core/v9/*` modifié.
- Aucun YAML modifié.
- Doctrina R2 (additif) respectée.

**Périmètre ZCode** (cette session parallèle) :
- SHADOW-EXPAND (en cours)
- Mise à jour ACTIVE_TASKS.md + BOARD.md (sa copie si besoin)
- Tests → commit → push (R28 motion CEO implicite « push et donne plan d'action »)

**Périmètre Hermes** (cette session) :
- ✅ P0+P1+P2 resync faits (commit `f94d2a9`)
- ✅ Boucle apprentissage activée (cron installé, 2 propositions générées)
- 🔄 P3-CONSUME-EXTEND — livraison prochaine (6-10h, 26 principes)
- Aligner COORDINATION_NOTE.md à chaque jalon pour ZCode

### Références
- Dernier commit distant : `2249fd9` (Phase 14.2 livraison, 15/07 ~05:50 UTC)
- Session §4 2026-07-15 : Phase 14.2 (cache TTL + bornes asymetriques + switch ON par defaut)
- Avant : `b2a6842` (note push §3)
- Avant : `f4e1798` (docs §2.1-2.5 arbitrage learning_loop + clôture P3-CONSUME-EXTEND)
- Avant : `ac26c3a` (priorité 3 14/07 — WIRE ON + dashboard HITL + shadow evaluateur)
- Avant : `01c2b9d` (P3-CONSUME-EXTEND COMPLET, Hermes)
- Avant : `f13c10f` (groupe 1 node_rule) / `eb1e7b9` (groupe 2 birth/break)
- Avant : `f94d2a9` (resync 18:25)
- Avant : `149f3b0` (7e MCP server)
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
- Tests baseline : **1344 verts + 1 skipped + 0 fail** (2:46, baseline 1330 + 14 Phase 14.2)


---

## 2026-07-15 ~16:25 UTC — Resync Hermes audit exécution

**Contexte** : Søn motion « vous gérer cela pas moi » 15/07. ZCode en
parallèle (events bus zcode:* actifs). Hermes audite working tree
post-commit `25c182f`, découvre livraison EXECUTION non autorisée.

**Livré par Hermes cette session** (5 commits atomiques) :
- `101a236` chore(v9): archive Phase 13 scripts batch resolve + tests
- `176b0d7` feat(v9): infra R28 — agent_bus_bridge + MCP stdio runtime + CLI bus
- `5222d00` feat(v9): paper-trade trade_engine + supervisor --paper-trade + orchestrator hook
- `7b74626` refactor(v9): MCP servers → stdio_runtime + telegram notifier résilient
- `015a814` chore(v9): resync AUTO:STATE + gitignore cleanup + session_startup hook

**HEAD** : `015a814` (up-to-date origin)

**Tests** : 1340 verts + 1 skip + 0 fail (baseline stable).

**Alertes CEO requises** :
1. Working tree contenait livraison EXECUTION réelle non autorisée →
   **ROLLBACK effectué** (4 fichiers core/v9/ + 2 reports + 2 scripts).
   Action manuelle requise sur `config/v9_kill_switches.env` (gitignoré,
   contient encore `V9_EXECUTION_ENABLED=1`).
2. Commit ZCode `f5eacdc` D-QL5 (R28 ouverte multi-agents) poussé
   unilateralement. Hermes a pull-rebasé sans rollback (motion CEO
   présumée). **CEO validation/rejet explicite requis**.

**Mémoriser** : pour les prochaines sessions, **AUDIT working tree
systématique** avant commit (le sale peut dormir entre sessions).

### Périmètre Hermes mis à jour cette session
- ✅ Audit + rollback exécution non autorisée (sauvegarde doctrine)
- ✅ Commit paper-trade trade_engine legitime (Phase 9.7+)
- ✅ Infra R28 (bus bridge + stdio runtime + CLI)
- ✅ Refacto MCP servers (stdio_runtime unifié)
- ✅ Resync docs AUTO:STATE au HEAD
- 🔄 COORDINATION_NOTE update (en cours)

### Périmètre ZCode (session parallèle)
- SHADOW-EXPAND (en cours, sa session)
- D-QL5 motion CEO (poussé `f5eacdc`, à valider par Søn)
