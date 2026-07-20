"""v9_cross_pair_metrics.py — Métriques cross-pair R2 additif (motion CEO #8).

Contexte : audit Opus 2026-07-20 (PROMPT_OPUS_REGIME_AUDIT_20260720.md §5.4) a
identifié que le RegimeDetector actuel lit les 8 devises indépendamment, sans
considérer le rapport de force d'une paire. Conséquence : le régime ne capte
pas le gradient inter-devises (USD fort vs GBP faible = signal baissier).

Ce module ajoute 2 métriques cross-pair sans toucher au RegimeDetector (R2) :
  1. cross_pair_dispersion(timestamp) : stddev des 8 forces à un instant t.
     Proxy volatilité réalisée inter-devises. Haute dispersion = marché en
     déséquilibre (souvent précurseur de retournement).
  2. pair_force_ratio(symbol, timestamp) : (force_ccy_base - force_ccy_quote)
     pour la paire. Lecture directe de la dynamique bilatérale.

Doctrine :
- R2 additif : module séparé, n'altère pas RegimeDetector.
- R6 défensif : retourne None si DB absente ou symbole inconnu.
- R18 : pure SQL + stdlib (statistiques), zéro LLM.

Usage :
    from core.v9.v9_cross_pair_metrics import (
        cross_pair_dispersion, pair_force_ratio, neutre_rate_24h,
    )
    disp = cross_pair_dispersion(db_path, ts_iso="2026-07-20T14:00:00+00:00")
    bias = pair_force_ratio(db_path, symbol="GBPUSD", ts_iso=...)
    rate = neutre_rate_24h(db_path, symbol="GBPUSD", timeframe="M15")
"""
from __future__ import annotations

import sqlite3
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "v9_forces.db"

# Mapping symbole → (force_devise_base, force_devise_quote)
SYMBOL_CURRENCY_MAP: dict[str, tuple[str, str]] = {
    "GBPUSD": ("force_gbp", "force_usd"),
    "USDJPY": ("force_usd", "force_jpy"),
    "USDCHF": ("force_usd", "force_chf"),
    "EURUSD": ("force_eur", "force_usd"),
    "AUDUSD": ("force_aud", "force_usd"),
    "USDCAD": ("force_usd", "force_cad"),
    "NZDUSD": ("force_nzd", "force_usd"),
    "EURJPY": ("force_eur", "force_jpy"),
    "GBPJPY": ("force_gbp", "force_jpy"),
}

FORCE_COLUMNS: list[str] = [
    "force_usd", "force_gbp", "force_eur", "force_jpy",
    "force_cad", "force_chf", "force_aud", "force_nzd",
]


def _connect(db_path: Path | str) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def cross_pair_dispersion(
    db_path: Path | str = DEFAULT_DB,
    ts_iso: str | None = None,
    symbol: str | None = None,
) -> Optional[float]:
    """Stddev des 8 forces à un instant t (proxy volatilité inter-devises).

    Args:
        db_path: chemin DB (défaut prod).
        ts_iso: ISO timestamp UTC. Si None, prend MAX(timestamp) de la DB.
        symbol: si fourni, restreint au (symbol, ts_iso) — sinon retourne
            la dispersion globale (toutes devises × tous symboles).

    Returns:
        Stddev des 8 forces (0-100) ou None si DB absente / pas de snapshot.

    R6 défensif : retourne None sur toute erreur, ne lève jamais.
    """
    try:
        with _connect(db_path) as conn:
            if ts_iso is None:
                row = conn.execute(
                    "SELECT MAX(timestamp) FROM forces_snapshots"
                ).fetchone()
                if not row or not row[0]:
                    return None
                ts_iso = row[0]
            if symbol:
                row = conn.execute(
                    f"SELECT {','.join(FORCE_COLUMNS)} FROM forces_snapshots "
                    "WHERE timestamp <= ? AND symbol = ? "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (ts_iso, symbol),
                ).fetchone()
            else:
                row = conn.execute(
                    f"SELECT {','.join(FORCE_COLUMNS)} FROM forces_snapshots "
                    "WHERE timestamp = ? LIMIT 1",
                    (ts_iso,),
                ).fetchone()
            if not row:
                return None
            forces = [float(v) for v in row if v is not None]
            if len(forces) < 2:
                return None
            return round(statistics.stdev(forces), 2)
    except Exception:  # noqa: BLE001
        return None


def pair_force_ratio(
    db_path: Path | str = DEFAULT_DB,
    symbol: str = "GBPUSD",
    ts_iso: str | None = None,
) -> Optional[float]:
    """Différence force(base) - force(quote) à un instant t.

    Returns:
        float ∈ [-100, +100] ou None.
        > 0 = devise base plus forte que quote (signal haussier pour symbol).
        < 0 = devise quote plus forte (signal baissier).
    """
    try:
        cols = SYMBOL_CURRENCY_MAP.get(symbol.upper())
        if not cols:
            return None
        col_base, col_quote = cols
        with _connect(db_path) as conn:
            if ts_iso is None:
                row = conn.execute(
                    "SELECT MAX(timestamp) FROM forces_snapshots WHERE symbol=?",
                    (symbol,),
                ).fetchone()
                if not row or not row[0]:
                    return None
                ts_iso = row[0]
            row = conn.execute(
                f"SELECT {col_base}, {col_quote} FROM forces_snapshots "
                "WHERE timestamp <= ? AND symbol = ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (ts_iso, symbol),
            ).fetchone()
            if not row or row[0] is None or row[1] is None:
                return None
            return round(float(row[0]) - float(row[1]), 2)
    except Exception:  # noqa: BLE001
        return None


def neutre_rate_24h(
    db_path: Path | str = DEFAULT_DB,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict:
    """Calcule le taux de régime NEUTRE sur les dernières 24h.

    Args:
        db_path: chemin DB.
        symbol: si fourni, restreint à ce symbole.
        timeframe: si fourni, restreint à ce TF.

    Returns:
        dict {total, neutre, pct, by_regime: {regime: count}}.
        pct ∈ [0, 100].

    R6 : retourne {"total": 0, "neutre": 0, "pct": 0.0, "by_regime": {}}.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        where_clauses = ["timestamp >= ?"]
        params: list = [cutoff]
        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            where_clauses.append("timeframe = ?")
            params.append(timeframe)
        where = " AND ".join(where_clauses)
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"SELECT regime_type, COUNT(*) FROM regime_snapshots "
                f"WHERE {where} GROUP BY regime_type",
                params,
            ).fetchall()
        if not rows:
            return {"total": 0, "neutre": 0, "pct": 0.0, "by_regime": {}}
        total = sum(c for _, c in rows)
        by_regime = {r: c for r, c in rows}
        neutre = by_regime.get("NEUTRE", 0)
        return {
            "total": total,
            "neutre": neutre,
            "pct": round(100.0 * neutre / total, 2) if total else 0.0,
            "by_regime": by_regime,
        }
    except Exception:  # noqa: BLE001
        return {"total": 0, "neutre": 0, "pct": 0.0, "by_regime": {}}


if __name__ == "__main__":
    # Smoke test CLI
    import sys, json
    db = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    print("=== Cross-pair dispersion (last snapshot global) ===")
    print(f"  global stddev 8 forces = {cross_pair_dispersion(db)}")
    print("=== Cross-pair dispersion per symbol (last) ===")
    for sym in SYMBOL_CURRENCY_MAP:
        print(f"  {sym} = {cross_pair_dispersion(db, symbol=sym)}")
    print("=== Pair force ratio (last) ===")
    for sym in SYMBOL_CURRENCY_MAP:
        print(f"  {sym} = {pair_force_ratio(db, symbol=sym)}")
    print("=== NEUTRE rate 24h (global) ===")
    print(json.dumps(neutre_rate_24h(db), indent=2))
