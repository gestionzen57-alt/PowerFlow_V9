# HERMES PROMPT MAX V2 — PowerFlow V10 | Lundi 10/08/2026 10:23 CEST

> **Généré par Perplexity CEO No-Limit**
> **ZCode en cours : analyse comparaison branches + repo_realignment_report.json**
> **Hermes : chantiers parallèles max pendant que ZCode tourne**
> Doctrine R1/R2/R6/R9/R10 stricte

---

## 📍 État du repo au démarrage de cette session

| Champ | Valeur |
|---|---|
| `feat/replay-fullstack-v10` HEAD | `218b5b3` |
| Tests replay | ✅ **1310/1310** |
| `feat/v10-c20-healthy` HEAD | `2c56432` |
| Tests healthy | ✅ **1310/1310** |
| `feat/v9-foundation-clean` HEAD | `31df487` (docs) |
| ZCode status | 🔄 EN COURS — repo_realignment_report.json |
| EURUSD HTF | ⚠️ STALE 13j — stale gate actif (auto-protégé) |
| Trou données | ❌ 07/08 20:57Z → 10/08 05:21Z exclu walk-forward |
| Ingestion live | ✅ 5/6 paires fraîches |

---

## 🎯 VOS 5 CHANTIERS HERMES — GO MAX PARALLÈLE

---

### ⚡ CHANTIER 1 — EURUSD HTF STALE : DIAGNOSTIC + FIX (P0)

**Problème :** EURUSD H1/M30/M15/M5 stale depuis 27/07 (13 jours). M1 EURUSD est frais. Cause : EA MT4 ne pousse pas les barres HTF EURUSD.

**Étape 1 — Diagnostic EA :**
```bash
# Vérifier quelles paires/TF sont réellement stale
python - <<'EOF'
import sqlite3, pandas as pd
conn = sqlite3.connect('data/powerflow.db')
df = pd.read_sql("""
    SELECT pair, timeframe,
           MAX(bar_time) as last_bar,
           ROUND((JULIANDAY('now') - JULIANDAY(MAX(bar_time))) * 1440, 1) as lag_min,
           COUNT(*) as bars_7j
    FROM forces_snapshots
    WHERE bar_time > datetime('now', '-7 days')
    GROUP BY pair, timeframe
    ORDER BY pair, lag_min DESC
""", conn)
print(df.to_string())
conn.close()
EOF
```

**Étape 2 — Identifier les combos concernés :**
```bash
python - <<'EOF'
import sqlite3, pandas as pd
conn = sqlite3.connect('data/powerflow.db')
stale = pd.read_sql("""
    SELECT pair, timeframe, MAX(bar_time) as last_bar
    FROM forces_snapshots
    GROUP BY pair, timeframe
    HAVING (JULIANDAY('now') - JULIANDAY(MAX(bar_time))) * 1440 > 90
    ORDER BY pair, timeframe
""", conn)
print(f"Combos stale (lag > 90 min) : {len(stale)}")
print(stale.to_string())
conn.close()
EOF
```

**Étape 3 — Patcher le StaleGate si nécessaire :**
- Si `v10_signal_generator_live.py` n'a pas de stale-gate par TF : ajouter R2 additif un wrapper `StaleGuardFilter` dans `core/v10/v10_stale_guard.py`
- Filter : si `lag_minutes[pair][tf] > STALE_THRESHOLD_MINUTES[tf]` → retourner `signal_level = 'NONE'` + logger `stale_blocked`
- Seuils recommandés : `M1=15, M5=30, M15=60, M30=90, H1=240, H4=480`

```python
# core/v10/v10_stale_guard.py (R2 additif pur)
from dataclasses import dataclass
from typing import Dict, Optional
import sqlite3
from datetime import datetime, timezone

STALE_THRESHOLDS = {"M1": 15, "M5": 30, "M15": 60, "M30": 90, "H1": 240, "H4": 480}

@dataclass
class StaleCheckResult:
    pair: str
    tf: str
    lag_minutes: float
    is_stale: bool
    threshold: int
    last_bar: Optional[str] = None

def check_stale(db_path: str, pair: str, tf: str) -> StaleCheckResult:
    """R6 fail-open : si erreur DB, retourner is_stale=False (laisser passer)"""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT MAX(bar_time) FROM forces_snapshots WHERE pair=? AND timeframe=?",
            (pair, tf)
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return StaleCheckResult(pair, tf, 9999, True, STALE_THRESHOLDS.get(tf, 90))
        last_bar = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
        lag = (datetime.now(timezone.utc) - last_bar).total_seconds() / 60
        threshold = STALE_THRESHOLDS.get(tf, 90)
        return StaleCheckResult(pair, tf, round(lag, 1), lag > threshold, threshold, row[0])
    except Exception:
        return StaleCheckResult(pair, tf, 0, False, STALE_THRESHOLDS.get(tf, 90))

def is_combo_fresh(db_path: str, pair: str, tf: str) -> bool:
    return not check_stale(db_path, pair, tf).is_stale
```

**Commit :**
```bash
git add core/v10/v10_stale_guard.py
git add tests/test_v10_stale_guard.py  # écrire 5-8 tests
git commit -m "feat(stale-guard): v10_stale_guard.py — StaleCheckResult + check_stale() + is_combo_fresh() [R2/R6/R9]"
```

---

### ⚡ CHANTIER 2 — WALK-FORWARD PROPRE SANS TROU (P1)

Le trou de données `07/08 20:57Z → 10/08 05:21Z` doit être exclu de tout walk-forward. Implémenter un `DataGapValidator` R2 additif :

```python
# core/v10/v10_data_gap_validator.py
from dataclasses import dataclass, field
from typing import List, Tuple
import sqlite3, pandas as pd

@dataclass
class GapReport:
    pair: str
    tf: str
    gaps: List[Tuple[str, str, float]]  # (start, end, duration_hours)
    total_gap_hours: float
    recommendation: str  # EXCLUDE | WARN | OK

KNOWN_GAPS = [
    ("2026-08-07T20:57:00Z", "2026-08-10T05:21:00Z"),  # weekend capture mort
]

def validate_data_continuity(db_path: str, pair: str, tf: str,
                              since: str = '2026-08-01') -> GapReport:
    """Détecte les trous > 2× la durée nominale d'une barre."""
    TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}
    tf_min = TF_MINUTES.get(tf, 30)
    threshold_min = tf_min * 2.5
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(
            "SELECT bar_time FROM forces_snapshots "
            "WHERE pair=? AND timeframe=? AND bar_time>? ORDER BY bar_time",
            conn, params=(pair, tf, since)
        )
        conn.close()
        if len(df) < 2:
            return GapReport(pair, tf, [], 0, "WARN")
        df['bar_time'] = pd.to_datetime(df['bar_time'], utc=True)
        gaps_min = df['bar_time'].diff().dt.total_seconds().dropna() / 60
        big_gaps = gaps_min[gaps_min > threshold_min]
        gap_list = []
        for idx in big_gaps.index:
            start = str(df.loc[idx-1, 'bar_time'])
            end = str(df.loc[idx, 'bar_time'])
            hrs = round(big_gaps[idx] / 60, 2)
            gap_list.append((start, end, hrs))
        total = sum(g[2] for g in gap_list)
        rec = "EXCLUDE" if total > 24 else ("WARN" if total > 2 else "OK")
        return GapReport(pair, tf, gap_list, total, rec)
    except Exception as e:
        return GapReport(pair, tf, [], 0, f"ERROR:{e}")
```

**Commit :**
```bash
git add core/v10/v10_data_gap_validator.py
git add tests/test_v10_data_gap_validator.py
git commit -m "feat(data-gap): v10_data_gap_validator.py — GapReport + validate_data_continuity() [R2/R9]"
```

---

### ⚡ CHANTIER 3 — LEARNING LOOP : RELANCER SUR DONNÉES FRAÎCHES (P1)

Depuis le trou de données, `LearningContinuum` et `MetaOptimizer` n'ont pas tourné. Relancer sur les données depuis `2026-08-10T05:21Z` :

```python
# scripts/run_learning_cycle_10_08.py
import json, sys
from datetime import datetime, timezone

try:
    from core.v10.v10_learning_continuum import LearningContinuum
    from core.v10.v10_meta_optimizer import MetaOptimizer
    from core.v10.v10_learning_persistence import LearningPersistence
except ImportError as e:
    print(f"[WARN] Import partiel : {e}")

DB = 'data/powerflow.db'
SINCE = '2026-08-10T05:21:00Z'

print(f"[{datetime.now(timezone.utc).isoformat()}] Lancement cycle learning...")

results = {}
try:
    lc = LearningContinuum(db_path=DB)
    r = lc.run_cycle(since=SINCE)
    results['learning_continuum'] = r
    print(f"LearningContinuum : {r}")
except Exception as e:
    results['learning_continuum'] = f'ERROR:{e}'
    print(f"[WARN] LearningContinuum : {e}")

try:
    mo = MetaOptimizer(db_path=DB)
    r = mo.run_cycle()
    results['meta_optimizer'] = r
    print(f"MetaOptimizer : {r}")
except Exception as e:
    results['meta_optimizer'] = f'ERROR:{e}'
    print(f"[WARN] MetaOptimizer : {e}")

try:
    lp = LearningPersistence(db_path=DB)
    lp.save_all()
    results['persistence'] = 'OK'
except Exception as e:
    results['persistence'] = f'ERROR:{e}'

out = f'reports/learning_cycle_2026_08_10.json'
with open(out, 'w') as f:
    json.dump({'ts': datetime.now(timezone.utc).isoformat(),
               'since': SINCE, 'results': results}, f, indent=2, default=str)
print(f"Rapport : {out}")
```

```bash
python scripts/run_learning_cycle_10_08.py
git add reports/learning_cycle_2026_08_10.json
git commit -m "feat(learning): cycle learning 10/08 — données post-trou 05:21Z [R1/R9]"
```

---

### ⚡ CHANTIER 4 — V10_HEALTH_DASHBOARD : SCRIPT MONITORING LIVE (P2)

Un script de monitoring en temps réel pour Søn, lisible en 10 secondes :

```python
# scripts/v10_health_dashboard.py
import sqlite3, pandas as pd
from datetime import datetime, timezone

DB = 'data/powerflow.db'

def main():
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"  PowerFlow V10 — Health Dashboard")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}")

    conn = sqlite3.connect(DB)

    # Fraîcheur par paire/TF
    df = pd.read_sql("""
        SELECT pair, timeframe,
               MAX(bar_time) as last_bar,
               ROUND((JULIANDAY('now') - JULIANDAY(MAX(bar_time))) * 1440, 0) as lag_min
        FROM forces_snapshots
        WHERE bar_time > datetime('now', '-2 days')
        GROUP BY pair, timeframe
        ORDER BY pair, timeframe
    """, conn)

    print("\n📊 FRESHNESS (lag en minutes)")
    pivot = df.pivot(index='pair', columns='timeframe', values='lag_min')
    print(pivot.to_string())

    # Paper trades recents
    try:
        trades = pd.read_sql("""
            SELECT pair, direction, pnl_pips, created_at
            FROM paper_trades
            ORDER BY created_at DESC LIMIT 10
        """, conn)
        print(f"\n📈 10 DERNIERS PAPER TRADES")
        print(trades.to_string(index=False))
        wr = (trades['pnl_pips'] > 0).mean()
        print(f"WR 10 derniers : {wr:.1%}")
    except Exception as e:
        print(f"[paper_trades] {e}")

    # Alertes stale
    stale = df[df['lag_min'] > 90]
    if len(stale):
        print(f"\n🔴 STALE ALERTS ({len(stale)} combos > 90 min)")
        print(stale[['pair', 'timeframe', 'lag_min', 'last_bar']].to_string(index=False))
    else:
        print("\n✅ Tous les combos sont frais (< 90 min)")

    conn.close()
    print(f"\n{'='*60}\n")

if __name__ == '__main__':
    main()
```

```bash
git add scripts/v10_health_dashboard.py
git commit -m "feat(dashboard): v10_health_dashboard.py — freshness + paper trades + stale alerts [R1/R9]"
```

---

### ⚡ CHANTIER 5 — PR VERS MAIN : PRÉPARATION (P2, conditionnel ZCode)

**Atténdre la décision ZCode sur la stratégie de réalignement (A/C/D) avant d'ouvrir la PR.**

Mais dès que ZCode livre `reports/repo_realignment_report.json` :

1. Si stratégie **A** (merge replay → healthy) :
```bash
git checkout feat/v10-c20-healthy
git merge origin/feat/replay-fullstack-v10 --no-ff \
  -m "merge(live-bridges): intégration bridges C3-C9 depuis replay-fullstack [R2/R9]"
pytest tests/ -q
git push origin feat/v10-c20-healthy
```

2. Si stratégie **D** (nouvelle branche unifiée) :
```bash
git checkout -b feat/v10-unified 2c56432
git cherry-pick <sha-bridges-c3> <sha-bridges-c4> ... <sha-bridges-c9>
pytest tests/ -q
git push origin feat/v10-unified
```

3. Ouvrir la PR vers `main` :
```bash
# Perplexity ouvrira la PR via GitHub MCP dès confirmation Hermes
```

---

## 📊 Métriques cibles session V2

| KPI | Actuel | Target |
|---|---|---|
| Tests replay | 1310/1310 ✅ | Maintenir |
| Tests healthy | 1310/1310 ✅ | Maintenir |
| StaleGuard | absent | ✅ livré + testé |
| DataGapValidator | absent | ✅ livré + testé |
| Learning cycle | non relancé | ✅ rapport JSON |
| Health dashboard | absent | ✅ script livré |
| EURUSD HTF | stale 13j | ❓ diagnostic terminal P0 |
| Merge/PR | en attente ZCode | ❓ décision post-rapport |

---

## 🛡️ Doctrine active

| Règle | Application |
|---|---|
| R1-AGIR | Push, scripts, modules sans attendre |
| R2-ADDITIF | 0 modification modules existants — nouveaux fichiers UNIQUEMENT |
| R6-FAIL-OPEN | Tous les scripts : try/except, jamais crash dur |
| R9-AUDIT | Chaque commit tracé, rapports JSON dans `reports/` |
| R10-CAPITAL | ❌ 0 ordre réel — R10 maintenu jusqu'à GO LIVE CEO |

---

## ⚠️ Ce que tu NE fais PAS

- ❌ Ne pas toucher `feat/v10-c20-healthy` avant rapport ZCode
- ❌ Ne pas merger avant validation Perplexity
- ❌ Ne pas lever R10
- ❌ Ne pas modifier les modules core existants (R2 strict)

---

*Généré par Perplexity CEO No-Limit — 2026-08-10 10:23 CEST*
*ZCode : repo_realignment_report.json en cours*
*Hermes : chantiers 1-5 go max*
