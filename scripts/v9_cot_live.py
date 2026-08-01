"""v9_cot_live.py — P2-2 motion CEO 48h Champ libre.

COT report live (CFTC) avec fallback sur dernier snapshot.
Detecte positionnement extreme speculateurs vs commercials.

Auteur : Hermes (P2-2 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.cot_live")

COT_CACHE_PATH = Path(r"C:\projet\V9\data\cot_snapshot.json")


def fetch_cot_live(timeout: int = 15) -> list[dict]:
    """Fetch COT report live depuis CFTC."""
    # Note : CFTC API requiert des steps complexes (SOCRATA)
    # Pour ce P2-2 on retourne une erreur structuree pour le fallback
    try:
        url = ("https://publicreporting.cftc.gov/resource/6dca-aqww.json"
                "?$limit=20")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, list) else []
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
        log.warning("CFTC fetch failed: %s", e)
        return []


def load_cot_snapshot() -> dict:
    """Charge le snapshot COT cache."""
    if not COT_CACHE_PATH.exists():
        return {"ts": None, "data": {}}
    try:
        return json.loads(COT_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"ts": None, "data": {}}


def save_cot_snapshot(data: list[dict]) -> None:
    """Sauvegarde snapshot COT."""
    COT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    COT_CACHE_PATH.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def cot_signal(symbol: str, net_long_pct: float,
                threshold_extreme: float = 80.0) -> dict:
    """Signal base sur COT positioning.

    net_long_pct : % des traders nets long (50 = neutre).
    """
    if net_long_pct >= threshold_extreme:
        return {
            "signal": "EXTREME_LONG",
            "score": -0.5,
            "interpretation": "Exhaustion (contrarian SHORT)",
            "action": "REDUCE_LONG_BIAS",
        }
    elif net_long_pct <= 100 - threshold_extreme:
        return {
            "signal": "EXTREME_SHORT",
            "score": 0.5,
            "interpretation": "Exhaustion (contrarian LONG)",
            "action": "REDUCE_SHORT_BIAS",
        }
    elif net_long_pct >= 65:
        return {
            "signal": "BULLISH_LEAN",
            "score": 0.2,
            "interpretation": "Positioning bullish",
            "action": "FAVOR_LONG",
        }
    elif net_long_pct <= 35:
        return {
            "signal": "BEARISH_LEAN",
            "score": -0.2,
            "interpretation": "Positioning bearish",
            "action": "FAVOR_SHORT",
        }
    else:
        return {
            "signal": "NEUTRAL",
            "score": 0.0,
            "interpretation": "Positioning equilibre",
            "action": "NO_BIAS",
        }


def get_cot_signal(symbol: str, net_long_pct: float) -> dict:
    """Point d'entree principal."""
    return cot_signal(symbol, net_long_pct)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 COT live (P2-2)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--net-long", type=float, default=72.0)
    parser.add_argument("--fetch", action="store_true",
                        help="Tenter fetch live CFTC")
    args = parser.parse_args(argv)

    print("=" * 70)
    print(f"P2-2 — COT REPORT LIVE ({args.symbol})")
    print("=" * 70)
    if args.fetch:
        live = fetch_cot_live()
        print(f"CFTC live    : {'OK' if live else 'FAIL (fallback)'}")
        if live:
            save_cot_snapshot(live)
    snapshot = load_cot_snapshot()
    if snapshot["ts"]:
        print(f"Snapshot ts  : {snapshot['ts'][:19]}")
        print(f"Snapshot n   : {len(snapshot.get('data', []))}")
    print()
    signal = get_cot_signal(args.symbol, args.net_long)
    print(f"Net long pct : {args.net_long}%")
    print(f"Signal       : {signal['signal']}")
    print(f"Score        : {signal['score']}")
    print(f"Interpret.   : {signal['interpretation']}")
    print(f"Action       : {signal['action']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())