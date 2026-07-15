"""PrincipleAlphaEngine — Moteur de mesure alpha par principe V9 (SOUL.md §3-4).

Couche 1+2 du moteur de recherche alpha : mesure la performance de chaque
principe déclenché sur toutes les dimensions (session, regime, timeframe,
direction, vol_regime), détecte les zones sur/sous-performantes, l'edge decay,
et classe les principes.

Chaque principe devient une stratégie mesurée :
  - WR, expectancy, avg_pips, total_pips, profit_factor, sharpe_like
  - max_drawdown, stability, hit_rate
  - décomposition par dimension (session × regime × timeframe × direction × vol)
  - détection de dégradation d'edge par fenêtre glissante

Source : principle_evaluations (triggered=1) JOIN decisions (is_win NOT NULL).
Les pips réels viennent de decisions.resolution_pips (signés).

Doctrine :
  - R18 : stdlib uniquement, aucun LLM, aucune dépendance externe
  - R2 : couche additive (lit les tables existantes, écrit sa propre table)
  - R6 : try/except, ne crash jamais l'orchestrateur
  - R25' : les métriques sont descriptives (l'auto-promotion vit ailleurs)
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.exit_simulator import infer_session_from_hour

log = logging.getLogger(__name__)

ALPHA_ENGINE_VERSION = "1.0"

# Sentinelle pour les dimensions non filtrées (permet l'upsert UNIQUE, les
# NULL SQLite étant considérés distincts et cassant ON CONFLICT).
ALL = "ALL"

# Dimensions décomposables par compute_all_dimensions.
DIMENSIONS = ("session", "regime", "timeframe", "direction", "vol_regime")

# Seuils de détection (SOUL.md §2).
UNDERPERF_DELTA = 15.0  # WR dimension < WR_global - 15% → underperforming
OUTPERF_DELTA = 10.0    # WR dimension > WR_global + 10% → outperforming
EDGE_DECAY_DELTA = 15.0  # dégradation WR > 15% sur fenêtre → alerte

ALPHA_METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS principle_alpha_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    principle_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    session TEXT,
    regime TEXT,
    timeframe TEXT,
    direction TEXT,
    n_trades INTEGER,
    wins INTEGER,
    losses INTEGER,
    win_rate REAL,
    expectancy REAL,
    avg_pips REAL,
    total_pips REAL,
    max_drawdown REAL,
    profit_factor REAL,
    sharpe_like REAL,
    stability REAL,
    source_type TEXT DEFAULT 'live',
    UNIQUE(principle_id, session, regime, timeframe, direction)
);
CREATE INDEX IF NOT EXISTS idx_alpha_metrics_principle
    ON principle_alpha_metrics (principle_id);
"""


def init_alpha_db(db_path: Path | None = None) -> None:
    """Crée la table principle_alpha_metrics si absente (idempotent)."""
    conn = get_connection(db_path)
    try:
        conn.executescript(ALPHA_METRICS_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _hour_of(timestamp: str | None) -> int:
    """Extrait l'heure UTC d'un timestamp ISO 8601 (0 si illisible)."""
    if not timestamp:
        return 0
    try:
        return datetime.fromisoformat(timestamp).astimezone(timezone.utc).hour
    except Exception:
        try:
            return int(timestamp[11:13])
        except Exception:
            return 0


def _pips_of(resolution_pips: Any, is_win: Any) -> float:
    """Pips signés d'un trade. Fallback ±1 si resolution_pips absent."""
    if resolution_pips is not None:
        try:
            return float(resolution_pips)
        except (TypeError, ValueError):
            pass
    return 1.0 if is_win == 1 else -1.0


def _metrics_from_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcule le bloc de métriques depuis une liste de trades.

    Chaque trade : {"is_win": 0|1, "pips": float}. Les trades sont supposés
    ordonnés chronologiquement (pour drawdown/stability).
    """
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "expectancy": 0.0, "avg_pips": 0.0, "total_pips": 0.0,
            "max_drawdown": 0.0, "profit_factor": 0.0, "sharpe_like": 0.0,
            "stability": 0.0, "hit_rate": 0.0,
        }

    pips = [float(t["pips"]) for t in trades]
    wins = sum(1 for t in trades if t["is_win"] == 1)
    losses = n - wins
    total_pips = sum(pips)
    avg_pips = total_pips / n
    win_rate = wins / n * 100.0
    hit_rate = sum(1 for p in pips if p > 0) / n * 100.0

    gross_win = sum(p for p in pips if p > 0)
    gross_loss = -sum(p for p in pips if p < 0)
    if gross_loss > 0:
        profit_factor = round(gross_win / gross_loss, 3)
    else:
        profit_factor = round(gross_win, 3) if gross_win > 0 else 0.0

    # Sharpe-like : moyenne / écart-type des pips.
    if n > 1:
        mean = avg_pips
        var = sum((p - mean) ** 2 for p in pips) / (n - 1)
        std = math.sqrt(var)
        sharpe_like = round(mean / std, 3) if std > 0 else 0.0
    else:
        sharpe_like = 0.0

    # Max drawdown : plus grande chute pic-à-creux de l'équité cumulée.
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pips:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Stability : régularité du WR à travers le temps (5 tranches).
    stability = _compute_stability(trades)

    return {
        "n_trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "expectancy": round(avg_pips, 3),
        "avg_pips": round(avg_pips, 3),
        "total_pips": round(total_pips, 2),
        "max_drawdown": round(max_dd, 2),
        "profit_factor": profit_factor,
        "sharpe_like": sharpe_like,
        "stability": stability,
        "hit_rate": round(hit_rate, 2),
    }


def _compute_stability(trades: list[dict[str, Any]], n_buckets: int = 5) -> float:
    """Régularité du WR dans le temps ∈ [0, 1].

    Découpe les trades en `n_buckets` tranches chronologiques, calcule le WR
    par tranche, et retourne 1 - dispersion normalisée. Un principe dont le WR
    reste stable dans le temps est plus fiable qu'un principe erratique.
    """
    n = len(trades)
    if n < n_buckets * 2:
        return 1.0 if n > 0 else 0.0
    size = n // n_buckets
    bucket_wr: list[float] = []
    for i in range(n_buckets):
        start = i * size
        end = start + size if i < n_buckets - 1 else n
        chunk = trades[start:end]
        if chunk:
            bucket_wr.append(sum(1 for t in chunk if t["is_win"] == 1) / len(chunk))
    if len(bucket_wr) < 2:
        return 1.0
    mean = sum(bucket_wr) / len(bucket_wr)
    var = sum((w - mean) ** 2 for w in bucket_wr) / len(bucket_wr)
    std = math.sqrt(var)
    # std ∈ [0, 0.5] en pratique ; on normalise sur 0.5.
    return round(max(0.0, 1.0 - std / 0.5), 3)


class PrincipleAlphaEngine:
    """Moteur de mesure alpha par principe.

    Usage :
        engine = PrincipleAlphaEngine()
        m = engine.compute_metrics("PRICE_LAG_AT_NODE_BIRTH")
        dims = engine.compute_all_dimensions("PRICE_LAG_AT_NODE_BIRTH")
        decay = engine.detect_edge_decay("PRICE_LAG_AT_NODE_BIRTH")
        ranking = engine.rank_principles(metric="expectancy")
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_alpha_db(self.db_path)
        self._trade_cache: dict[str, list[dict[str, Any]]] = {}

    # ── Chargement des trades ──

    def _fetch_trades(self, principle_id: str) -> list[dict[str, Any]]:
        """Trades résolus d'un principe, ordonnés chronologiquement.

        Un trade = un snapshot où le principe a triggered ET dont la décision
        a un outcome (is_win). Enrichi des dimensions (session, regime, tf,
        direction, vol_regime).
        """
        if principle_id in self._trade_cache:
            return self._trade_cache[principle_id]

        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            has_vol = self._has_vol_regime(conn)
            vol_select = (
                "(SELECT rs.vol_regime FROM regime_snapshots rs "
                " WHERE rs.forces_snapshot_ref = pe.snapshot_id "
                " ORDER BY rs.rowid DESC LIMIT 1)"
                if has_vol else "NULL"
            )
            rows = conn.execute(
                f"""
                SELECT d.is_win AS is_win,
                       d.resolution_pips AS resolution_pips,
                       d.timestamp AS ts,
                       d.regime_type AS regime,
                       COALESCE(pe.direction, d.direction) AS direction,
                       COALESCE(pe.timeframe, d.timeframe) AS timeframe,
                       {vol_select} AS vol_regime
                FROM principle_evaluations pe
                JOIN decisions d ON d.snapshot_id = pe.snapshot_id
                WHERE pe.principle_id = ?
                  AND pe.triggered = 1
                  AND d.is_win IS NOT NULL
                ORDER BY d.timestamp ASC
                """,
                (principle_id,),
            ).fetchall()
        except Exception as exc:
            log.debug("alpha: _fetch_trades failed [%s]: %s", principle_id, exc)
            rows = []
        finally:
            conn.close()

        trades: list[dict[str, Any]] = []
        for r in rows:
            trades.append({
                "is_win": r["is_win"],
                "pips": _pips_of(r["resolution_pips"], r["is_win"]),
                "session": infer_session_from_hour(_hour_of(r["ts"])),
                "regime": r["regime"] or ALL,
                "timeframe": r["timeframe"] or ALL,
                "direction": r["direction"] or ALL,
                "vol_regime": r["vol_regime"] or ALL,
            })
        self._trade_cache[principle_id] = trades
        return trades

    @staticmethod
    def _has_vol_regime(conn: sqlite3.Connection) -> bool:
        """True si regime_snapshots porte la colonne vol_regime (migration)."""
        try:
            cols = {d[1] for d in conn.execute(
                "PRAGMA table_info(regime_snapshots)").fetchall()}
            return "vol_regime" in cols
        except Exception:
            return False

    @staticmethod
    def _filter(
        trades: list[dict[str, Any]],
        session: str | None = None,
        regime: str | None = None,
        timeframe: str | None = None,
        direction: str | None = None,
        vol_regime: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filtre les trades selon les dimensions non-None."""
        out = trades
        if session is not None:
            out = [t for t in out if t["session"] == session]
        if regime is not None:
            out = [t for t in out if t["regime"] == regime]
        if timeframe is not None:
            out = [t for t in out if t["timeframe"] == timeframe]
        if direction is not None:
            out = [t for t in out if t["direction"] == direction]
        if vol_regime is not None:
            out = [t for t in out if t["vol_regime"] == vol_regime]
        return out

    # ── Métriques ──

    def compute_metrics(
        self,
        principle_id: str,
        session: str | None = None,
        regime: str | None = None,
        timeframe: str | None = None,
        direction: str | None = None,
        min_n: int = 5,
    ) -> dict[str, Any]:
        """Métriques d'un principe pour une combinaison de dimensions.

        Args:
            principle_id: identifiant du principe
            session/regime/timeframe/direction: filtres optionnels (None = tous)
            min_n: nb minimal de trades pour juger l'échantillon suffisant

        Returns:
            dict de métriques + flag `insufficient` si n < min_n.
        """
        trades = self._filter(
            self._fetch_trades(principle_id),
            session=session, regime=regime,
            timeframe=timeframe, direction=direction,
        )
        metrics = _metrics_from_trades(trades)
        metrics.update({
            "principle_id": principle_id,
            "session": session,
            "regime": regime,
            "timeframe": timeframe,
            "direction": direction,
            "insufficient": metrics["n_trades"] < min_n,
        })
        return metrics

    def compute_all_dimensions(
        self, principle_id: str, min_n: int = 5,
    ) -> dict[str, Any]:
        """Décompose le principe sur toutes les dimensions.

        Retourne pour chaque dimension un dict {valeur: métriques}, plus la
        liste des zones underperforming et outperforming vs le WR global.
        """
        trades = self._fetch_trades(principle_id)
        global_metrics = _metrics_from_trades(trades)
        global_wr = global_metrics["win_rate"]

        result: dict[str, Any] = {
            "principle_id": principle_id,
            "global": global_metrics,
            "dimensions": {},
            "underperforming": [],
            "outperforming": [],
        }

        for dim in DIMENSIONS:
            values = sorted({t[dim] for t in trades})
            dim_result: dict[str, Any] = {}
            for val in values:
                subset = [t for t in trades if t[dim] == val]
                m = _metrics_from_trades(subset)
                m["insufficient"] = m["n_trades"] < min_n
                dim_result[val] = m
                if m["n_trades"] >= min_n:
                    if m["win_rate"] < global_wr - UNDERPERF_DELTA:
                        result["underperforming"].append({
                            "dimension": dim, "value": val,
                            "win_rate": m["win_rate"], "n_trades": m["n_trades"],
                            "delta": round(m["win_rate"] - global_wr, 2),
                        })
                    elif m["win_rate"] > global_wr + OUTPERF_DELTA:
                        result["outperforming"].append({
                            "dimension": dim, "value": val,
                            "win_rate": m["win_rate"], "n_trades": m["n_trades"],
                            "delta": round(m["win_rate"] - global_wr, 2),
                        })
            result["dimensions"][dim] = dim_result

        return result

    def detect_edge_decay(
        self,
        principle_id: str,
        window_sizes: list[int] | None = None,
        threshold: float = EDGE_DECAY_DELTA,
    ) -> dict[str, Any]:
        """Détecte la dégradation d'edge par fenêtre glissante.

        Compare le WR des N derniers trades au WR global. Si la dégradation
        dépasse `threshold` sur une fenêtre, lève une alerte.
        """
        window_sizes = window_sizes or [50, 100, 200]
        trades = self._fetch_trades(principle_id)
        global_metrics = _metrics_from_trades(trades)
        global_wr = global_metrics["win_rate"]

        result: dict[str, Any] = {
            "principle_id": principle_id,
            "global_wr": global_wr,
            "n_total": len(trades),
            "windows": {},
            "decayed": False,
            "alert": None,
        }

        for w in window_sizes:
            if len(trades) < w:
                result["windows"][w] = {"insufficient": True, "n": len(trades)}
                continue
            recent = trades[-w:]
            recent_wr = _metrics_from_trades(recent)["win_rate"]
            delta = round(recent_wr - global_wr, 2)
            decayed = delta < -threshold
            result["windows"][w] = {
                "recent_wr": recent_wr,
                "global_wr": global_wr,
                "delta": delta,
                "decayed": decayed,
            }
            if decayed:
                result["decayed"] = True
                result["alert"] = (
                    f"{principle_id}: edge decay {delta:+.1f}% sur {w} trades "
                    f"(récent {recent_wr:.1f}% vs global {global_wr:.1f}%)"
                )

        return result

    def list_principles(self) -> list[str]:
        """Tous les principle_id ayant au moins un trade déclenché."""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT principle_id FROM principle_evaluations "
                "WHERE triggered = 1"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        except Exception:
            return []
        finally:
            conn.close()

    def rank_principles(
        self, metric: str = "expectancy", min_n: int = 10,
    ) -> list[tuple[str, float, int]]:
        """Classe les principes par métrique décroissante.

        Returns:
            liste de (principle_id, valeur_metrique, n_trades), meilleurs d'abord.
        """
        ranking: list[tuple[str, float, int]] = []
        for pid in self.list_principles():
            m = _metrics_from_trades(self._fetch_trades(pid))
            if m["n_trades"] < min_n:
                continue
            value = m.get(metric)
            if value is None:
                continue
            ranking.append((pid, float(value), m["n_trades"]))
        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking

    def get_dashboard(self, min_n: int = 5) -> dict[str, Any]:
        """Tableau de bord complet : tous principes × toutes dimensions."""
        dashboard: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "principles": {},
            "ranking_expectancy": self.rank_principles("expectancy", min_n),
            "ranking_win_rate": self.rank_principles("win_rate", min_n),
        }
        for pid in self.list_principles():
            try:
                dashboard["principles"][pid] = {
                    "all_dimensions": self.compute_all_dimensions(pid, min_n),
                    "edge_decay": self.detect_edge_decay(pid),
                }
            except Exception as exc:
                log.debug("alpha: dashboard failed [%s]: %s", pid, exc)
        return dashboard

    # ── Persistance ──

    def persist_metrics(
        self, principle_id: str, source_type: str = "live",
    ) -> int:
        """Persiste les métriques globales + par session dans la table.

        Retourne le nombre de lignes upsertées.
        """
        init_alpha_db(self.db_path)
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        n_written = 0
        try:
            # Ligne globale + une ligne par session (dimension la plus utile).
            rows_to_write: list[tuple[str | None, str | None]] = [(None, None)]
            trades = self._fetch_trades(principle_id)
            sessions = sorted({t["session"] for t in trades})
            rows_to_write += [(s, None) for s in sessions]

            for session, regime in rows_to_write:
                m = self.compute_metrics(
                    principle_id, session=session, regime=regime,
                )
                if m["n_trades"] == 0:
                    continue
                conn.execute(
                    """
                    INSERT INTO principle_alpha_metrics (
                        principle_id, timestamp, session, regime, timeframe,
                        direction, n_trades, wins, losses, win_rate, expectancy,
                        avg_pips, total_pips, max_drawdown, profit_factor,
                        sharpe_like, stability, source_type
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(principle_id, session, regime, timeframe, direction)
                    DO UPDATE SET
                        timestamp=excluded.timestamp,
                        n_trades=excluded.n_trades, wins=excluded.wins,
                        losses=excluded.losses, win_rate=excluded.win_rate,
                        expectancy=excluded.expectancy, avg_pips=excluded.avg_pips,
                        total_pips=excluded.total_pips,
                        max_drawdown=excluded.max_drawdown,
                        profit_factor=excluded.profit_factor,
                        sharpe_like=excluded.sharpe_like,
                        stability=excluded.stability,
                        source_type=excluded.source_type
                    """,
                    (
                        principle_id, now,
                        session if session is not None else ALL,
                        regime if regime is not None else ALL,
                        ALL, ALL,
                        m["n_trades"], m["wins"], m["losses"], m["win_rate"],
                        m["expectancy"], m["avg_pips"], m["total_pips"],
                        m["max_drawdown"], m["profit_factor"], m["sharpe_like"],
                        m["stability"], source_type,
                    ),
                )
                n_written += 1
            conn.commit()
        except Exception as exc:
            log.debug("alpha: persist_metrics failed [%s]: %s", principle_id, exc)
        finally:
            conn.close()
        return n_written

    def invalidate_cache(self) -> None:
        """Vide le cache des trades (après nouvelles clôtures)."""
        self._trade_cache.clear()
