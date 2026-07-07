"""Seuils adaptatifs V9 — propositions ONLY, zero application auto.

Problème résolu (CEO quant stratège 2026-07-07) :
- config.py contient des seuils PROVISIONAL/portés V8 (SEUIL_PALIER=0.5,
  REPLAY_MIN_CAS=3, SIMILARITY_THRESHOLD=0.65) jamais recalibrés sur V9.
- Perplexity les a gelés par règle 22 ("1 livraison = 1 commit").
- Søn se retrouve à tourner avec des seuils V8 sur données V9 = logique.

Conception (anti-bridage explicite) :
- Module pure-Python : agrège observations live, propose seuils révisés.
- **AUCUNE écriture dans config.py**. Toute proposition doit être appliquée
  manuellement par Søn après lecture du diff.
- Compat Règle 30 + 25 : pas d'invention de seuil chiffré sans backtest prouvé.

Fonctions livrées :
- compute_replay_min_cas(actual_replay_count, total_replay_wins)
- compute_antagonism_threshold(recent_scenes_with_antagonism)
- compute_similarity_threshold(recent_behaviors)
- propose_thresholds_diff() : retourne dict seuils actuels vs proposés (CLI)

Garde-fou : retourne un dict sérialisable, JAMAIS d'écriture DB directe
sur la table learning_proposals (c'est learning_loop.py qui s'en charge).
"""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from typing import Any

from core.v9.config import (
    ANTAGONISM_THRESHOLD as CURRENT_ANTAGONISM,
    REPLAY_MIN_CAS as CURRENT_REPLAY_MIN,
    SIMILARITY_THRESHOLD as CURRENT_SIMILARITY,
)


def compute_replay_min_cas(actual_replay_count: int, total_replay_wins: int) -> int:
    """Propose replay_min_cas adaptatif selon l'historique observé.

    Logique (repère initial, révisable par Søn — règle 25) :
    - 0 replay observé → 1 (lâche, anti-paradoxe BOOT)
    - 1-2 replays → 1 (consolider)
    - 3-9 replays → 2 (montée progressive)
    - 10+ replays → 3 (calibré, comme V8 original)

    Returns entier >= 1 (jamais 0, jamais négatif).
    """
    if actual_replay_count <= 0:
        return 1
    if actual_replay_count < 3:
        return 1
    if actual_replay_count < 10:
        return 2
    return 3


def compute_antagonism_threshold(
    recent_scenes_with_antagonism: list[float],
    target_quantile: float = 0.75,
) -> float:
    """Propose seuil d'antagonisme adaptatif (à calibrer sur scenes.observees).

    Logique : P{quantile} des antagonismes réellement observés sur N scènes
    récentes. Republie ce que V8 faisait, sans l'inventer.

    Args:
        recent_scenes_with_antagonism: liste de antagonisme_score par scène.
        target_quantile: quantile cible (défaut 0.75 = "75% des scènes
                          avec antagonisme significatif").
    Returns:
        Seuil proposé. Si < 5 observations, retourne le seuil actuel inchangé
        (règle 25 — pas d'invention).
    """
    if len(recent_scenes_with_antagonism) < 5:
        return CURRENT_ANTAGONISM  # pas assez de données, on garde
    sorted_obs = sorted(recent_scenes_with_antagonism)
    idx = int(len(sorted_obs) * target_quantile)
    idx = min(idx, len(sorted_obs) - 1)
    return round(sorted_obs[idx], 2)


def compute_similarity_threshold(recent_behaviors: list[float]) -> float:
    """Propose seuil de similarité adaptatif.

    Logique : médiane + 1.5*IQR des similarités observées, clampé [0.5, 0.9].
    Garde le seuil par défaut si moins de 10 observations.
    """
    if len(recent_behaviors) < 10:
        return CURRENT_SIMILARITY
    s = sorted(recent_behaviors)
    n = len(s)
    median = (s[n // 2 - 1] + s[n // 2]) / 2 if n % 2 == 0 else s[n // 2]
    # IQR simplifié (P75 - P25)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1
    proposed = median + 1.5 * iqr
    return round(max(0.5, min(0.9, proposed)), 3)


# ────────────────────────────────────────────────────────────
# Bootstrap DB : on utilise le même canal SQLite pour récupérer
# les observations depuis la DB live. Lecture seule.
# ────────────────────────────────────────────────────────────

@contextmanager
def _conn(db_path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def propose_thresholds_diff(db_path=None) -> dict[str, Any]:
    """Calcule le diff actuel vs proposé pour tous les seuils adaptatifs.

    Returns dict sérialisable JSON avec :
    - current : dict seuils actuels
    - proposed : dict seuils proposés
    - sample_size : n observations par seuil
    - ready_to_apply : bool (au moins 1 seuil change et n suffisant)
    - rationale : explication textuelle par seuil
    """
    from core.v9.config import DB_PATH as DEFAULT_DB
    db_path = db_path or DEFAULT_DB

    # Lecture live — compte replays et observe antagonismes/similarités
    replay_count = 0
    replay_wins = 0
    antagonisms: list[float] = []
    similarities: list[float] = []

    try:
        with _conn(db_path) as c:
            # Replay outcomes (text replay file) — on compte les WIN résolus
            try:
                row = c.execute(
                    "SELECT COUNT(*) FROM decisions WHERE is_win IS NOT NULL"
                ).fetchone()
                replay_count = int(row[0] or 0)
            except sqlite3.OperationalError:
                replay_count = 0

            try:
                row = c.execute(
                    "SELECT COUNT(*) FROM decisions WHERE is_win = 1"
                ).fetchone()
                replay_wins = int(row[0] or 0)
            except sqlite3.OperationalError:
                replay_wins = 0

            # Antagonismes observés (depuis scenes.antagonismes_json)
            # Pas de ORDER BY timestamp DESC — scènes peut être une table
            # partielle en test/dev. LIMIT 200 plafonne le coût.
            try:
                rows_scenes = c.execute(
                    "SELECT antagonismes_json FROM scenes "
                    "WHERE antagonismes_json IS NOT NULL "
                    "AND antagonismes_json != '[]' "
                    "LIMIT 200"
                ).fetchall()

                import json
                for srow in rows_scenes:
                    if hasattr(srow, "keys"):
                        raw_json = srow["antagonismes_json"]
                    else:
                        raw_json = srow[0]
                    if not raw_json:
                        continue
                    try:
                        data = json.loads(raw_json)
                        items = data if isinstance(data, list) else []
                        for a in items:
                            if isinstance(a, dict) and "intensite" in a:
                                antagonisms.append(float(a["intensite"]))
                            elif isinstance(a, (int, float)):
                                antagonisms.append(float(a))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
            except sqlite3.OperationalError:
                pass  # scènes absente — antagonisms reste []

            # Similarités observées (depuis behaviors.similarite_score)
            try:
                rows_behaviors = c.execute(
                    "SELECT similarite_score FROM behaviors "
                    "WHERE similarite_score IS NOT NULL "
                    "LIMIT 200"
                ).fetchall()

                for brow in rows_behaviors:
                    if hasattr(brow, "keys"):
                        raw = brow["similarite_score"]
                    else:
                        raw = brow[0]
                    try:
                        similarities.append(float(raw))
                    except (TypeError, ValueError):
                        continue
            except sqlite3.OperationalError:
                pass  # behaviors absente — similarities reste []
    except sqlite3.OperationalError:
        # DB live absente (tests, dev sans données)
        pass

    # Propositions
    p_replay = compute_replay_min_cas(replay_count, replay_wins)
    p_antag = compute_antagonism_threshold(antagonisms)
    p_simil = compute_similarity_threshold(similarities)

    current = {
        "REPLAY_MIN_CAS": CURRENT_REPLAY_MIN,
        "ANTAGONISM_THRESHOLD": CURRENT_ANTAGONISM,
        "SIMILARITY_THRESHOLD": CURRENT_SIMILARITY,
    }
    proposed = {
        "REPLAY_MIN_CAS": p_replay,
        "ANTAGONISM_THRESHOLD": p_antag,
        "SIMILARITY_THRESHOLD": p_simil,
    }
    sample = {
        "REPLAY_MIN_CAS": f"n_decisions_resolved={replay_count}",
        "ANTAGONISM_THRESHOLD": f"n_antagonisms_observed={len(antagonisms)}",
        "SIMILARITY_THRESHOLD": f"n_similarities_observed={len(similarities)}",
    }
    rationale = {
        "REPLAY_MIN_CAS": (
            f"{replay_count} décisions résolues → seuil adaptatif propose "
            f"{p_replay} (vs {CURRENT_REPLAY_MIN} gelé V8)."
        ),
        "ANTAGONISM_THRESHOLD": (
            f"{len(antagonisms)} antagonismes observés → P75 = {p_antag} "
            f"(vs {CURRENT_ANTAGONISM} gelé V8)."
        ) if len(antagonisms) >= 5 else (
            f"Pas assez d'observations ({len(antagonisms)} < 5), "
            f"seuil conservé à {CURRENT_ANTAGONISM}."
        ),
        "SIMILARITY_THRESHOLD": (
            f"{len(similarities)} similarités observées → median+1.5IQR = {p_simil} "
            f"(vs {CURRENT_SIMILARITY} gelé V8)."
        ) if len(similarities) >= 10 else (
            f"Pas assez d'observations ({len(similarities)} < 10), "
            f"seuil conservé à {CURRENT_SIMILARITY}."
        ),
    }
    ready = (
        current != proposed
        and replay_count >= 5  # Règle 30 palier 1
    )

    return {
        "current": current,
        "proposed": proposed,
        "sample_size": sample,
        "ready_to_apply": ready,
        "rationale": rationale,
    }
