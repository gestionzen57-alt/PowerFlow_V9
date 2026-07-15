"""v9_alpha_report.py — Rapport alpha quotidien PowerFlow V9 (SOUL.md §2, cron 6h).

Génère un rapport Markdown de l'état alpha du système :
  - Top / bottom principes par expectancy et par WR
  - Zones underperforming (à surveiller / mettre DORMANT)
  - Edge decay (principes en dégradation)
  - Cascades boosters et dampeners découvertes

Proactif (SOUL.md) : le système voit, propose, alerte. Le rapport peut être
publié sur le bus agent et déclencher une alerte Telegram en cas d'anomalie
(edge decay détecté, principe passé sous seuil de rentabilité).

Usage :
    python scripts/v9_alpha_report.py                # rapport stdout
    python scripts/v9_alpha_report.py --publish      # + bus agent + Telegram
    python scripts/v9_alpha_report.py --out FILE.md  # écrit dans un fichier

Doctrine :
  - R18 : stdlib uniquement (le report ne fait aucun appel LLM)
  - R6 : best-effort, ne crash jamais (bus/Telegram optionnels)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.principle_alpha_engine import PrincipleAlphaEngine  # noqa: E402
from core.v9.principle_cascade_engine import PrincipleCascadeEngine  # noqa: E402

# Seuils d'anomalie déclenchant une alerte (SOUL.md §2).
UNPROFITABLE_EXPECTANCY = 0.0   # expectancy < 0 → non rentable
MIN_N_FOR_ALERT = 20            # échantillon minimal pour alerter


def build_report(min_n: int = 10) -> dict[str, Any]:
    """Construit le rapport alpha structuré (données brutes)."""
    alpha = PrincipleAlphaEngine()
    cascade = PrincipleCascadeEngine()

    ranking_exp = alpha.rank_principles(metric="expectancy", min_n=min_n)
    ranking_wr = alpha.rank_principles(metric="win_rate", min_n=min_n)

    # Edge decay + underperformance par principe.
    decays: list[dict[str, Any]] = []
    underperformers: list[dict[str, Any]] = []
    for pid, _val, _n in ranking_exp:
        try:
            d = alpha.detect_edge_decay(pid)
            if d["decayed"]:
                decays.append(d)
            dims = alpha.compute_all_dimensions(pid, min_n=min_n)
            for u in dims["underperforming"]:
                underperformers.append({"principle_id": pid, **u})
        except Exception:
            continue

    try:
        cascades = cascade.discover_cascades(min_n=20, min_wr_lift=5.0, persist=True)
    except Exception:
        cascades = []
    boosters = [c for c in cascades if c["kind"] == "booster"]
    dampeners = [c for c in cascades if c["kind"] == "dampener"]

    # Anomalies : principes non rentables sur échantillon suffisant.
    unprofitable = [
        {"principle_id": pid, "expectancy": val, "n": n}
        for pid, val, n in ranking_exp
        if val < UNPROFITABLE_EXPECTANCY and n >= MIN_N_FOR_ALERT
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_n": min_n,
        "ranking_expectancy": ranking_exp,
        "ranking_win_rate": ranking_wr,
        "edge_decays": decays,
        "underperformers": underperformers,
        "boosters": boosters,
        "dampeners": dampeners,
        "unprofitable": unprofitable,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Rend le rapport en Markdown lisible."""
    lines: list[str] = []
    lines.append("# PowerFlow V9 — Rapport Alpha")
    lines.append("")
    lines.append(f"*Généré le {report['generated_at']} (min_n={report['min_n']})*")
    lines.append("")

    exp = report["ranking_expectancy"]
    lines.append("## Top principes (expectancy)")
    lines.append("")
    lines.append("| # | Principe | Expectancy (pips) | n |")
    lines.append("|---|---|---|---|")
    for i, (pid, val, n) in enumerate(exp[:10], 1):
        lines.append(f"| {i} | {pid} | {val:+.3f} | {n} |")
    lines.append("")

    if len(exp) > 3:
        lines.append("## Bottom principes (expectancy)")
        lines.append("")
        lines.append("| Principe | Expectancy (pips) | n |")
        lines.append("|---|---|---|")
        for pid, val, n in exp[-5:]:
            lines.append(f"| {pid} | {val:+.3f} | {n} |")
        lines.append("")

    lines.append("## Anomalies — principes non rentables")
    lines.append("")
    if report["unprofitable"]:
        lines.append("| Principe | Expectancy | n | Action proposée |")
        lines.append("|---|---|---|---|")
        for u in report["unprofitable"]:
            lines.append(
                f"| {u['principle_id']} | {u['expectancy']:+.3f} | {u['n']} | "
                f"⚠️ surveiller / DORMANT |"
            )
    else:
        lines.append("Aucun principe non rentable sur échantillon suffisant. ✅")
    lines.append("")

    lines.append("## Edge decay (dégradation d'edge)")
    lines.append("")
    if report["edge_decays"]:
        for d in report["edge_decays"]:
            lines.append(f"- ⚠️ {d['alert']}")
    else:
        lines.append("Aucune dégradation d'edge détectée. ✅")
    lines.append("")

    lines.append("## Zones underperforming")
    lines.append("")
    if report["underperformers"]:
        lines.append("| Principe | Dimension | Valeur | WR | Δ | n |")
        lines.append("|---|---|---|---|---|---|")
        for u in report["underperformers"][:20]:
            lines.append(
                f"| {u['principle_id']} | {u['dimension']} | {u['value']} | "
                f"{u['win_rate']:.1f}% | {u['delta']:+.1f} | {u['n_trades']} |"
            )
    else:
        lines.append("Aucune zone sous-performante flagrante. ✅")
    lines.append("")

    lines.append("## Cascades boosters")
    lines.append("")
    if report["boosters"]:
        lines.append("| Cascade | WR | Lift | n |")
        lines.append("|---|---|---|---|")
        for c in report["boosters"][:10]:
            lines.append(
                f"| {c['cascade_id']} | {c['win_rate']:.1f}% | "
                f"{c['wr_lift']:+.1f} | {c['n_trades']} |"
            )
    else:
        lines.append("Aucune cascade booster découverte.")
    lines.append("")

    lines.append("## Cascades dampeners (combinaisons à éviter)")
    lines.append("")
    if report["dampeners"]:
        lines.append("| Cascade | WR | Lift | n |")
        lines.append("|---|---|---|---|")
        for c in report["dampeners"][:10]:
            lines.append(
                f"| {c['cascade_id']} | {c['win_rate']:.1f}% | "
                f"{c['wr_lift']:+.1f} | {c['n_trades']} |"
            )
    else:
        lines.append("Aucune cascade dampener découverte.")
    lines.append("")

    return "\n".join(lines)


def _has_anomaly(report: dict[str, Any]) -> bool:
    """True si le rapport contient une anomalie méritant une alerte."""
    return bool(report["edge_decays"] or report["unprofitable"])


def publish_to_bus(report: dict[str, Any]) -> bool:
    """Publie un résumé du rapport sur le bus agent (best-effort, R6)."""
    try:
        from core.v9.agent_bus_bridge import BusBridge
        bridge = BusBridge(agent_name="learn-analyst", source="hermes")
        top = report["ranking_expectancy"][:3]
        severity = "warning" if _has_anomaly(report) else "info"
        bridge.publish_event(
            "alpha_report",
            {
                "generated_at": report["generated_at"],
                "top_principles": [{"id": p, "expectancy": v, "n": n}
                                   for p, v, n in top],
                "n_edge_decays": len(report["edge_decays"]),
                "n_unprofitable": len(report["unprofitable"]),
                "n_boosters": len(report["boosters"]),
                "n_dampeners": len(report["dampeners"]),
            },
            severity=severity,
        )
        return True
    except Exception:
        return False


def notify_telegram(report: dict[str, Any]) -> bool:
    """Alerte Telegram best-effort si anomalie détectée (R6, jamais bloquant)."""
    if not _has_anomaly(report):
        return False
    try:
        from core.v9.decision_logger import _load_telegram_config_safe
        cfg = _load_telegram_config_safe()
        if cfg is None:
            return False
        from scripts.v9_telegram_notifier import send_telegram

        lines = ["[V9] Rapport Alpha — anomalie détectée"]
        for d in report["edge_decays"][:3]:
            lines.append(f"⚠️ {d['alert']}")
        for u in report["unprofitable"][:3]:
            lines.append(
                f"⚠️ {u['principle_id']} non rentable "
                f"(exp {u['expectancy']:+.2f}, n={u['n']})"
            )
        lines.append("Descriptif — aucune application automatique.")
        return send_telegram("\n".join(lines), cfg, timeout=5)
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rapport alpha V9")
    parser.add_argument("--publish", action="store_true",
                        help="Publie sur le bus agent + alerte Telegram si anomalie")
    parser.add_argument("--out", type=str, default=None,
                        help="Écrit le rapport Markdown dans ce fichier")
    parser.add_argument("--min-n", type=int, default=10,
                        help="Nb minimal de trades pour retenir un principe")
    args = parser.parse_args(argv)

    # Console Windows (cp1252) : force UTF-8 pour les emojis du rapport.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    report = build_report(min_n=args.min_n)
    md = render_markdown(report)

    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Rapport écrit dans {args.out}")
    else:
        print(md)

    if args.publish:
        bus_ok = publish_to_bus(report)
        tg_ok = notify_telegram(report)
        print(f"\n[publish] bus={'ok' if bus_ok else 'skip'} "
              f"telegram={'sent' if tg_ok else 'skip'}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
