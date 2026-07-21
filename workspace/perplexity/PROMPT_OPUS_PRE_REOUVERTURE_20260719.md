# PROMPT OPUS — Pré-réouverture 2026-07-19 §23h UTC

> **Destinataire** : Claude Code Opus (ou Sonnet à défaut), lecture initiale
> **Émetteur** : Søn CEO + ZCode
> **Date d'envoi** : 2026-07-19 10:05 UTC
> **Date butoir** : 2026-07-19 22:00 UTC (réouverture effective marché forex en DST US)
> **Doctrine** : R2 additif · R6 défensif · R7 tests verts · R8 doc · R14 Git vérité · R18 code pur · R22 1 périmètre = 1 livraison · R23 principes YAML · R26 DECISIONS_LOG · R28 Hermes push · R30 boucle fermée
> **Mode** : Code + commit, **zéro motion CEO requise** pour ce qui est dans le périmètre (motion antérieure « oui go full audit 8 axes » + « Construis le watchdog maintenant » + « révoque les 4 tokens via @BotFather » reste à faire par Søn). Tu ne push que via Hermes en fin de session (R28).

---

## 0. Mission en une phrase

Avant la réouverture forex de ce soir 23h UTC (effective ~22h UTC DST US), **livrer 3 corrections ciblées** pour transformer le prototype `v9_live_watchdog.py` (déjà committé en `85d7113`) en un **filet de sécurité live opérationnel**, et **déployer 2 crons manquants** pour que la machine tourne vraiment surveillée. Tout le reste est **HORS PÉRIMÈTRE** (R22 strict). Tu ne traites pas les axes 1, 2, 3, 5, 7 de l'audit — ils sont déjà livrés ou délégués CEO. Tu ne modifies ni `trade_engine.py` ni `config.py` sauf strictement nécessaire (préférer wrappers).

---

## 1. Contexte hérité — ce que tu n'as pas à refaire

### 1.1 État au démarrage
- **HEAD** : `dcd2fed` sur `feat/v9-foundation-clean` (le tien après ce prompt sera probablement `dcd2fed` + 1 à 3 commits)
- **Working tree** : 4 fichiers `data/strategy_pole/*.json` modifiés par l'auto-calibrateur (à NE PAS toucher, ce sont des artefacts — ne jamais `git add data/strategy_pole/`)
- **Tests baseline** : `2270 passed / 10 failed préexistants / 3 skipped` (fails = 5 baissier_audit + 2 mcp_servers + 1 telegram + 2 trade_engine_long_only, **documentés hors périmètre** — ne pas les considérer comme des régressions)
- **DB** : `data/v9_forces.db` (~2.61 GB, 25 tables)
- **Marché** : actuellement FERMÉ (sam après 21h UTC). Réouverture ~22h UTC dimanche 19/07.
- **Session Opus précédente** : audit edgefund 8 axes, 6 documents livrés, 1 module watchdog créé (`85d7113`)

### 1.2 Fichiers que tu dois connaître intimement (lis-les en intégralité)
- `core/v9/v9_live_watchdog.py` (256 LOC) — module créé, mais **5 défauts majeurs** listés en §2
- `core/v9/v9_loop_breaker.py` (340 LOC) — fonctionne, mais **lit `os.environ` au lieu de `core.v9.kill_switches`** ⚠️ cause du P0.4
- `core/v9/kill_switches.py` (115 LOC) — chargeur central qui lit `config/v9_kill_switches.env`
- `config/v9_kill_switches.env` (178 lignes) — source de vérité runtime
- `scripts/v9_load_kill_switches.py` (78 LOC) — wrapper qui charge le `.env` puis exec
- `scripts/v9_supervisor.py` — le process réel que `V9_PaperTradeLoop` lance (sans wrapper = sans kill switches !)
- `scripts/v9_paper_trade_run.py` — entry point du paper-trade loop

### 1.3 P0 confirmés par l'audit exhaustif
- **P0.1** : 4 tokens Telegram exposés (`8656…`, `8790…`, `8932…`, `8948…`) — **action CEO**, pas toi
- **P0.2** : Watchdog sans appelant, sans cron, sans alerte, sans arrêt
- **P0.3** : Action critique recommandée par le watchdog = `V9_GBPUSD_LONG_ONLY=0` (DÉSACTIVE le garde, pas un arrêt !)
- **P0.4** : Modules critiques lisent `os.environ` au lieu de `kill_switches.py` (P0.4 silencieux)
- **P0.5** : Tâches Windows en échec (PaperTradeLoop, StrategyPoleRecompute, HeartbeatCheck, HeartbeatAlert)

---

## 2. Périmètre EXACT de cette livraison (3 chantiers, R22 strict)

### CHANTIER A — Watchdog opérationnel (5 correctifs + runner)

#### A.1 Corriger les défauts du module `core/v9/v9_live_watchdog.py`

**Modifier le fichier existant** (ne pas créer de nouveau module — R2 additif sur l'existant). Toutes les modifications sont rétro-compatibles : les 12 tests existants doivent continuer à passer (avec ajustement éventuel de `test_health_critical_wr` ligne 138 qui assert `V9_GBPUSD_LONG_ONLY=0` in actions → ce test devra être remplacé par un test vérifiant le VRAI switch d'arrêt).

**5 corrections** :

1. **Action P0 = arrêt réel** : remplacer `V9_GBPUSD_LONG_ONLY=0` (interdit) par un **vrai switch d'arrêt du paper-trading**. Créer un nouveau kill switch `V9_PAPER_TRADE_HALT=1` dans `config/v9_kill_switches.env.example` ET dans `core/v9/kill_switches.py` (ajouter `paper_trade_halt_enabled()`). Quand le watchdog détecte critique, il recommande `V9_PAPER_TRADE_HALT=1` + `V9_NO_BAISSIERE=1` (renforcement, pas relâche). Et il **NE TOUCHE PAS** `V9_GBPUSD_LONG_ONLY`.

2. **Read-only strict SQLite** : remplacer `sqlite3.connect(str(db_path))` par `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` dans `_fetch_recent_trades` ET `_fetch_dd_24h`. Gérer `sqlite3.OperationalError` « attempt to write a readonly database » proprement (retourner `db_error`).

3. **Segmenter le WR par (symbol, direction)** : au lieu d'aggréger les 50 derniers trades, **filtrer** par :
   - `symbol='GBPUSD' AND direction='haussiere'` (scénario de la motion long-only) — c'est le focus
   - les autres paires/directions = log uniquement, pas de verdict
   - Renommer `wr_recent` → `wr_long_only_gbpusd` pour transparence
   - Si moins de 10 trades GBPUSD long → `no_data` (pas d'alerte)

4. **Renommer `dd_24h_pips` → `net_pnl_24h_pips`** (c'est un P&L net, pas un drawdown — c'est une faute de métrique). Garder le calcul identique. Update `to_dict()`. Update les 2 tests qui assertent `d.dd_24h_pips` (T3, T6) pour utiliser `d.net_pnl_24h_pips`.

5. **Distinguer `db_error` de `no_data`** : si la DB est absente, introuvable, schema incompatible, ou si la requête échoue pour une raison autre que `no rows`, retourner `status="db_error"` (et non `no_data`). Un db_error doit **toujours** générer une alerte `p0` (télémétrie muette = danger). Ajouter 2 tests : `test_db_missing_schema`, `test_db_locked`.

**Tests à ajouter** (`tests/test_v9_live_watchdog.py`, total doit passer de 12 à ~18) :
- `test_health_p0_does_not_disable_long_only` : assert que la reco P0 ne contient PAS `V9_GBPUSD_LONG_ONLY=0`
- `test_health_p0_recommends_paper_trade_halt` : assert que la reco P0 contient `V9_PAPER_TRADE_HALT=1`
- `test_health_segmented_long_only` : DB avec 50 trades mix → WR global différent du WR GBPUSD long only, et seul ce dernier compte
- `test_db_locked_returns_error` : DB ouverte en écriture exclusive par un autre process → `db_error`
- `test_no_long_only_trades_returns_no_data` : 50 trades shorts uniquement → `no_data`, pas de verdict
- `test_readonly_connection_uri` : la connexion passe par `?mode=ro` (tester en monkeypatchant `sqlite3.connect` et en vérifiant l'URI)

#### A.2 Créer le runner `scripts/v9_live_watchdog_run.py`

**Nouveau fichier** (~120 LOC). Script standalone, pas un module :
- Args : `--db-path` (défaut `data/v9_forces.db`), `--json` (sortie structurée), `--exit-code` (retourne 0=ok, 1=warn, 2=critical, 3=db_error, 4=disabled)
- Charge `V9_LIVE_WATCHDOG_ENABLED` depuis `core.v9.kill_switches` (PAS os.environ)
- Appelle `check_health()`
- Écrit log structuré dans `logs/v9_live_watchdog.log` (append, JSON lines)
- Si `alert_level` != "none" et `--alert-telegram` est passé, envoie Telegram via `mcp__v9-telegram__send_alert` (avec import try/except pour ne pas crasher si MCP non dispo en CLI)
- Si `recommended_actions` non vide et `--apply-recommendations` est passé, **append** les actions au `.env` (avec backup `config/v9_kill_switches.env.bak.<timestamp>`). Mais JAMAIS `V9_GBPUSD_LONG_ONLY=0` (blacklist).
- Sortie JSON : `{"timestamp": ..., "status": ..., "net_pnl_24h_pips": ..., "wr_long_only_gbpusd": ..., "n_recent": ..., "triggered": [...], "recommended_actions": [...], "alert_level": ...}`

**Tests** `tests/test_v9_live_watchdog_run.py` (~6 tests) :
- `test_exit_code_mapping` : disabled=4, ok=0, warn=1, critical=2, db_error=3
- `test_json_output` : sortie contient les champs requis
- `test_apply_recommendations_writes_env` : avec `--apply-recommendations`, le fichier `.env` est mis à jour + backup créé
- `test_apply_recommendations_blacklists_long_only` : passer une reco contenant `V9_GBPUSD_LONG_ONLY=0` ne doit PAS l'écrire (blacklist safety)
- `test_no_alert_when_disabled` : si switch OFF, pas d'alerte Telegram
- `test_log_file_appended` : 2 runs successifs → 2 lignes JSON dans le log

#### A.3 Wire `core.v9.kill_switches.live_watchdog_enabled()`

Dans `core/v9/kill_switches.py`, **ajouter** (sans casser l'existant) :
```python
LIVE_WATCHDOG_ENABLED_ENV = "V9_LIVE_WATCHDOG_ENABLED"

def live_watchdog_enabled() -> bool:
    """Kill switch V9_LIVE_WATCHDOG_ENABLED (défaut OFF tant que pas motion CEO explicite)."""
    return is_enabled(LIVE_WATCHDOG_ENABLED_ENV)

def paper_trade_halt_enabled() -> bool:
    """V9_PAPER_TRADE_HALT — HALT TOTAL du paper-trading (R6 fail-safe).
    Défaut OFF. Quand ON, le moteur de paper-trade ne doit rien ouvrir.
    Action de niveau P0 recommandée par le watchdog critique.
    """
    return is_enabled("V9_PAPER_TRADE_HALT")
```

Et dans `core/v9/v9_live_watchdog.py`, remplacer :
```python
def live_watchdog_enabled() -> bool:
    return os.environ.get(LIVE_WATCHDOG_ENABLED_ENV, "0") in ("1", "true", "True")
```
par :
```python
def live_watchdog_enabled() -> bool:
    try:
        from core.v9.kill_switches import live_watchdog_enabled as _ks
        return _ks()
    except Exception:
        return os.environ.get(LIVE_WATCHDOG_ENABLED_ENV, "0") in ("1", "true", "True")
```

Idem pour `v9_loop_breaker.py` ligne 81-84 : remplacer la lecture `os.environ` par un import `from core.v9.kill_switches import loop_breaker_enabled as _ks_ks` (ou ajouter `loop_breaker_enabled()` dans kill_switches.py et l'utiliser). **Priorité** : ne pas casser le test `test_loop_breaker_disabled` qui assert `allowed=True` quand switch off.

### CHANTIER B — Câblage kill switches runtime (P0.4)

#### B.1 Corriger `v9_loop_breaker.py` (cause du P0.4)

Remplacer ligne 81-84 :
```python
def loop_breaker_enabled() -> bool:
    val = os.environ.get(LOOP_BREAKER_ENABLED_ENV, "0")
    return val in ("1", "true", "True")
```

par (ajout d'une fonction `loop_breaker_enabled` dans `core/v9/kill_switches.py` qui appelle `is_enabled("V9_LOOP_BREAKER_ENABLED")`, puis import) :

```python
def loop_breaker_enabled() -> bool:
    """Lecture défensive : kill_switches d'abord, fallback os.environ."""
    try:
        from core.v9.kill_switches import loop_breaker_enabled as _ks
        return _ks()
    except Exception:
        val = os.environ.get(LOOP_BREAKER_ENABLED_ENV, "0")
        return val in ("1", "true", "True")
```

Et ajouter dans `core/v9/kill_switches.py` :
```python
LOOP_BREAKER_ENABLED_ENV = "V9_LOOP_BREAKER_ENABLED"

def loop_breaker_enabled() -> bool:
    return is_enabled(LOOP_BREAKER_ENABLED_ENV)
```

#### B.2 Ajouter l'entrée `V9_LIVE_WATCHDOG_ENABLED=0` dans `config/v9_kill_switches.env`

Append (en fin de fichier, après le bloc HITL) :
```bash
# === Live Watchdog (commit 85d7113 + corrections 2026-07-19) ===
# Kill switch principal du watchdog live. Défaut OFF tant que pas motion CEO
# explicite. Quand ON, scripts/v9_live_watchdog_run.py peut être appelé par
# V9_LiveWatchdogLoop (cron dédié) sans modifier de code.
# Action P0 = recommandation V9_PAPER_TRADE_HALT=1 (R6 fail-safe).
V9_LIVE_WATCHDOG_ENABLED=1
V9_PAPER_TRADE_HALT=0
V9_WATCHDOG_DD_24H_PIPS=-200
V9_WATCHDOG_WR_WINDOW=50
V9_WATCHDOG_WR_WARN=0.80
V9_WATCHDOG_WR_CRIT=0.60
```

**Motion CEO implicite** : on active `V9_LIVE_WATCHDOG_ENABLED=1` ici, dans le cadre de la motion « Construis le watchdog maintenant » qui vaut mandat d'activation runtime. C'est une motion CEO explicite (audit edgefund 2026-07-19). **Tu peux le faire sans nouveau round**.

#### B.3 Script de déploiement `scripts/install_v9_live_watchdog_cron.bat`

**Nouveau fichier** (~30 LOC). Crée la tâche Windows `V9_LiveWatchdogLoop` qui lance le runner toutes les 5 minutes :
- Utilise `schtasks /Create /SC MINUTE /MO 5 /TN V9_LiveWatchdogLoop /TR ".venv\Scripts\python.exe -X utf8 scripts/v9_live_watchdog_run.py --alert-telegram --json" /RU SYSTEM /RL HIGHEST /F`
- `WorkingDirectory` = `C:\projet\V9`
- Vérifie que la tâche est créée (`schtasks /Query /TN V9_LiveWatchdogLoop`)
- Affiche le résultat

Idem `scripts/install_v9_paper_trade_loop_wrapper.bat` (~30 LOC) qui **remplace** la tâche `V9_PaperTradeLoop` actuelle par une version qui passe par `v9_load_kill_switches.py` :
- Backup de la tâche actuelle via `schtasks /Query /XML > backups/V9_PaperTradeLoop_original.xml`
- Delete + Recreate : `schtasks /Create /SC MINUTE /MO 5 /TN V9_PaperTradeLoop /TR ".venv\Scripts\python.exe -X utf8 scripts/v9_load_kill_switches.py -- scripts/v9_supervisor.py --paper-trade" /RU SYSTEM /RL HIGHEST /F`

**Tests** : ces 2 fichiers `.bat` ne sont pas testables en pytest, mais **doivent être validés** par un `bash` dry-run (parser la syntaxe) ou simplement lancés en mode `--dry-run` si tu implémentes ce flag.

### CHANTIER C — Documentation & trace session (R8, R26)

#### C.1 Créer `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`

**Nouveau fichier** (~80 LOC). Checklist HITL pour la réouverture de ce soir. Contenu obligatoire :
- Statut des 5 P0 (P0.1, P0.2, P0.3, P0.4, P0.5) avec ✅/⚠️/❌
- Procédure de rotation des 4 tokens (action CEO uniquement)
- Procédure d'installation des 2 nouvelles tâches Windows (avec commandes copy-paste)
- Smoke test post-install : `python scripts/v9_live_watchdog_run.py --once` doit retourner `status=ok` ou `status=no_data` (PAS critical, parce qu'on a moins de 10 trades GBPUSD long post-réouverture)
- Plan d'observation 24h : WR par heure, DD cumulé, alertes Telegram
- Critères de NO-GO post-réouverture (à documenter en append-only après 23h UTC)

#### C.2 Mettre à jour `docs/STATE.md` §Phase actuelle

Ajouter en haut de la phase actuelle (juste après le bloc « Session Claude Code 2026-07-18 — REGIME_GATE + CVaR + CVD ») :

```markdown
**Session Opus 2026-07-19 — Pré-réouverture 23h UTC (watchdog opérationnel + câblage kill switches) :**

Trois chantiers R22 strict (chantier A watchdog + chantier B kill switches + chantier C doc) :
- **A** : 5 corrections `v9_live_watchdog.py` (action P0 = `V9_PAPER_TRADE_HALT=1` au lieu de désactiver long-only, read-only URI, segmentation GBPUSD long, renommage `net_pnl_24h_pips`, distinction `db_error`) + runner `scripts/v9_live_watchdog_run.py` (CLI + JSON + exit code + Telegram optionnel) + wire `kill_switches.live_watchdog_enabled()`. ~12 → ~18 tests verts.
- **B** : `v9_loop_breaker.py` corrigé pour utiliser `core.v9.kill_switches` (P0.4 résolu) + entrée `V9_LIVE_WATCHDOG_ENABLED=1` dans `v9_kill_switches.env` (motion CEO « Construis le watchdog » interprétée comme activation runtime) + 2 scripts `.bat` d'installation des tâches `V9_LiveWatchdogLoop` (5min) et refit `V9_PaperTradeLoop` via wrapper.
- **C** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md` (checklist HITL) + maj `STATE.md` + entrée `DECISIONS_LOG.md`.
- **Hors périmètre** : 4 tokens (action CEO), 4 jours captés ≠ 12 jours (correction doc uniquement), propagation Active=44 vs 45 (fix doc), axes 1/2/3/5/7 audit (déjà livrés).
- **Tests** : baseline 2270/10/3 + 18 nouveaux watchdog = 2288 passed attendu (10 fails préexistants inchangés).
```

#### C.3 Entrée `workspace/perplexity/memory/DECISIONS_LOG.md`

Append (après l'entrée `2026-07-19 — Audit edgefund complet 8 axes (OPUS) — thèse renversée + watchdog live` existante) :

```markdown
### 2026-07-19 — Pré-réouverture §23h UTC (OPUS) — Watchdog opérationnel + câblage kill switches

- **Décision** : 3 chantiers R22 strict livrés avant réouverture forex 23h UTC. Motion CEO « Construis le watchdog maintenant » interprétée comme mandat d'activation runtime (`V9_LIVE_WATCHDOG_ENABLED=1`).
- **Chantier A (watchdog opérationnel)** : 5 défauts corrigés dans `core/v9/v9_live_watchdog.py` (action P0 = `V9_PAPER_TRADE_HALT=1` au lieu de `V9_GBPUSD_LONG_ONLY=0` qui ré-autorisait les shorts, read-only URI `mode=ro`, segmentation GBPUSD long only, `net_pnl_24h_pips` au lieu de `dd_24h_pips` qui était un P&L, distinction `db_error` vs `no_data`). Runner `scripts/v9_live_watchdog_run.py` créé (CLI, JSON, exit code 0-4, Telegram optionnel, log JSONL, `--apply-recommendations` avec blacklist long-only). Wire `kill_switches.live_watchdog_enabled()` + `paper_trade_halt_enabled()`. ~12 → ~18 tests verts.
- **Chantier B (kill switches runtime P0.4)** : `v9_loop_breaker.py` lit désormais `core.v9.kill_switches` (fallback `os.environ`). Entrée `V9_LIVE_WATCHDOG_ENABLED=1` + `V9_PAPER_TRADE_HALT=0` + 4 seuils watchdog dans `v9_kill_switches.env`. 2 scripts `.bat` d'install : `install_v9_live_watchdog_cron.bat` (5min), `install_v9_paper_trade_loop_wrapper.bat` (refit via `v9_load_kill_switches.py`).
- **Chantier C (doc)** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md` créé, `STATE.md` maj phase, présente entrée.
- **Impact** : `v9_live_watchdog.py` (5 modifs) + `v9_loop_breaker.py` (1 modif) + `kill_switches.py` (+2 fonctions) + `v9_kill_switches.env` (+6 lignes) + 1 nouveau runner + 1 nouveau test file + 2 nouveaux `.bat`. Aucun `trade_engine.py` ni `config.py` touché. Aucun YAML modifié. Aucune migration DB.
- **Référence** : `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`.
- **Action CEO seule** : rotation 4 tokens via @BotFather (`8656…`, `8790…`, `8932…`, `8948…`) avant 22h UTC.
```

---

## 3. Garde-fous stricts (HORS PÉRIMÈTRE)

**Tu ne fais AUCUNE des actions suivantes** (R22 strict) :
- ❌ Modifier `core/v9/trade_engine.py` (sauf si tu importes une fonction ; n'altère pas le flow)
- ❌ Modifier `core/v9/config.py`
- ❌ Toucher aux YAML principes
- ❌ Toucher aux data/strategy_pole/*.json (working tree sale mais légitime)
- ❌ Réécrire l'audit edgefund Axes 1, 2, 3, 5, 7 (déjà livrés)
- ❌ Migrations DB
- ❌ Activer `V9_GBPUSD_LONG_ONLY=0` (interdit, c'est le contraire d'un arrêt)
- ❌ Désactiver `V9_LOOP_BREAKER_ENABLED` ou `V9_NO_BAISSIERE`
- ❌ Pousser (push) — R28 : Hermes est l'unique push operator. Tu prépares, **Hermes pousse**.

Si tu détectes un P0 supplémentaire non listé en §1.3, **documente-le** dans `PRE_REOUVERTURE_CHECKLIST_20260719.md` section « P0 résiduels » et **ne le fixe pas** dans cette session. Motion CEO distincte requise.

---

## 4. Workflow étape par étape

### Étape 1 — Sanité base (5 min)
```bash
cd C:/projet/V9
git status              # doit montrer 4 fichiers data/strategy_pole/*.json modifiés
git log --oneline -5    # HEAD = dcd2fed
pytest tests/ -q --co   # doit collecter ~2283 tests
```

### Étape 2 — Lire les 7 fichiers pivants listés en §1.2

Tu dois les lire **en intégralité** avant de toucher au code. Pas de raccourci.

### Étape 3 — Chantier A.1 (corrections watchdog, ~45 min)
1. Modifier `core/v9/v9_live_watchdog.py` selon §2.A.1
2. Mettre à jour `tests/test_v9_live_watchdog.py` (les 12 tests existants + 6 nouveaux)
3. Lancer : `pytest tests/test_v9_live_watchdog.py -v` → 18 verts attendus

### Étape 4 — Chantier A.2 (runner, ~30 min)
1. Créer `scripts/v9_live_watchdog_run.py` (CLI)
2. Créer `tests/test_v9_live_watchdog_run.py` (6 tests)
3. Lancer : `pytest tests/test_v9_live_watchdog_run.py -v` → 6 verts attendus

### Étape 5 — Chantier A.3 (wire kill_switches, ~15 min)
1. Ajouter `live_watchdog_enabled()` + `paper_trade_halt_enabled()` + `loop_breaker_enabled()` dans `core/v9/kill_switches.py`
2. Mettre à jour `live_watchdog_enabled()` dans `v9_live_watchdog.py` (utiliser le kill_switches central)
3. Lancer : `pytest tests/ -q -k "watchdog or loop_breaker or kill_switches"` → tous verts

### Étape 6 — Chantier B.1 (corriger v9_loop_breaker, ~10 min)
1. Modifier `v9_loop_breaker.py` ligne 81-84 selon §2.B.1
2. Lancer : `pytest tests/test_v9_loop_breaker.py -v` → tous verts

### Étape 7 — Chantier B.2 (maj .env, ~5 min)
1. Appender le bloc `V9_LIVE_WATCHDOG_ENABLED=1...` à `config/v9_kill_switches.env`
2. Vérifier que `python -c "from core.v9.kill_switches import live_watchdog_enabled; print(live_watchdog_enabled())"` retourne `True`

### Étape 8 — Chantier B.3 (scripts .bat, ~15 min)
1. Créer `scripts/install_v9_live_watchdog_cron.bat`
2. Créer `scripts/install_v9_paper_trade_loop_wrapper.bat`
3. **NE PAS LES EXÉCUTER** (la session est sur la machine de dev, pas le VPS de prod) — mais vérifier qu'ils parsent (tu peux les ouvrir dans un parser BAT, ou simplement vérifier la syntaxe visuellement)

### Étape 9 — Chantier C (doc, ~20 min)
1. Créer `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`
2. Maj `docs/STATE.md` (ajouter le bloc session)
3. Append `DECISIONS_LOG.md`

### Étape 10 — Validation finale (10 min)
```bash
# Sanité globale
pytest tests/ -q                                    # 2288 passed, 10 failed (inchangés), 3 skipped
python scripts/v9_live_watchdog_run.py --json       # doit retourner status="disabled" ou "ok" selon état
python -c "from core.v9.kill_switches import live_watchdog_enabled, paper_trade_halt_enabled, loop_breaker_enabled; print(f'watchdog={live_watchdog_enabled()} halt={paper_trade_halt_enabled()} loop_breaker={loop_breaker_enabled()}')"
```

### Étape 11 — Commits atomiques (3 commits max, R26)
```bash
git add core/v9/v9_live_watchdog.py core/v9/v9_live_watchdog.py core/v9/kill_switches.py tests/test_v9_live_watchdog.py
git commit -m "feat(v9): watchdog opérationnel — P0 halted switch + read-only + segmentation GBPUSD long (motion §Construis le watchdog)"

git add scripts/v9_live_watchdog_run.py tests/test_v9_live_watchdog_run.py scripts/install_v9_live_watchdog_cron.bat scripts/install_v9_paper_trade_loop_wrapper.bat config/v9_kill_switches.env
git commit -m "feat(v9): runner watchdog CLI + 2 crons Windows + activation V9_LIVE_WATCHDOG_ENABLED (pré-réouverture §23h UTC)"

git add docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md docs/STATE.md workspace/perplexity/memory/DECISIONS_LOG.md core/v9/v9_loop_breaker.py
git commit -m "docs(v9): checklist pré-réouverture 19/07 §23h UTC + maj STATE/DECISIONS_LOG (P0.4 câblage kill switches résolu)"
```

### Étape 12 — Push
**TU NE PUSH PAS** (R28). Tu termines ta réponse avec :
```
[HERMES ACTION REQUIRED] 3 commits prêts sur feat/v9-foundation-clean :
- <sha1> feat(v9): watchdog opérationnel
- <sha2> feat(v9): runner + crons + activation
- <sha3> docs(v9): checklist + STATE + DECISIONS_LOG
Push via : git push origin feat/v9-foundation-clean
```

---

## 5. Critères de succès (definition of done)

| # | Critère | Mesure |
|---|---|---|
| 1 | Watchdog P0 ne touche plus à `V9_GBPUSD_LONG_ONLY=0` | `grep -r "V9_GBPUSD_LONG_ONLY=0" core/v9/v9_live_watchdog.py` → 0 résultat |
| 2 | Watchdog ouvre SQLite en `mode=ro` | `grep "mode=ro" core/v9/v9_live_watchdog.py` → 2 hits (fetch_recent + fetch_dd) |
| 3 | Watchdog segmente par (symbol, direction) | `grep "GBPUSD" core/v9/v9_live_watchdog.py` → au moins 3 hits (filtre SQL) |
| 4 | Runner CLI existe et retourne JSON | `python scripts/v9_live_watchdog_run.py --json` → JSON valide |
| 5 | `v9_loop_breaker.py` lit `kill_switches` | `grep -n "os.environ" core/v9/v9_loop_breaker.py` → 0 hit (ou uniquement dans fallback) |
| 6 | `V9_LIVE_WATCHDOG_ENABLED=1` dans le .env | `grep "V9_LIVE_WATCHDOG_ENABLED=1" config/v9_kill_switches.env` → 1 hit |
| 7 | Tests verts : 18 watchdog + 6 runner | `pytest tests/test_v9_live_watchdog.py tests/test_v9_live_watchdog_run.py -q` → 24 passed |
| 8 | Baseline non régressée | `pytest tests/ -q` → 2288 passed / 10 failed / 3 skipped (mêmes 10 fails préexistants) |
| 9 | Checklist existe | `ls docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md` |
| 10 | STATE.md maj | `grep "Pré-réouverture §23h UTC" docs/STATE.md` → 1 hit |
| 11 | DECISIONS_LOG maj | `grep "Pré-réouverture §23h UTC" workspace/perplexity/memory/DECISIONS_LOG.md` → 1 hit |
| 12 | 3 commits atomiques | `git log --oneline HEAD~3..HEAD` → 3 commits avec messages conformes |

Si un critère échoue, **ne commit pas** tant que c'est rouge.

---

## 6. Communication finale (à mettre dans ta dernière réponse)

```
✅ Session pré-réouverture §23h UTC — terminée

Commits préparés (R28, push via Hermes) :
- <sha1> watchdog opérationnel (chantier A)
- <sha2> runner + crons + activation (chantier B)
- <sha3> docs + STATE + DECISIONS_LOG (chantier C)

Tests : <N> passed, baseline préservée (10 fails préexistants inchangés)

🔴 Actions CEO avant 22h UTC (irréversibles / externes) :
1. Rotation 4 tokens Telegram via @BotFather : 8656…, 8790…, 8932…, 8948…
2. (Optionnel) Désindexer config/telegram.json.bak.20260717 si tu veux nettoyer l'historique

⚙️ Action Søn (une fois le code poussé par Hermes) :
1. Pull sur VPS
2. Lancer scripts/install_v9_live_watchdog_cron.bat (1 fois)
3. Lancer scripts/install_v9_paper_trade_loop_wrapper.bat (1 fois, backup de l'ancienne tâche)
4. python scripts/v9_live_watchdog_run.py --once (smoke test, doit retourner ok/no_data, pas critical)
5. Attendre 22h UTC, observer 5 min, vérifier Telegram
6. Si smoke test = critical : NE PAS OUVRIR, motion CEO pour désactiver V9_LIVE_WATCHDOG_ENABLED
```

---

## 7. Anti-régressions (rappels doctrinaux)

- **R2** : tout est additif sur l'existant. Tu ne supprimes aucun test, aucune fonction. Tu ajoutes ou amendes.
- **R6** : ton code doit être défensif (try/except, valeurs par défaut saines). Le watchdog **ne doit jamais crasher** le paper-trade loop.
- **R7** : aucun test rouge non justifié. Si un test existant casse, soit tu le mets à jour (avec justification), soit tu annules ta modif.
- **R8** : doc mise à jour dans le même commit que le code qu'elle documente.
- **R14** : git est la source de vérité. Pas de backup manuel hors `backups/`.
- **R18** : pas de LLM dans le cœur cognitif. Le watchdog = sqlite3 + math. Pas d'appel Ollama/OpenRouter.
- **R22** : 1 périmètre = 1 livraison. 3 chantiers listés ci-dessus = 1 livraison (la « pré-réouverture »).
- **R23** : tu ne touches pas aux YAML, donc R23 N/A.
- **R26** : 1 entrée `DECISIONS_LOG.md` par livraison (cette session = 1 entrée).
- **R28** : **TU NE PUSH PAS**. Hermes pousse.
- **R30** : le watchdog **recommande**, ne mute pas. Seul `--apply-recommendations` (utilisé par l'opérateur) mute. Sinon, R6 fail-safe.

---

## 8. Si tu bloques (escalade)

Si tu rencontres un blocage que tu ne peux pas résoudre en 2 essais, **documente** et **continue** :
- Log dans `PRE_REOUVERTURE_CHECKLIST_20260719.md` §« Blocages session »
- Mentionne dans ta réponse finale sous « ⚠️ Blocages »
- Ne jamais inventer une solution non testée pour avancer
- Ne jamais désactiver un test pour le faire passer

Si tu détectes une **incohérence avec la doctrine** (R7, R22, R30), **stop** et signale — ne contourne pas.

---

**Bon courage Opus. La machine doit être sous filet avant 22h UTC.**

— Søn CEO, via ZCode
