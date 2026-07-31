"""v9_spread_simulator.py — Phase 10 motion CEO « EDGE FUND MAX ».

R6 Perplexity : paper_trades n'a aucun tracking spread/slippage. Tous les
pips calcules sont mid-price. En live, spread GBPUSD typique = 1-1.5 pip,
slippage possible en news = 3-5 pips. Sur TP=25/SL=8, le spread represente
6-12% du TP.

Module : applique un spread simule configurable a chaque paper_trade a la
cloture, ajuste pips_simulated, et stocke le breakdown pour audit.

Typiques par symbol (mid-market estimation):
- GBPUSD: spread 1.2 pip, slippage 0.3 pip = total 1.5
- EURUSD: spread 1.0 pip, slippage 0.5 pip = total 1.5
- USDJPY: spread 1.5 pip, slippage 0.3 pip = total 1.8
- AUDUSD: spread 1.8 pip, slippage 0.5 pip = total 2.3
- USDCHF: spread 1.8 pip, slippage 0.5 pip = total 2.3
- USDCAD: spread 2.0 pip, slippage 0.5 pip = total 2.5
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger("v9.spread_simulator")

# Spread + slippage par symbol (pip). Mise a jour possible via env
# V9_SPREAD_<SYMBOL> (en pip, decimal autorise).
DEFAULT_SPREAD_PIPS = {
    "GBPUSD": 1.5,
    "EURUSD": 1.5,
    "USDJPY": 1.8,
    "AUDUSD": 2.3,
    "USDCHF": 2.3,
    "USDCAD": 2.5,
}


def get_spread_pips(symbol: str) -> float:
    """Retourne spread+slippage total pour le symbol (lecture env priorite)."""
    sym = symbol.upper()
    env_key = f"V9_SPREAD_{sym}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            log.warning("V9_SPREAD_%s=%s invalide, defaut applique", sym, env_val)
    return DEFAULT_SPREAD_PIPS.get(sym, 2.0)


def apply_spread_to_trades(
    db_path: Path | str,
    *,
    closed_only: bool = True,
    dry_run: bool = False,
) -> dict[str, int]:
    """Applique spread retroactivement sur tous les paper_trades.

    Modifie pips_simulated = pips_simulated - spread_pips si is_win=1
    (gain reduit du spread) et pips_simulated = pips_simulated - spread_pips
    si is_win=0 (perte aggravee du spread).

    Retourne dict {updated: N, total: N, total_pips_delta: float}.

    Note : utilise des champs derives (pas de colonnes ajoutees) pour eviter
    migration DB. Stocke dans pips_spread_cost les colonnes supplementaires.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"updated": 0, "total": 0, "total_pips_delta": 0.0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Verifier presence colonnes spread (migrate-once)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(paper_trades)")}
    has_spread_col = "spread_pips" in cols
    has_net_col = "pips_net_of_spread" in cols
    if not has_spread_col:
        conn.execute("ALTER TABLE paper_trades ADD COLUMN spread_pips REAL")
    if not has_net_col:
        conn.execute("ALTER TABLE paper_trades ADD COLUMN pips_net_of_spread REAL")
    if not (has_spread_col and has_net_col):
        conn.commit()
        log.info("v9_spread: colonnes spread migrees")

    # Selection des trades a mettre a jour (utilise WHERE qui marche
    # meme si colonnes viennent d'etre ajoutees : on filtre sur NULL).
    where = "WHERE pips_net_of_spread IS NULL"
    if closed_only:
        where += " AND closed_at IS NOT NULL"

    rows = conn.execute(f"""
        SELECT trade_id, snapshot_id, pips_simulated, is_win
        FROM paper_trades {where}
    """).fetchall()

    updated = 0
    total_delta = 0.0
    for r in rows:
        # Extraire symbol depuis snapshot_id (format v9-<SYM>-<TF>-...)
        snap = str(r["snapshot_id"])
        parts = snap.split("-")
        if len(parts) < 3:
            continue
        sym = parts[1]
        spread = get_spread_pips(sym)
        # Aplique le spread : gain reduit (win) ou perte aggravee (loss)
        new_pips = float(r["pips_simulated"]) - spread
        if not dry_run:
            conn.execute("""
                UPDATE paper_trades
                SET spread_pips = ?, pips_net_of_spread = ?
                WHERE trade_id = ?
            """, (spread, new_pips, r["trade_id"]))
        updated += 1
        total_delta += -spread  # toujours -spread (frais)

    if not dry_run:
        conn.commit()
    conn.close()

    log.info(
        "v9_spread: %d/%d trades mis a jour, delta_pips_total=%.1f%s",
        updated, len(rows), total_delta, " (dry_run)" if dry_run else "",
    )
    return {
        "updated": updated,
        "total": len(rows),
        "total_pips_delta": total_delta,
    }


def compute_net_expectancy(db_path: Path | str) -> dict[str, float]:
    """Calcule expectancy nette (apres spread) sur 90j GBPUSD haussiere 11-13h."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"n": 0, "wr": 0.0, "expectancy_brut": 0.0, "expectancy_net": 0.0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT COUNT(*) n,
               ROUND(100.0*SUM(is_win)/COUNT(*),1) wr,
               ROUND(AVG(pips_simulated),2) expectancy_brut,
               ROUND(AVG(COALESCE(pips_net_of_spread, pips_simulated)),2) expectancy_net,
               ROUND(SUM(COALESCE(pips_net_of_spread, pips_simulated)),1) total_net
        FROM paper_trades
        WHERE substr(snapshot_id,4,6) = 'GBPUSD'
          AND direction = 'haussiere'
          AND opened_at > datetime('now','-90 days')
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


def detect_wr_early_warning(
    db_path: Path | str,
    *,
    lookback_days: int = 7,
    drift_threshold: float = 5.0,
) -> dict[str, object]:
    """L12 (Phase 11 motion CEO) — Detecte derive WR avant seuil critique.

    Si le WR 7j glissant baisse de > `drift_threshold` pts sur 3 jours
    consecutifs → alerte "wr_early_warning" (avant le seuil wr_below_threshold
    60% du cron Phase 7).

    Audit de tendance lineaire : on calcule le WR pour 3 fenetres
    consecutives de 7j et regarde si la baisse cumulee > drift_threshold.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"alert": False, "reason": "db_missing"}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = []
    for offset in (0, 1, 2):
        start = offset * 24 * 60  # 24h decalage
        end = lookback_days * 24 * 60 + start
        row = conn.execute("""
            SELECT COUNT(*) n,
                   ROUND(100.0*SUM(is_win)*1.0/COUNT(*),1) wr
            FROM paper_trades
            WHERE substr(snapshot_id,4,6) = 'GBPUSD'
              AND direction = 'haussiere'
              AND opened_at > datetime('now', ? || ' minutes')
              AND opened_at <= datetime('now', ? || ' minutes')
        """, (-end, -start)).fetchone()
        rows.append(dict(row) if row else {"n": 0, "wr": 0.0})
    conn.close()

    if rows[2]["n"] < 5:
        # Pas assez de data → pas d'alerte
        return {"alert": False, "reason": "insufficient_data",
                "wr_recent": rows[0], "wr_mid": rows[1], "wr_old": rows[2]}

    # Calcul derive : WR recents - WR anciens
    drift = rows[0]["wr"] - rows[2]["wr"]
    declining = (rows[0]["wr"] <= rows[1]["wr"] <= rows[2]["wr"])
    # Wait — on veut detecter baisse, donc recent < mid < old (decline)
    # recent est rows[0] (les plus recents = aujourd'hui)
    # old est rows[2] (il y a 2j)

    if drift <= -drift_threshold and declining:
        return {
            "alert": True,
            "reason": "wr_declining_3d",
            "drift_pts": drift,
            "wr_recent": rows[0],
            "wr_mid": rows[1],
            "wr_old": rows[2],
            "recommendation": "rollback_to_shadow_mode",
        }

    return {
        "alert": False,
        "reason": "stable",
        "drift_pts": drift,
        "wr_recent": rows[0],
        "wr_mid": rows[1],
        "wr_old": rows[2],
    }