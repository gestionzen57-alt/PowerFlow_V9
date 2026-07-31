"""v9_human_mirror.py — Module d'apprentissage du fingerprint humain (J3 28/07).

Motion CEO « GO MAX » : le système doit apprendre ta façon de trader
pour filtrer les trades manqués (mode READONLY par défaut, ACTIF via
V9_HUMAN_MIRROR_BLOCKING=1).

Concepts :
- Saisie manuelle de trades réels via scripts/v9_log_human_trade.py
- Table v9_human_trades (symbol, direction, tf, prix_entry, sl, tp, confidence, snapshot_id_approx, timestamp)
- Score match entre signal live et pattern historique (heuristique : heure proche, prix proche, principes overlappants, sens)
- Mode READONLY (log seulement) vs BLOCKING (downgrade action si score < seuil)
- R2 additif, R6 jamais bloquant (DB indisponible → score=0.5 neutre).

Architecturalement, ce module est séparé de principle_engine (pas dans la
chaîne cognitive). Il consomme les signaux émis et les compare au pattern.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("v9.human_mirror")


def mirror_enabled() -> bool:
    """Kill switch V9_HUMAN_MIRROR_ENABLED — module actif (défaut OFF, R25')."""
    return os.environ.get("V9_HUMAN_MIRROR_ENABLED", "1") == "1"


def mirror_blocking_enabled() -> bool:
    """Kill switch V9_HUMAN_MIRROR_BLOCKING — downgrade action si score<seuil."""
    return os.environ.get("V9_HUMAN_MIRROR_BLOCKING", "0") == "1"


def block_threshold() -> float:
    """Seuil de score match en dessous duquel l'action est downgrade (défaut 0.5)."""
    try:
        return float(os.environ.get("V9_HUMAN_MIRROR_BLOCK_THRESHOLD", "0.5"))
    except Exception:
        return 0.5


def _score_components(
    signal: dict,
    human: dict,
    current_hour_utc: int,
) -> tuple[float, list[str]]:
    """Calcule les composantes du score 0-1 entre un signal live et un trade humain.

    Composantes (chacune 0..1, pondérées) :
    0.20 — même symbol
    0.20 — même direction
    0.15 — même timeframe (ou proche)
    0.15 — prix entry proche (delta < 50 pips)
    0.10 — principes overlappants (Jaccard)
    0.10 — session (mapped via hour UTC)
    0.10 — confiance similaire (+/- 15 pts)
    Total max = 1.0.
    """
    score = 0.0
    details = []

    sym_sig = str(signal.get("symbol", "")).upper()
    sym_hum = str(human.get("symbol", "")).upper()
    if sym_sig and sym_hum and sym_sig == sym_hum:
        score += 0.20
        details.append(f"symbol_match:{sym_sig}")

    dir_sig = str(signal.get("direction", "")).lower()
    dir_hum = str(human.get("direction", "")).lower()
    if dir_sig and dir_hum and dir_sig == dir_hum:
        score += 0.20
        details.append(f"direction_match:{dir_sig}")

    tf_sig = signal.get("timeframe")
    tf_hum = human.get("timeframe")
    if tf_sig and tf_hum:
        try:
            d = abs(int(tf_sig) - int(tf_hum))
            tf_score = max(0.0, 1.0 - d / 60.0)  # 60 min = 0
            score += 0.15 * tf_score
            if tf_score > 0.5:
                details.append(f"tf_close:{tf_sig}~{tf_hum}")
        except (TypeError, ValueError):
            pass

    px_sig = signal.get("entry_price")
    px_hum = human.get("entry_price")
    if px_sig and px_hum:
        try:
            delta_pips = abs(float(px_sig) - float(px_hum)) * 10000
            # Normalisation : 0 pip = 1.0, 50+ pips = 0.0
            px_score = max(0.0, 1.0 - delta_pips / 50.0)
            score += 0.15 * px_score
            if px_score > 0.5:
                details.append(f"price_close:{delta_pips:.1f}pips")
        except (TypeError, ValueError):
            pass

    pr_sig = set(signal.get("principes", []) or [])
    pr_hum = set(human.get("principes", []) or [])
    if pr_sig or pr_hum:
        union = pr_sig | pr_hum
        inter = pr_sig & pr_hum
        if union:
            jaccard = len(inter) / len(union)
            score += 0.10 * jaccard
            if jaccard > 0.3:
                details.append(f"principes_overlap:{jaccard:.2f}")

    # Session : mappée via current_hour_utc.
    # asie 0-7, sydney 1-8, london 7-16, overlap 12-17, new_york 13-22.
    sess_sig = signal.get("session", "")
    sess_hum = human.get("session", "")
    if sess_sig and sess_hum and sess_sig == sess_hum:
        score += 0.10
        details.append(f"session_match:{sess_sig}")
    elif sess_sig or sess_hum:
        # Session différente → partiel si heures chevauchent
        sess_score = 0.0
        if 7 <= current_hour_utc <= 16 and sess_sig in ("asie", "sydney", "london", "overlap"):
            sess_score = 0.05
        elif 13 <= current_hour_utc <= 22 and sess_sig in ("overlap", "new_york"):
            sess_score = 0.05
        score += sess_score
        if sess_score > 0:
            details.append(f"session_partial:{current_hour_utc}h")

    conf_sig = signal.get("confiance", 0)
    conf_hum = human.get("confiance", 0)
    if conf_sig and conf_hum:
        delta = abs(int(conf_sig) - int(conf_hum))
        conf_score = max(0.0, 1.0 - delta / 30.0)  # ±15 pts = full, ±30 = 0
        score += 0.10 * conf_score
        if conf_score > 0.5:
            details.append(f"conf_close:{conf_sig}~{conf_hum}")

    return min(score, 1.0), details


def load_human_trades(db_path: Path | str | None = None, limit: int = 100) -> list[dict]:
    """Charge les N derniers trades humains depuis v9_human_trades (lecture seule).

    Best-effort (R6) : si table absente (DB non migrée), retourne [].
    """
    from core.v9.config import DB_PATH

    path = Path(db_path) if db_path else DB_PATH
    rows = []
    try:
        with sqlite3.connect(str(path)) as conn:
            try:
                cur = conn.execute(
                    "SELECT * FROM v9_human_trades "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            except sqlite3.OperationalError:
                # Table non migrée — R6, silencieux
                return []
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                # Parse JSON columns if present
                for k in ("principes", "metadata"):
                    if k in d and isinstance(d[k], str):
                        try:
                            d[k] = json.loads(d[k])
                        except (ValueError, TypeError):
                            d[k] = []
                rows.append(d)
    except Exception as exc:
        log.debug("load_human_trades best-effort failed: %s", exc)
    return rows


def match_score(
    signal: dict,
    db_path: Path | str | None = None,
    current_hour_utc: int | None = None,
) -> dict:
    """Compare un signal live à tous les trades humains, retourne le meilleur match.

    Args:
        signal: dict avec clés symbol, direction, timeframe, entry_price,
                confiance, session, principes (liste ou null).
        db_path: chemin DB (défaut DB_PATH config).
        current_hour_utc: heure UTC (défaut: maintenant).

    Returns:
        dict avec score (0-1), best_match (humain dict), n_humans (compteur),
        action_recommended ('keep' | 'downgrade' | 'observe').
    """
    if current_hour_utc is None:
        current_hour_utc = datetime.utcnow().hour

    humans = load_human_trades(db_path)
    if not humans:
        # Pas de données humaines → neutre, on n'influence pas la décision.
        return {
            "score": 0.5,
            "best_match": None,
            "n_humans": 0,
            "action_recommended": "keep",
            "details": ["no_human_data"],
        }

    best_score = 0.0
    best_match = None
    best_details = []
    for h in humans:
        s, det = _score_components(signal, h, current_hour_utc)
        if s > best_score:
            best_score = s
            best_match = h
            best_details = det

    # Décision
    threshold = block_threshold()
    if best_score >= 0.8:
        action = "keep"
    elif best_score >= threshold:
        action = "observe"
    else:
        action = "downgrade"

    return {
        "score": best_score,
        "best_match": best_match,
        "n_humans": len(humans),
        "action_recommended": action,
        "details": best_details,
    }
