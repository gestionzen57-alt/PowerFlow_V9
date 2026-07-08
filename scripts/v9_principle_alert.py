#!/usr/bin/env python3
"""v9_principle_alert.py — Alerte hit_rate sur principes ACTIVE.

Surveille les 11 principes ACTIVE (PRINCIPLE_ACTIVE_IDS) et émet une alerte
si un principe présente un hit_rate structurellement bas (suspect), ou
si un nouveau principe vient d'être promu sans accumulation suffisante.

Contexte (angle mort #1, brief 2026-07-08) : GRAMMAR_CONTEXTE promu SHADOW→ACTIVE
2026-07-08 avec hit_rate 100% sur 1491 triggers → suspect (biais haussier
AUDIT_DB §6, 91% sur 3 jours). Sans monitoring continu, on risque de ne
détecter la régression qu'au prochain Phase 13 readiness (hebdomadaire).
Ce script ferme la boucle de surveillance quotidienne.

Seuils d'alerte (alignés R30 + recommandations Søn) :
- HR brut < 60%        ET  n_resolved ≥ 100   → ALERT_REGRESSION
- HR brut = 100%       ET  n_resolved ≥ 500   → ALERT_SUSPECT_PERFECT
- n_triggers < 50      ET  promoted_at < 7j   → ALERT_INSUFFICIENT_DATA
- HR brut None (0 WIN/LOSS résolu)            → ALERT_BLOCKED_DATA

Aucun seuil numérique n'est inventé — les valeurs 60% et 50 viennent de
DOCTRINE.md R30 ; les seuils 100 et 500 sont dérivés logiquement
(100 = significance stat minimale, 500 = au-dessus du pic GC).

Doctrine préservée :
- R18 : zéro LLM dans la boucle (calcul SQL pur).
- R8 : aucune modif core/v9/* (lecture seule sur DB).
- R25' : alerte = information, pas décision de déclassement (CEO requis).
- R26 : 1 commit = 1 unité logique.

Usage :
    python scripts/v9_principle_alert.py --once            # cycle d'alerte
    python scripts/v9_principle_alert.py --once --json     # sortie JSON
    python scripts/v9_principle_alert.py --once --log      # append au log

Sortie standard : tableau compact + liste alertes (chacune avec level/pid/raison).
Code retour : 0 si aucune alerte, 1 si alertes émises, 2 si erreur technique.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, PRINCIPLE_ACTIVE_IDS  # noqa: E402

# ── Seuils d'alerte ───────────────────────────────────────────────
# R30 : hit_rate ≥ 60% sur ≥ 50 décl. pour promotion structurelle.
THRESHOLD_HR_LOW = 60.0          # % en dessous = regression
THRESHOLD_TRIGGERS_MIN = 50      # significance (R30)
THRESHOLD_SIGNIFICANCE_N = 100   # n_resolved min pour alerter regression
THRESHOLD_SUSPECT_PERFECT_N = 500  # n_resolved au-dessus duquel HR=100% est suspect
THRESHOLD_INSUFFICIENT_DAYS = 7  # fenêtre post-promotion sans accumulation

# ── Logger ────────────────────────────────────────────────────────
LOG_PATH = ROOT_DIR / "logs" / "v9_principle_alert.log"
logger = logging.getLogger("v9.principle_alert")


def _setup_logging() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(str(LOG_PATH), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _eval_active(conn: sqlite3.Connection, pid: str) -> dict[str, Any]:
    """Pour un principe ACTIVE, calcule n_triggers / n_resolved / hit_rate.

    Réutilise la même jointure principle_evaluations ↔ decisions que
    v9_phase13_readiness.py pour cohérence inter-scripts. Aucune logique
    divergente — alert = lecture, audit = verdict.
    """
    n_trig = conn.execute(
        "SELECT COUNT(*) FROM principle_evaluations "
        "WHERE principle_id = ? AND triggered = 1",
        (pid,),
    ).fetchone()[0]

    n_resolved = 0
    hr_pct: float | None = None
    if n_trig > 0:
        cur = conn.execute(
            """
            SELECT COUNT(*) FROM principle_evaluations pe
            JOIN decisions d ON d.snapshot_id = pe.snapshot_id
            WHERE pe.principle_id = ? AND pe.triggered = 1
              AND d.is_win IS NOT NULL
            """,
            (pid,),
        )
        n_resolved = cur.fetchone()[0]
        if n_resolved > 0:
            cur = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN d.is_win = 1 THEN 1 ELSE 0 END) * 100.0
                    / COUNT(*)
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ? AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                """,
                (pid,),
            )
            hr_pct = round(cur.fetchone()[0], 1)

    # Lecture de promoted_at depuis le YAML (champ ajouté Phase 9.10.1)
    promoted_at: str | None = None
    yaml_path = ROOT_DIR / "core" / "v9" / "principles" / f"{pid}.yaml"
    if yaml_path.exists():
        try:
            import yaml  # noqa: PLC0415

            spec = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            promoted_at = spec.get("promoted_at")
        except Exception:  # noqa: BLE001
            promoted_at = None

    return {
        "principle_id": pid,
        "n_triggers": n_trig,
        "n_resolved": n_resolved,
        "hit_rate_pct": hr_pct,
        "promoted_at": promoted_at,
    }


def _classify_alert(counters: dict[str, Any]) -> dict[str, str] | None:
    """Classifie un compteur en alerte (None si tout va bien).

    Logique : on parcourt les 4 règles dans l'ordre de criticité décroissante.
    Première règle qui match = alerte. Pas d'empilement (1 alerte max par pid).
    """
    n_trig = counters["n_triggers"]
    n_resolved = counters["n_resolved"]
    hr = counters["hit_rate_pct"]
    promoted_at = counters["promoted_at"]

    # R1 — WIN/LOSS = 0 résolu → phase bloquée
    if n_trig > 0 and n_resolved == 0:
        return {
            "level": "BLOCKED_DATA",
            "reason": f"{n_trig} triggers mais 0 WIN/LOSS résolu (resolver daemon KO ?)",
        }

    # R2 — HR parfait sur trop de décisions → suspect (biais marché)
    if hr is not None and hr >= 100.0 and n_resolved >= THRESHOLD_SUSPECT_PERFECT_N:
        return {
            "level": "SUSPECT_PERFECT",
            "reason": f"HR 100% sur {n_resolved} résolus (>{THRESHOLD_SUSPECT_PERFECT_N}) — biais haussier / data leak ?",
        }

    # R3 — HR < 60% sur ≥ 100 résolus → regression structurelle
    if (
        hr is not None
        and hr < THRESHOLD_HR_LOW
        and n_resolved >= THRESHOLD_SIGNIFICANCE_N
    ):
        return {
            "level": "REGRESSION",
            "reason": f"HR {hr}% < {THRESHOLD_HR_LOW}% sur {n_resolved} résolus (≥{THRESHOLD_SIGNIFICANCE_N})",
        }

    # R4 — promotion fraîche (< 7j) sans accumulation suffisante
    if promoted_at and n_trig < THRESHOLD_TRIGGERS_MIN:
        try:
            promo_dt = datetime.fromisoformat(str(promoted_at)).replace(
                tzinfo=timezone.utc
            )
            age_days = (datetime.now(timezone.utc) - promo_dt).days
            if age_days <= THRESHOLD_INSUFFICIENT_DAYS:
                return {
                    "level": "INSUFFICIENT_DATA",
                    "reason": f"promu il y a {age_days}j, {n_trig} triggers (<{THRESHOLD_TRIGGERS_MIN}) — accumulation en cours",
                }
        except ValueError:
            pass

    # R5 — ratio résolus/triggers trop faible → resolver daemon stale/mort
    # Déclenche seulement si ≥50 triggers (significance R30) ET ratio < 5%
    # (= 1 décision résolue pour 20 triggers). Le resolver tourne toutes
    # les 5min ; un ratio normal est > 30% sur des décisions de plus de 24h.
    if n_trig >= THRESHOLD_TRIGGERS_MIN and n_resolved > 0:
        ratio_pct = n_resolved / n_trig * 100
        if ratio_pct < 5.0:
            return {
                "level": "RESOLVER_STALE",
                "reason": f"{n_trig} triggers mais {n_resolved} résolus ({ratio_pct:.1f}%) — resolver daemon en panne ?",
            }

    return None


def audit(db_path: Path = DB_PATH) -> dict[str, Any]:
    """Pour chaque ACTIVE, calcule compteurs + classifie alertes.

    Retourne un dict avec :
    - per_principle : liste de compteurs + éventuelle alerte
    - alerts : liste aplatie des alertes (pour alerte globale)
    - n_active : nombre d'ACTIVE audités
    - timestamp : horodatage UTC ISO8601
    """
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        per_principle = []
        alerts = []
        for pid in PRINCIPLE_ACTIVE_IDS:
            counters = _eval_active(conn, pid)
            alert = _classify_alert(counters)
            entry = {**counters, "alert": alert}
            per_principle.append(entry)
            if alert is not None:
                alerts.append({"principle_id": pid, **alert})
        return {
            "per_principle": per_principle,
            "alerts": alerts,
            "n_active": len(PRINCIPLE_ACTIVE_IDS),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def render_text(report: dict) -> str:
    lines = [
        "PowerFlow V9 — Alert hit_rate ACTIVE",
        "=" * 60,
        f"Timestamp UTC : {report['timestamp']}",
        f"ACTIVE audités : {report['n_active']}",
        f"Alertes        : {len(report['alerts'])}",
        "",
        f"  {'PRINCIPE':<28} {'TRIG':>6} {'RES':>6} {'HR%':>7}  ALERTE",
    ]
    for r in report["per_principle"]:
        hr = f"{r['hit_rate_pct']:.1f}" if r["hit_rate_pct"] is not None else "—"
        alert_lvl = r["alert"]["level"] if r["alert"] else ""
        lines.append(
            f"  {r['principle_id']:<28} {r['n_triggers']:>6} "
            f"{r['n_resolved']:>6} {hr:>7}  {alert_lvl}"
        )
    if report["alerts"]:
        lines += ["", "ALERTES À INVESTIGUER :"]
        for a in report["alerts"]:
            lines.append(f"  - [{a['level']}] {a['principle_id']}: {a['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="Alerte hit_rate sur principes ACTIVE (surveillance continue)"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--once", action="store_true", required=True,
                        help="Exécute un cycle d'alerte puis sort")
    parser.add_argument("--json", action="store_true",
                        help="Sortie JSON au format structuré")
    parser.add_argument("--log", action="store_true",
                        help="Append les alertes au log v9_principle_alert.log")
    args = parser.parse_args(argv)

    try:
        report = audit(args.db)
    except Exception as exc:  # noqa: BLE001
        logger.error("audit_failed: %s", exc)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))

    if args.log and report["alerts"]:
        for a in report["alerts"]:
            logger.warning(
                "ALERT %s pid=%s reason=%s",
                a["level"], a["principle_id"], a["reason"],
            )

    # Code retour : 0 si tout va bien, 1 si alertes (permet au cron d'agir)
    return 1 if report["alerts"] else 0


if __name__ == "__main__":
    sys.exit(main())