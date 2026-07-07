---
name: powerflow-v9-threshold-calibrator
category: mlops
description: Calibration automatique des seuils V9 depuis la DB live. Scan les distributions (ANTAGONISM, PLIURE, COALITION), propose seuils P50/P75/P90/P95 + impact sur nombre de détections. Remplace les calibrations manuelles powerflow-calibration.
trigger: "Calibrer ANTAGONISM_THRESHOLD" | "Recalibrer PLIURE" | "Distribution des écarts de force" | "Combien de coalitions détectées avec seuil X"
tools_needed: [terminal, read_file, execute_code]
---

## 🎯 OBJECTIF

Remplacer les calibrations manuelles (sessions 2026-06 et 2026-07 : ANTAGONISM
10.0→31.39 sur n=218 M5+, PLIURE 3.0→1.7 sur n=1454 M5+) par un scanner SQL
automatique qui :
1. Charge la distribution réelle de l'observable depuis `forces_snapshots`
2. Propose 4-5 quantiles candidats (P50, P75, P90, P95)
3. Pour chaque candidat, calcule l'impact sur le nombre de coalitions /
   antagonismes / pliures détectés
4. Génère un rapport comparatif avant que l'opérateur décide

Contexte : actuellement `core/v9/config.py` contient des seuils en dur
(COALITION_THRESHOLD=5.0, ANTAGONISM_THRESHOLD=31.39, PLIURE_THRESHOLD=1.7),
recalibrés à la main après inspection de 200+ snapshots.

## 🔍 DIAGNOSTIC RAPIDE

```bash
# 1. État actuel des seuils (lecture config)
grep -E "^COALITION_THRESHOLD|^ANTAGONISM_THRESHOLD|^PLIURE_THRESHOLD" core/v9/config.py

# 2. Volume de données disponibles
sqlite3 data/v9_forces.db "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM forces_snapshots WHERE timeframe='M5' AND stale=0;"

# 3. Distribution rapide de l'écart max|force_a - force_b|
sqlite3 data/v9_forces.db "
SELECT
  printf('P50: %.2f', AVG(diff)),
  printf('P90: %.2f', diff) FROM (
    SELECT ABS(force_usd - force_jpy) AS diff FROM forces_snapshots
    WHERE timeframe='M5' AND stale=0
    ORDER BY diff LIMIT 1 OFFSET (SELECT COUNT(*)*50/100 FROM forces_snapshots WHERE timeframe='M5' AND stale=0)
  );"
```

## 🛠️ SCRIPT `scripts/calibrate_threshold.py`

### Étape 1 — Charger la distribution des observables

```python
# scripts/calibrate_threshold.py
import sqlite3
from pathlib import Path
from statistics import quantiles

DB_PATH = Path("data/v9_forces.db")

def load_force_diffs(db_path: Path = DB_PATH, timeframe: str = "M5",
                     min_n: int = 100) -> list[float]:
    """Charge les écarts |force_a - force_b| pour toutes les paires (a,b)
    du panier 8 devises sur tous les snapshots M5+ non-stale. Renvoie une
    liste plate de ~28*paires*N valeurs."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute(
            "SELECT force_usd, force_gbp, force_eur, force_jpy, "
            "       force_cad, force_chf, force_aud, force_nzd "
            "FROM forces_snapshots WHERE timeframe = ? AND stale = 0 "
            "AND is_closed_bar = 1",
            (timeframe,),
        ).fetchall()
    finally:
        conn.close()

    diffs = []
    for r in rows:
        forces = list(r)
        # Toutes les paires (a,b) — 28 paires pour 8 devises
        for i in range(8):
            for j in range(i + 1, 8):
                diffs.append(abs(forces[i] - forces[j]))
    if len(diffs) < min_n:
        raise ValueError(f"Pas assez de données ({len(diffs)} < {min_n})")
    return diffs


def quantile_candidates(diffs: list[float]) -> dict[float, dict]:
    """Renvoie un dict {seuil_candidat: {quantile, count_above}} pour les
    seuils P50, P75, P80, P90, P95."""
    if not diffs:
        return {}
    sorted_diffs = sorted(diffs)
    n = len(sorted_diffs)
    quantiles_pct = quantiles(sorted_diffs, n=100, method="inclusive")
    # quantiles_pct[k] = valeur au k-ème percentile (k=1..99)
    candidates = {}
    for pct in (50, 75, 80, 90, 95):
        idx = min(pct - 1, len(quantiles_pct) - 1)
        val = quantiles_pct[idx]
        count_above = sum(1 for d in sorted_diffs if d >= val)
        candidates[round(val, 2)] = {
            "percentile": pct,
            "count_above": count_above,
            "fraction_above": round(count_above / n, 4),
        }
    return candidates
```

### Étape 2 — Impact sur le nombre de coalitions détectées

```python
def coalition_impact(threshold: float, db_path: Path = DB_PATH,
                     timeframe: str = "M5", n_snapshots: int = 200) -> dict:
    """Simule combien de coalitions (>=2 devises alignées) seraient
    détectées avec ce seuil sur les N derniers snapshots M5+."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute(
            "SELECT force_usd, force_gbp, force_eur, force_jpy, "
            "       force_cad, force_chf, force_aud, force_nzd "
            "FROM forces_snapshots WHERE timeframe = ? AND stale = 0 "
            "AND is_closed_bar = 1 "
            "ORDER BY timestamp DESC LIMIT ?",
            (timeframe, n_snapshots),
        ).fetchall()
    finally:
        conn.close()

    total_coalitions = 0
    snapshots_with_coal = 0
    for r in rows:
        forces = sorted([(i, v) for i, v in enumerate(r)], key=lambda x: x[1])
        clusters = []
        current = [forces[0]]
        for idx, val in forces[1:]:
            if val - current[-1][1] <= threshold:
                current.append((idx, val))
            else:
                if len(current) >= 2:
                    clusters.append(current)
                current = [(idx, val)]
        if len(current) >= 2:
            clusters.append(current)
        total_coalitions += len(clusters)
        if clusters:
            snapshots_with_coal += 1
    return {
        "threshold": threshold,
        "snapshots_analyzed": len(rows),
        "total_coalitions": total_coalitions,
        "snapshots_with_coalition": snapshots_with_coal,
        "mean_coalitions_per_snapshot": round(total_coalitions / max(len(rows), 1), 3),
    }
```

### Étape 3 — Rapport comparatif

```python
def full_report(db_path: Path = DB_PATH, timeframe: str = "M5") -> dict:
    diffs = load_force_diffs(db_path, timeframe)
    candidates = quantile_candidates(diffs)
    report = {"n_diffs": len(diffs), "candidates": {}}
    for threshold, meta in candidates.items():
        impact = coalition_impact(threshold, db_path, timeframe)
        report["candidates"][threshold] = {**meta, **impact}
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(full_report(), indent=2))
```

### Étape 4 — Application du seuil choisi

```python
# Une fois le seuil validé par l'opérateur (sur 200+ snapshots),
# patcher config.py :
#   COALITION_THRESHOLD = 5.0  # ancien
#   COALITION_THRESHOLD = 7.4  # nouveau, après calibration live n=1194

# Toujours committer avec message :
#   fix(v9): <SEUIL>_THRESHOLD recalibre (n=<N>, P<PCT>, ancien=X -> nouveau=Y)
```

## ✅ VALIDATION

```bash
# 1. Le script tourne sans erreur sur la DB live
python scripts/calibrate_threshold.py --timeframe M5 --json | jq '.candidates | length'

# 2. Les counts sont cohérents avec le code (à ±10% près pour M5+)
python -c "
import sqlite3
c = sqlite3.connect('data/v9_forces.db')
n = c.execute('SELECT COUNT(*) FROM scenes WHERE coalitions_json != \"[]\"').fetchone()[0]
print(f'Scenes avec coalitions: {n}')
"

# 3. Tests existants toujours verts
python -m pytest tests/ -q --tb=line | tail -3
```

## 📚 RÉFÉRENCES

- Sessions de calibration passées : ANTAGONISM 10.0→31.39 (commit 460716f, n=218 M5+), PLIURE 3.0→1.7 (commit e9bd9b1, n=1454 M5+)
- Seuils actuels : `core/v9/config.py` lignes COALITION_THRESHOLD / ANTAGONISM_THRESHOLD / PLIURE_THRESHOLD
- Skill connexe : `powerflow-calibration` (calibration manuelle historique) — cette skill la complète, ne la remplace pas