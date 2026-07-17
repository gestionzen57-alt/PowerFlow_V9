#!/usr/bin/env python
"""v9_dashboard_risk.py — Dashboard espérance / RR (Phase 13.3, lecture seule).

Le win-rate (WR) est une métrique BIAISÉE quand TP < SL : avec le profil
statique historique (TP=8 / SL=15, RR≈0.53), il faut gagner ~65 % des trades
juste pour être à l'équilibre. Ce script produit la métrique de pilotage
fiable — l'ESPÉRANCE en pips par trade — et confronte le RR statique réalisé
au RR *planifié* que poserait le DynamicRiskManager (SHADOW), pour éclairer la
décision CEO d'activation.

Trois sections :

  1. DASHBOARD RISK      — par paire : trades, WR, RR réalisé, espérance (pips),
                           profit total. Source : decisions résolues (is_win +
                           resolution_pips), le résultat RÉEL sous SL/TP statique.
  2. DIAGNOSTIC PHASES   — distribution des phases rejouées par le
                           DynamicRiskManager sur les contextes réels, + WR par
                           phase. Explique le « 85 % distribution ».
  3. SIMULATION DYNAMIC  — RR statique réalisé  vs  RR moyen *planifié* par le
                           DynamicRiskManager. ⚠ Le RR dynamique est PLANIFIÉ
                           (tp/sl visés), pas réalisé : il ne préjuge pas du WR
                           futur, qui exige une validation live.

Doctrine : R18 (aucun LLM), R2 (additif), R6 (défensif, ne bloque jamais).
Aucune écriture — ni DB, ni fichier. `order_executor` / `config` non touchés.

Usage :
    python scripts/v9_dashboard_risk.py                 # tout l'historique résolu
    python scripts/v9_dashboard_risk.py --since 2026-07-14
    python scripts/v9_dashboard_risk.py --replay-limit 4000
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Racine projet importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.decision_logger import load_contexte_complet  # noqa: E402

# Profil statique historique (référence de comparaison).
STATIC_TP, STATIC_SL = 8.0, 15.0
STATIC_RR = round(STATIC_TP / STATIC_SL, 2)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Section 1 : espérance par paire (résultats réels) ─────────────────

def per_pair_expectancy(conn: sqlite3.Connection, since: str | None) -> list[dict]:
    where = "WHERE is_win IS NOT NULL AND resolution_pips IS NOT NULL"
    params: list = []
    if since:
        where += " AND date(timestamp) >= ?"
        params.append(since)
    rows = conn.execute(
        f"""
        SELECT symbol,
               COUNT(*)                                              AS n,
               AVG(is_win) * 100.0                                   AS wr,
               AVG(CASE WHEN is_win = 1 THEN resolution_pips END)    AS avg_win,
               AVG(CASE WHEN is_win = 0 THEN resolution_pips END)    AS avg_loss,
               AVG(resolution_pips)                                  AS expectancy,
               SUM(resolution_pips)                                  AS profit
        FROM decisions
        {where}
        GROUP BY symbol
        HAVING n > 0
        ORDER BY n DESC
        """,
        params,
    ).fetchall()
    out = []
    for r in rows:
        avg_win = r["avg_win"] or 0.0
        avg_loss = r["avg_loss"] or 0.0  # négatif (pips perdus)
        # RR réalisé = récompense moyenne / risque moyen encouru.
        rr = round(avg_win / abs(avg_loss), 2) if avg_loss else 0.0
        out.append(
            {
                "symbol": r["symbol"],
                "n": r["n"],
                "wr": r["wr"] or 0.0,
                "rr": rr,
                "expectancy": r["expectancy"] or 0.0,
                "profit": r["profit"] or 0.0,
            }
        )
    return out


# ── Sections 2 & 3 : replay du DynamicRiskManager ─────────────────────

def replay_dynamic(
    conn: sqlite3.Connection,
    since: str | None,
    limit: int,
    resolved_only: bool = False,
) -> dict:
    """Rejoue le DynamicRiskManager sur des contextes réels.

    Retourne : distribution des phases, WR par phase (jointe aux résultats),
    et RR planifié moyen (dynamique). Ne lève jamais (R6).

    `resolved_only` : ne rejoue que les décisions résolues (is_win non nul).
    C'est la fenêtre de la validation (WR interprétable), mais un échantillon
    biaisé (paires/période où les trades ont abouti). `resolved_only=False`
    rejoue les décisions les plus RÉCENTES (représentatif de ce que verra le
    moteur en live), résolues ou non.
    """
    from core.v9.dynamic_risk_manager import DynamicRiskManager

    drm = DynamicRiskManager()

    where = "WHERE contexte_complet_json IS NOT NULL"
    if resolved_only:
        where += " AND is_win IS NOT NULL"
    params: list = []
    if since:
        where += " AND date(timestamp) >= ?"
        params.append(since)
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT contexte_complet_json, is_win
        FROM decisions
        {where}
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    phase_counts: Counter = Counter()
    phase_wins: dict[str, list[int]] = defaultdict(list)
    rr_dynamic: list[float] = []
    fallback = 0
    errors = 0
    processed = 0

    for r in rows:
        try:
            ctx = load_contexte_complet(r["contexte_complet_json"])
            if not isinstance(ctx, dict):
                errors += 1
                continue
            dec = drm.evaluate(ctx)
            processed += 1
            phase_counts[dec.phase] += 1
            if dec.source == "fallback":
                fallback += 1
            else:
                rr_dynamic.append(dec.rr_ratio)
            if r["is_win"] is not None:
                phase_wins[dec.phase].append(int(r["is_win"]))
        except Exception:  # R6 — jamais bloquant
            errors += 1

    avg_rr_dyn = round(sum(rr_dynamic) / len(rr_dynamic), 2) if rr_dynamic else 0.0
    return {
        "processed": processed,
        "fallback": fallback,
        "errors": errors,
        "phase_counts": phase_counts,
        "phase_wins": phase_wins,
        "avg_rr_dynamic": avg_rr_dyn,
        "n_dynamic": len(rr_dynamic),
    }


# ── Rendu ─────────────────────────────────────────────────────────────

def _fmt_row(cols: list[str], widths: list[int]) -> str:
    return "│ " + " │ ".join(c.ljust(w) for c, w in zip(cols, widths)) + " │"


def _render_phase_table(rep: dict, title: str, note: str) -> list[str]:
    lines: list[str] = [title, ""]
    total = sum(rep["phase_counts"].values()) or 1
    lines.append(f"  Contextes rejoués : {rep['processed']}   "
                 f"fallback : {rep['fallback']}   erreurs : {rep['errors']}")
    lines.append("")
    ph_headers = ["Phase", "N", "%", "Résolus", "WR"]
    ph_widths = [14, 7, 6, 8, 6]
    lines.append("┌" + "┬".join("─" * (w + 2) for w in ph_widths) + "┐")
    lines.append(_fmt_row(ph_headers, ph_widths))
    lines.append("├" + "┼".join("─" * (w + 2) for w in ph_widths) + "┤")
    for phase, n in rep["phase_counts"].most_common():
        wins = rep["phase_wins"].get(phase, [])
        wr = f"{100.0 * sum(wins) / len(wins):.1f}%" if wins else "—"
        lines.append(_fmt_row([
            phase, str(n), f"{100.0 * n / total:.1f}%", str(len(wins)), wr,
        ], ph_widths))
    lines.append("└" + "┴".join("─" * (w + 2) for w in ph_widths) + "┘")
    if note:
        lines.append("")
        lines.append(note)
    return lines


def render(
    pairs: list[dict], rep_resolved: dict, rep_recent: dict, since: str | None
) -> str:
    lines: list[str] = []
    period = since or "tout l'historique"
    lines.append("═══ DASHBOARD RISK ═══")
    lines.append("")
    lines.append(f"Période : {period}   |   profil statique réf. : "
                 f"TP={STATIC_TP:.0f}/SL={STATIC_SL:.0f} (RR={STATIC_RR})")
    lines.append("")

    # Section 1
    headers = ["Paire", "Trades", "WR", "RR", "Espérance", "Profit"]
    widths = [8, 6, 6, 5, 9, 9]
    lines.append("┌" + "┬".join("─" * (w + 2) for w in widths) + "┐")
    lines.append(_fmt_row(headers, widths))
    lines.append("├" + "┼".join("─" * (w + 2) for w in widths) + "┤")
    tot_n = tot_profit = 0.0
    for p in pairs:
        tot_n += p["n"]
        tot_profit += p["profit"]
        lines.append(_fmt_row([
            p["symbol"],
            str(p["n"]),
            f"{p['wr']:.1f}%",
            f"{p['rr']:.2f}",
            f"{p['expectancy']:+.2f}",
            f"{p['profit']:+.1f}",
        ], widths))
    lines.append("└" + "┴".join("─" * (w + 2) for w in widths) + "┘")
    lines.append(f"  Total : {int(tot_n)} trades   profit cumulé : {tot_profit:+.1f} pips")
    lines.append("")
    lines.append("  ⓘ Espérance (pips/trade) = métrique de pilotage. WR seul trompe")
    lines.append("    quand TP<SL (RR<1) : un WR élevé peut masquer une espérance nulle.")
    lines.append("")

    # Section 2a — diagnostic phases : fenêtre résolue (celle de la validation)
    note_resolved = (
        "  ⓘ 85 % « distribution » ICI reproduit le chiffre de la validation.\n"
        "    Cause : sur cet échantillon résolu (ancien, ~GBPUSD), le qualifieur\n"
        "    behavior_analyzer étiquette « culmination » toute qualification qui\n"
        "    persiste ≥3 barres à intensité non décroissante (= PERSISTANCE, pas\n"
        "    épuisement au sens AT), et point_de_rupture y est rare → le\n"
        "    classifieur retombe sur culmination→distribution."
    )
    lines += _render_phase_table(
        rep_resolved,
        "═══ DIAGNOSTIC PHASES — fenêtre RÉSOLUE (= validation) ═══",
        note_resolved,
    )
    lines.append("")

    # Section 2b — diagnostic phases : fenêtre récente (représentative live)
    note_recent = (
        "  ⚠ Sur les décisions RÉCENTES, la distribution N'EST PLUS à 85 % :\n"
        "    point_de_rupture est bien plus fréquent → CASSURE (priorité > distribution)\n"
        "    pré-empte. La répartition des phases est NON-STATIONNAIRE : le « 85 % »\n"
        "    est un artefact de l'échantillon résolu, PAS ce que verra le moteur en\n"
        "    live. ⇒ ne bloque pas l'activation. NOUVEAU point de vigilance : la part\n"
        "    de CASSURE (profil agressif SL18/TP22) dépend du taux de point_de_rupture\n"
        "    — à surveiller sous APPLY."
    )
    lines += _render_phase_table(
        rep_recent,
        "═══ DIAGNOSTIC PHASES — fenêtre RÉCENTE (représentative live) ═══",
        note_recent,
    )
    lines.append("")

    # Section 3 — simulation RR (sur la fenêtre récente, représentative)
    rep = rep_recent
    lines.append("═══ SIMULATION DYNAMIC RISK (fenêtre récente) ═══")
    lines.append("")
    lines.append(f"  RR statique (réalisé, réf.) : {STATIC_RR}")
    lines.append(f"  RR DynamicRisk (planifié)   : {rep['avg_rr_dynamic']}  "
                 f"(sur {rep['n_dynamic']} décisions dynamiques)")
    if rep["avg_rr_dynamic"] and STATIC_RR:
        gain = round((rep["avg_rr_dynamic"] / STATIC_RR - 1) * 100, 0)
        lines.append(f"  Gain de RR planifié         : {gain:+.0f}%")
    lines.append("")
    lines.append("  ⚠ Le RR dynamique est PLANIFIÉ (tp/sl visés), pas réalisé. Un RR")
    lines.append("    plus haut abaisse le WR d'équilibre requis, mais le WR effectif")
    lines.append("    sous gestion dynamique n'est pas connu tant que le mode APPLY")
    lines.append("    n'a pas tourné en live. Décision d'activation = CEO (Søn).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dashboard espérance / RR (lecture seule)")
    ap.add_argument("--since", default=None, help="Date ISO min (YYYY-MM-DD)")
    ap.add_argument("--replay-limit", type=int, default=8000,
                    help="Nb max de contextes rejoués (défaut 8000)")
    ap.add_argument("--db", default=None, help="Chemin DB (défaut : config.DB_PATH)")
    args = ap.parse_args(argv)

    db_path = Path(args.db) if args.db else DB_PATH
    if not db_path.exists():
        print(f"DB introuvable : {db_path}", file=sys.stderr)
        return 2

    conn = _connect(db_path)
    try:
        pairs = per_pair_expectancy(conn, args.since)
        rep_resolved = replay_dynamic(
            conn, args.since, args.replay_limit, resolved_only=True
        )
        rep_recent = replay_dynamic(
            conn, args.since, args.replay_limit, resolved_only=False
        )
    finally:
        conn.close()

    print(render(pairs, rep_resolved, rep_recent, args.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
