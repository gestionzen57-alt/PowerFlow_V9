#!/usr/bin/env python3
"""mcp-v9-p3-consume — MCP server ciblé pour P3-CONSUME (commit 5e1b9df).

Premier consommateur de seuils adaptatifs : ADAPTIVE_VOL_GATE (SHADOW).
Pattern : value_field sur coalition_strength et antagonism_strength pour
consommer adaptive_coalition_threshold et adaptive_antagonism_threshold
posés dans _load_shared_context par P3-WIRE (commit 1babf14).

Tools exposés (stdin/stdout JSON-RPC simplifié, transport subprocess Hermes) :
- principle(name: str) → dict       (détail d'un principe par nom)
- adaptive_thresholds() → dict      (vol_atr/level état lecture seule)
- principle_stats() → dict         (compte ACTIVE/SHADOW, total)
- shadow_principles() → list[dict]  (liste des SHADOW seulement)
- p3_consume_summary() → dict      (résumé global P3-CONSUME)

Doctrine : R25' (SHADOW par défaut, pas de promotion ACTIVE sans motion CEO).
Lecture seule sur le code + DB, aucun write.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
PRINCIPLES_DIR = ROOT_DIR / "core" / "v9" / "principles"
ADAPTIVE_THRESHOLDS_PATH = ROOT_DIR / "core" / "v9" / "adaptive_thresholds_at_runtime.py"
DOCTRINE_PATH = ROOT_DIR / "docs" / "DOCTRINE.md"


def _list_yaml_files() -> list[Path]:
    return sorted([p for p in PRINCIPLES_DIR.glob("*.yaml")])


def _read_yaml(path: Path) -> dict:
    """Parse minimal d'un YAML de principe (champs principaux)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            out[key] = val
    return out


def handle_principle(args: dict) -> dict:
    """Détail d'un principe par nom (fichier YAML)."""
    name = args.get("name", "").strip()
    if not name:
        return {"error": "name manquant"}
    path = PRINCIPLES_DIR / f"{name}.yaml"
    if not path.exists():
        return {"error": f"principe '{name}' introuvable (cherché: {path})"}
    return {"name": name, "yaml": _read_yaml(path)}


def handle_adaptive_thresholds(args: dict) -> dict:
    """État des seuils adaptatifs (lecture du module P3 pur)."""
    if not ADAPTIVE_THRESHOLDS_PATH.exists():
        return {"error": f"module P3 introuvable: {ADAPTIVE_THRESHOLDS_PATH}"}
    text = ADAPTIVE_THRESHOLDS_PATH.read_text(encoding="utf-8", errors="replace")
    out = {"module": "core/v9/adaptive_thresholds_at_runtime.py"}
    # Extraire VOL_MULTIPLIER
    m = re.search(r"VOL_MULTIPLIER:\s*dict\[str, float\]\s*=\s*\{([^}]+)\}", text)
    if m:
        out["VOL_MULTIPLIER"] = m.group(1).strip()
    m = re.search(r"NEWS_MULTIPLIER:\s*dict\[str, float\]\s*=\s*\{([^}]+)\}", text)
    if m:
        out["NEWS_MULTIPLIER"] = m.group(1).strip()
    m = re.search(r"BASELINE_THRESHOLDS:\s*dict\[str, float\]\s*=\s*\{([^}]+)\}", text)
    if m:
        out["BASELINE_THRESHOLDS"] = m.group(1).strip()
    m = re.search(r"MIN_MULTIPLIER\s*=\s*([\d.]+)", text)
    if m:
        out["MIN_MULTIPLIER"] = m.group(1)
    m = re.search(r"MAX_MULTIPLIER\s*=\s*([\d.]+)", text)
    if m:
        out["MAX_MULTIPLIER"] = m.group(1)
    out["p3_wire_commit"] = "1babf14"
    out["p3_consume_commit"] = "5e1b9df (premier consommateur: ADAPTIVE_VOL_GATE)"
    return out


def handle_principle_stats(args: dict) -> dict:
    """Compte ACTIVE/SHADOW/total dans le catalogue YAML."""
    files = _list_yaml_files()
    active = shadow = 0
    by_kind = {"node_rule": 0, "grammar": 0}
    by_id = []
    for f in files:
        y = _read_yaml(f)
        st = y.get("v9_status") or y.get("status") or "?"
        if st == "ACTIVE":
            active += 1
        elif st == "SHADOW":
            shadow += 1
        kind = y.get("kind", "?")
        if kind in by_kind:
            by_kind[kind] += 1
        by_id.append({"name": f.stem, "status": st, "kind": kind})
    return {
        "total": len(files),
        "active": active,
        "shadow": shadow,
        "by_kind": by_kind,
        "principles": by_id,
    }


def handle_shadow_principles(args: dict) -> dict:
    """Liste des principes SHADOW (R25' : pas de promotion ACTIVE sans motion CEO)."""
    files = _list_yaml_files()
    shadows = []
    for f in files:
        y = _read_yaml(f)
        st = y.get("v9_status") or y.get("status") or "?"
        if st == "SHADOW":
            shadows.append({
                "name": f.stem,
                "kind": y.get("kind", "?"),
                "created_at": y.get("created_at", ""),
                "created_by": y.get("created_by", ""),
                "promoted_at": y.get("promoted_at", "null"),
            })
    return {"count": len(shadows), "shadows": shadows}


def handle_p3_consume_summary(args: dict) -> dict:
    """Résumé global P3-CONSUME pour le level up 2026-07-14."""
    return {
        "p3_consume_commit": "5e1b9df (Hermes, 2026-07-14)",
        "premier_consommateur": "ADAPTIVE_VOL_GATE (SHADOW)",
        "pattern": "value_field sur coalition_strength/antagonism_strength "
                    "consommant adaptive_coalition_threshold/antagonism_threshold",
        "pre_requis": "P3-WIRE ON (V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1)",
        "shadow_mode_2026_07_14": "P2 livré commit 0c0c334, ON par défaut",
        "auto_apply": "Aucun (propose-only, R25' = pas d'auto-promotion)",
        "skill_documentation": "skills/powerflow-v9-p3-consume/SKILL.md (commit 206b7a6)",
        "tests_passing": "1277 + 2 skipped = 0 fail (post P3-CONSUME)",
        "docstring_count": "0 (module pur, pas de LLM dans la boucle, R18)",
    }


HANDLERS = {
    "principle": handle_principle,
    "adaptive_thresholds": handle_adaptive_thresholds,
    "principle_stats": handle_principle_stats,
    "shadow_principles": handle_shadow_principles,
    "p3_consume_summary": handle_p3_consume_summary,
}


def main() -> None:
    from stdio_runtime import serve

    serve(HANDLERS, "v9-p3-consume")


if __name__ == "__main__":
    main()
