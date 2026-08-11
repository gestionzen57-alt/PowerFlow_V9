"""Replay point-in-time via ReplayEngine (R2 additif) — VALIDE le fix lookahead au cœur.

Utilise `ReplayEngine.run_all(point_in_time=True)` : h4_bias recalculé par barre
(bar_time<=i) + fractal neutralisé. Sans lookahead. Même résolution PnL que C21.

Compare avec `point_in_time=False` (comportement historique = lookahead) pour
quantifier l'écart. Usage : python scripts/run_replay_pointintime.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10.v10_replay_engine import ReplayEngine  # noqa: E402

PAIRS = ("EURUSD", "USDCAD", "USDCHF")
TFS = ("M15",)
LIMIT = 800
DB = "data/v9_forces.db"
SESSION = "LONDON"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    print(f"[{_now()}] ReplayEngine POINT-IN-TIME validation {PAIRS} × {TFS} × {LIMIT}")
    for pit in (True, False):
        eng = ReplayEngine(db_path=DB, session=SESSION)
        # monkeypatch _load_bars honnête (bug C10 force_native)
        def _load_bars_fixed(conn, symbol, tf, limit):
            rows = conn.execute(
                "SELECT bar_time AS timestamp, open, high, low, close, tick_volume, "
                "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd "
                "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
                "ORDER BY bar_time DESC LIMIT ?",
                (symbol.upper(), tf.upper(), limit),
            ).fetchall()
            bars = []
            for r in reversed(rows):
                b = dict(r)
                for k in ("open", "high", "low", "close"):
                    b[k] = float(b.get(k) or 0.0)
                b["tick_volume"] = float(b.get("tick_volume") or 0.0)
                for c in ("force_usd", "force_gbp", "force_eur", "force_jpy",
                          "force_cad", "force_chf", "force_aud", "force_nzd"):
                    b[c] = float(b.get(c) or 50.0)
                b["direction"] = b.get("direction", "neutre")
                b["vitesse"] = float(b.get("vitesse") or 0.0)
                bars.append(b)
            return bars
        import core.v10.v10_replay_engine as engmod
        engmod._load_bars = _load_bars_fixed

        rep = eng.run_all(pairs=PAIRS, timeframes=TFS, limit=LIMIT,
                          run_c10_postprocess=False, point_in_time=pit)
        mode = "POINT-IN-TIME (0 lookahead)" if pit else "HISTORIQUE (lookahead)"
        n = rep.n_total_trades
        wr = rep.global_wr
        pnl = rep.global_pnl_pips
        print(f"\n=== {mode} ===")
        print(f"n_trades={n} WR={wr:.4f} PnL={pnl:+.2f} live_ready={rep.live_ready}")
        out = ROOT / "reports" / f"replay_engine_pit_{'honest' if pit else 'lookahead'}_20260811.json"
        out.write_text(json.dumps({
            "ts": _now(), "mode": mode, "n_trades": n,
            "wr": wr, "pnl_pips": pnl, "live_ready": rep.live_ready,
        }, indent=1), encoding="utf-8")
        print(f"Rapport : {out}")


if __name__ == "__main__":
    main()
