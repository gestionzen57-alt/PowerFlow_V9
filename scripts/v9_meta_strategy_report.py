"""v9_meta_strategy_report.py — Rapport edge uplift legacy vs meta (Phase E shadow).

**Pourquoi ce script existe** :
- Phase 1 (commit `0d5e81c`) a livré `core/v9/v9_meta_strategy_shadow.py` qui
  log les comparaisons legacy/meta dans `meta_strategy_shadow_log` (R2 additif).
- Ce script agrège ces logs pour mesurer l'**edge uplift** potentiel avant
  câblage runtime (= motion CEO distincte après validation R25').
- Sortie : tableau Markdown `reports/meta_strategy/YYYY-MM-DD_HHMM.md`.

**Volet doctrinal** :
- R2 additif (lecture seule sur meta_strategy_shadow_log, jamais destructif)
- R6 défensif (DB absente = exit propre code 0 + message)
- R18 code pur (zéro LLM, 100% stdlib)

**Usage** :
```bash
# Dry-run (défaut) : affiche rapport console + écrit Markdown
.venv/Scripts/python.exe scripts/v9_meta_strategy_report.py

# Depuis 24h
.venv/Scripts/python.exe scripts/v9_meta_strategy_report.py --since 24h

# DB custom
.venv/Scripts/python.exe scripts/v9_meta_strategy_report.py --db-path data/test_regen.db

# Ne pas écrire le fichier Markdown
.venv/Scripts/python.exe scripts/v9_meta_strategy_report.py --no-write
```
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ------------------------------------------------------------------ paths


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "v9_forces.db"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "meta_strategy"


# ------------------------------------------------------------------ helpers


def _since_ts(since: str) -> float:
    """Convertit '24h' / '7d' / '1h' en timestamp epoch."""
    now = time.time()
    if since.endswith("h"):
        hours = int(since[:-1])
        return now - hours * 3600
    if since.endswith("d"):
        days = int(since[:-1])
        return now - days * 86400
    if since.endswith("m"):
        minutes = int(since[:-1])
        return now - minutes * 60
    # ISO timestamp direct
    try:
        return datetime.fromisoformat(since).timestamp()
    except ValueError as e:
        raise SystemExit(f"FORMAT --since invalide ({since}): {e}. Attendu '24h'/'7d'/'1h' ou ISO.")


def _check_table(db_path: Path) -> bool:
    """Vérifie que meta_strategy_shadow_log existe. False = table absente."""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='meta_strategy_shadow_log'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️  Erreur accès DB: {e}", file=sys.stderr)
        return False


# ------------------------------------------------------------------ aggregations


def aggregate_overall(db_path: Path, since_ts: float | None) -> dict:
    """Stats globales : n, agreement_rate, sources meta, distributions stratégies."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        where = ""
        params: tuple = ()
        if since_ts is not None:
            where = "WHERE created_at >= ?"
            params = (since_ts,)
        row = conn.execute(
            f"SELECT COUNT(*) AS n, AVG(agreement) AS agr FROM meta_strategy_shadow_log {where}",
            params,
        ).fetchone()
        n = int(row["n"]) if row else 0
        agreement_rate = float(row["agr"]) if row and row["agr"] is not None else 0.0

        sources = {}
        for r in conn.execute(
            f"SELECT meta_source, COUNT(*) AS n FROM meta_strategy_shadow_log {where} "
            f"GROUP BY meta_source ORDER BY n DESC", params,
        ).fetchall():
            sources[r["meta_source"]] = int(r["n"])

        strat_legacy = {}
        for r in conn.execute(
            f"SELECT legacy_strategy, COUNT(*) AS n FROM meta_strategy_shadow_log {where} "
            f"GROUP BY legacy_strategy ORDER BY n DESC", params,
        ).fetchall():
            strat_legacy[r["legacy_strategy"]] = int(r["n"])

        strat_meta = {}
        for r in conn.execute(
            f"SELECT meta_strategy, COUNT(*) AS n FROM meta_strategy_shadow_log {where} "
            f"GROUP BY meta_strategy ORDER BY n DESC", params,
        ).fetchall():
            strat_meta[r["meta_strategy"]] = int(r["n"])

        first_ts = conn.execute(
            f"SELECT MIN(created_at) AS t FROM meta_strategy_shadow_log {where}", params,
        ).fetchone()
        last_ts = conn.execute(
            f"SELECT MAX(created_at) AS t FROM meta_strategy_shadow_log {where}", params,
        ).fetchone()
        first = first_ts["t"] if first_ts else None
        last = last_ts["t"] if last_ts else None

        return {
            "n_shadows": n,
            "agreement_rate": round(agreement_rate, 4),
            "meta_sources": sources,
            "strategy_legacy_distribution": strat_legacy,
            "strategy_meta_distribution": strat_meta,
            "first_ts": first,
            "last_ts": last,
        }
    finally:
        conn.close()


def aggregate_by_segment(db_path: Path, since_ts: float | None) -> list[dict]:
    """Stats par (symbol, timeframe, regime_type, phase) — segments denses."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        where = ""
        params: tuple = ()
        if since_ts is not None:
            where = "WHERE created_at >= ?"
            params = (since_ts,)
        rows = conn.execute(
            f"""
            SELECT symbol, timeframe, regime_type, phase,
                   COUNT(*) AS n,
                   AVG(agreement) AS agr,
                   GROUP_CONCAT(DISTINCT legacy_strategy) AS legacy_strats,
                   GROUP_CONCAT(DISTINCT meta_strategy) AS meta_strats
            FROM meta_strategy_shadow_log {where}
            GROUP BY symbol, timeframe, regime_type, phase
            HAVING n >= 3
            ORDER BY n DESC
            LIMIT 50
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def aggregate_by_meta_strategy(db_path: Path, since_ts: float | None) -> list[dict]:
    """Stats par stratégie meta — pour voir la répartition proposée."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        where = ""
        params: tuple = ()
        if since_ts is not None:
            where = "WHERE created_at >= ?"
            params = (since_ts,)
        rows = conn.execute(
            f"""
            SELECT meta_strategy,
                   COUNT(*) AS n,
                   AVG(legacy_confidence) AS avg_legacy_conf,
                   AVG(meta_confidence) AS avg_meta_conf,
                   AVG(agreement) AS agr
            FROM meta_strategy_shadow_log {where}
            GROUP BY meta_strategy
            ORDER BY n DESC
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ------------------------------------------------------------------ rendering


def render_markdown(
    *,
    overall: dict,
    segments: list[dict],
    by_strategy: list[dict],
    db_path: Path,
    since_label: str,
) -> str:
    """Génère le rapport Markdown."""
    lines = []
    lines.append(f"# Rapport Meta-Strategy Shadow — {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"- **DB** : `{db_path}`")
    lines.append(f"- **Fenêtre** : {since_label}")
    if overall["first_ts"] and overall["last_ts"]:
        first = datetime.fromtimestamp(overall["first_ts"], tz=timezone.utc).isoformat()
        last = datetime.fromtimestamp(overall["last_ts"], tz=timezone.utc).isoformat()
        lines.append(f"- **Première shadow** : {first}")
        lines.append(f"- **Dernière shadow** : {last}")
    lines.append("")
    lines.append("## Vue globale")
    lines.append("")
    lines.append(f"- **Total shadows** : {overall['n_shadows']}")
    lines.append(f"- **Agreement rate** : {overall['agreement_rate'] * 100:.2f}% "
                 f"(legacy == meta)")
    lines.append("")
    lines.append("### Sources meta")
    lines.append("")
    lines.append("| Source | N |")
    lines.append("|--------|---|")
    for src, n in overall["meta_sources"].items():
        lines.append(f"| `{src}` | {n} |")
    lines.append("")
    lines.append("### Distribution stratégies legacy")
    lines.append("")
    lines.append("| Stratégie | N |")
    lines.append("|-----------|---|")
    for s, n in overall["strategy_legacy_distribution"].items():
        lines.append(f"| `{s}` | {n} |")
    lines.append("")
    lines.append("### Distribution stratégies meta")
    lines.append("")
    lines.append("| Stratégie | N |")
    lines.append("|-----------|---|")
    for s, n in overall["strategy_meta_distribution"].items():
        lines.append(f"| `{s}` | {n} |")
    lines.append("")
    if segments:
        lines.append("## Top segments (≥3 shadows)")
        lines.append("")
        lines.append("| Symbol | TF | Regime | Phase | N | Agreement | Legacy | Meta |")
        lines.append("|--------|----|----|-------|---|-----------|--------|------|")
        for s in segments:
            lines.append(
                f"| `{s['symbol']}` | `{s['timeframe']}` | `{s['regime_type']}` | "
                f"`{s['phase']}` | {s['n']} | "
                f"{s['agr'] * 100:.1f}% | "
                f"`{s['legacy_strats']}` | `{s['meta_strats']}` |"
            )
        lines.append("")
    if by_strategy:
        lines.append("## Confiance par stratégie meta")
        lines.append("")
        lines.append("| Stratégie | N | Avg legacy conf | Avg meta conf | Agreement |")
        lines.append("|-----------|---|-----------------|---------------|-----------|")
        for r in by_strategy:
            lines.append(
                f"| `{r['meta_strategy']}` | {r['n']} | "
                f"{r['avg_legacy_conf']:.3f} | {r['avg_meta_conf']:.3f} | "
                f"{(r['agr'] or 0) * 100:.1f}% |"
            )
        lines.append("")
    lines.append("## Verdict motion CEO")
    lines.append("")
    if overall["n_shadows"] == 0:
        lines.append("⚠️  Aucun shadow log — kill switch `V9_META_STRATEGY_SHADOW_ENABLED` "
                     "probablement OFF ou DB jamais alimentée.")
    elif overall["n_shadows"] < 100:
        lines.append(f"🟡 Volumétrie faible ({overall['n_shadows']} shadows) — "
                     f"attendre ≥500 shadows avant motion CEO câblage runtime.")
    else:
        lines.append(f"🟢 Volumétrie suffisante ({overall['n_shadows']} shadows). "
                     f"Lancer motion CEO si edge uplift mesuré >+5 pts WR et >+0.5 PF.")
    lines.append("")
    return "\n".join(lines)


def render_console_summary(overall: dict) -> None:
    """Sortie console compacte pour live-monitoring."""
    print(f"📊 Meta-Strategy Shadow Report")
    print(f"   Shadows total : {overall['n_shadows']}")
    print(f"   Agreement     : {overall['agreement_rate'] * 100:.2f}%")
    print(f"   Sources meta  : {overall['meta_sources']}")
    print(f"   Legacy dist   : {overall['strategy_legacy_distribution']}")
    print(f"   Meta dist     : {overall['strategy_meta_distribution']}")


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rapport edge uplift meta-strategy shadow (Phase E)")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Chemin DB (défaut: {DEFAULT_DB_PATH})")
    parser.add_argument("--since", type=str, default="24h",
                        help="Fenêtre temporelle (24h, 7d, 1h, ou ISO timestamp)")
    parser.add_argument("--no-write", action="store_true",
                        help="Ne pas écrire le fichier Markdown")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR,
                        help=f"Dossier rapport (défaut: {DEFAULT_REPORT_DIR})")
    args = parser.parse_args(argv)

    # Sanity checks
    if not _check_table(args.db_path):
        print(f"⚠️  Table meta_strategy_shadow_log absente dans {args.db_path}.")
        print(f"   Active le kill switch V9_META_STRATEGY_SHADOW_ENABLED=1 et fais tourner")
        print(f"   le pipeline pour générer les premiers shadows.")
        return 0

    # Window
    try:
        since_ts = _since_ts(args.since)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    since_label = args.since if ":" not in args.since else f"since {args.since}"

    # Aggregations
    overall = aggregate_overall(args.db_path, since_ts)
    segments = aggregate_by_segment(args.db_path, since_ts)
    by_strategy = aggregate_by_meta_strategy(args.db_path, since_ts)

    # Console summary
    render_console_summary(overall)

    # Markdown write
    if not args.no_write:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
        report_path = args.report_dir / f"{stamp}_phase_e_meta_shadow.md"
        md = render_markdown(
            overall=overall,
            segments=segments,
            by_strategy=by_strategy,
            db_path=args.db_path,
            since_label=since_label,
        )
        report_path.write_text(md, encoding="utf-8")
        print(f"📝 Rapport écrit : {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())