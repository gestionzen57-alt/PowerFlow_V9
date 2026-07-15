---
name: powerflow-v9-replay-benchmark
category: mlops
description: Replay benchmark multi-seuils sur l'historique V9. Orchestre la boucle scene_builder.build_scene() × N seuils candidats × M snapshots, mesure distributions de confiance + win-rate par seuil, génère rapport comparatif.
trigger: '"Valider changement de seuil sur historique" | "Replay ANTAGONISM vs 50" | "Quel seuil maximise win_rate" | "Tester impact PLIURE sur 1194 snapshots"'
tools_needed: [terminal, execute_code, write_file]
---

## 🎯 OBJECTIF

Valider un changement de seuil (ANTAGONISM_THRESHOLD, PLIURE_THRESHOLD,
COALITION_THRESHOLD, ou nouveau seuil de la Tâche A/B/C) sur l'historique
live V9 sans attendre des semaines de paper-trading. Orchestre :

1. Snapshot de la DB live (forces_snapshots + scenes déjà construites)
2. Re-build de chaque scène avec chaque seuil candidat
3. Calcul de métriques par seuil (win_rate, mean_confidence, n_detections,
   latence)
4. Rapport Markdown comparatif avec recommandation

Contexte : `scripts/regenerate_chain.py` sait rejouer une scène, mais ne
bench pas plusieurs seuils en parallèle. Cette skill ajoute la dimension
"compare N seuils sur le même historique".

## 🔍 DIAGNOSTIC RAPIDE

```bash
# 1. Volume de scènes disponibles
sqlite3 data/v9_forces.db "SELECT COUNT(*) FROM scenes WHERE stale=0;"

# 2. Issues de replay disponibles (WIN/LOSS)
test -f data/replay_outcomes.json && jq 'length' data/replay_outcomes.json

# 3. Latence moyenne actuelle de build_scene
python -c "
import sqlite3, time
from core.v9.scene_builder import SceneBuilder
b = SceneBuilder()
c = sqlite3.connect('data/v9_forces.db')
n = 0; t0 = time.perf_counter()
for sid in c.execute('SELECT scene_id FROM scenes ORDER BY timestamp DESC LIMIT 100').fetchall():
    b.build_scene(sid[0]); n += 1
print(f'{n} scenes in {time.perf_counter()-t0:.2f}s ({(time.perf_counter()-t0)/n*1000:.0f}ms/scene)')
"
```

## 🛠️ SCRIPT `scripts/replay_benchmark.py`

### Étape 1 — Snapshot de la DB vers DB éphémère

```python
# scripts/replay_benchmark.py
import shutil
import sqlite3
from pathlib import Path

def snapshot_db(src: Path = Path("data/v9_forces.db"),
                dst: Path = Path("data/v9_replay_bench.db")) -> Path:
    """Copie la DB live vers une DB éphémère pour ne pas polluer la prod."""
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)
    # Aussi copier -wal et -shm si présents (WAL mode)
    for ext in ("-wal", "-shm"):
        p = src.with_suffix(src.suffix + ext)
        if p.exists():
            shutil.copy2(p, dst.with_suffix(dst.suffix + ext))
    return dst
```

### Étape 2 — Re-build d'une scène avec un seuil custom

```python
def rebuild_scene_with_threshold(scene_id: str, db_path: Path,
                                 threshold_overrides: dict) -> dict:
    """Reconstruit une scène avec seuils custom. threshold_overrides est
    un dict {nom: valeur} parmi {'coalition_threshold', 'antagonism_threshold',
    'pliure_threshold'}."""
    from core.v9.scene_builder import SceneBuilder
    builder = SceneBuilder(db_path=db_path, config=threshold_overrides)
    return builder.build_scene(scene_id)
```

### Étape 3 — Calcul de métriques par seuil

```python
def compute_metrics(scene: dict, threshold_name: str, new_value: float) -> dict:
    """Métriques observables d'une scène re-buildée avec un seuil donné."""
    coalitions = scene.get("coalitions", [])
    antagonismes = scene.get("antagonismes", [])
    cin = scene.get("cinematique_locale", {})
    risk = scene.get("risk_assessment", {})
    return {
        "scene_id": scene["scene_id"],
        "n_coalitions": len(coalitions),
        "n_antagonismes": len(antagonismes),
        "max_coalition_intensite": max((c.get("intensite_alignement", 0) for c in coalitions), default=0.0),
        "max_antagonisme_intensite": max((a.get("intensite_conflit", 0) for a in antagonismes), default=0.0),
        "pliure_detectee": cin.get("pliure", {}).get("detectee", False),
        "pliure_severite": cin.get("pliure", {}).get("severite"),
        "risk_sentiment": risk.get("risk_sentiment"),
        "risk_confidence": risk.get("risk_confidence", 0),
    }


def aggregate_metrics(per_scene_metrics: list[dict]) -> dict:
    """Agrège les métriques d'un benchmark sur N scènes."""
    if not per_scene_metrics:
        return {}
    n = len(per_scene_metrics)
    return {
        "n_scenes": n,
        "mean_coalitions_per_scene": round(sum(m["n_coalitions"] for m in per_scene_metrics) / n, 3),
        "mean_antagonismes_per_scene": round(sum(m["n_antagonismes"] for m in per_scene_metrics) / n, 3),
        "pct_pliure_detectee": round(sum(1 for m in per_scene_metrics if m["pliure_detectee"]) / n * 100, 2),
        "risk_sentiment_distribution": _distribution(m["risk_sentiment"] for m in per_scene_metrics),
        "mean_risk_confidence": round(sum(m["risk_confidence"] for m in per_scene_metrics) / n, 1),
    }

def _distribution(items):
    from collections import Counter
    return dict(Counter(items))
```

### Étape 4 — Boucle de benchmark

```python
import json
import time
from datetime import datetime, timezone

def run_benchmark(scene_ids: list[str], db_path: Path,
                  threshold_name: str, candidates: list[float],
                  output_path: Path = Path("docs/benchmarks/benchmark_<TS>.md")
                  ) -> dict:
    """Pour chaque seuil candidat, re-joue toutes les scènes et agrège."""
    results = {"threshold_name": threshold_name, "candidates": {}}
    t_start = time.perf_counter()

    for value in candidates:
        per_scene = []
        for sid in scene_ids:
            scene = rebuild_scene_with_threshold(sid, db_path, {threshold_name: value})
            metrics = compute_metrics(scene, threshold_name, value)
            per_scene.append(metrics)
        agg = aggregate_metrics(per_scene)
        results["candidates"][value] = agg
        print(f"  {threshold_name}={value}: {agg['mean_coalitions_per_scene']:.2f} coal/scene, "
              f"{agg['pct_pliure_detectee']:.1f}% pliure")

    results["elapsed_s"] = round(time.perf_counter() - t_start, 2)
    results["n_scenes"] = len(scene_ids)

    # Générer le rapport Markdown
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_report(results), encoding="utf-8")
    return results


def _format_report(results: dict) -> str:
    md = [f"# Benchmark {results['threshold_name']} — {results['n_scenes']} scènes\n"]
    md.append(f"_Généré le {datetime.now(timezone.utc).isoformat()} — "
              f"durée: {results['elapsed_s']}s_\n")
    md.append("| Seuil | Coal/scène | Antag/scène | % Pliure | % RISK_ON | "
              "Mean Conf |")
    md.append("|---:|---:|---:|---:|---:|---:|")
    for val, agg in results["candidates"].items():
        rs_dist = agg.get("risk_sentiment_distribution", {})
        pct_risk_on = round(rs_dist.get("RISK_ON", 0) / max(results["n_scenes"], 1) * 100, 1)
        md.append(f"| {val} | {agg['mean_coalitions_per_scene']} | "
                  f"{agg['mean_antagonismes_per_scene']} | {agg['pct_pliure_detectee']} | "
                  f"{pct_risk_on} | {agg['mean_risk_confidence']} |")
    return "\n".join(md) + "\n"
```

### Étape 5 — Lancement type

```bash
# Benchmark ANTAGONISM_THRESHOLD sur 200 dernières scènes M5+
python scripts/replay_benchmark.py \
  --threshold antagonism_threshold \
  --candidates 25.0,28.0,31.39,35.0,40.0 \
  --n-scenes 200 \
  --timeframe M5 \
  --output docs/benchmarks/bench_antagonism_$(date +%Y%m%d).md
```

## ✅ VALIDATION

```bash
# 1. Le benchmark tourne en < 60s pour 200 scènes × 5 seuils
time python scripts/replay_benchmark.py --threshold coalition_threshold \
  --candidates 4.0,5.0,6.0 --n-scenes 50 --timeframe M5

# 2. Le rapport est généré et lisible
test -f docs/benchmarks/bench_*.md && head -20 docs/benchmarks/bench_*.md

# 3. Tests existants toujours verts (la DB éphémère n'a pas pollué la prod)
python -m pytest tests/ -q --tb=line | tail -3
```

## 📚 RÉFÉRENCES

- `scripts/regenerate_chain.py` : rejoue UNE scène avec config par défaut
- `core/v9/scene_builder.py:SceneBuilder.__init__` : accepte config dict pour surcharger seuils
- Format rapport : inspiré de `docs/checkpoints/CHECKPOINT_*.md` (sections tableaux)
- Skill connexe : `powerflow-v9-threshold-calibrator` (propose les seuils candidats à tester)