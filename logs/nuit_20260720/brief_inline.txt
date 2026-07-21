# PROMPT CLAUDE CODE — Session nuit Phase E Meta-Strategy Optimizer

**Mode AUTO-PILOTE** (motion CEO Søn 2026-07-20 ~23h UTC : « tu vas optimiser toute la nuit avec claude et claude opus, voit tout »)
**Périmètre strict** : Phase E Meta-Strategy Optimizer (V9_META_STRATEGY_OPTIMIZER_ENABLED=1)
**Provider** : Claude Code CLI Sonnet local (Søn 2026-07-20 ~23h UTC)
**Critère d'arrêt** : pas d'arrêt — tourner jusqu'à épuisement budget ou edge decay détecté
**Working dir** : `C:\projet\V9` (bash `/c/projet/V9`)
**Branche** : `feat/v9-foundation-clean` (up-to-date origin, HEAD `6aee973`)
**Pythonn** : `.venv/Scripts/python.exe` (PAS `python` qui est le venv Hermes sans pytest)

---

## Contexte en 1 minute

PowerFlow V9 = système de lecture comportementale des forces de marché (forex 6 paires live : GBPUSD, USDJPY, USDCHF, EURUSD, AUDUSD ; USDCAD blacklisté). Pipeline MT4 SDI (port 31685) → captures → scenes → decisions → paper_trades. Phase E (Système Prédictif, R33) active 4 modules :
- `V9_META_STRATEGY_OPTIMIZER_ENABLED=1` ← **TON SUJET**
- `V9_BAYESIAN_PREDICTOR_ENABLED=1`
- `V9_PREDICTIVE_ENGINE_ENABLED=1`
- `V9_LEARN_LOOP_ENABLED=1`

**Volumétrie live 2026-07-20 23h UTC** :
- 8771 décisions résolues (DB live `data/v9_forces.db` 3.7 GB)
- 4817 paper_trades clôturés (historique) + 178 nouveaux en cours session
- 226 strategies scorées dans `principle_scores`
- 332 principle_scores, 5331 décisions 24h, M5 GBPUSD validé bilatéral (motion #23, Δ NEUTRE -59.2 pts)

**Module livré, pas câblé runtime** :
`core/v9/v9_meta_strategy_optimizer.py` (579 LOC, R33, R2 additif, R6 défensif, R18 code pur) — 32 tests verts (`tests/test_v9_meta_strategy_optimizer.py`). Lit `principle_scores` + `paper_trades` + `cycle_memory`, score composite `(WR × PF/5 × (1-DD) × log(n+1)^0.2 × ctx_weight)`, top-1 parmi TP_SL / TRAILING / TP_PARTIAL / FAST_EXIT. **MAIS** : `grep meta_strategy core/v9/decision_logger.py core/v9/trade_engine.py core/v9/v9_strategy_pole.py` = **0 hit**. Le module existe en isolated, n'influence aucune décision live.

---

## Périmètre STRICT cette nuit

### ✅ Tu PEUX faire

1. **Câblage runtime** `meta_strategy_optimizer.recommend(...)` dans la chaîne de décision live :
   - Soit hook `core/v9/v9_strategy_pole.py::StrategySelector.recommend()` (remplacement complet)
   - Soit hook `core/v9/decision_logger.py::_determine_action()` (sélection stratégie au moment de la décision)
   - Soit fallback shadow : logging du `recommend()` sans influencer le trade, pour comparer live vs meta (R25' strict)
   - **RECOMMANDATION** : commencer par **fallback shadow** (motion CEO « voir tout » = observer d'abord), publier un rapport, puis activer câblage runtime via nouvelle motion CEO.

2. **CLI production** : créer ou étendre `scripts/v9_meta_strategy_report.py` qui :
   - scanne les `paper_trades` dernières 24h (178 visibles, 4817 historique)
   - calcule edge uplift mesuré : `WR_meta − WR_legacy`, `PF_meta − PF_legacy`, `avg_pips_meta − avg_pips_legacy`
   - sortie : tableau Markdown par `(symbol, regime_type, phase)` + verdict (uplift >+5 pts WR ? uplift >+0.5 PF ?)
   - dry-run par défaut, `--apply` pour écrire dans `principle_scores` (R2 additif, jamais destructif)

3. **Tests verts** : étendre `tests/test_v9_meta_strategy_optimizer.py` pour couvrir câblage runtime + CLI. Cible : +10 tests, 0 régression.

4. **Backup MD5 R8** obligatoire AVANT toute modif `core/v9/*` :
   ```bash
   mkdir -p docs/calibration/backups/2026-07-20_meta_strategy_wire
   git show HEAD:core/v9/<file>.py > docs/calibration/backups/2026-07-20_meta_strategy_wire/<file>.py.bak
   md5sum <file>.py.bak > <file>.py.bak.md5
   ```

5. **DECISIONS_LOG** : entrée §2026-07-20 23h UTC (motion CEO AUTO-PILOTE nuit) avec bilan tests + edge uplift mesuré.

6. **Commit atomique R22 + R26** : 1 commit par unité logique, push via Hermes **UNIQUEMENT** si Søn envoie « go r28 » explicite pendant la nuit. Sinon commits locaux + handoff au matin.

### ❌ Tu NE PEUX PAS faire (motion #18 + fondateur)

- **Activer** `REGIME_TIMEFRAME_OVERRIDES` runtime (motion CEO #18 = ready-not-active, R25' strict, validation 2 sem. paper-trade requise avant promotion). Les 6 lignes restent commentées dans `core/v9/config.py`.
- **Toucher** `core/v9/order_executor.py` ou activer `V9_EXECUTION_ENABLED=1` (Phase 12 gel fondateur, R12).
- **Modifier** les constantes doctrine tranchées CEO : `DYNAMIC_BLACKLIST_SESSIONS`, `DYNAMIC_PROFILES`, `HITL_CONF_HIGH=80`, `CONFIANCE_MIN=80`, `ANTAGONISM_THRESHOLD=31.39`, `COALITION_THRESHOLD=5.38`, `PLIURE_THRESHOLD=1.7`.
- **Toucher** `core/v9/auto_calibrator.py` ou `core/v9/decision_logger.py` de manière destructive (R8 backup posé, motion antérieure).
- **Auto-push** sans motion CEO explicite « go r28 » (R28 stricte hors mandat).

### ⚠️ Garde-fous runtime

- **R2 additif strict** : tout nouveau champ préfixé `meta_strategy_*` dans `principle_scores` / `paper_trades`, jamais destructif.
- **R6 défensif** : try/except sur lecture DB, fallback `StrategySelector.recommend()` si contexte pauvre ou engine OFF.
- **R7 tests verts** : `pytest tests/test_v9_meta_strategy_optimizer.py -q` doit rester 100% vert, **0 fail toléré**.
- **R8 backup MD5** : obligatoire avant modif `core/v9/*`.
- **R18 code pur** : **zéro LLM dans la boucle critique**. Module 100% stdlib + sqlite3.
- **R25'** : promotion meta → câblage runtime = motion CEO distincte. **Shadow d'abord**, activation runtime = motion CEO future.

---

## Procédure suggérée (8h de budget)

### Phase 1 — Recon (1h, 23h30 → 00h30 UTC)
1. `git pull` + `.venv/Scripts/python.exe -m pytest tests/test_v9_meta_strategy_optimizer.py -q` → base 32 verts.
2. Lire `core/v9/v9_meta_strategy_optimizer.py` en entier (579 LOC).
3. Lire `core/v9/v9_strategy_pole.py::StrategySelector.recommend()` (interface cible).
4. Lire `core/v9/decision_logger.py::_determine_action()` (chemin live actuel).
5. Lire `core/v9/trade_engine.py` (si trade Engine intègre déjà strategy_pole).
6. Identifier le **point de hook** optimal (decision_logger vs strategy_pole vs trade_engine).

### Phase 2 — Câblage shadow (2h, 00h30 → 02h30 UTC)
1. Ajouter `meta_strategy_optimizer.recommend()` dans le flux live **en lecture seule** : calcule la décision meta, log à côté de la décision legacy sans l'influencer.
2. Backup MD5 R8 des fichiers touchés.
3. Table de comparaison : `legacy_strategy`, `meta_strategy`, `agreement`, `wr_meta_pred`, `wr_legacy_obs` (sur N dernières décisions résolues).
4. Tests : `test_meta_strategy_shadow_wiring.py` (NEW, +8 tests) :
   - kill switch ON/OFF respecté
   - DB manquante → fallback sans crash
   - 5 contextes différents (symbol × regime × phase × vol × direction) → 5 candidats scored
   - agreement/différences décomptées
5. `pytest tests/ -q --no-header -x` doit rester 0 fail.

### Phase 3 — CLI rapport (2h, 02h30 → 04h30 UTC)
1. `scripts/v9_meta_strategy_report.py` (NEW, ~150 LOC) :
   - agrège les `paper_trades` dernières 24h par `(symbol, regime_type, phase, strategy)`
   - calcule edge uplift live (legacy vs meta)
   - sortie Markdown dans `reports/meta_strategy/YYYY-MM-DD_HHMM.md`
2. Tests `test_v9_meta_strategy_report.py` (NEW, +6 tests) : mock DB, dry-run, --apply idempotent.
3. Cron `V9_MetaStrategyReport` toutes les 6h (aligné sur `V9_RegimeCalibrationLoop` motion #18). Installation :
   ```bash
   python scripts/install_cron.py --task V9_MetaStrategyReport --script scripts/v9_meta_strategy_report.py --every 6h
   ```
4. Vérifier cron Ready via `Get-ScheduledTask | Where-Object {$_.TaskName -like "V9_*"}`.

### Phase 4 — Validation edge uplift (2h, 04h30 → 06h30 UTC)
1. Run `scripts/v9_meta_strategy_report.py --since 7d` → tableau edge uplift 7 derniers jours.
2. Si uplift mesuré >+5 pts WR ET >+0.5 PF sur sous-ensemble dense (≥3 symboles × 2 regimes × 2 phases × ≥10 trades) → **câblage runtime réel** (remplacer fallback par meta réel).
3. Si uplift ≤+5 pts ou volumétrie insuffisante → rester en shadow, redocumenter motion CEO future.

### Phase 5 — Clôture (30min, 06h30 → 07h UTC)
1. `pytest tests/ -q` global, push test count dans `AGENT.md` AUTO:STATE.
2. DECISIONS_LOG §2026-07-20 23h UTC « Motion CEO AUTO-PILOTE nuit Phase E — bilan ».
3. Si commits pushables : laisser en local, push matin après motion CEO.
4. Notification Telegram à Søn (kill switch `TELEGRAM_BLOQUÉ` actif runtime, fallback : `data/v9_edge_alert_state.json`).
5. Mettre à jour `workspace/perplexity/COORDINATION_NOTE.md` §2026-07-20 23h UTC « session nuit Phase E bilan ».

---

## Livrables attendus fin de nuit

| # | Livrable | Chemin | Status |
|---|----------|--------|--------|
| 1 | Câblage shadow live | `core/v9/v9_meta_strategy_optimizer.py` + 1 fichier hook | ✅ ou 🟡 |
| 2 | CLI rapport | `scripts/v9_meta_strategy_report.py` | ✅ ou 🟡 |
| 3 | Cron 6h | `V9_MetaStrategyReport` Ready | ✅ ou 🟡 |
| 4 | Tests | `+14 tests verts` cumulés sur Phase E | ✅ ou 🟡 |
| 5 | Backup MD5 R8 | `docs/calibration/backups/2026-07-20_meta_strategy_wire/` | ✅ |
| 6 | Edge uplift mesuré | `reports/meta_strategy/2026-07-21_*.md` | ✅ |
| 7 | DECISIONS_LOG | §2026-07-20 23h UTC | ✅ |
| 8 | COORDINATION_NOTE update | §2026-07-20 23h UTC | ✅ |
| 9 | AGENT.md AUTO:STATE sync | tests count + HEAD | ✅ |

---

## Arrêt session

- **Pas d'arrêt auto** (motion Søn 2026-07-20 ~23h UTC).
- **Arrêt explicite** : Søn envoie « stop » ou « bilan » ou « push r28 » via Telegram ou chat.
- **Arrêt de sécurité** : si `pytest tests/ -q` montre >3 fails nouveaux OU si `core/v9/order_executor.py` ou `V9_EXECUTION_ENABLED` touchés → rollback immédiat, motion CEO STOP_AUTO_PILOTE.

---

## Référence rapide

- AGENT.md : racine `C:\projet\V9\AGENT.md` (auto-sync `scripts/v9_sync_state.py`)
- DECISIONS_LOG : `workspace\perplexity\memory\DECISIONS_LOG.md` §2026-07-20 19h00 UTC
- ROADMAP Claude Code : `workspace\perplexity\ROADMAP_CLAUDE_CODE.md`
- COORDINATION_NOTE : `workspace\perplexity\COORDINATION_NOTE.md`
- Skill V9 module authoring : `powerflow-v9-module-authoring` §17
- Skill CEO prompt generator : `powerflow-v9-ceo-prompt-generator` (brief generation)

---

## Anti-régression (R28 procédure 2026-07-09)

- Aucun fichier hors `core/v9/`, `scripts/`, `tests/`, `docs/calibration/backups/`, `workspace/perplexity/`, `reports/` modifié.
- Aucun secret touché (`config/telegram.json` sanctuarisé).
- Aucun push sans motion CEO explicite.
- Bash `$PATH` = `.venv/Scripts/` actif (Hermes venv), sinon utiliser `.venv/Scripts/python.exe` systématiquement.

---

**Bon travail Claude Code, AUTO-PILOTE Phase E — bilan Telegram matin.**

— Søn CEO, motion 2026-07-20 ~23h UTC