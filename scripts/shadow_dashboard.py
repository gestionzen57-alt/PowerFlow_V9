"""V10 Shadow Dashboard — métriques live des shadow_continuous_*.json (R2 additif).

Z3 (ZCode 10/08) — DOCTRINE_PERFORMANCE P6 :
  - WR rolling 20/50/100 trades
  - PF rolling (gross wins / |gross losses|)
  - Sharpe rolling (mean/std des pnl_pips)
  - Distribution par paire
  - Distribution par TF

Dépendances : stdlib + numpy uniquement (pas de pandas/matplotlib).
R10 : lecture seule — zéro ordre réel.
R9 : sortie terminal + rapport JSON optionnel (--json).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from typing import Dict, List, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
PATTERNS = ("shadow_continuous_state.json", "shadow_continuous_*.json", "shadow_continuous_final.json")


def _load_trades(reports_dir: str) -> List[dict]:
    """Charge tous les trades depuis les shadow_continuous_*.json (dédupliqués par ts+pair+tf)."""
    seen: set = set()
    trades: List[dict] = []
    files = []
    for pat in PATTERNS:
        files.extend(sorted(glob.glob(os.path.join(reports_dir, pat))))
    # Ordre : state d'abord (le plus récent), puis checkpoints, puis final
    files = sorted(set(files))
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        state = d.get("state", d) if isinstance(d, dict) else {}
        for t in state.get("trades", []):
            if not isinstance(t, dict) or "result" not in t:
                continue
            key = (t.get("pair", ""), t.get("tf", ""), t.get("ts", ""))
            if key in seen:
                continue
            seen.add(key)
            trades.append(t)
    return trades


def _rolling(values: List[float], window: int) -> List[float]:
    """Moyenne glissante simple (stdlib)."""
    if not values:
        return []
    out = []
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        out.append(sum(values[lo:i + 1]) / (i - lo + 1))
    return out


def _wr_rolling(trades: List[dict], window: int) -> List[float]:
    """WR glissant : fraction de WIN sur les `window` derniers trades."""
    out = []
    for i in range(len(trades)):
        lo = max(0, i - window + 1)
        chunk = trades[lo:i + 1]
        out.append(sum(1 for t in chunk if t.get("result") == "WIN") / len(chunk))
    return out


def _pf_rolling(trades: List[dict], window: int) -> List[float]:
    """PF glissant : gross wins / |gross losses| sur la fenêtre."""
    out = []
    for i in range(len(trades)):
        lo = max(0, i - window + 1)
        chunk = trades[lo:i + 1]
        gw = sum(t.get("pnl_pips", 0.0) for t in chunk if t.get("pnl_pips", 0.0) > 0)
        gl = abs(sum(t.get("pnl_pips", 0.0) for t in chunk if t.get("pnl_pips", 0.0) < 0))
        out.append(gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0))
    return out


def _sharpe_rolling(pnls: List[float], window: int) -> List[float]:
    """Sharpe glissant : mean/std des pnl_pips sur la fenêtre."""
    out = []
    for i in range(len(pnls)):
        lo = max(0, i - window + 1)
        chunk = pnls[lo:i + 1]
        avg = sum(chunk) / len(chunk)
        var = sum((p - avg) ** 2 for p in chunk) / len(chunk)
        std = math.sqrt(var)
        out.append(avg / std if std > 0 else 0.0)
    return out


def _fmt(v: float) -> str:
    if v == float("inf"):
        return "inf"
    if v != v:  # NaN
        return "nan"
    return f"{v:.3f}"


def _render(trades: List[dict], json_out: Optional[str]) -> dict:
    n = len(trades)
    pnls = [t.get("pnl_pips", 0.0) for t in trades]
    wins = sum(1 for t in trades if t.get("result") == "WIN")
    losses = sum(1 for t in trades if t.get("result") == "LOSS")
    bes = sum(1 for t in trades if t.get("result") == "BE")
    wr = wins / n if n else 0.0
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0)
    avg = sum(pnls) / n if n else 0.0
    std = math.sqrt(sum((p - avg) ** 2 for p in pnls) / n) if n > 1 else 0.0
    sharpe = avg / std if std > 0 else 0.0

    # Distributions
    by_pair: Dict[str, int] = {}
    by_tf: Dict[str, int] = {}
    for t in trades:
        by_pair[t.get("pair", "?")] = by_pair.get(t.get("pair", "?"), 0) + 1
        by_tf[t.get("tf", "?")] = by_tf.get(t.get("tf", "?"), 0) + 1

    # Rolling
    wr20 = _wr_rolling(trades, 20)
    wr50 = _wr_rolling(trades, 50)
    wr100 = _wr_rolling(trades, 100)
    pf20 = _pf_rolling(trades, 20)
    pf50 = _pf_rolling(trades, 50)
    sh20 = _sharpe_rolling(pnls, 20)
    sh50 = _sharpe_rolling(pnls, 50)

    def _last(seq: List[float]) -> float:
        return seq[-1] if seq else 0.0

    report = {
        "n_trades": n,
        "wins": wins, "losses": losses, "be": bes,
        "wr_global": round(wr, 4),
        "pf_global": round(pf, 4),
        "sharpe_global": round(sharpe, 4),
        "pnl_total_pips": round(sum(pnls), 2),
        "wr_rolling": {"w20": round(_last(wr20), 4), "w50": round(_last(wr50), 4), "w100": round(_last(wr100), 4)},
        "pf_rolling": {"w20": round(_last(pf20), 4), "w50": round(_last(pf50), 4)},
        "sharpe_rolling": {"w20": round(_last(sh20), 4), "w50": round(_last(sh50), 4)},
        "by_pair": by_pair,
        "by_tf": by_tf,
        "mode": "SHADOW",
        "r10": "zero order real",
    }

    # ── Affichage terminal ──────────────────────────────────────────────
    print("=" * 62)
    print("V10 SHADOW DASHBOARD — métriques live (DOCTRINE P6)")
    print("=" * 62)
    print(f"Trades résolus : {n}  (WIN {wins} / LOSS {losses} / BE {bes})")
    print(f"PnL total      : {sum(pnls):+.2f} pips")
    print(f"WR global      : {wr:.1%}")
    print(f"PF global      : {_fmt(pf)}")
    print(f"Sharpe global  : {_fmt(sharpe)}")
    print("-" * 62)
    print("Rolling (dernière valeur) :")
    print(f"  WR     w20={_fmt(_last(wr20))}  w50={_fmt(_last(wr50))}  w100={_fmt(_last(wr100))}")
    print(f"  PF     w20={_fmt(_last(pf20))}  w50={_fmt(_last(pf50))}")
    print(f"  Sharpe w20={_fmt(_last(sh20))}  w50={_fmt(_last(sh50))}")
    print("-" * 62)
    print("Distribution par paire :")
    for pair, cnt in sorted(by_pair.items(), key=lambda kv: -kv[1]):
        print(f"  {pair}: {cnt}")
    print("Distribution par TF :")
    for tf, cnt in sorted(by_tf.items(), key=lambda kv: -kv[1]):
        print(f"  {tf}: {cnt}")
    print("=" * 62)

    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Rapport JSON : {json_out}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="V10 Shadow Dashboard (métriques live)")
    ap.add_argument("--reports-dir", default=REPORTS_DIR, help="répertoire des shadow_continuous_*.json")
    ap.add_argument("--json", default=None, help="écrire le rapport JSON à ce chemin")
    args = ap.parse_args()

    trades = _load_trades(args.reports_dir)
    if not trades:
        print(f"[WARN] aucun trade trouvé dans {args.reports_dir} (pattern shadow_continuous_*.json)")
        return 1
    _render(trades, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
