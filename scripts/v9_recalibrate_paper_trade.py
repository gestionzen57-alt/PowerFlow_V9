#!/usr/bin/env python3
"""v9_recalibrate_paper_trade.py — Recalibrage de la table TP/SL du resolver.

Réconciliation 2026-07-20. Lance `PaperTradeResolver.calibrate_from_history(N)`,
affiche le diff avant/après, et — sur confirmation — persiste la nouvelle table
dans `config/v9_paper_trade_resolver.json` + logge dans DECISIONS_LOG.md.

N'active RIEN en mode ACTIVE (R25') : la table calibrée est une *proposition*
persistée ; le paper-trade loop continue de tourner en shadow tant qu'aucune
motion CEO n'a promu le resolver.

Usage :
    python scripts/v9_recalibrate_paper_trade.py --dry-run   # diff seul, 0 écriture
    python scripts/v9_recalibrate_paper_trade.py --yes       # applique sans prompt
    python scripts/v9_recalibrate_paper_trade.py             # prompt interactif
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.v9_paper_trade_resolver import PaperTradeResolver  # noqa: E402

DEFAULT_DB = ROOT_DIR / "data" / "v9_forces.db"
CONFIG_PATH = ROOT_DIR / "config" / "v9_paper_trade_resolver.json"
DECISIONS_LOG = ROOT_DIR / "workspace" / "perplexity" / "memory" / "DECISIONS_LOG.md"


def _table_to_json(table: dict) -> dict:
    """Sérialise {(tf, vol): (tp, sl)} → {"tf|vol": [tp, sl]} (clés JSON-safe)."""
    return {f"{tf}|{vol}": [tp, sl] for (tf, vol), (tp, sl) in sorted(table.items())}


def _print_diff(before: dict, after: dict) -> int:
    """Affiche le diff avant/après. Retourne le nombre de lignes modifiées."""
    changed = 0
    print(f"{'contexte':<16} {'avant (tp/sl)':<18} {'après (tp/sl)':<18}")
    print("-" * 54)
    for key in sorted(set(before) | set(after)):
        b = before.get(key)
        a = after.get(key)
        tf, vol = key
        b_s = f"{b[0]}/{b[1]}" if b else "—"
        a_s = f"{a[0]}/{a[1]}" if a else "—"
        mark = "" if b == a else "  ← modifié"
        if b != a:
            changed += 1
        print(f"{tf+'/'+vol:<16} {b_s:<18} {a_s:<18}{mark}")
    return changed


def _append_decisions_log(n_days: int, changed: int, config_path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        cfg_display = config_path.relative_to(ROOT_DIR)
    except ValueError:
        cfg_display = config_path
    entry = (
        f"\n### {ts} — Recalibrage table PaperTradeResolver (shadow)\n\n"
        f"- Source : `calibrate_from_history({n_days})` sur `decisions.resolution_pips`.\n"
        f"- Lignes modifiées : {changed}.\n"
        f"- Table persistée : `{cfg_display}` (proposition, "
        f"resolver toujours en SHADOW — R25').\n"
        f"- Promotion ACTIVE : conditionnée à motion CEO explicite.\n"
    )
    DECISIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DECISIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(entry)


def run(db_path: Path, n_days: int, dry_run: bool, assume_yes: bool,
        config_path: Path = CONFIG_PATH) -> int:
    resolver = PaperTradeResolver(db_path=str(db_path))
    before = resolver.get_table()
    after = resolver.calibrate_from_history(n_days)

    print(f"Recalibrage depuis {n_days} jours d'historique ({db_path.name}) :\n")
    changed = _print_diff(before, after)
    print(f"\n{changed} contexte(s) modifié(s).")

    if dry_run:
        print("\n(dry-run : aucune écriture — ni config, ni DECISIONS_LOG.)")
        return 0

    if not assume_yes:
        try:
            resp = input("\nAppliquer et persister la nouvelle table ? [y/N] ").strip().lower()
        except EOFError:
            resp = "n"
        if resp not in ("y", "yes", "o", "oui"):
            print("Abandonné — aucune écriture.")
            return 0

    resolver.set_table(after)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_days": n_days,
        "mode": "shadow",
        "table": _table_to_json(after),
    }
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nTable persistée : {config_path}")

    _append_decisions_log(n_days, changed, config_path)
    print(f"DECISIONS_LOG mis à jour : {DECISIONS_LOG.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Recalibrage table TP/SL du PaperTradeResolver.")
    parser.add_argument("--days", type=int, default=30, help="Fenêtre historique (défaut 30).")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB), help="Chemin DB.")
    parser.add_argument("--dry-run", action="store_true", help="Diff seul, aucune écriture.")
    parser.add_argument("--yes", action="store_true", help="Applique sans prompt interactif.")
    args = parser.parse_args()
    return run(Path(args.db), args.days, args.dry_run, args.yes)


if __name__ == "__main__":
    sys.exit(main())
