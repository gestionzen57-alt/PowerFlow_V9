"""PrincipleScorer — Score historique des principes pour pondération (Phase 13.2).

Maintient une table `principle_scores` dans la DB avec les performances
historiques de chaque principe et combinaison de principes.

Permet à l'arbiter de pondérer la confiance selon le score réel :
  - Un principe avec WR 95% sur 100 trades → confiance boostée
  - Un principe avec WR 50% sur 10 trades → confiance réduite
  - Combinaison jamais vue → confiance neutre (mode conservateur)

Usage :
    scorer = PrincipleScorer()
    scorer.update(decision_id)  # après résolution
    weights = scorer.get_weights(principes_list)  # pour arbitrage
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

PRINCIPLE_SCORER_VERSION = "1.0"

# Seuil minimum d'échantillon pour qu'un score soit significatif
MIN_SAMPLE_SCORE = 5

# Table de scoring
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS principle_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    principle_id TEXT NOT NULL,
    combination_hash TEXT,  -- MD5 des principes combinés (NULL = seul)
    n_trades INTEGER NOT NULL DEFAULT 0,
    n_wins INTEGER NOT NULL DEFAULT 0,
    n_losses INTEGER NOT NULL DEFAULT 0,
    total_pips REAL NOT NULL DEFAULT 0.0,
    avg_pips REAL NOT NULL DEFAULT 0.0,
    win_rate REAL NOT NULL DEFAULT 0.0,
    last_updated TEXT NOT NULL,
    UNIQUE(principle_id, combination_hash)
)
"""


def _combination_hash(principes: list[str]) -> str | None:
    """Hash déterministe d'une combinaison de principes (triée)."""
    if not principes:
        return None
    import hashlib
    key = ",".join(sorted(principes))
    return hashlib.md5(key.encode()).hexdigest()[:12]


class PrincipleScorer:
    """Scoreur historique des principes.

    Maintient les stats par principe seul ET par combinaison.
    """
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def update_from_decision(
        self, decision_id: str, conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Met à jour les scores à partir d'une décision résolue.

        Args:
            decision_id: ID de la décision
            conn: Connexion partagée (optionnelle)

        Returns:
            True si mis à jour, False si pas de données
        """
        close_conn = conn is None
        if conn is None:
            conn = self._connect()

        try:
            row = conn.execute(
                "SELECT principes_json, is_win, resolution_pips "
                "FROM decisions WHERE decision_id = ? AND is_win IS NOT NULL",
                (decision_id,),
            ).fetchone()
            if row is None:
                return False

            import json
            try:
                principes = json.loads(row["principes_json"])
            except (json.JSONDecodeError, TypeError):
                principes = []

            if not principes:
                return False

            is_win = row["is_win"]
            pips = row["resolution_pips"] or 0.0
            now_iso = datetime.now(timezone.utc).isoformat()

            # Mise à jour par principe seul
            for p in principes:
                self._upsert(conn, p, None, is_win, pips, now_iso)

            # Mise à jour par combinaison
            comb_hash = _combination_hash(principes)
            if comb_hash:
                self._upsert(conn, "|".join(principes), comb_hash, is_win, pips, now_iso)

            conn.commit()
            return True
        finally:
            if close_conn:
                conn.close()

    def _upsert(
        self, conn: sqlite3.Connection,
        principle_id: str, comb_hash: str | None,
        is_win: int, pips: float, now_iso: str,
    ) -> None:
        """Upsert atomique d'un score."""
        existing = conn.execute(
            "SELECT n_trades, n_wins, total_pips FROM principle_scores "
            "WHERE principle_id = ? AND (combination_hash IS ? OR "
            "(combination_hash IS NULL AND ? IS NULL))",
            (principle_id, comb_hash, comb_hash),
        ).fetchone()

        if existing:
            n = existing["n_trades"] + 1
            nw = existing["n_wins"] + (1 if is_win else 0)
            tp = existing["total_pips"] + pips
            conn.execute(
                "UPDATE principle_scores SET n_trades=?, n_wins=?, n_losses=?, "
                "total_pips=?, avg_pips=?, win_rate=?, last_updated=? "
                "WHERE principle_id=? AND "
                "(combination_hash IS ? OR (combination_hash IS NULL AND ? IS NULL))",
                (n, nw, n - nw, tp, round(tp / n, 1), round(nw / n * 100, 1),
                 now_iso, principle_id, comb_hash, comb_hash),
            )
        else:
            conn.execute(
                "INSERT INTO principle_scores "
                "(principle_id, combination_hash, n_trades, n_wins, n_losses, "
                "total_pips, avg_pips, win_rate, last_updated) "
                "VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
                (principle_id, comb_hash,
                 1 if is_win else 0, 0 if is_win else 1,
                 pips, round(pips, 1), 100.0 if is_win else 0.0, now_iso),
            )

    def get_weights(
        self, principes: list[str],
    ) -> dict[str, Any]:
        """Retourne les poids pour une liste de principes.

        Returns:
            dict avec :
              - weight: float (0.5 à 1.5) — facteur multiplicatif pour confiance
              - avg_win_rate: float — WR moyen pondéré
              - n_samples: int — nombre total d'échantillons
              - details: list[dict] — détail par principe
        """
        if not principes:
            return {"weight": 1.0, "avg_win_rate": 0.0, "n_samples": 0, "details": []}

        conn = self._connect()
        try:
            weights: list[float] = []
            details: list[dict] = []
            total_samples = 0

            for p in principes:
                row = conn.execute(
                    "SELECT n_trades, n_wins, win_rate, avg_pips "
                    "FROM principle_scores "
                    "WHERE principle_id = ? AND combination_hash IS NULL",
                    (p,),
                ).fetchone()

                if row and row["n_trades"] >= MIN_SAMPLE_SCORE:
                    wr = row["win_rate"]
                    n = row["n_trades"]
                    avg = row["avg_pips"]
                    # Poids : WR/100 * min(n/20, 1.5) → 0.5 à 1.5
                    w = max(0.5, min(1.5, (wr / 100.0) * min(n / 20.0, 1.5)))
                    weights.append(w)
                    total_samples += n
                    details.append({
                        "principle": p,
                        "win_rate": wr,
                        "n_trades": n,
                        "avg_pips": avg,
                        "weight": round(w, 2),
                    })
                else:
                    # Pas assez de données → poids neutre
                    weights.append(1.0)
                    details.append({
                        "principle": p,
                        "win_rate": None,
                        "n_trades": row["n_trades"] if row else 0,
                        "avg_pips": None,
                        "weight": 1.0,
                        "reason": "insufficient_data" if (row and row["n_trades"] < MIN_SAMPLE_SCORE) else "no_data",
                    })

            # Poids global = moyenne des poids
            avg_weight = sum(weights) / len(weights) if weights else 1.0
            # WR moyen = moyenne des WR pondérée par n_trades
            weighted_wr = sum(
                d["win_rate"] * d["n_trades"] for d in details
                if d.get("win_rate") is not None
            ) / max(1, total_samples) if total_samples > 0 else 0.0

            return {
                "weight": round(avg_weight, 2),
                "avg_win_rate": round(weighted_wr, 1),
                "n_samples": total_samples,
                "details": details,
            }
        finally:
            conn.close()

    def get_top_combinations(
        self, limit: int = 10, min_trades: int = 5,
    ) -> list[dict]:
        """Retourne les meilleures combinaisons de principes."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT principle_id, n_trades, n_wins, win_rate, avg_pips "
                "FROM principle_scores "
                "WHERE combination_hash IS NOT NULL AND n_trades >= ? "
                "ORDER BY win_rate DESC, n_trades DESC LIMIT ?",
                (min_trades, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
