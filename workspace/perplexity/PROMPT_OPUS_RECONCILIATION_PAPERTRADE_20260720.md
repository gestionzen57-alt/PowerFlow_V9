# PROMPT OPUS — Réconciliation PaperTrade vs Decisions (2026-07-20 01h30 UTC)

> **Destinataire** : Claude Code Opus (ou Sonnet à défaut), lecture initiale
> **Émetteur** : Søn CEO + ZCode (audit live 01h03 UTC)
> **Date d'envoi** : 2026-07-20 01:30 UTC
> **Doctrine** : R2 additif · R6 défensif · R7 tests verts · R8 doc · R14 Git vérité · R18 code pur · R22 1 périmètre = 1 livraison · R23 principes YAML · R26 DECISIONS_LOG · R28 Hermes push · R30 boucle fermée
> **Mode** : Code + commit, **motion CEO « oui go full audit 8 axes » déjà acquise**. Tu ne push que via Hermes en fin de session (R28).

---

## 0. Mission en une phrase

**Réconcilier les deux moteurs de résolution** (`decisions.is_win` DYNAMIC vs `paper_trades.is_win` fixe) en créant un **`PaperTradeResolver` unique** qui consomme les seuils adaptatifs (P3-WIRE) et dimensionne TP/SL par contexte (vol_regime, session, timeframe). **Livrer 2 chantiers** : (A) module `PaperTradeResolver` + résolution unifiée, (B) audit de la qualité des résolutions passées + script de recalibrage. **Aucune autre intervention**. R22 strict.

---

## 1. Contexte hérité — l'incohérence détectée à 01h03 UTC

### 1.1 Audit live 2026-07-20 01:03 UTC — divergences mesurées

| Source | Total clôturé | Wins | Losses | WR | Pips total |
|---|---|---|---|---|---|
| `decisions` (résolution DYNAMIC) | 8 441 | 7 374 | 1 067 | **87.3%** | **+46 628** |
| `paper_trades` (résolution fixe) | 4 832 | 1 150 | 3 682 | **23.8%** | **-47 374** |

→ **Désaccord total, quasi miroir** (+46 628 vs -47 374). Deux moteurs, deux comptages, deux vérités incompatibles. C'est inacceptable pour un système qui prétend mesurer sa performance.

### 1.2 Diagnostic technique

**Bug confirmé** : le `PaperTradeLoop` applique des **TP/SL fixes (5.5/-17.5 pips)** codés en dur, sans considération de :
- `vol_regime` (LOW/NORMAL/HIGH/EXTREME)
- `session` (Sydney/London/NY)
- `timeframe` (M1/M5/M15)
- `confiance` (62 vs 71 vs 90)
- seuils adaptatifs posés par P3-WIRE (`adaptive_antagonism_threshold`, etc.)

→ Sur M1 Sydney en vol_regime LOW, un TP de 5.5 pips est **irréaliste** (le bruit intra-bar M1 = 8-12 pips) → le SL se déclenche avant le TP → WR dégradé artificiellement.

**Le `decisions` DYNAMIC** à l'inverse utilise probablement une **résolution à horizon** (pas de SL strict, sortie à expiration du signal) → il « gagne » virtuellement sur 87% des cas mais ne reflète pas la réalité d'exécution.

### 1.3 État au démarrage

- **HEAD** : `1072999` sur `feat/v9-foundation-clean` (post-réconciliation kill switches du 19/07 §23h UTC)
- **Working tree** : 4 fichiers `data/strategy_pole/*.json` modifiés par l'auto-calibrateur (à NE PAS toucher, R22 strict)
- **Tests baseline** : `~2288 passed / 10 failed préexistants / 3 skipped` (fails documentés hors périmètre)
- **DB** : `data/v9_forces.db` (~2.61 GB, 25 tables) — **NE PAS MIGRER** (R22 strict)
- **Marché** : OUVERT, session Sydney (EURUSD M1 actif), pipeline PID 5576, port 31685 listening
- **Vol_regime live** : LOW (Sydney, début de semaine)

### 1.4 Fichiers que tu dois connaître intimement

- `scripts/v9_paper_trade_run.py` — entry point du paper-trade loop (contient la résolution fixe 5.5/-17.5)
- `core/v9/paper_trade_loop.py` (ou équivalent) — la boucle de résolution actuelle (à localiser via grep)
- `core/v9/v9_decision_resolver.py` (ou équivalent) — la résolution DYNAMIC de `decisions` (à localiser via grep)
- `core/v9/_load_shared_context.py` (P3-WIRE) — pose les seuils adaptatifs consommés par ADAPTIVE_VOL_GATE
- `core/v9/zone_detector.py` — source de `vol_regime`
- `data/v9_forces.db` table `paper_trades` (4 832 lignes) — input de l'audit
- `data/v9_forces.db` table `decisions` (76 345 lignes, 8 441 résolues) — input de l'audit
- `core/v9/principles/adaptive_vol_gate.yaml` — premier consommateur des seuils adaptatifs (référence)
- `mcp__v9-sqlite__principle_scores_top` — pattern RAG sur les combinaisons

### 1.5 Motion CEO acquise

- « oui go full audit 8 axes » (2026-07-19) — couvre l'audit de cohérence interne
- « Construis le watchdog maintenant » (2026-07-19) — couvre l'observabilité
- **Motion implicite** : la réconciliation paper_trades ↔ decisions fait partie de l'audit de cohérence interne. Tu peux la traiter sans nouveau round CEO.

---

## 2. Périmètre EXACT de cette livraison (2 chantiers, R22 strict)

### CHANTIER A — `PaperTradeResolver` unique (résolution par contexte)

#### A.1 Créer `core/v9/v9_paper_trade_resolver.py`

**Nouveau module** (~250 LOC). Classe `PaperTradeResolver` qui **remplace** la résolution fixe par une résolution paramétrique par contexte.

**Signature** :
```python
@dataclass
class ResolutionContext:
    vol_regime: str  # "LOW" | "NORMAL" | "HIGH" | "EXTREME"
    session: str     # "sydney" | "london" | "ny" | "overlap"
    timeframe: str   # "M1" | "M5" | "M15" | "H1" | "H4" | "D1"
    confiance: int   # 0-100
    symbol: str      # "GBPUSD" | "EURUSD" | ...
    direction: str   # "haussiere" | "baissiere"

@dataclass
class ResolvedOutcome:
    is_win: int      # 0 | 1
    pips: float
    exit_reason: str # "tp" | "sl" | "horizon" | "timeout" | "risk_off"
    tp_used: float
    sl_used: float

class PaperTradeResolver:
    def __init__(self, db_path: str, kill_switches_path: Optional[str] = None):
        """Charge les seuils adaptatifs depuis P3-WIRE (optionnel)."""
        ...

    def resolve(self, trade: dict, ctx: ResolutionContext) -> ResolvedOutcome:
        """Résout un trade selon son contexte. TP/SL paramétriques."""
        ...

    def tp_sl_for(self, ctx: ResolutionContext) -> Tuple[float, float]:
        """
        Retourne (tp_pips, sl_pips) selon le contexte.

        Table de base (à raffiner depuis les données historiques) :
        ┌──────────┬─────────┬──────────────┬─────────────┐
        │ TF / Vol │ LOW     │ NORMAL       │ HIGH        │
        ├──────────┼─────────┼──────────────┼─────────────┤
        │ M1       │ 8 / -10│ 12 / -15     │ 18 / -22    │
        │ M5       │ 15/-18 │ 22 / -25     │ 35 / -40    │
        │ M15      │ 30/-35 │ 45 / -50     │ 70 / -80    │
        │ H1       │ 60/-70 │ 90 / -100    │ 140/-160    │
        └──────────┴─────────┴──────────────┴─────────────┘

        Ajustements supplémentaires :
        - confiance < 70 : TP × 0.8, SL × 1.2 (plus conservateur)
        - confiance ≥ 90 : TP × 1.2, SL × 0.9 (plus agressif)
        - session sydney : multiplier par 0.7 (vol plus faible)
        - session overlap : multiplier par 1.1 (vol plus forte)
        """
        ...

    def calibrate_from_history(self, n_days: int = 30) -> Dict[str, Tuple[float, float]]:
        """
        Re-calibre la table TP/SL depuis les snapshots des N derniers jours.
        Algorithme : pour chaque (tf, vol_regime), trouver le TP/SL qui maximise
        un score composite (WR × avg_win - (1-WR) × |avg_loss|) sur les résolutions
        DYNAMIC passées dans `decisions`.
        Retourne la nouvelle table (peut être injectée via set_table).
        """
        ...

    def set_table(self, table: Dict[Tuple[str, str], Tuple[float, float]]) -> None:
        """Override la table TP/SL (utile après calibrate_from_history)."""
        ...
```

**Tests** `tests/test_v9_paper_trade_resolver.py` (~12 tests) :
- `test_resolve_low_vol_m1_short_tp` : contexte vol=LOW, tf=M1, conf=80 → TP=12, SL=-15, is_win sur trade qui monte de 14 pips
- `test_resolve_high_vol_h1_long_sl` : contexte vol=HIGH, tf=H1, conf=85 → TP=140, SL=-160, is_win=0 sur trade qui perd 100 pips
- `test_tp_sl_scales_with_confiance` : même (tf, vol) mais conf=60 vs conf=95 → TP/SL différents
- `test_session_multiplier_sydney` : session=sydney → TP/SL réduits de 30%
- `test_session_multiplier_overlap` : session=overlap → TP/SL augmentés de 10%
- `test_resolve_returns_exit_reason` : chaque résolution retourne `exit_reason` correct (tp, sl, horizon, timeout)
- `test_calibrate_from_history_runs` : avec une DB factice, `calibrate_from_history(7)` retourne une table non vide
- `test_calibrate_table_improves_wr` : après calibrate, le WR sur un échantillon test est ≥ WR initial
- `test_set_table_overrides_default` : `set_table({("M1", "LOW"): (5, -5)})` est respecté
- `test_resolve_handles_zero_pips` : trade avec pips_simulated=0 → is_win=0, exit_reason="timeout"
- `test_resolve_handles_extreme_vol` : vol=EXTREME → TP/SL scalent correctement (×1.5 vs HIGH)
- `test_resolver_is_deterministic` : 2 appels successifs avec même input → même output

#### A.2 Wire le `PaperTradeResolver` dans le loop existant

**Modifier `scripts/v9_paper_trade_run.py`** (et tout fichier de loop trouvé via grep) :
- Remplacer la résolution fixe par : `resolver = PaperTradeResolver(db_path="data/v9_forces.db")` + `outcome = resolver.resolve(trade, ctx)` où `ctx` est construit depuis `trade["vol_regime"]`, `trade["session"]`, etc.
- **Garde-fou R6** : si `resolver` échoue (DB absente, vol_regime inconnu), fallback sur la résolution fixe actuelle (5.5/-17.5) avec un log WARNING.
- **Ne PAS désactiver** la résolution existante : ajouter le resolver en mode **shadow** d'abord, logger ses résultats, et n'écraser `is_win` qu'après motion CEO explicite (R25').

**Tests d'intégration** `tests/test_paper_trade_run_uses_resolver.py` (~4 tests) :
- `test_paper_trade_run_imports_resolver` : vérifier que `v9_paper_trade_run.py` importe bien `PaperTradeResolver`
- `test_paper_trade_run_logs_shadow_resolution` : un trade clôturé génère 2 logs : un pour la résolution fixe (effective), un pour la résolution resolver (shadow)
- `test_resolver_shadow_does_not_overwrite` : la table `paper_trades` n'est PAS modifiée par le shadow resolver
- `test_resolver_failure_triggers_fallback` : si `PaperTradeResolver` lève une exception, le loop continue avec la résolution fixe

#### A.3 Indicateur de divergence live

**Ajouter dans `core/v9/v9_live_watchdog.py`** (ou nouveau module `v9_resolution_drift.py`) une fonction `compute_resolution_drift(db_path)` qui :
- Calcule le WR sur les 100 derniers `paper_trades` ET sur les 100 dernières `decisions` résolues (DYNAMIC)
- Retourne `(wr_paper_trades, wr_decisions, drift_pct)` où `drift_pct = |wr_decisions - wr_paper_trades| × 100`
- Si `drift_pct > 20` → alerte `WARN` (divergence forte)
- Si `drift_pct > 40` → alerte `CRITICAL` (système incohérent, R30 boucle fermée cassée)

**Tests** `tests/test_resolution_drift.py` (~4 tests) :
- `test_drift_zero_when_identical` : WR identiques → drift=0, pas d'alerte
- `test_drift_warn_at_25_pct` : WR 70 vs 95 → drift=25, alerte WARN
- `test_drift_critical_at_45_pct` : WR 50 vs 95 → drift=45, alerte CRITICAL
- `test_drift_handles_empty_table` : table vide → retourne `(None, None, None)`, pas de crash

### CHANTIER B — Audit rétrospectif + recalibrage

#### B.1 Script `scripts/v9_audit_resolution_drift.py`

**Nouveau script CLI** (~150 LOC). Audite la divergence historique entre `decisions` et `paper_trades` :
- Lit les 2 tables sur les 30 derniers jours
- Groupe par (symbol, timeframe, direction, vol_regime, session) quand disponible
- Calcule pour chaque groupe : WR paper, WR decision, drift, n_trades, avg_pips_paper, avg_pips_decision
- Génère un rapport Markdown dans `workspace/perplexity/audits/RESOLUTION_DRIFT_AUDIT_<timestamp>.md`
- Affiche un résumé console (top 5 groupes les plus divergents)
- Exit code 0 si drift_max < 20, 1 si 20 ≤ drift_max < 40, 2 si drift_max ≥ 40

**Tests** `tests/test_v9_audit_resolution_drift.py` (~5 tests) :
- `test_audit_generates_report_file` : avec une DB factice, le rapport est créé
- `test_audit_groups_by_context` : 100 trades sur 3 contextes différents → 3 lignes dans le rapport
- `test_audit_exits_zero_on_low_drift` : drift < 20 → exit 0
- `test_audit_exits_two_on_critical` : drift ≥ 40 → exit 2
- `test_audit_report_contains_top5` : le rapport contient une section "Top 5 divergences"

#### B.2 Script `scripts/v9_recalibrate_paper_trade.py`

**Nouveau script CLI** (~100 LOC). Lance `resolver.calibrate_from_history(30)` et :
- Affiche la table avant/après (diff visuel)
- Demande confirmation interactive (sauf `--yes`)
- Si confirmé, applique la nouvelle table via `resolver.set_table()` ET **append** la table dans `config/v9_paper_trade_resolver.json` (nouveau fichier de config)
- Log l'opération dans `workspace/perplexity/memory/DECISIONS_LOG.md`

**Tests** `tests/test_v9_recalibrate_paper_trade.py` (~4 tests) :
- `test_recalibrate_shows_diff` : avec DB factice, affiche bien avant/après
- `test_recalibrate_writes_json_config` : après confirm, `config/v9_paper_trade_resolver.json` est créé
- `test_recalibrate_appends_decisions_log` : une entrée est ajoutée à `DECISIONS_LOG.md`
- `test_recalibrate_dry_run_does_not_write` : avec `--dry-run`, aucun fichier n'est créé

---

## 3. Garde-fous stricts (HORS PÉRIMÈTRE)

**Tu ne fais AUCUNE des actions suivantes** (R22 strict) :
- ❌ Migrer la DB (ajout de colonnes, nouvelles tables)
- ❌ Modifier `core/v9/v9_decision_resolver.py` (le moteur DYNAMIC est la référence, pas la cible)
- ❌ Activer le `PaperTradeResolver` en mode **non-shadow** (R25' : promotion conditionnée à motion CEO explicite après validation des tests)
- ❌ Modifier `config/v9_kill_switches.env` (R6 : pas touche aux kill switches runtime sans motion)
- ❌ Toucher aux YAML principes (R23)
- ❌ Toucher aux `data/strategy_pole/*.json` (artefacts auto-calibrateur)
- ❌ Pousser (push) — R28 : Hermes est l'unique push operator
- ❌ Désactiver le `paper_trade_run` existant

Si tu détectes un problème supplémentaire (e.g. vol_regime NULL dans `paper_trades`, timeframe manquant), **documente-le** dans `workspace/perplexity/audits/PAPER_TRADE_GAPS_<timestamp>.md` et **ne le fixe pas** dans cette session.

---

## 4. Workflow étape par étape

### Étape 1 — Sanité base (5 min)
```bash
cd C:/projet/V9
git status
git log --oneline -5    # HEAD = 1072999
pytest tests/ -q --co   # doit collecter ~2300+ tests
```

### Étape 2 — Localiser les fichiers pivants
```bash
grep -rn "5.5\|17.5" core/v9/ scripts/ | grep -i "tp\|sl\|pips"
grep -rn "is_win.*=" scripts/v9_paper_trade_run.py
grep -rn "vol_regime" data/v9_forces.db.schema 2>/dev/null || sqlite3 data/v9_forces.db ".schema paper_trades"
```

### Étape 3 — Vérifier le marché
```bash
python scripts/v9_ops.py health
python scripts/v9_ops.py status
```

### Étape 4 — Chantier A.1 (resolver, ~60 min)
1. Créer `core/v9/v9_paper_trade_resolver.py`
2. Créer `tests/test_v9_paper_trade_resolver.py` (12 tests)
3. `pytest tests/test_v9_paper_trade_resolver.py -v` → 12 verts

### Étape 5 — Chantier A.2 (wire dans loop, ~20 min)
1. Modifier `scripts/v9_paper_trade_run.py` (import + shadow mode)
2. Créer `tests/test_paper_trade_run_uses_resolver.py` (4 tests)
3. `pytest tests/test_paper_trade_run_uses_resolver.py -v` → 4 verts

### Étape 6 — Chantier A.3 (drift live, ~20 min)
1. Ajouter `compute_resolution_drift()` dans `v9_live_watchdog.py` OU créer `core/v9/v9_resolution_drift.py`
2. Créer `tests/test_resolution_drift.py` (4 tests)
3. `pytest tests/test_resolution_drift.py -v` → 4 verts

### Étape 7 — Chantier B.1 (audit script, ~30 min)
1. Créer `scripts/v9_audit_resolution_drift.py`
2. Créer `tests/test_v9_audit_resolution_drift.py` (5 tests)
3. Lancer en mode `--dry-run` pour vérifier qu'il parse la DB sans crasher

### Étape 8 — Chantier B.2 (recalibrage, ~20 min)
1. Créer `scripts/v9_recalibrate_paper_trade.py`
2. Créer `tests/test_v9_recalibrate_paper_trade.py` (4 tests)

### Étape 9 — Validation finale (10 min)
```bash
pytest tests/ -q                                    # baseline préservée + ~29 nouveaux tests verts
python scripts/v9_audit_resolution_drift.py --dry-run
python scripts/v9_recalibrate_paper_trade.py --dry-run
python -c "from core.v9.v9_paper_trade_resolver import PaperTradeResolver; r = PaperTradeResolver('data/v9_forces.db'); print(r.tp_sl_for(__import__('core.v9.v9_paper_trade_resolver', fromlist=['ResolutionContext'])(vol_regime='LOW', session='sydney', timeframe='M1', confiance=80, symbol='GBPUSD', direction='haussiere')))"
```

### Étape 10 — Commits atomiques (2 commits max, R26)
```bash
git add core/v9/v9_paper_trade_resolver.py core/v9/v9_resolution_drift.py tests/test_v9_paper_trade_resolver.py tests/test_resolution_drift.py
git commit -m "feat(v9): PaperTradeResolver paramétrique par (tf, vol, session, conf) + drift detector (audit 01h03 UTC)"

git add scripts/v9_paper_trade_run.py scripts/v9_audit_resolution_drift.py scripts/v9_recalibrate_paper_trade.py tests/test_paper_trade_run_uses_resolver.py tests/test_v9_audit_resolution_drift.py tests/test_v9_recalibrate_paper_trade.py config/v9_paper_trade_resolver.json workspace/perplexity/audits/
git commit -m "feat(v9): wire shadow PaperTradeResolver + audit/recalibrage CLI (réconciliation décisions ↔ paper_trades)"
```

### Étape 11 — Push
**TU NE PUSH PAS** (R28). Termine avec :
```
[HERMES ACTION REQUIRED] 2 commits prêts sur feat/v9-foundation-clean :
- <sha1> PaperTradeResolver + drift detector
- <sha2> wire shadow + audit/recalibrage CLI
Push via : git push origin feat/v9-foundation-clean
```

---

## 5. Critères de succès (definition of done)

| # | Critère | Mesure |
|---|---|---|
| 1 | `PaperTradeResolver` existe et a 12 tests verts | `pytest tests/test_v9_paper_trade_resolver.py -q` → 12 passed |
| 2 | TP/SL paramétriques par (tf, vol, session, conf) | Test `test_tp_sl_scales_with_confiance` + `test_session_multiplier_*` verts |
| 3 | `calibrate_from_history` fonctionne | Test `test_calibrate_from_history_runs` vert |
| 4 | Wire shadow dans `v9_paper_trade_run.py` | `grep "PaperTradeResolver" scripts/v9_paper_trade_run.py` → 1 hit import |
| 5 | Drift detector fonctionne | `pytest tests/test_resolution_drift.py -q` → 4 passed |
| 6 | Audit script génère rapport | `python scripts/v9_audit_resolution_drift.py --dry-run` exit 0 |
| 7 | Recalibrage fonctionne en dry-run | `python scripts/v9_recalibrate_paper_trade.py --dry-run` exit 0 |
| 8 | Baseline non régressée | `pytest tests/ -q` → ~2317 passed / 10 failed (inchangés) / 3 skipped |
| 9 | Aucun fichier hors périmètre touché | `git diff --name-only HEAD~2..HEAD` → uniquement fichiers listés en §2 |
| 10 | 2 commits atomiques | `git log --oneline HEAD~2..HEAD` → 2 commits avec messages conformes |

Si un critère échoue, **ne commit pas** tant que c'est rouge.

---

## 6. Communication finale (à mettre dans ta dernière réponse)

```
✅ Session réconciliation paper_trades ↔ decisions — terminée

Commits préparés (R28, push via Hermes) :
- <sha1> PaperTradeResolver + drift detector (chantier A)
- <sha2> wire shadow + audit/recalibrage CLI (chantier B)

Tests : <N> passed, baseline préservée (10 fails préexistants inchangés)

🎯 Découvertes audit 01h03 UTC :
- paper_trades WR=23.8% (-47374 pips) vs decisions WR=87.3% (+46628 pips)
- Cause : TP/SL fixes (5.5/-17.5) inadaptés au contexte M1 Sydney
- Fix : PaperTradeResolver paramétrique par (tf, vol_regime, session, confiance)
- Mode shadow d'abord — promotion ACTIVE après motion CEO explicite (R25')

🔴 Actions CEO après push :
1. Lire le rapport d'audit : workspace/perplexity/audits/RESOLUTION_DRIFT_AUDIT_<ts>.md
2. Si la table recalibrée est convaincante : motion « go recalibrate paper_trade »
3. Surveiller le drift detector (alertes Telegram si drift > 20%)
```

---

## 7. Anti-régressions (rappels doctrinaux)

- **R2** : tout est additif. Tu ne supprimes aucun test, aucune fonction.
- **R6** : ton code doit être défensif. Le resolver ne doit JAMAIS crasher le paper-trade loop (fallback résolution fixe).
- **R7** : aucun test rouge non justifié.
- **R8** : doc mise à jour dans le même commit que le code qu'elle documente.
- **R14** : git est la source de vérité.
- **R18** : pas de LLM dans le cœur cognitif. Le resolver = math + heuristiques déterministes.
- **R22** : 1 périmètre = 1 livraison. 2 chantiers = 1 livraison (la « réconciliation »).
- **R25'** : le resolver est livré en **shadow** uniquement. Promotion ACTIVE = motion CEO explicite.
- **R26** : 1 entrée `DECISIONS_LOG.md` par livraison.
- **R28** : **TU NE PUSH PAS**. Hermes pousse.
- **R30** : le drift detector **recommande** (alertes Telegram), ne mute pas.

---

## 8. Si tu bloques (escalade)

Si tu rencontres un blocage :
- Log dans `workspace/perplexity/audits/PAPER_TRADE_GAPS_<timestamp>.md`
- Mentionne dans ta réponse finale sous « ⚠️ Blocages »
- Ne jamais inventer une solution non testée
- Ne jamais désactiver un test pour le faire passer

Si tu détectes une **incohérence avec la doctrine** (R7, R22, R25', R30), **stop** et signale — ne contourne pas.

---

**La réconciliation est le seul chemin vers la confiance dans les chiffres. Pas de paper_trades fiable = pas de promotion ACTIVE possible.**

— Søn CEO, via ZCode (audit live 01h03 UTC, 2026-07-20)
