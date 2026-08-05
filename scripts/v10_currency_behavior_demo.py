"""V10 Currency Behavior Demo — exécute la lecture complète du comportement.

Lecture de la DB réelle (forces_snapshots) : comportement des devises
par (paire, TF) + fidélité (garde-fou C) + calibration proposée.

Output :
  - reports/v10_currency_behavior_YYYYMMDD.json (R9 audit JSON)
  - console : résumé lisible CEO (narratives)

Usage :
  python scripts/v10_currency_behavior_demo.py [--pair GBPUSD] [--days 7]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_currency_behavior import (  # noqa: E402
    calibrate_regime_thresholds,
    classify_currency_states,
    detect_coalitions,
    detect_drift,
    get_behavior_state,
    load_currency_series,
    compute_leadership,
    classify_regime,
    compute_lead_lag,
    compute_fidelity,
    compute_fidelity_composite,
    compute_fidelity_extreme,
    build_narrative,
    build_causal_narrative,
    session_of,
)

DB_PATH = str(ROOT / "data" / "v9_forces.db")
REPORTS_DIR = ROOT / "reports"


def main() -> int:
    ap = argparse.ArgumentParser(description="V10 Currency Behavior Demo")
    ap.add_argument("--pair", default="GBPUSD")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": DB_PATH,
        "pair": args.pair,
        "days": args.days,
        "layers": {},
        "state": get_behavior_state(),
    }

    # ── Layer 0 — Observation ────────────────────────────────────────
    m30 = load_currency_series(DB_PATH, args.pair, "M30", days=args.days)
    h1 = load_currency_series(DB_PATH, args.pair, "H1", days=args.days)
    h4 = load_currency_series(DB_PATH, args.pair, "H4", days=args.days)
    report["layers"]["0_observation"] = {
        "M30": m30.to_dict(), "H1": h1.to_dict(), "H4": h4.to_dict(),
    }
    if len(m30) < 20:
        print(f"⚠️  Données insuffisantes pour {args.pair} M30 "
              f"({len(m30)} points) — R6 fail-open.")
        return 1

    # ── Layer 1 — Comportement ───────────────────────────────────────
    session = session_of(__import__("datetime").datetime.strptime(
        m30.timestamps[-1][:19], "%Y-%m-%dT%H:%M:%S"))
    # (session_of attend un datetime aware ; on le construit proprement)
    from datetime import datetime as _dt, timezone as _tz
    ts_last = _dt.fromisoformat(m30.timestamps[-1].replace("Z", "+00:00"))
    session = session_of(ts_last)
    report["layers"]["1_comportement"] = {
        "session": session,
        "etats": classify_currency_states(m30),
        "coalitions": detect_coalitions(m30),
        "leadership": compute_leadership(m30),
        "regime": classify_regime(m30, session=session),
        "lead_lag_H4_M30": compute_lead_lag(h4, m30),
    }

    # ── Layer 2 — Fidélité (garde-fou C) ─────────────────────────────
    fid_m30 = compute_fidelity(m30)
    fid_h1 = compute_fidelity(h1) if len(h1) >= 10 else {}
    fid_comp = compute_fidelity_composite(fid_m30, fid_h1)
    fid_extreme = compute_fidelity_extreme(m30)
    report["layers"]["2_fidelite"] = {
        "M30": fid_m30, "H1": fid_h1, "composite": fid_comp,
        "extreme": fid_extreme,
    }

    # ── Layer 3 — Apprentissage ──────────────────────────────────────
    report["layers"]["3_apprentissage"] = {
        "calibration_regime": calibrate_regime_thresholds(m30),
        "drift": detect_drift(
            [fid_m30.get("composite", 0.0)] if fid_m30 else []),
    }

    # ── Layer 4 — Expression ─────────────────────────────────────────
    ctx = {
        "leadership": report["layers"]["1_comportement"]["leadership"],
        "regime": report["layers"]["1_comportement"]["regime"],
        "lead_lag": report["layers"]["1_comportement"]["lead_lag_H4_M30"],
        "fidelity_composite": fid_comp,
        "fidelity_extreme": fid_extreme,
    }
    report["layers"]["4_expression"] = {
        "narrative": build_narrative(ctx),
        "causal_narrative": build_causal_narrative(ctx),
    }
    report["verdict"] = "DEGRADED" if (
        not fid_comp["reliable"] and not fid_extreme["extreme_reliable"]
    ) else "RELIABLE"

    # ── Output ───────────────────────────────────────────────────────
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / (
        f"v10_currency_behavior_{datetime.now(timezone.utc):%Y%m%d}.json")
    out_path.write_text(json.dumps(report, indent=1, default=str),
                        encoding="utf-8")

    # ── Console CEO ──────────────────────────────────────────────────
    etats = report["layers"]["1_comportement"]["etats"]
    line_states = "  ".join(
        f"{c.upper()}={etats[c]['state'][:4]}" for c in
        sorted(etats, key=lambda k: -etats[k]["value"]))
    print(f"\n🔵 V10 CURRENCY BEHAVIOR — {args.pair} ({args.days}j) "
          f"[{session}]\n")
    print(f"  États    : {line_states}")
    ld = report["layers"]["1_comportement"]["leadership"]
    print(f"  Leader   : {ld.get('leader', '?')} "
          f"({ld.get('leader_strength', '?')}) — "
          f"rotation={ld.get('rotation_detected', False)}")
    rg = report["layers"]["1_comportement"]["regime"]
    print(f"  Régime   : {rg.get('regime', '?')} "
          f"[lecture {rg.get('chosen', '?')}]")
    co = report["layers"]["1_comportement"]["coalitions"]
    if co["coalitions"]:
        c0 = co["coalitions"][0]
        print(f"  Coalition: {'+'.join(c0['members'])} "
              f"(corr {c0['corr']}, {c0['label']})")
    ll = report["layers"]["1_comportement"]["lead_lag_H4_M30"]
    print(f"  Causalité: {ll.get('lead_lag', '?')} "
          f"({ll.get('n_currencies_leads', 0)}/{ll.get('n_currencies_total', 0)} devises)")
    print(f"  Fidélité : composite={fid_comp.get('composite', 0.0):.3f} "
          f"→ {'✅' if fid_comp.get('reliable') else '⚠️'}")
    fx = fid_extreme
    if fx.get("best_currency"):
        print(f"  Extrême  : {fx['best_currency']} WR {fx.get('best_wr_pct', '?')}% "
              f"aux queues (P{fx.get('percentile', 90):.0f}/P{100 - fx.get('percentile', 90):.0f}) "
              f"— {'✅ fiable' if fx.get('extreme_reliable') else '⚠️ pas assez de devises fiables'}")
    verdict = "✅ RELIABLE" if report["verdict"] == "RELIABLE" else "⚠️ DÉGRADÉE (exclue du gate R10)"
    print(f"  Verdict  : {verdict}")
    print(f"  Narrative: {report['layers']['4_expression']['narrative']}")
    print(f"  Causale  : {report['layers']['4_expression']['causal_narrative']}")
    print(f"\n  Rapport  : {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
