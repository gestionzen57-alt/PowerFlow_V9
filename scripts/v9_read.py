#!/usr/bin/env python3
"""v9_read.py — MODE LECTURE V9 : « qu'est-ce que tu vois ? »

CLI de lecture seule sur data/v9_forces.db, appuyé sur
core/v9/memory_query.py. Aucune écriture DB, aucune logique de trading,
0 modification du pipeline existant.

Usage :
    python scripts/v9_read.py                    # narrative courte (6 lignes)
    python scripts/v9_read.py --deep              # état complet + mémoire
    python scripts/v9_read.py --scene <scene_id>  # détail d'une scène + similitudes
    python scripts/v9_read.py --watch             # boucle de rafraîchissement 30s
    python scripts/v9_read.py --yaml <principle_id>  # historique d'un principe
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.memory_query import (  # noqa: E402
    find_similar_scenes,
    get_current_state,
    get_market_narrative,
    get_yaml_triggers_history,
)

WATCH_INTERVAL_SECONDS = 30


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _fmt(value: object, default: str = "—") -> object:
    return value if value not in (None, "") else default


def render_current_state(db_path: Path | None = None) -> str:
    state = get_current_state(db_path=db_path)
    if not state:
        return "État courant : aucune donnée (DB absente)."

    scene = state.get("scene") or {}
    behavior = state.get("behavior") or {}
    window = state.get("window") or {}
    exploit = state.get("exploitability") or {}
    regime = state.get("regime") or {}
    signals = state.get("signals") or []
    decisions = state.get("decisions") or []
    principles = state.get("principle_evaluations") or []

    lines = ["── ÉTAT COURANT ─────────────────────────────────────────"]
    lines.append(f"Scène          : {_fmt(scene.get('scene_id'))} ({_fmt(scene.get('timestamp'))})")
    lines.append(
        f"Comportement   : {_fmt(behavior.get('qualification'))} "
        f"— confiance {_fmt(behavior.get('confiance_qualification'))}/100"
    )
    lines.append(
        f"Fenêtre        : {_fmt(window.get('statut'))} "
        f"— confiance {_fmt(window.get('niveau_confiance'))}/100"
    )
    lines.append(
        f"Exploitabilité : {_fmt(exploit.get('statut'))} "
        f"— confiance {_fmt(exploit.get('niveau_confiance_global'))}/100"
    )
    lines.append(f"Régime         : {_fmt(regime.get('regime_type'))}")

    lines.append(f"Signaux récents ({len(signals)}) :")
    for s in signals:
        lines.append(
            f"  - {_fmt(s.get('direction'))} conf={_fmt(s.get('confiance'))} "
            f"{_fmt(s.get('symbol'))}/{_fmt(s.get('timeframe'))}"
        )

    lines.append(f"Décisions récentes ({len(decisions)}) :")
    for d in decisions:
        lines.append(
            f"  - {_fmt(d.get('action'))} {_fmt(d.get('direction'))} "
            f"{_fmt(d.get('symbol'))}/{_fmt(d.get('timeframe'))}"
        )

    lines.append(f"Principes déclenchés récemment ({len(principles)}) :")
    for p in principles:
        lines.append(
            f"  - {_fmt(p.get('principle_id'))} "
            f"({_fmt(p.get('direction'))}, conf={_fmt(p.get('confidence'))})"
        )

    return "\n".join(lines)


def render_similar_scenes(scene_id: str, db_path: Path | None = None) -> str:
    similar = find_similar_scenes(scene_id, db_path=db_path)
    if not similar:
        return f"Aucune scène similaire trouvée pour {scene_id} (7 derniers jours)."

    lines = [f"── SCÈNES SIMILAIRES À {scene_id} ──────────────────────"]
    for s in similar:
        outcome = s.get("outcome") or "en cours"
        lines.append(
            f"  score={s['score']:<5.0f} {_fmt(s.get('timestamp'))}  "
            f"comportement={_fmt(s.get('qualification'))}  "
            f"fenêtre={_fmt(s.get('window_statut'))}  outcome={outcome}"
        )
    return "\n".join(lines)


def render_yaml_triggers(hours: int = 24, db_path: Path | None = None) -> str:
    hist = get_yaml_triggers_history(hours=hours, db_path=db_path)
    if not hist or not hist.get("per_principle"):
        return f"Aucun principe déclenché sur les dernières {hours}h."

    lines = [f"── PRINCIPES DÉCLENCHÉS (dernières {hours}h) ────────────"]
    for pid in hist.get("top5", []):
        entry = hist["per_principle"][pid]
        lines.append(
            f"  {pid:<28} déclenchements={entry['count']:<4} "
            f"conf_moy={_fmt(entry.get('confiance_moyenne'))} "
            f"direction={_fmt(entry.get('direction_dominante'))}"
        )
    return "\n".join(lines)


def render_yaml_detail(name: str, hours: int = 24, db_path: Path | None = None) -> str:
    hist = get_yaml_triggers_history(hours=hours, db_path=db_path)
    entry = (hist.get("per_principle") or {}).get(name)
    if entry is None:
        return f"{name} : aucun déclenchement sur les dernières {hours}h."
    return (
        f"── {name} — dernières {hours}h ───────────────────────────\n"
        f"Déclenchements   : {entry['count']}\n"
        f"Confiance moy.   : {_fmt(entry.get('confiance_moyenne'))}\n"
        f"Direction domin. : {_fmt(entry.get('direction_dominante'))}"
    )


def render_deep(db_path: Path | None = None) -> str:
    parts = [get_market_narrative(db_path=db_path), "", render_current_state(db_path)]

    state = get_current_state(db_path=db_path)
    scene = (state or {}).get("scene") or {}
    if scene.get("scene_id"):
        parts += ["", render_similar_scenes(scene["scene_id"], db_path)]

    parts += ["", render_yaml_triggers(db_path=db_path)]
    return "\n".join(parts)


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def run_watch(db_path: Path | None = None, interval: float = WATCH_INTERVAL_SECONDS) -> int:
    try:
        while True:
            clear_screen()
            print(get_market_narrative(db_path=db_path))
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="MODE LECTURE V9 — qu'est-ce que tu vois ?"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--deep", action="store_true", help="État complet + mémoire")
    parser.add_argument("--scene", type=str, default=None, help="Détail d'une scène + similitudes")
    parser.add_argument("--watch", action="store_true", help="Boucle de rafraîchissement (30s)")
    parser.add_argument("--yaml", type=str, default=None, help="Historique d'un principe")
    args = parser.parse_args(argv)

    if args.watch:
        return run_watch(args.db)
    if args.scene:
        print(render_similar_scenes(args.scene, args.db))
        return 0
    if args.yaml:
        print(render_yaml_detail(args.yaml, db_path=args.db))
        return 0
    if args.deep:
        print(render_deep(args.db))
        return 0

    print(get_market_narrative(db_path=args.db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
