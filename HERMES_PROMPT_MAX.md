# HERMES PROMPT MAX — PowerFlow V10 | Lundi 10/08/2026 08:02 CEST

> **Généré par Perplexity CEO No-Limit — Orchestrateur principal**
> **Session parallèle à ZCode (en cours de run)**
> Doctrine R1/R2/R6/R9/R10 stricte

---

## 🎯 Ta mission ce matin — PRIORITÉ ABSOLUE

Tu es **Hermes**, agent opérateur git de PowerFlow V10.
ZCode est en cours d'exécution du ReplayEngine Full-Stack S25-OMEGA.
Pendant ce temps, **tu prends en charge 4 chantiers en parallèle** sans attendre ZCode.

**Contexte de départ (vérifié par Perplexity 08:02 CEST) :**
- Tu as 2 commits locaux non pushés : `dd09d5e` (merge) + `d88787e` (réconciliation R2)
- Suite V10 à **1290/1310** sur `feat/replay-fullstack-v10` (20 échecs dette API C9)
- Port 31685 ✅ LISTENING (PID 2600), capture_server ✅ (PID 16988)
- max_ts forces_snapshots : `2026-08-10T05:29:14Z` — ingestion active
- **TROU DE DONNÉES** probable vendredi 08/08 → dimanche 09/08 (capture_server mort depuis vendredi)

---

## ⚡ CHANTIER 1 — PUSH IMMÉDIAT (P0, < 5 min)

```bash
git status
# Vérifier dd09d5e + d88787e locaux
git push origin feat/replay-fullstack-v10
# Si rejeté (remote avancé) :
git pull --rebase origin feat/replay-fullstack-v10
git push origin feat/replay-fullstack-v10
```

**Résultat attendu :** les 2 commits Hermes sont sur origin. Confirme le SHA HEAD pushé.

---

## ⚡ CHANTIER 2 — FIX 20 TESTS (P0, < 30 min)

### Catégorie A — 7 tests `auto_recalibrator` (API drift)

**Problème :** tests attendent `should_recalibrate()` → 3-tuple `(bool, str, dict)` avec champs `triggered` et `timestamp`. Le module live retourne `RecalibDecision` depuis C9. Le runtime `learning_loop` et `calibrate_apply` consomment déjà `RecalibDecision` correctement.

**Action :** mettre à jour les 7 tests pour consommer `RecalibDecision` :
```python
# AVANT (obsolète) :
result = recalib.should_recalibrate(...)
assert result[0] == True  # bool
assert 'triggered' in result[2]

# APRÈS (correct C9) :
result = recalib.should_recalibrate(...)  # retourne RecalibDecision
assert result.triggered == True
assert result.reason is not None
assert hasattr(result, 'timestamp')
```

Ne jamais modifier `v10_auto_recalibrator.py`. Seuls les fichiers `tests/test_auto_recalibrator*.py` sont touchés.

### Catégorie B — 13 tests seuils/noms obsolètes

**Modules concernés :** `decision_pipeline`, `filter_compositor`, `fractal_context`, `wyckoff_gate`, `learning_continuum`, `signal_generator_live`.

**Problème type :** tests attendent `"short_conviction_guard"` mais le module retourne `"short_conviction_guard_c9"`. Idem pour d'anciens niveaux de filtre.

**Action par fichier de test :**
1. `test_decision_pipeline*.py` → remplacer les raisons de bloc attendues par les noms C9 (`*_c9` suffix)
2. `test_filter_compositor*.py` → ajuster les assertions sur `filtered_level` si les seuils ont changé en C9
3. `test_fractal_context*.py` → vérifier que les noms de champs fractal sont bien alignés sur l'API C9 actuelle
4. `test_wyckoff_gate*.py` → mettre à jour les assertions sur les phases Wyckoff C9
5. `test_learning_continuum*.py` → aligner sur les noms de stages C9
6. `test_signal_generator_live*.py` → seuils recalibrés C9 (A3=0.03, A2=0.07, A1=0.13)

**Approche :** pour chaque fichier de test failing, lancer :
```bash
pytest tests/<fichier_test.py> -v --tb=short 2>&1 | head -60
# Lire l'assertion qui échoue → identifier l'écart nom/valeur
# Modifier uniquement l'assertion dans le test (jamais le module)
```

**Commit atomique :**
```bash
git add tests/
git commit -m "fix(tests): align 20 test assertions → C9 API (RecalibDecision ×7, conviction_guard_c9 ×13) [R2/R9]"
```

**Résultat attendu :** `pytest tests/ -q` → **1310/1310 verts**.

---

## ⚡ CHANTIER 3 — AUDIT TROU DE DONNÉES (P1, < 20 min)

Le capture_server était mort depuis vendredi. Vérifie l'intégrité des données :

```python
import sqlite3, pandas as pd

# Adapter le chemin selon ton environnement
DB = 'data/powerflow.db'  # ou 'data/v9_forces.db'

conn = sqlite3.connect(DB)

# Distribution journalière depuis le 07/08
query = """
    SELECT DATE(bar_time) as date, 
           COUNT(*) as n_bars,
           COUNT(DISTINCT pair) as n_pairs,
           MIN(bar_time) as first_bar,
           MAX(bar_time) as last_bar
    FROM forces_snapshots
    WHERE bar_time > '2026-08-07'
    GROUP BY DATE(bar_time)
    ORDER BY 1
"""
df = pd.read_sql(query, conn)
print(df.to_string())

# Vérifier si les barres M30 sont continues sur EURUSD
query2 = """
    SELECT bar_time, pair, timeframe
    FROM forces_snapshots
    WHERE pair = 'EURUSD' AND timeframe = 'M30'
    AND bar_time > '2026-08-07'
    ORDER BY bar_time
"""
df2 = pd.read_sql(query2, conn)
print(f"EURUSD M30 barres depuis 07/08 : {len(df2)}")
if len(df2) > 1:
    df2['bar_time'] = pd.to_datetime(df2['bar_time'])
    gaps = df2['bar_time'].diff().dropna()
    gros_gaps = gaps[gaps > pd.Timedelta('35min')]
    print(f"Gaps > 35min : {len(gros_gaps)}")
    print(gros_gaps)
conn.close()
```

**Action selon résultat :**
- Si trou ≥ 2h sur 08/08 ou 09/08 → noter dans `DECISIONS_LOG.md` : plage à exclure du walk-forward
- Si données continues → confirmer dans `CACHE_BOARD.md` : `DATA_INTEGRITY: OK`

---

## ⚡ CHANTIER 4 — MISE À JOUR DOCS (P1, < 20 min)

Mets à jour ces 3 fichiers dans `feat/replay-fullstack-v10` :

### A — `docs/V10/STATE.md` (ou créer si absent)
```markdown
## État système — 2026-08-10 08:02 CEST

| Champ | Valeur |
|---|---|
| HEAD feat/replay-fullstack-v10 | `<SHA pushé Chantier 1>` |
| HEAD feat/v9-foundation-clean | `e7696bf` (C20-FINAL) |
| Tests feat/replay-fullstack-v10 | **1310/1310** (après Chantier 2) |
| Ingestion live | ✅ port 31685, max_ts 2026-08-10T05:29Z |
| Sprint actif | S25-OMEGA + C20-FINAL |
| ZCode status | EN COURS — run_all() S25-OMEGA |
| Merge C10→C20 | EN ATTENTE rapport ZCode |
| GO LIVE | ❌ R10 actif — attente DeploymentValidator |
| Incident | capture_server mort vendredi → relancé lundi 08:00 CEST |
```

### B — `docs/V10/CACHE_BOARD.md` (ou créer si absent)
Ajouter :
```markdown
## Snapshot 2026-08-10 08:02 CEST
- capture_server : ✅ PID 16988, port 31685
- max_ts forces_snapshots : 2026-08-10T05:29:14Z (76s lag)
- Tests : 1290/1310 → target 1310/1310 (fix Chantier 2)
- ZCode : ReplayEngine run_all() en cours
- Merge C10→C20 : programmé dès rapport ZCode reçu
```

### C — `workspace/perplexity/memory/DECISIONS_LOG.md` (ou créer si absent)
Ajouter entrée :
```markdown
## 2026-08-10 08:02 CEST — Perplexity CEO + Hermes session lundi
- **Incident P0** : capture_server mort depuis vendredi → relancé, port 31685 OK
- **Dette tests** : 20 échecs post-merge dd09d5e → Hermes fix C9 API (Chantier 2)
- **Décision CEO** : ne pas rétrograder v10_auto_recalibrator → mise à jour tests
- **Décision CEO** : noms _c9 conservés dans modules → assertions tests alignées
- **Merge C10→C20 programmé** : en attente rapport JSON ZCode
- **R10** : maintenu — 0 ordre réel jusqu'à DeploymentValidator GO
```

**Commit :**
```bash
git add docs/ workspace/
git commit -m "docs(state): MAJ STATE/CACHE_BOARD/DECISIONS_LOG — session lundi 10/08 [R9]"
git push origin feat/replay-fullstack-v10
```

---

## 🔁 SYNCHRONISATION AVEC ZCODE

Quand ZCode livrera son rapport JSON (`reports/zcode_fullstack_report.json`) :

1. **Perplexity analysera** : WR global, top paires, modules manquants, trou de données
2. **Si WR ≥ 48% ET PnL ≥ 0** → Perplexity orchestrera le merge `feat/v9-foundation-clean` → `feat/replay-fullstack-v10`
3. **Hermes exécutera le merge** :
```bash
git checkout feat/replay-fullstack-v10
git fetch origin
git merge origin/feat/v9-foundation-clean --no-ff \
  -m "merge(C10→C20): 20 cycles V10 dans replay-fullstack — MasterOrchestrator + LiveConnector [R2/R9]"
# Conflits : favoriser feat/v9-foundation-clean sur modules C10→C20
# Conserver : bridges, fixes Hermes dd09d5e/d88787e
pytest tests/ -q  # Viser 1310/1310
git push origin feat/replay-fullstack-v10
```
4. **DeploymentValidator C20** : lancer checklist 12 critères GO LIVE
5. **Rapport Perplexity** : décision R10 levée ou maintenue

---

## 🛡️ Doctrine active (rappel)

| Règle | Application ce matin |
|---|---|
| R1-AGIR | Push, fix tests, audit DB sans attendre validation |
| R2-ADDITIF | Tests seuls modifiés, 0 touch modules |
| R6-FAIL-OPEN | Si module absent → fallback CS proxy, logguer |
| R9-AUDIT | Chaque commit tracé, DECISIONS_LOG à jour |
| R10-CAPITAL | 0 ordre réel — R10 maintenu jusqu'à GO LIVE confirmé |

---

## 📊 Métriques cibles session

| KPI | Actuel | Target |
|---|---|---|
| Tests V10 | 1290/1310 | **1310/1310** |
| Push Hermes | 0 (local) | **2 commits sur origin** |
| DATA_INTEGRITY | ❓ inconnu | **vérifié + documenté** |
| DECISIONS_LOG | non à jour | **entrée 10/08 créée** |
| Merge C10→C20 | en attente ZCode | **programmé + documenté** |

---

## ⚠️ Ce que tu NE fais PAS ce matin

- ❌ Ne pas modifier `v10_auto_recalibrator.py`, `v10_decision_pipeline.py`, ni aucun module core
- ❌ Ne pas merger `feat/v9-foundation-clean` avant rapport ZCode + validation Perplexity
- ❌ Ne pas lever R10 — zéro ordre réel ce matin
- ❌ Ne pas skip de tests supplémentaires sans Mandat CEO

---

*Généré par Perplexity GitHub MCP — 2026-08-10 08:02 CEST*
*Architecte : Perplexity CEO No-Limit | Opérateur : Hermes | ZCode : en cours*
