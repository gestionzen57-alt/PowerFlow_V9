"""v9_bear_dashboard.py — Calculs baissiers pour le dashboard (Tâche 3).

Mission baissier 2/2. Ce module contient la logique PURE (sqlite3 + stdlib,
aucune dépendance FastAPI) alimentant les endpoints
``/api/bear-stats`` et ``/api/currency-bias-matrix`` de
``core/v9/v9_dashboard_api.py``.

Séparé du module FastAPI pour rester testable sous le venv projet (.venv), où
FastAPI n'est pas installé. Les endpoints du dashboard ne sont que de fins
wrappers autour de ces fonctions.

Doctrine :
  R6 — chaque calcul est défensif : toute erreur/absence de donnée retombe sur
       une valeur neutre, jamais d'exception remontée.
  R18 — pur Python + sqlite3 (aucun LLM).
  R2 — additif : ne modifie aucune table, lecture seule.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _connect(db_path: Path | str) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def _constitutive(symbol: str | None) -> set[str]:
    """Devises constitutives d'un symbole (GBPUSD → {GBP, USD}); {} si non standard."""
    if symbol and len(symbol) == 6:
        return {symbol[:3].upper(), symbol[3:].upper()}
    return set()


def bear_stats_from_conn(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    """Stats baissières brutes d'un symbole depuis une connexion ouverte.

    Champs : WR baissier/haussier, effectifs, drift journalier (proxy M5),
    would_skip (candidats au skip), saved_pips, divergence M1/M5.
    """
    out: dict[str, Any] = {
        "symbol": symbol,
        "baissier_wr_pct": None,
        "haussier_wr_pct": None,
        "baissier_n": 0,
        "haussier_n": 0,
        "drift_pips_per_day": None,
        "would_skip_count": 0,
        "would_skip_saved_pips": None,
        "bias_divergence_m1_m5": None,
    }

    # WR par direction.
    try:
        for direction, wr_key, n_key in (
            ("baissiere", "baissier_wr_pct", "baissier_n"),
            ("haussiere", "haussier_wr_pct", "haussier_n"),
        ):
            row = conn.execute(
                """
                SELECT COUNT(*) AS n, COALESCE(SUM(pt.is_win), 0) AS w,
                       COALESCE(SUM(pt.pips_simulated), 0) AS pips
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE d.symbol = ? AND pt.direction = ?
                  AND pt.closed_at IS NOT NULL
                """,
                (symbol, direction),
            ).fetchone()
            n = row[0] or 0
            out[n_key] = n
            if n > 0:
                out[wr_key] = round((row[1] or 0) / n * 100, 1)
            if direction == "baissiere":
                # would_skip = tous les baissiers (candidats au skip structurel).
                # saved_pips = pips nets baissiers (négatif = perte évitée).
                out["would_skip_count"] = n
                out["would_skip_saved_pips"] = round(row[2] or 0, 1)
    except Exception as exc:  # R6
        out["error_wr"] = str(exc)

    # Drift journalier (pips/jour) — proxy sur les closes M5 récents.
    try:
        rows = conn.execute(
            """
            SELECT bar_time, close FROM forces_snapshots
            WHERE symbol = ? AND timeframe = 'M5' AND stale = 0
            ORDER BY bar_time DESC LIMIT 288
            """,
            (symbol,),
        ).fetchall()
        if len(rows) >= 2:
            from core.v9.exit_simulator import pips_multiplier_for_symbol
            pip_mult = pips_multiplier_for_symbol(symbol)
            newest_t, newest_c = rows[0][0], float(rows[0][1])
            oldest_t, oldest_c = rows[-1][0], float(rows[-1][1])
            span_days = max((newest_t - oldest_t) / 86400.0, 1e-9)
            drift_pips = (newest_c - oldest_c) * pip_mult
            out["drift_pips_per_day"] = round(drift_pips / span_days, 1)
    except Exception as exc:  # R6
        out["error_drift"] = str(exc)

    # Divergence M1 vs M5 via BearPerceptionCorrection (standalone bar_time=now).
    try:
        from core.v9.v9_bear_perception import BearPerceptionCorrection
        # On réutilise le chemin de la connexion pour rester cohérent.
        db_file = _conn_db_path(conn)
        corrector = BearPerceptionCorrection(db_file)
        signal = corrector.detect_fast_movement(
            symbol=symbol, decision_id=f"dash_{symbol}",
        )
        out["bias_divergence_m1_m5"] = signal.divergence_ratio
    except Exception as exc:  # R6
        out["error_divergence"] = str(exc)

    return out


def _conn_db_path(conn: sqlite3.Connection) -> str:
    """Récupère le chemin fichier d'une connexion sqlite (PRAGMA database_list)."""
    try:
        for _seq, name, file in conn.execute("PRAGMA database_list").fetchall():
            if name == "main" and file:
                return file
    except Exception:
        pass
    return ":memory:"


def bear_stats(db_path: Path | str, symbol: str = "GBPUSD") -> dict[str, Any]:
    """Stats baissières complètes + recommandation heuristique.

    Wrapper haut-niveau consommé par l'endpoint ``/api/bear-stats``.
    """
    conn = _connect(db_path)
    try:
        stats = bear_stats_from_conn(conn, symbol)
    finally:
        conn.close()

    enabled = os.environ.get("V9_BEAR_PERCEPTION_ENABLED", "0") in ("1", "true", "True")
    stats["bear_perception_enabled"] = enabled

    baissier_wr = stats.get("baissier_wr_pct")
    haussier_wr = stats.get("haussier_wr_pct")
    if baissier_wr is not None and haussier_wr is not None:
        if baissier_wr < 20.0 and haussier_wr > 60.0:
            stats["recommandation"] = "act_fix" if not enabled else "monitor_fix"
        elif baissier_wr < 40.0:
            stats["recommandation"] = "observe"
        else:
            stats["recommandation"] = "healthy"
    else:
        stats["recommandation"] = "insufficient_data"

    stats["timestamp"] = datetime.now(timezone.utc).isoformat()
    return stats


def currency_bias_matrix(db_path: Path | str) -> dict[str, Any]:
    """Matrice symbole × currency des décisions (ratio constitutif).

    Wrapper consommé par l'endpoint ``/api/currency-bias-matrix``.
    """
    conn = _connect(db_path)
    matrix: list[dict[str, Any]] = []
    try:
        try:
            rows = conn.execute(
                """
                SELECT symbol, currency, COUNT(*) AS n
                FROM decisions
                WHERE symbol IS NOT NULL AND currency IS NOT NULL
                GROUP BY symbol, currency
                ORDER BY symbol, n DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []  # colonne currency absente (DB ancienne)

        by_symbol: dict[str, dict[str, int]] = {}
        for sym, cur, n in rows:
            by_symbol.setdefault(sym, {})[str(cur).upper()] = n

        for sym, cur_counts in by_symbol.items():
            constitutive = _constitutive(sym)
            total = sum(cur_counts.values())
            in_scope = sum(
                cnt for c, cnt in cur_counts.items() if c in constitutive
            )
            matrix.append({
                "symbol": sym,
                "total_decisions": total,
                "constitutive_ratio_pct": (
                    round(in_scope / total * 100, 1) if total else None
                ),
                "currencies": [
                    {"currency": c, "count": cnt, "constitutive": c in constitutive}
                    for c, cnt in sorted(
                        cur_counts.items(), key=lambda kv: kv[1], reverse=True,
                    )
                ],
            })
    finally:
        conn.close()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "matrix": matrix,
    }
