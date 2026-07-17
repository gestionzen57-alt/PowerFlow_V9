#!/usr/bin/env python3
"""mcp-v9-strategy-pole — MCP server pour le pôle stratégie V9.

Tools exposés :
- meta() → dict                (métriques méta globales)
- catalogue(min_n) → list     (recalcule + retourne tous les segments)
- top(n, by) → list           (top N stratégies par métrique)
- worst(n, min_n) → list       (bottom N stratégies)
- recommend(principle, session, regime) → dict
- tune(min_n) → list          (grid search TP/SL + sauvegarde overrides)
- save_catalogue() → str      (chemin du fichier sauvegardé)

Doctrine R18 : pas de LLM. Code pur sur data/v9_forces.db.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Permet l'import des modules core.v9
ROOT_DIR = Path(r"C:\projet\V9")
sys.path.insert(0, str(ROOT_DIR))

from core.v9.v9_strategy_pole import (  # noqa: E402
    StrategyCatalogue,
    StrategySelector,
    StrategyTuner,
    compute_meta_metrics,
)


def _serialize(obj: Any) -> Any:
    """Sérialise récursivement les dataclasses en dicts."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


def handle_meta(args: dict) -> dict:
    """Métriques méta globales du paper-trade."""
    try:
        return _serialize(compute_meta_metrics())
    except Exception as exc:
        return {"error": str(exc)}


def handle_catalogue(args: dict) -> dict:
    """Recalcule le catalogue des stratégies. Retourne liste des segments."""
    try:
        min_n = int(args.get("min_n", 20))
        cat = StrategyCatalogue()
        n = cat.recompute(min_n=min_n)
        segments = _serialize(list(cat._cache.values()))
        return {"count": n, "min_n": min_n, "segments": segments}
    except Exception as exc:
        return {"error": str(exc)}


def handle_top(args: dict) -> dict:
    """Top N stratégies par métrique (avg_pips / confidence_score / profit_factor)."""
    try:
        n = int(args.get("n", 5))
        by = args.get("by", "avg_pips")
        min_n = int(args.get("min_n", 10))
        cat = StrategyCatalogue()
        cat.recompute(min_n=min_n)
        top = cat.top(n=n, by=by)
        return {"by": by, "count": len(top), "segments": _serialize(top)}
    except Exception as exc:
        return {"error": str(exc)}


def handle_worst(args: dict) -> dict:
    """Bottom N stratégies par expectancy (n >= min_n)."""
    try:
        n = int(args.get("n", 5))
        min_n = int(args.get("min_n", 20))
        cat = StrategyCatalogue()
        cat.recompute(min_n=min_n)
        worst = cat.worst(n=n, min_n=min_n)
        return {"count": len(worst), "segments": _serialize(worst)}
    except Exception as exc:
        return {"error": str(exc)}


def handle_recommend(args: dict) -> dict:
    """Recommandation stratégique pour (principle, session, regime)."""
    try:
        principle = args.get("principle")
        session = args.get("session")
        regime = args.get("regime")
        if not principle or not session or not regime:
            return {
                "error": "Missing required args: principle, session, regime",
            }
        cat = StrategyCatalogue()
        cat.recompute(min_n=10)
        selector = StrategySelector(catalogue=cat, tuner=StrategyTuner())
        rec = selector.recommend(principle, session, regime)
        return _serialize({
            "principle": rec.principle,
            "session": rec.session,
            "regime": rec.regime,
            "recommended_tp": rec.recommended_tp,
            "recommended_sl": rec.recommended_sl,
            "recommended_strategy": rec.recommended_strategy,
            "confidence": rec.confidence,
            "sample_size": rec.sample_size,
            "source": rec.source,
            "rationale": rec.rationale,
        })
    except Exception as exc:
        return {"error": str(exc)}


def handle_tune(args: dict) -> dict:
    """Tune tous les segments du catalogue (grid search TP/SL)."""
    try:
        min_n = int(args.get("min_n", 20))
        apply_overrides = bool(args.get("apply", True))

        cat = StrategyCatalogue()
        cat.recompute(min_n=min_n)
        tuner = StrategyTuner()
        results = tuner.tune_all(catalogue=cat)

        out = {"count": len(results), "min_n": min_n, "segments": results}
        if apply_overrides and results:
            path = tuner.save_overrides(results)
            out["overrides_path"] = str(path)
        return out
    except Exception as exc:
        return {"error": str(exc)}


def handle_save_catalogue(args: dict) -> dict:
    """Sauvegarde le catalogue dans data/strategy_pole/catalogue.json."""
    try:
        min_n = int(args.get("min_n", 20))
        cat = StrategyCatalogue()
        n = cat.recompute(min_n=min_n)
        path = cat.save_cache()
        return {"saved_segments": n, "path": str(path)}
    except Exception as exc:
        return {"error": str(exc)}


# ── Router stdio MCP ────────────────────────────────────────────────


HANDLERS = {
    "meta": handle_meta,
    "catalogue": handle_catalogue,
    "top": handle_top,
    "worst": handle_worst,
    "recommend": handle_recommend,
    "tune": handle_tune,
    "save_catalogue": handle_save_catalogue,
}


def main() -> int:
    """Point d'entrée stdio MCP. Lit les requêtes JSON-lines sur stdin."""
    print(json.dumps({"ready": True, "server": "v9_strategy_pole", "version": "1.0"}),
          flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            tool = req.get("tool")
            args = req.get("args", {})
            handler = HANDLERS.get(tool)
            if handler is None:
                resp = {"error": f"unknown tool: {tool!r}",
                        "available": list(HANDLERS.keys())}
            else:
                resp = handler(args)
        except json.JSONDecodeError as exc:
            resp = {"error": f"invalid JSON: {exc}"}
        except Exception as exc:
            resp = {"error": f"handler failed: {exc}"}
        print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())