#!/usr/bin/env python
"""v9_walk_forward.py — Lance la validation walk-forward et écrit le rapport.

Un edge mesuré sur tout l'historique peut être un artefact d'optimisation.
Ce script répond à : « le seuil calibré sur le passé tient-il sur le futur
jamais vu ? » — la seule question qui distingue un edge réel de l'overfitting.

Usage :
    python scripts/v9_walk_forward.py                       # global, 5 fenêtres
    python scripts/v9_walk_forward.py --windows 6
    python scripts/v9_walk_forward.py --symbol GBPUSD
    python scripts/v9_walk_forward.py --out docs/reports/walk_forward_20260718.md

Doctrine : R18 (code pur), R2 (lecture seule, ne modifie aucune calibration).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Racine projet dans le path (exécution directe).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v9.walk_forward import (  # noqa: E402
    DEFAULT_N_WINDOWS,
    WalkForwardValidator,
    render_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validation walk-forward V9")
    parser.add_argument("--windows", type=int, default=DEFAULT_N_WINDOWS,
                        help=f"Nombre de fenêtres (défaut {DEFAULT_N_WINDOWS})")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Restreindre à un symbole (défaut : tous)")
    parser.add_argument("--db", type=str, default=None, help="Chemin DB alternatif")
    parser.add_argument("--out", type=str, default=None,
                        help="Fichier Markdown de sortie (défaut : "
                             "docs/reports/walk_forward_<date>.md)")
    parser.add_argument("--json", action="store_true",
                        help="Affiche aussi le JSON sur stdout")
    args = parser.parse_args()

    validator = WalkForwardValidator(db_path=args.db)
    report = validator.run(n_windows=args.windows, symbol=args.symbol)

    now = datetime.now(timezone.utc)
    md = render_markdown(report, generated_at=now.isoformat())

    if args.out:
        out_path = Path(args.out)
    else:
        scope = args.symbol or "all"
        out_path = Path("docs/reports") / (
            f"walk_forward_{now:%Y%m%d}"
            f"{'' if scope == 'all' else '_' + scope}.md"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    print(f"Verdict : {report.verdict}")
    print(f"OOS expectancy moyenne : {report.mean_oos_expectancy:.3f} pips")
    print(f"Rapport écrit : {out_path}")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
