#!/usr/bin/env python3
"""v9_cognitive.py — CLI JOURNAL COGNITIF : capture V9 ↔ corrections Søn.

Couche outillage sur `core/v9/cognitive_journal.py`. 0 écriture dans
data/v9_forces.db, 0 modification de core/v9/config.py, orchestrator.py,
principle_engine.py, principles/*.yaml.

Usage :
    python scripts/v9_cognitive.py --log
    python scripts/v9_cognitive.py --correct <id> --narrative "..." --direction "..." [--patterns "a,b"]
    python scripts/v9_cognitive.py --pending [--limit 5]
    python scripts/v9_cognitive.py --lessons [--confidence-min 0.3]
    python scripts/v9_cognitive.py --learn
    python scripts/v9_cognitive.py --watch
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9 import cognitive_journal  # noqa: E402

WATCH_LOG_INTERVAL_S = 300      # log toutes les 5 min
WATCH_LEARN_INTERVAL_S = 1800   # apprend toutes les 30 min


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def run_log(market_db_path: Path | None, db_path: Path | None) -> int:
    reading_id = cognitive_journal.log_v9_reading(market_db_path=market_db_path, db_path=db_path)
    reading = cognitive_journal.get_reading(reading_id, db_path=db_path)
    narrative = reading["v9_narrative"] if reading else ""
    print(f"── LECTURE V9 #{reading_id} ─────────────────────────────")
    print(narrative)
    return 0


def run_correct(
    reading_id: int,
    narrative: str,
    direction: str | None,
    patterns: str | None,
    db_path: Path | None,
) -> int:
    cognitive_journal.log_son_correction(reading_id, narrative, direction, patterns, db_path=db_path)
    print(f"Correction enregistrée pour la lecture #{reading_id}.")
    return 0


def run_pending(limit: int, db_path: Path | None) -> int:
    pending = cognitive_journal.get_pending_corrections(limit=limit, db_path=db_path)
    if not pending:
        print("Aucune lecture en attente de correction.")
        return 0
    print(f"── {len(pending)} LECTURE(S) EN ATTENTE ────────────────")
    for r in pending:
        print(f"#{r['id']} ({r['timestamp']}) direction_v9={r.get('direction_v9') or '—'}")
        print(f"  {r['v9_narrative']}")
    return 0


def run_lessons(confidence_min: float, db_path: Path | None) -> int:
    lessons = cognitive_journal.get_lessons(confidence_min=confidence_min, db_path=db_path)
    if not lessons:
        print(f"Aucune leçon avec confiance >= {confidence_min}.")
        return 0
    print(f"── {len(lessons)} LEÇON(S) APPRISE(S) ──────────────────")
    for lesson in lessons:
        print(f"[{lesson['confidence']:.2f}] {lesson['rule']}")
    return 0


def run_learn(db_path: Path | None) -> int:
    created = cognitive_journal.learn_from_corrections(db_path=db_path)
    if not created:
        print("Aucun nouveau pattern répété (seuil : 3 occurrences).")
        return 0
    print(f"── {len(created)} NOUVELLE(S) LEÇON(S) ─────────────────")
    for lesson in created:
        print(f"[{lesson['confidence']:.2f}] {lesson['rule']}")
    return 0


def run_watch(market_db_path: Path | None, db_path: Path | None) -> int:
    elapsed = 0
    try:
        while True:
            reading_id = cognitive_journal.log_v9_reading(market_db_path=market_db_path, db_path=db_path)
            print(f"[{_now()}] Lecture V9 #{reading_id} capturée.")
            elapsed += WATCH_LOG_INTERVAL_S
            if elapsed >= WATCH_LEARN_INTERVAL_S:
                created = cognitive_journal.learn_from_corrections(db_path=db_path)
                if created:
                    print(f"[{_now()}] {len(created)} nouvelle(s) leçon(s) apprise(s).")
                elapsed = 0
            time.sleep(WATCH_LOG_INTERVAL_S)
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="JOURNAL COGNITIF V9 — capture + corrections Søn.")
    parser.add_argument("--db", type=Path, default=None, help="DB du journal (data/v9_cognitive.db par défaut).")
    parser.add_argument("--market-db", type=Path, default=None, help="DB marché (data/v9_forces.db par défaut).")
    parser.add_argument("--log", action="store_true", help="Capture l'état V9 actuel dans le journal.")
    parser.add_argument("--correct", type=int, default=None, metavar="ID", help="Enregistre une correction Søn.")
    parser.add_argument("--narrative", type=str, default="", help="Narrative de correction (avec --correct).")
    parser.add_argument("--direction", type=str, default=None, help="Direction de correction (avec --correct).")
    parser.add_argument("--patterns", type=str, default=None, help="Patterns CSV (avec --correct).")
    parser.add_argument("--pending", action="store_true", help="Affiche les lectures en attente de correction.")
    parser.add_argument("--limit", type=int, default=5, help="Limite pour --pending.")
    parser.add_argument("--lessons", action="store_true", help="Affiche les leçons apprises.")
    parser.add_argument("--confidence-min", type=float, default=0.3, help="Seuil pour --lessons.")
    parser.add_argument("--learn", action="store_true", help="Lance l'apprentissage sur les corrections.")
    parser.add_argument("--watch", action="store_true", help="Boucle : log/5min, apprend/30min.")
    args = parser.parse_args(argv)

    if args.watch:
        return run_watch(args.market_db, args.db)
    if args.correct is not None:
        return run_correct(args.correct, args.narrative, args.direction, args.patterns, args.db)
    if args.pending:
        return run_pending(args.limit, args.db)
    if args.lessons:
        return run_lessons(args.confidence_min, args.db)
    if args.learn:
        return run_learn(args.db)
    if args.log:
        return run_log(args.market_db, args.db)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
