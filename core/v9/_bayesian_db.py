"""_bayesian_db.py — Lecture seule DB pour la calibration bayésienne (Axe 1.1).

Lit `data/v9_forces.db` (SQLite, **mode read-only strict** `mode=ro`) et
agrège les décisions résolues en compteurs WIN/LOSS par contexte, prêts à
être transformés en distributions Beta(α,β) par `bayesian_calibrator`.

Schéma réel (vérifié 2026-07-21, table `decisions`) — la spécification
d'origine référençait des colonnes fantômes (`principle_source`, `session`,
`regime`, `confidence`, `pnl_pips`). Les colonnes réelles utilisées ici :

- `principes_json`  : tableau JSON des principes source (explosé → 1 ligne / principe)
- `symbol`, `timeframe`
- `regime_type`     : régime (la « regime » de la spec)
- `confiance`       : entier 0-100 (la « confidence » de la spec)
- `is_win`          : 1 / 0 / NULL (non résolu)
- `resolution_strategy` : filtre `'DYNAMIC'` (exclut les 330 `SKIPPED`,
                          is_win=0 par convention mais qui ne sont pas de vraies pertes)
- `timestamp`       : ISO 8601 UTC → session dérivée (pas de colonne `session`)

Doctrine : R6 (ne jamais lever — toute erreur DB → structure vide), R18
(zéro LLM / réseau), lecture seule stricte (aucune écriture, aucune migration).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from core.v9.exit_simulator import infer_session_from_hour

logger = logging.getLogger("v9.bayesian_db")

# Clé de contexte : (principle, symbol, timeframe, session, regime).
ContextKey = tuple[str, str, str, str, str]


def _connect_ro(db_path: Path | str) -> sqlite3.Connection:
    """Connexion SQLite **read-only** (URI `mode=ro`). Lève si le fichier
    est absent — l'appelant (R6) capture et retombe sur une structure vide."""
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _session_from_timestamp(ts: str | None) -> str:
    """Dérive la session de marché depuis un timestamp ISO 8601 UTC.

    Pas de colonne `session` dans `decisions` — on la reconstruit via
    l'heure UTC (même heuristique que `exit_simulator.infer_session_from_hour`,
    source unique de vérité des sessions). Fallback `'inconnue'` si parse KO."""
    if not ts:
        return "inconnue"
    try:
        # Formats observés : '2026-07-21T05:38:58.579517+00:00'
        return infer_session_from_hour(datetime.fromisoformat(ts).hour)
    except (ValueError, TypeError):
        try:
            return infer_session_from_hour(int(ts[11:13]))
        except (ValueError, IndexError):
            return "inconnue"


def _parse_principles(principes_json: str | None) -> list[str]:
    """Parse le tableau JSON `principes_json`. Best-effort (R6) : renvoie
    une liste vide sur JSON invalide ou type inattendu."""
    if not principes_json:
        return []
    try:
        parsed = json.loads(principes_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(p) for p in parsed if p]


def read_context_aggregates(
    db_path: Path | str, min_n: int = 1, window_days: int = 30
) -> dict[ContextKey, dict[str, int]]:
    """Agrège les décisions résolues (`resolution_strategy='DYNAMIC'`) par
    contexte (principle × symbol × timeframe × session × regime).

    Une décision porte potentiellement plusieurs principes (`principes_json`) :
    elle est comptée dans le contexte de **chaque** principe (explosion),
    cohérent avec la sémantique « probabilité de gain par principe × contexte ».

    Args:
        db_path: chemin de la DB (lue en `mode=ro`).
        min_n: n minimum pour retenir un contexte (défaut 1 = tous).
        window_days: fenêtre glissante (défaut 30 j).

    Returns:
        `{context_key: {"wins": int, "losses": int, "n": int}}`. Vide si la
        DB est inaccessible / la table absente (R6 défensif).
    """
    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error as exc:
        logger.error("bayesian_db: DB inaccessible (%s) — agrégats vides", exc)
        return {}
    try:
        rows = conn.execute(
            "SELECT principes_json, symbol, timeframe, regime_type, is_win, timestamp "
            "FROM decisions "
            "WHERE is_win IS NOT NULL AND resolution_strategy = 'DYNAMIC' "
            "AND timestamp > datetime('now', ?)",
            (f"-{int(window_days)} days",),
        ).fetchall()
    except sqlite3.Error as exc:
        logger.error("bayesian_db: lecture decisions échouée (%s)", exc)
        return {}
    finally:
        conn.close()

    agg: dict[ContextKey, dict[str, int]] = {}
    for row in rows:
        session = _session_from_timestamp(row["timestamp"])
        regime = row["regime_type"] or "inconnu"
        symbol = row["symbol"] or "?"
        timeframe = row["timeframe"] or "?"
        is_win = row["is_win"]
        for principle in _parse_principles(row["principes_json"]):
            key: ContextKey = (principle, symbol, timeframe, session, regime)
            bucket = agg.setdefault(key, {"wins": 0, "losses": 0, "n": 0})
            if is_win == 1:
                bucket["wins"] += 1
            else:
                bucket["losses"] += 1
            bucket["n"] += 1

    return {k: v for k, v in agg.items() if v["n"] >= min_n}


def read_confidence_outcomes(
    db_path: Path | str, window_days: int = 7
) -> tuple[list[float], list[int]]:
    """Lit (confiance normalisée 0-1, is_win) sur la fenêtre récente pour le
    calcul du Brier score / calibration plot.

    Returns:
        `(predictions, outcomes)` — `predictions` = confiance/100.0 ∈ [0,1],
        `outcomes` = is_win ∈ {0,1}. Deux listes vides si DB inaccessible (R6).
    """
    try:
        conn = _connect_ro(db_path)
    except sqlite3.Error as exc:
        logger.error("bayesian_db: DB inaccessible pour Brier (%s)", exc)
        return [], []
    try:
        rows = conn.execute(
            "SELECT confiance, is_win FROM decisions "
            "WHERE is_win IS NOT NULL AND resolution_strategy = 'DYNAMIC' "
            "AND confiance IS NOT NULL AND timestamp > datetime('now', ?)",
            (f"-{int(window_days)} days",),
        ).fetchall()
    except sqlite3.Error as exc:
        logger.error("bayesian_db: lecture confiance échouée (%s)", exc)
        return [], []
    finally:
        conn.close()

    predictions = [max(0.0, min(1.0, float(r["confiance"]) / 100.0)) for r in rows]
    outcomes = [int(r["is_win"]) for r in rows]
    return predictions, outcomes
