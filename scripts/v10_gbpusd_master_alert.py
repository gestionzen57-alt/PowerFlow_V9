#!/usr/bin/env python3
"""v10_gbpusd_master_alert.py — Alerte GBPUSD UNIFIÉE (toutes lectures combinées).

Combine en UN signal de retournement anticipé :
- CINÉMATIQUE : exhaustion du pic de force, divergence force/prix, accélération
- SWEEP : stop hunt (liquidité balayée)
- NIVEAUX : résistance/support, rejet
- MOMENTUM : pente prix
- FORCES : niveau GBP

Détecte le retournement AVANT qu'il n'arrive (anticipation), pas après.
Envoie Telegram si signal STRONG.

R10 : lecture only, zéro ordre réel.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data" / "v9_forces.db").exists() else Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.v9_telegram_notifier import load_telegram_config, send_telegram  # noqa: E402
from scripts.v10_force_cinematics import _analyze  # noqa: E402
from scripts.v10_liquidity_sweep import _detect_sweep  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
PAIR = "GBPUSD"
STATE_FILE = ROOT / "reports" / "v10_gbpusd_master_state.json"


def _load_series(tf, n=80):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT bar_time, force_gbp, force_usd, close, high, low, open "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time ASC",
        (PAIR, tf),
    ).fetchall()
    con.close()
    return rows[-n:]


def _read_signal():
    sig = {"pair": PAIR, "ts": dt.datetime.now(dt.UTC).isoformat()}
    reasons = []
    score = 0

    for tf in ("H4", "H1", "M30"):
        series = _load_series(tf)
        if len(series) < 10:
            continue
        # Cinématique
        cin = _analyze(series, tf)
        sig[f"cin_{tf}"] = cin
        if cin.get("exhaustion_pic"):
            score += 2
            reasons.append(f"[{tf}] EXHAUSTION pic force {cin.get('gbp_pic')}→{cin.get('last_gbp')} (épuisement)")
        if cin.get("divergence_force_price"):
            score += 2
            reasons.append(f"[{tf}] DIVERGENCE : pic force {cin.get('divergence_detail', {}).get('force_pic')} mais prix à {cin.get('last_price')} non confirmé")
        if cin.get("slope_gbp_5", 0) < 0 and cin.get("slope_price_5", 0) > 0:
            score += 1
            reasons.append(f"[{tf}] Force décline ({cin.get('slope_gbp_5')}) mais prix monte ({cin.get('slope_price_5')}%)")

        # Sweep
        bars = [{"high": s[4], "low": s[5], "close": s[3], "open": s[6], "bar_time": s[0]} for s in series]
        sweep = _detect_sweep(bars)
        if sweep:
            sig[f"sweep_{tf}"] = sweep
            score += 3
            reasons.append(f"[{tf}] SWEEP {sweep['direction']} : {sweep['reason']}")

    # Forces actuelles
    try:
        from core.v10.v10_fatman_db_reader import get_fatman_live
        st = get_fatman_live(PAIR, "H4", db_path=str(DB))
        sig["fatman_h4"] = {"gbp": round(st.base_score, 1), "usd": round(st.quote_score, 1), "momentum": st.momentum.value}
        if st.base_score >= 65 and st.momentum.value == "DOWN":
            score += 1
            reasons.append(f"Fatman GBP {st.base_score:.0f} fort + momentum DOWN (épuisement)")
    except Exception:
        pass

    sig["score"] = score
    sig["reasons"] = reasons
    sig["level"] = "STRONG" if score >= 5 else ("MODERATE" if score >= 3 else "WEAK")
    return sig


def _should_alert(prev, cur):
    if cur["level"] == "STRONG" and (prev is None or prev.get("level") != "STRONG"):
        return True
    # re-alerte si un NOUVEAU sweep ou exhaustion apparaît même en STRONG
    if prev and prev.get("level") == "STRONG":
        prev_sweep = prev.get("sweep_h4")
        cur_sweep = cur.get("sweep_h4")
        if prev_sweep != cur_sweep and cur_sweep:
            return True
    return False


def _build_msg(sig):
    lines = [
        "POWERFLOW V10 — MASTER ALERT GBPUSD (anticipation)",
        f"🕐 {sig['ts']}",
        "",
        f"Signal {sig['level']} (score {sig['score']})",
    ]
    for r in sig.get("reasons", []):
        lines.append(f"  • {r}")
    lines.append("")
    lines.append("R10 : lecture only. Retournement ANTICIPÉ — confirmer par rejet + SL au-dessus du sommet.")
    return "\n".join(lines)


def main():
    prev = None
    if STATE_FILE.exists():
        try:
            prev = json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception:
            prev = None
    sig = _read_signal()
    alert = _should_alert(prev, sig)

    STATE_FILE.write_text(json.dumps({
        "level": sig["level"], "score": sig["score"], "ts": sig["ts"],
        "reasons": sig.get("reasons", []), "sweep_h4": sig.get("sweep_h4"),
    }, indent=1), encoding="utf-8")

    print(f"GBPUSD master signal: {sig['level']} (score {sig['score']})")
    for r in sig.get("reasons", []):
        print(f"  {r}")
    if not alert:
        print("(pas de nouvelle alerte)")
        return 0

    msg = _build_msg(sig)
    cfg = load_telegram_config()
    ok = send_telegram(msg, cfg)
    print(f"[{'OK' if ok else 'KO'}] Master alerte GBPUSD envoyée.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
