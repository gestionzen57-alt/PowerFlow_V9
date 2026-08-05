"""V10 Dataset Refresh — garde v10_signals_clean frais (Levier 2, Phase 33).

Diagnostic 2026-08-05 : v10_signals_clean figé au 2026-08-04T21:35 (le
daemon scanner tué par Ctrl+C le 04/08 16:15, LastTaskResult
0xC000013A). Le pipeline entier (paper trader, walk-forward,
calibrateurs) tournait sur des données d'hier soir.

Ce script régénère le dataset propre (truncate_first + INSERT) puis
écrit un rapport JSON. À planifier toutes les heures (Windows Task
Scheduler) : python scripts/v10_dataset_refresh.py

Output : reports/v10_dataset_refresh_YYYYMMDD.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_signal_generator_live import generate_clean_dataset  # noqa: E402

DB_PATH = str(ROOT / "data" / "v9_forces.db")
REPORTS_DIR = ROOT / "reports"


def main() -> int:
    ts = datetime.now(timezone.utc).isoformat()
    report = generate_clean_dataset(DB_PATH, truncate_first=True,
                                    timestamp=ts)
    d = report.as_dict()
    d["generated_at"] = ts
    d["status"] = "OK" if d.get("n_signals_persisted", 0) > 0 else "EMPTY"
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"v10_dataset_refresh_{datetime.now(timezone.utc):%Y%m%d}.json"
    out.write_text(json.dumps(d, indent=1, default=str), encoding="utf-8")
    print(f"[V10 DATASET REFRESH {datetime.now(timezone.utc):%H:%M:%S}Z] "
          f"signaux={d.get('n_signals_persisted', 0)} "
          f"snapshots={d.get('n_snapshots_loaded', 0)} "
          f"→ {out.name}")
    return 0 if d.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
