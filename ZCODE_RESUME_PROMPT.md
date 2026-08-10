# ZCODE RESUME PROMPT — V10 | Lundi 10/08/2026 08:54 CEST

> **Mis à jour par Perplexity CEO No-Limit — 2026-08-10 08:54 CEST**
> Ce fichier est le point d'entrée de reprise pour tout agent (ZCode, Hermes, Perplexity).
> Lire ce fichier EN PREMIER à chaque reprise de session.

---

## 📍 État courant — Lundi 10/08 08:54 CEST

| Champ | Valeur |
|---|---|
| **Branche saine de référence** | `feat/v10-c20-healthy` |
| **HEAD sain** | `2c56432` |
| **Tests branche saine** | **1310/1310 verts** ✅ |
| **Branche live** | `feat/replay-fullstack-v10` |
| **HEAD replay** | `e2fcb3a` (origin) + 2 commits Hermes locaux |
| **Tests replay** | 1290/1310 (20 échecs dette API C9) |
| **Branche base docs** | `feat/v9-foundation-clean` |
| **HEAD base** | `a3b320f` (docs Perplexity 08:02) |
| **Sprint actif** | **S25-OMEGA POST-RAPPORT** |
| **ZCode status** | ✅ Rapport livré — nouvelle mission assignée |
| **Ingestion live** | ✅ port 31685 actif |
| **Anomalie détectée** | ⚠️ EURUSD HTF stale — voir section ci-dessous |

---

## 🆕 Nouveau jalon — `feat/v10-c20-healthy` @ `2c56432`

ZCode a livré son rapport et identifié une **branche saine** :

- **`feat/v10-c20-healthy`** — HEAD `2c56432`
- **1310/1310 tests verts** — suite complète propre
- **Audit kill V9-only passé** : 0 import `core/v9/` dans les modules V10
- Contient les 20 cycles C10→C20 dans un état cohérent et testable
- **Cette branche est la nouvelle source de vérité architecturale**

---

## ⚠️ Anomalie active — EURUSD HTF stale

**Détectée par ZCode dans le rapport live :**
- Les données HTF (H4 / H1) de EURUSD présentent un **stale** (fraîcheur dégradée)
- Impact potentiel : filtre H4 bias désactivé (pass-through C8 BLOCK2) → signaux A3 non filtrés
- **À surveiller** : si l'anomalie persiste > 2 barres M30, déclencher `SessionFilter` manual override

**Vérification :**
```python
import sqlite3, pandas as pd
conn = sqlite3.connect('data/powerflow.db')
df = pd.read_sql("""
    SELECT timeframe, MAX(bar_time) as last_bar,
           ROUND((JULIANDAY('now') - JULIANDAY(MAX(bar_time))) * 24 * 60, 1) as lag_minutes
    FROM forces_snapshots
    WHERE pair = 'EURUSD'
    GROUP BY timeframe
    ORDER BY timeframe
""", conn)
print(df)
conn.close()
# Si lag_minutes > 90 pour H1 ou H4 → stale confirmé
```

---

## 🎯 MISSION IMMÉDIATE ZCODE — Comparaison branches + Recommandation réalignement

### Contexte
Trois branches coexistent avec des états divergents. ZCode doit produire une **analyse comparative objective** et recommander le réalignement du repo.

### Étape 1 — Cartographie des branches

```bash
# Depuis le repo local
git log --oneline feat/v10-c20-healthy | head -10
git log --oneline feat/replay-fullstack-v10 | head -10
git log --oneline feat/v9-foundation-clean | head -10

# Commits présents dans replay mais absents de healthy :
git log --oneline feat/v10-c20-healthy..feat/replay-fullstack-v10

# Commits présents dans healthy mais absents de replay :
git log --oneline feat/replay-fullstack-v10..feat/v10-c20-healthy

# Delta fichiers entre les deux branches :
git diff --stat feat/v10-c20-healthy feat/replay-fullstack-v10
```

### Étape 2 — Tests comparatifs

```bash
# Sur feat/v10-c20-healthy
git checkout feat/v10-c20-healthy
pytest tests/ -q --tb=no 2>&1 | tail -3

# Sur feat/replay-fullstack-v10
git checkout feat/replay-fullstack-v10
pytest tests/ -q --tb=no 2>&1 | tail -3

# Identifier les 20 tests échouants :
pytest tests/ -q --tb=line 2>&1 | grep FAILED
```

### Étape 3 — Audit imports V9 (kill audit)

```bash
# Vérifier qu'aucun module V10 n'importe core/v9/ :
grep -r "from core.v9" core/v10/ --include="*.py"
grep -r "import core.v9" core/v10/ --include="*.py"
# Résultat attendu sur feat/v10-c20-healthy : 0 ligne
# Sur feat/replay-fullstack-v10 : noter les éventuelles violations
```

### Étape 4 — Audit EURUSD HTF stale

```python
import sqlite3, pandas as pd
conn = sqlite3.connect('data/powerflow.db')

# Fraîcheur par paire et TF
df = pd.read_sql("""
    SELECT pair, timeframe,
           MAX(bar_time) as last_bar,
           ROUND((JULIANDAY('now') - JULIANDAY(MAX(bar_time))) * 1440, 1) as lag_min,
           COUNT(*) as total_bars
    FROM forces_snapshots
    WHERE bar_time > datetime('now', '-7 days')
    GROUP BY pair, timeframe
    ORDER BY lag_min DESC
""", conn)
print(df.to_string())

# Focus EURUSD HTF
eurusd = df[df['pair'] == 'EURUSD']
print("\nEURUSD fraîcheur :")
print(eurusd)
conn.close()
```

### Étape 5 — Rapport de réalignement à produire

ZCode produit `reports/repo_realignment_report.json` :

```json
{
  "timestamp": "<ISO UTC>",
  "branches": {
    "feat/v10-c20-healthy": {
      "head": "2c56432",
      "tests": "1310/1310",
      "v9_imports": 0,
      "modules_count": 0,
      "assessment": "REFERENCE_SAINE"
    },
    "feat/replay-fullstack-v10": {
      "head": "<SHA>",
      "tests": "1290/1310",
      "v9_imports": 0,
      "unique_commits": [],
      "assessment": "LIVE_OPERATIONNEL_DETTE_TESTS"
    },
    "feat/v9-foundation-clean": {
      "head": "a3b320f",
      "assessment": "DOCS_ORCHESTRATION"
    }
  },
  "eurusd_htf_stale": {
    "detected": true,
    "h1_lag_minutes": 0,
    "h4_lag_minutes": 0,
    "severity": "LOW|MEDIUM|HIGH",
    "action": "MONITOR|OVERRIDE|HALT"
  },
  "unique_value_replay": [
    "Bridges live (C3-C9 patches)",
    "Fixes bugs C6 DP always-WAIT",
    "Session-aware delta_force C9"
  ],
  "unique_value_healthy": [
    "C10-C20 testés proprement",
    "MasterOrchestrator",
    "DeploymentValidator",
    "LiveConnector",
    "BacktestEngine"
  ],
  "recommendation": {
    "strategy": "MERGE_REPLAY_INTO_HEALTHY | REBASE_HEALTHY_ON_REPLAY | CHERRY_PICK",
    "rationale": "<explication>",
    "steps": [],
    "risk": "LOW|MEDIUM|HIGH",
    "eta_minutes": 0
  },
  "go_live_readiness": {
    "blocking_issues": [],
    "verdict": "NOT_READY|READY_PAPER|READY_LIVE"
  }
}
```

---

## 🛡️ Doctrine active

| Règle | Status |
|---|---|
| R1-AGIR | ✅ action directe sans validation |
| R2 additif pur | ✅ 0 modification modules existants |
| R6-fail-open | ✅ fallback CS proxy si module manquant |
| R9-AUDIT | ✅ JSON rapport complet |
| R10-CAPITAL | ✅ 0 ordre réel — attente GO LIVE CEO |

---

## 📚 Documents clés

- `ORCHESTRATION_UPDATE_2026_08_10_0808.md` — snapshot orchestration ce matin **(lire)**
- `HERMES_PROMPT_MAX.md` — chantiers Hermes parallèles
- `ORCHESTRATION_STATE.md` — état multi-agents et plan merge
- `ZCODE_PROMPT.md` — prompt complet ZCode Full-Stack

---

*Mis à jour par Perplexity CEO No-Limit — 2026-08-10 08:54 CEST*
