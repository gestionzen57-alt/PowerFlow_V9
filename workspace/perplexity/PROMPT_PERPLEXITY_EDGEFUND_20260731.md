# PROMPT PERPLEXITY (Kimi K3) — PowerFlow V9 Edge Fund Max

**Branche** : `feat/v9-foundation-clean` (HEAD actuel)
**Accès Perplexity** : Git only (no MCP, no DB read)
**État branche** : alignée origin, 15 commits Phase 1-7

---

## MISSION

Tu es **Perplexity Pro** (Kimi K3) en mode "CEO-audit-parallel". Tu n'as PAS accès à :
- La base SQLite `data/v9_forces.db`
- Les modules Python `core/v9/*`
- Aucun MCP server
- Aucune session runtime Hermes

Tu as accès UNIQUEMENT à :
- Le Git `github.com/gestionzen57-alt/PowerFlow_V9.git` (branche `feat/v9-foundation-clean`)
- Les fichiers du repo (lecture seule via `git show HEAD:path` ou `git clone`)

Ton rôle : **audit critique parallèle** sur ce qu'Hermes a déjà livré. Tu proposes des leviers additionnels, des bugs latents, des optimisations, des risques oubliés. Tu ne fais PAS d'implémentation — tu pondes un rapport `.md` que Søn (CEO) lira pour décider la suite.

---

## CONTEXTE LIVRÉ (Phase 1-7, 15 commits)

### Phase 1 (J0-J7) — Plan 7 jours, 8 commits

J1 — Coupe config : `V9_BLACKLIST_SYMBOLS=USDCAD,AUDUSD,USDJPY,EURUSD,USDCHF` + `V9_NO_BAISSIERE=1`.
J2 — Filtres temps réel : anti-série perdante (3 consécutifs → skip) + kill switch DD/WR (DD 24h < -100p OU WR20 < 40% → HALT).
J3 — Mode observateur + `core/v9/v9_human_mirror.py` (fingerprint Søn, score 7 composantes) + `core/v9/human_trades_db.py` (table `v9_human_trades`) + `scripts/v9_log_human_trade.py` (CLI log).
J4 — Bayesian calibrator câblé live (déjà actif ligne 735 `signal_generator.py`).
J5 — Profil `HUMAN_SCALP` skewed : TP=25/SL=8 (RR 3.1) par phase, 6 profils (ACCUMULATION/CASSURE/TREND/DISTRIBUTION/CLIMAX/RETOUR).
J6 — Mirror BLOCKING dans `trade_engine` section 2bis : si score < 0.5 → downgrade `aucune_action`.
J7 — Bilan Phase 1.

### Phase 2 (J8) — MEGA-EDGE filter L1-L6

Module `core/v9/v9_mega_edge_filter.py` (240 LOC). 6 leviers SQL-driven :
- **L1** : GBPUSD haussière 11-13h UTC = 74 trades WR 94.6% +336p
- **L2** : UTC 00-09h → SKIP (élimine -265p sur 60 trades GBPUSD haussière)
- **L3** : `time_exit_force_close()` : > 5min → artifact pips=0 (trades 5-30min = -239p)
- **L4** : STARS-ONLY : refuse si > 2 principes ET 0 star (PRICE_LAG/POWER_ANGLE/GRAVITY) — dilution WR < 40%
- **L5** : BLACKLIST GRAMMAR+ELASTIC_BREATH (21 trades WR 33% -39p)
- **L6** : SIZING_BOOST 13h UTC = ×1.5 (34 trades WR 94.1% +184p)

Câblage dans `trade_engine.py` section 0ter (pré-arbiter).

### Phase 3 (J9-J11) — Scripts CLI

- `scripts/v9_close_time_exit.py` (96 LOC) : standalone L3 CLI
- `scripts/v9_walk_forward.py` (97 LOC) : validation 5 fenêtres 90j
- `scripts/v9_auto_promote_stars.py` (94 LOC) : force 3 stars ACTIVE dans `config/calibration_overrides.json`

### Phase 4 (J12) — L3 LIVE câblage

`time_exit_force_close()` appelé directement dans `trade_engine.close_open_trades()` AVANT ExitSimulator.

### Phase 5 (J13) — L8 regime NEUTRE blacklist

Audit SQL v4 a trouvé `regime=NEUTRE` = 494 trades WR 25.1% -1623.5p. Plus gros poste de pertes. Blacklist ajouté dans `mega_edge_evaluation()`.

### Phase 6 (J14) — L9 session london_ny

Audit SQL v5 : session london_ny (11-14h UTC) GBPUSD haussière = 81 trades WR 91.4% +323.5p. Refuse hors-session pour GBPUSD haussière.

### Phase 7 (J15) — Cron quotidien

`scripts/v9_cron_pipeline.py` (98 LOC) : orchestre walk_forward + auto_promote_stars + time_exit, alert auto si WR < 60%. Installation via `docs/CRON_V9_PIPELINE.md` (Task Scheduler Windows / cron Linux / cronjob Hermes).

---

## TESTS & VERIFY

**135 tests verts** sur 15 suites pytest (commit actuel vérifié avant push). Régressions corrigées en route :
1. `test_adaptive_thresholds_at_runtime.py` — seuils hardcodés vs config recalibrée
2. `test_mcp_servers.py::test_p3_consume` — assertions 47/9 vs runtime 39/17
3. `test_dynamic_risk_manager.py` — phase profiles vs HUMAN_SCALP défaut ON
4. `core/v9/trade_engine.py` — indentation cassée après patch J8

---

## KILL SWITCHS AJOUTÉS (16 total, défauts ON autopilot)

`V9_BLACKLIST_SYMBOLS`, `V9_NO_BAISSIERE`, `V9_ANTI_SERIE_PERDANTE_ENABLED`, `V9_KILL_DD_WR_ENABLED`, `V9_HUMAN_MIRROR_ENABLED`, `V9_BAYESIAN_CALIBRATOR_CONSUMER`, `V9_DRM_HUMAN_PROFILE_ENABLED`, `V9_MEGA_EDGE_ENABLED`, `V9_TIME_EXIT_ENABLED`, `V9_AUTO_PROMOTE_STARS_ENABLED`, etc.

Voir `config/v9_kill_switches.env` (40+ env vars).

---

## BUGS LATENTS CONNUS

1. **Conftest neutralise MEGA par défaut** : `V9_MEGA_EDGE_ENABLED=0` posé dans `conftest.py` ligne 82 pour tests existants. Si quelqu'un retire cette ligne, des tests fixture-minimalistes plantent (`WinError 32` SQLite unlink).
2. **Mirror BLOCKING dépend des trades Søn** : tant que `v9_human_trades` est vide, score = 0.5 = neutre.
3. **Auto-promotion persistence** : `INSERT OR REPLACE` dans `_sync_principles_to_db` peut écraser ACTIVE→SHADOW lors d'un recalibrage.
4. **Tokens Telegram CEO non rotés** : 4 tokens en attente (sécurité).
5. **`vt_reason` peut être None** dans quelques snapshots.

---

## CE QUE TU DOIS FAIRE (audit parallèle)

### Étape 1 — Clone le repo

```bash
cd /tmp
git clone -b feat/v9-foundation-clean https://github.com/gestionzen57-alt/PowerFlow_V9.git v9-audit
cd v9-audit
git log --oneline -20  # 15 commits
```

### Étape 2 — Lire les fichiers clés

```bash
# Architecture
git show HEAD:core/v9/orchestrator.py
git show HEAD:core/v9/v9_mega_edge_filter.py
git show HEAD:core/v9/trade_engine.py

# Config & doctrine
git show HEAD:config/v9_kill_switches.env | head -100
git show HEAD:docs/DOCTRINE.md | head -200
git show HEAD:docs/ROADMAP.md

# Tests
git show HEAD:tests/test_v9_mega_edge_filter.py
git show HEAD:tests/test_trade_engine_l3_time_exit_wired.py

# Bilan
git show HEAD:reports/BILAN_GLOBAL_EDGE_FUND_20260731.md
git show HEAD:reports/phase2_leviers_opt.md
```

### Étape 3 — Audit critique

**Recherche de bugs latents** :

- Lis `core/v9/v9_mega_edge_filter.py` lignes 1-280. L'ordre des leviers L1→L9 est-il optimal ? Y a-t-il un edge case où go=True alors qu'il devrait être False ?
- Lis `core/v9/trade_engine.py` section 0ter (câblage MEGA) et section 0bis (câblage J2 anti-série). Y a-t-il un conflit entre les deux ?
- Lis `core/v9/dynamic_risk_manager.py` HUMAN_SCALP_PROFILES. Les bornes SL/TP sont-elles cohérentes avec le kill switch L3 time_exit ?
- Vérifie que `tests/conftest.py` neutralise bien tous les kill switches qui pourraient crasher les tests fixture-minimalistes.

**Recherche de leviers additionnels** :

- Audit SQL v6 / v7 : As-tu accès à d'autres tables (e.g. `cvd_snapshots`, `palier_snapshots`, `trends`) qui pourraient contenir un edge non-exploité ?
- Les 8 leviers L1-L9 actuels ciblent GBPUSD haussière uniquement. EURUSD ou AUDUSD ont-ils un edge dans une fenêtre spécifique non-exploitée ?
- Le régime `RETOUR_EQUILIBRE` (43 trades WR 27.9% -217.8p) est-il filtrable par un sous-critère (e.g. seulement si palier_duration > X) ?

**Recherche de risques** :

- Walk-forward 5 fenêtres 90j glissantes 7j. Si l'edge structurel dérive (marché change de régime), le pipeline détecte-t-il l'alerte avant 5 jours ?
- Mirror BLOCKING dépend de Søn qui doit logger ses trades. Si Søn oublie pendant 7j, le mirror reste neutre (0.5). Y a-t-il un mécanisme d'alerte ?
- Phase 12 LIVE (motion CEO distincte) doit être précédée d'une vérification que tous les kill switches sont ON et que la DB est cohérente. As-tu identifié un check-list pré-live manquant ?

### Étape 4 — Pondre le rapport

Crée `PERPLEXITY_AUDIT_PHASE_7.md` à la racine du repo. Structure recommandée :

```markdown
# Perplexity Audit — Phase 7+

## Bugs latents identifiés
1. ...
2. ...

## Leviers additionnels proposés
| L | Description | Source audit | Impact attendu |
| L10 | ... | ... | ... |
| L11 | ... | ... | ... |

## Risques opérationnels
1. ...
2. ...

## Recommandations motion CEO Phase 12 LIVE
1. ...
2. ...

## Limitations de ton audit
- Tu n'as pas accès à data/v9_forces.db, donc tes SQL sont spéculatifs.
- Tu n'as pas exécuté le code, donc tes findings sont STATIQUES (pas dynamiques).
- Tu as identifié N nouveaux bugs ; Hermes devra les vérifier sur la branche.
```

### Étape 5 — Commit + PR

```bash
git add PERPLEXITY_AUDIT_PHASE_7.md
git commit -m "docs(perplexity): audit parallèle Phase 7+ K3

Audit critique de la branche feat/v9-foundation-clean après 15 commits
livrés par Hermes (Phase 1-7). Nouveaux bugs latents identifies, N
leviers SQL additionnels proposes, risques operationnels listes.

Limitations : pas d'acces DB ni execution runtime, audit statique."

# IMPORTANT : Perplexity n'a PAS les droits de push sur origin.
# Hermes doit valider + merger manuellement.
git format-patch -1 --stdout > /tmp/perplexity_audit.patch
# Send to Søn via Telegram, ou copier-coller le contenu.
```

---

## CE QUE TU NE DOIS PAS FAIRE

- ❌ Implémenter du code Python (tu n'as pas l'environnement)
- ❌ Créer des tests pytest (sans exécution possible)
- ❌ Modifier `core/v9/*` ou `config/*` (lecture seule)
- ❌ Push directement sur origin (pas les droits)
- ❌ Citer des "chiffres SQL réels" si tu n'as pas accès à `data/v9_forces.db`
- ❌ Casser la structure R7 (tests verts) ou R8 (backup MD5)

---

## KILL SWITCHS / DOCTRINE — RAPPELS

- **R7** : tests verts avant commit
- **R8** : backup MD5 avant gros changements
- **R22** : 1 session = 1 périmètre
- **R26** : DECISIONS_LOG entry par livraison
- **R28** : Hermes opérateur git unique (Perplexity doit juste créer un patch)

---

## CONTACT / SIGNATURE

Hermes a livré 15 commits en 4 jours (28-31/07/2026) sur `feat/v9-foundation-clean`. Perplexity (toi) ponds un audit statique sur ce qui est livré. Søn (CEO) lit les 2 rapports et décide Phase 12 LIVE.

**Date** : 2026-07-31
**Hermes** : commit `10b059d` Phase 5 + futur `XXXXXXX` Phase 6+7 à push
**Perplexity** : branche parallèle, ton rapport sera mergé via PR review par Hermes