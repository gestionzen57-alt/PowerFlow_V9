---
name: powerflow-v9-scene-diff
category: data-science
description: "Diff structurel entre 2 scènes V9 consécutives du même (symbol, timeframe). Affiche ce qui a changé : coalitions apparues/disparues, rotation de leadership, bascule, risk_sentiment, regime, pliure. Sortie Markdown lisible."
trigger: "Que s'est-il passé entre cette scène et la précédente | Diff entre scene-X et scene-Y | Snapshot de l'évolution d'une scène | Pourquoi le sentiment est passé de RISK_ON à RISK_OFF"
tools_needed: [terminal, read_file, execute_code, write_file]
---

## 🎯 OBJECTIF

Répondre en 10 secondes à "que s'est-il passé entre cette scène et la
précédente ?" en extrayant les deltas structurels :

- Coalitions : apparues / disparues / composition changée
- Rotation de leadership : detectée ? ancien → nouveau
- Bascule d'équilibre : nouvelle ? même sens / inversion
- Risk sentiment : RISK_ON → RISK_OFF ? confidence delta ?
- Cinématique : pliure, pente, vitesse
- Regime : type, cassure, mean_reversion
- Zone : compression/extension, niveau référence

Contexte : pendant le paper-trading, l'opérateur regarde une scène X et
veut comprendre l'évolution depuis la scène X-1 du même (symbol, TF).
Actuellement il faut ouvrir 2 fichiers JSON et comparer à l'œil.

## 🔍 DIAGNOSTIC RAPIDE

```bash
# 1. Lister les 2 scènes à comparer (par scene_id OU timestamp range)
sqlite3 data/v9_forces.db "
SELECT scene_id, timestamp, timeframes_concernes FROM scenes
WHERE forces_snapshot_ref IN (
  SELECT snapshot_id FROM forces_snapshots WHERE symbol='EURUSD' AND timeframe='M5'
)
ORDER BY timestamp DESC LIMIT 2;
"

# 2. Charger les JSON complets des 2 scènes
sqlite3 -json data/v9_forces.db "
SELECT scene_id, timestamp, coalitions_json, antagonismes_json,
       cinematique_json, confluences_mtf_json, risque_json, regime_json
FROM scenes WHERE scene_id IN ('scene-prev', 'scene-curr');
" > /tmp/scenes_diff.json
```

## 🛠️ SCRIPT `scripts/scene_diff.py`

### Étape 1 — Charger et normaliser 2 scènes

```python
# scripts/scene_diff.py
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/v9_forces.db")

def load_scene_by_id(scene_id: str, db_path: Path = DB_PATH) -> dict:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        row = conn.execute(
            "SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"scene {scene_id!r} introuvable")
        # Convertir Row en dict + parser les JSON
        d = dict(row)
        for col in ("coalitions_json", "antagonismes_json", "cinematique_json",
                    "confluences_mtf_json", "contexte_temporel_json",
                    "risk_assessment_json", "zone_json"):
            raw = d.get(col)
            try:
                d[col.replace("_json", "")] = json.loads(raw) if raw else {}
            except (TypeError, ValueError):
                d[col.replace("_json", "")] = {}
        return d
    finally:
        conn.close()


def load_consecutive_scenes(symbol: str, timeframe: str,
                            db_path: Path = DB_PATH) -> tuple[dict, dict]:
    """Charge les 2 dernières scènes du même (symbol, timeframe)."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        rows = conn.execute(
            "SELECT s.scene_id FROM scenes s "
            "JOIN forces_snapshots f ON f.snapshot_id = s.forces_snapshot_ref "
            "WHERE f.symbol = ? AND f.timeframe = ? AND s.stale = 0 "
            "ORDER BY s.timestamp DESC LIMIT 2",
            (symbol, timeframe),
        ).fetchall()
        if len(rows) < 2:
            raise ValueError(f"<2 scènes pour {symbol} {timeframe}")
        scene_ids = [r[0] for r in rows]
        # Plus récente en premier, plus ancienne en second
        return load_scene_by_id(scene_ids[0], db_path), load_scene_by_id(scene_ids[1], db_path)
    finally:
        conn.close()
```

### Étape 2 — Calcul des deltas par dimension

```python
def coalition_delta(prev: dict, curr: dict) -> dict:
    """Compare les coalitions par composition (frozenset)."""
    def coalition_keys(scene):
        keys = {}
        for c in scene.get("coalitions", []):
            key = frozenset(c.get("devises_alignees", []))
            keys[key] = c
        return keys
    p_keys, c_keys = coalition_keys(prev), coalition_keys(curr)
    return {
        "appeared": [list(k) for k in c_keys.keys() - p_keys.keys()],
        "disappeared": [list(k) for k in p_keys.keys() - c_keys.keys()],
        "persisted": [list(k) for k in c_keys.keys() & p_keys.keys()],
        "intensity_drift": {
            list(k): {
                "prev": p_keys[k].get("intensite_alignement"),
                "curr": c_keys[k].get("intensite_alignement"),
                "delta": round(c_keys[k].get("intensite_alignement", 0)
                              - p_keys[k].get("intensite_alignement", 0), 3),
                "age_bars": c_keys[k].get("age_bars"),
                "trend": c_keys[k].get("intensite_trend"),
            }
            for k in c_keys.keys() & p_keys.keys()
        },
    }


def rotation_delta(prev: dict, curr: dict) -> dict:
    """Toutes les rotations de leadership entre les 2 scènes."""
    rotations = []
    for c in curr.get("coalitions", []):
        rot = c.get("rotation_leadership", {})
        if rot.get("detectee"):
            rotations.append({
                "devises": c.get("devises_alignees"),
                "ancien_leader": rot.get("ancien_leader"),
                "nouveau_leader": rot.get("nouveau_leader"),
            })
    return {"detected": rotations}


def bascule_delta(prev: dict, curr: dict) -> dict:
    """Bascule d'équilibre dans les antagonismes."""
    prev_basc = {frozenset(a["devises_en_conflit"]): a.get("bascule_equilibre")
                 for a in prev.get("antagonismes", [])
                 if a.get("bascule_equilibre", {}).get("detectee")}
    curr_basc = {frozenset(a["devises_en_conflit"]): a.get("bascule_equilibre")
                 for a in curr.get("antagonismes", [])
                 if a.get("bascule_equilibre", {}).get("detectee")}
    new_pairs = [list(k) for k in curr_basc.keys() - prev_basc.keys()]
    same_sens = []
    sens_inversion = []
    for pair in curr_basc.keys() & prev_basc.keys():
        prev_sens = prev_basc[pair].get("sens")
        curr_sens = curr_basc[pair].get("sens")
        if prev_sens and curr_sens:
            if prev_sens == curr_sens:
                same_sens.append({"pair": list(pair), "sens": curr_sens})
            else:
                sens_inversion.append({
                    "pair": list(pair),
                    "avant": prev_sens,
                    "apres": curr_sens,
                })
    return {"new": new_pairs, "same_sens": same_sens, "inversion": sens_inversion}


def risk_delta(prev: dict, curr: dict) -> dict:
    """Risk sentiment + confidence."""
    p_risk = prev.get("risk_assessment", {})
    c_risk = curr.get("risk_assessment", {})
    return {
        "sentiment_changed": p_risk.get("risk_sentiment") != c_risk.get("risk_sentiment"),
        "prev_sentiment": p_risk.get("risk_sentiment"),
        "curr_sentiment": c_risk.get("risk_sentiment"),
        "confidence_delta": c_risk.get("risk_confidence", 0) - p_risk.get("risk_confidence", 0),
        "persistance_confirmee": c_risk.get("persistance_confirmee"),
    }


def cinematique_delta(prev: dict, curr: dict) -> dict:
    """Pente, pliure, vitesse."""
    p_cin = prev.get("cinematique_locale", {})
    c_cin = curr.get("cinematique_locale", {})
    return {
        "pente_prev": p_cin.get("pente"),
        "pente_curr": c_cin.get("pente"),
        "pliure_newly_detected": (
            c_cin.get("pliure", {}).get("detectee")
            and not p_cin.get("pliure", {}).get("detectee")
        ),
        "pliure_severite": c_cin.get("pliure", {}).get("severite"),
        "velocite_delta": round(
            c_cin.get("velocite_moyenne", 0) - p_cin.get("velocite_moyenne", 0), 6),
    }
```

### Étape 3 — Rapport Markdown

```python
def format_diff_report(prev: dict, curr: dict) -> str:
    """Génère un rapport Markdown lisible du diff entre 2 scènes."""
    coal = coalition_delta(prev, curr)
    rot = rotation_delta(prev, curr)
    basc = bascule_delta(prev, curr)
    risk = risk_delta(prev, curr)
    cin = cinematique_delta(prev, curr)

    md = [f"# Scene Diff — {curr['symbol']} {curr['timeframe']}\n"]
    md.append(f"- **prev**: `{prev['scene_id']}` @ {prev['timestamp']}")
    md.append(f"- **curr**: `{curr['scene_id']}` @ {curr['timestamp']}\n")

    md.append("## Coalitions")
    if coal["appeared"]:
        md.append(f"- Apparues: {coal['appeared']}")
    if coal["disappeared"]:
        md.append(f"- Disparues: {coal['disappeared']}")
    if coal["intensity_drift"]:
        md.append("- Persistees avec drift:")
        for k, v in coal["intensity_drift"].items():
            md.append(f"  - {k}: {v['prev']} → {v['curr']} (Δ {v['delta']:+}, "
                      f"age={v['age_bars']}, trend={v['trend']})")

    md.append("\n## Rotations de leadership")
    if rot["detected"]:
        for r in rot["detected"]:
            md.append(f"- {r['devises']}: {r['ancien_leader']} → {r['nouveau_leader']}")
    else:
        md.append("- Aucune")

    md.append("\n## Bascules d'équilibre")
    if basc["new"]:
        md.append(f"- Nouvelles: {basc['new']}")
    if basc["inversion"]:
        md.append("- Inversées:")
        for inv in basc["inversion"]:
            md.append(f"  - {inv['pair']}: {inv['avant']} → {inv['apres']}")
    if not basc["new"] and not basc["inversion"]:
        md.append("- Aucune nouvelle ni inversion")

    md.append("\n## Risk Sentiment")
    md.append(f"- {risk['prev_sentiment']} → {risk['curr_sentiment']} "
              f"(Δ conf {risk['confidence_delta']:+})")
    md.append(f"- Persistance confirmée: {risk['persistance_confirmee']}")

    md.append("\n## Cinématique")
    md.append(f"- Pente: {cin['pente_prev']} → {cin['pente_curr']}")
    if cin["pliure_newly_detected"]:
        md.append(f"- ⚠️ Pliure nouvellement détectée (sévérité {cin['pliure_severite']})")
    md.append(f"- Δ vélocité: {cin['velocite_delta']:+.6f}")

    return "\n".join(md) + "\n"


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--timeframe", default="M5")
    p.add_argument("--output", default=None, help="Chemin de sortie .md")
    args = p.parse_args()

    curr, prev = load_consecutive_scenes(args.symbol, args.timeframe)
    report = format_diff_report(prev, curr)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report)
```

### Étape 4 — Lancement type

```bash
# Diff des 2 dernières scènes EURUSD M5
python scripts/scene_diff.py --symbol EURUSD --timeframe M5

# Sauvegarder pour archivage
python scripts/scene_diff.py --symbol GBPUSD --timeframe M15 \
  --output docs/diffs/$(date +%Y%m%d)_gbpusd_m15.md
```

## ✅ VALIDATION

```bash
# 1. Le script tourne sans erreur sur la DB live
python scripts/scene_diff.py --symbol EURUSD --timeframe M5 | head -10

# 2. Le rapport contient les sections attendues
python scripts/scene_diff.py --symbol EURUSD --timeframe M5 | grep -E "^## "

# 3. Les deltas reflètent l'état réel des DB
sqlite3 data/v9_forces.db "SELECT risk_sentiment FROM risk_assessment LIMIT 5;"
```

## 📚 RÉFÉRENCES

- Sources : `core/v9/scene_builder.py:build_scene`, `core/v9/risk_meter.py:assess`
- Champs JSON parsés : `coalitions_json`, `antagonismes_json`, `cinematique_json`,
  `confluences_mtf_json`, `risk_assessment_json`, `zone_json`
- Skill connexe : `powerflow-recit-causal` (vue narrative sur plusieurs scènes),
  cette skill est le zoom local entre 2 scènes