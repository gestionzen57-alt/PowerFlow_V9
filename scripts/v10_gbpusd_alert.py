#!/usr/bin/env python3
"""v10_gbpusd_alert.py — Alerte GBPUSD fort signal potentiel (Telegram).

Trade GBPUSD exclusivement. Détecte les signaux FORTS par confluence
(Fatman + VSA + niveaux + momentum) et alerte Telegram dès qu'un setup se
confirme (notamment un rejet sous résistance = signal de vente du pic).

R10 : lecture only. Alerte = information, jamais un ordre réel.
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

from core.v10.v10_fatman_db_reader import get_fatman_live  # noqa: E402
from scripts.v9_telegram_notifier import load_telegram_config, send_telegram  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
PAIR = "GBPUSD"
STATE_FILE = ROOT / "reports" / "v10_gbpusd_alert_state.json"


def _load_bars(tf, limit=300):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, tick_volume "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (PAIR, tf, limit),
    ).fetchall()
    con.close()
    bars = []
    for r in reversed(rows):
        b = dict(r)
        for k in ("open", "high", "low", "close", "tick_volume"):
            b[k] = float(b.get(k) or 0.0)
        bars.append(b)
    return bars


def _detect_resistance(bars, window=10):
    """Résistance la plus proche du prix courant (swing highs)."""
    n = len(bars)
    if n < 2 * window:
        return None
    swing = []
    for i in range(window, n - window):
        h = bars[i]["high"]
        if h >= max(bars[j]["high"] for j in range(i - window, i + window + 1)):
            swing.append(h)
    if not swing:
        return None
    close = bars[-1]["close"]
    return min(swing, key=lambda s: abs(s - close))


def _read_signal():
    """Construit le signal GBPUSD. Retourne dict complet + score."""
    sig = {"pair": PAIR, "ts": dt.datetime.now(dt.UTC).isoformat()}
    reasons = []
    score = 0

    # Fatman
    try:
        st = get_fatman_live(PAIR, "H4", db_path=str(DB))
        gbp_f = st.base_score
        usd_f = st.quote_score
        mom = st.momentum.value
        sig["fatman_h4"] = {"gbp": round(gbp_f, 1), "usd": round(usd_f, 1), "momentum": mom, "gbp_rank": st.base_rank}
        if gbp_f >= 65:
            score += 1
            reasons.append(f"Fatman GBP {gbp_f:.0f} (très fort)")
        if mom == "DOWN" and gbp_f >= 60:
            score += 1
            reasons.append("Force extrême + momentum DOWN (épuisement)")
    except Exception as e:
        sig["fatman_error"] = str(e)

    # Niveaux + rejet (multi-TF)
    for tf in ("H4", "H1"):
        bars = _load_bars(tf)
        if len(bars) < 30:
            continue
        res = _detect_resistance(bars)
        close = bars[-1]["close"]
        if res:
            d_pips = round(abs(res - close) / 0.0001, 1)
            sig[f"res_{tf}"] = {"level": round(res, 5), "dist_pips": d_pips}
            if d_pips <= 25:
                score += 1
                reasons.append(f"Sur résistance {tf} {res:.5f} ({d_pips:.0f} pips)")
            # Rejet : bougie baissière qui ferme SOUS le niveau après l'avoir touché
            if len(bars) >= 2:
                prev, cur = bars[-2], bars[-1]
                touched = prev["high"] >= res - 0.0001
                closed_below = cur["close"] < res
                if touched and closed_below and cur["close"] < cur["open"]:
                    score += 3
                    reasons.append(f"REJET confirmé {tf} : touche {res:.5f} puis close sous (courant)")

    # Momentum H1
    h1 = _load_bars("H1")
    if len(h1) >= 20:
        slope = (h1[-1]["close"] - h1[-10]["close"]) / (h1[-10]["close"] or 1e-9) * 100
        sig["mom_h1"] = round(slope, 3)
        if slope < -0.05:
            score += 1
            reasons.append(f"Momentum H1 négatif ({slope:.2f}%)")

    sig["score"] = score
    sig["reasons"] = reasons
    sig["level"] = "STRONG" if score >= 4 else ("MODERATE" if score >= 2 else "WEAK")
    return sig


def _should_alert(prev, cur):
    """Anti-spam : alerte seulement si le niveau monte ou que c'est STRONG nouveau."""
    if cur["level"] == "STRONG" and (prev is None or prev.get("level") != "STRONG"):
        return True
    if cur["level"] == "STRONG" and prev and prev.get("level") == "STRONG":
        return False  # déjà alerté
    return False


def _build_msg(sig):
    lines = [
        "POWERFLOW V10 — ALERTE GBPUSD",
        f"🕐 {sig['ts']}",
        "",
        f"Signal {sig['level']} (score {sig['score']})",
    ]
    for r in sig.get("reasons", []):
        lines.append(f"  • {r}")
    lines.append("")
    lines.append("R10 : lecture only. Vérifier rejet + SL au-dessus du sommet avant toute action.")
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

    # Persister l'état
    STATE_FILE.write_text(json.dumps({
        "level": sig["level"], "score": sig["score"], "ts": sig["ts"], "reasons": sig.get("reasons", []),
    }, indent=1), encoding="utf-8")

    # Console
    print(f"GBPUSD signal: {sig['level']} (score {sig['score']})")
    for r in sig.get("reasons", []):
        print(f"  {r}")
    if not alert:
        print("(pas de nouvelle alerte — anti-spam)")
        return 0

    # Envoyer Telegram
    msg = _build_msg(sig)
    cfg = load_telegram_config()
    ok = send_telegram(msg, cfg)
    print(f"[{'OK' if ok else 'KO'}] Alerte GBPUSD envoyée.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
