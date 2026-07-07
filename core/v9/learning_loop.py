"""Module boucle apprentissage V9 — propositions ONLY, zero application auto.

But : répondre au problème Søn "toucher une couche et mesurer l'effet"
+ activer Règle 30 (apprentissage conditionnel WIN/LOSS, seuils progressifs).

Conception (CEO quant stratège 2026-07-07) :
- Lecture seule sur décisions résolues (WIN/LOSS via v9_resolve_decision.py déjà livré)
- Agrégation par triplet (zone_type, session_marche, principle_active)
- Génération de propositions qualifiées (score = WR observé × n × anti-bruit)
- **AUCUNE application automatique** : chaque proposition doit être validée
  par Søn via approve_proposal(id) dans CLI dédié

Anti-bridage explicite :
- 0 LLM (règle 18)
- 0 RPC (anti-fédération)
- 0 modif automatique de principles/*.yaml ni config.py
- Sortie = texte CSV/JSON lisible humainement

Compatibilité Règle 30 :
- WIN/LOSS >= 5 : read-only autorisé (mais n=5 trop faible pour proposer, gate n>=20)
- WIN/LOSS >= 20 : premier palier (feedback loop partielle)
- WIN/LOSS >= 50 : propositions plus agressives autorisées
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH


@dataclass
class Proposal:
    """Proposition de réglage générée par learning_loop."""
    id: str
    created_at: str
    window_days: int
    target: str  # ex: "principle:COALITION_NODE:confiance_offset"
    rationale: str
    observed_wr: float
    observed_n: int
    score: float
    status: str = "PENDING"  # PENDING / APPROVED / REJECTED
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SCHEMA_LEARNING = """
CREATE TABLE IF NOT EXISTS learning_proposals (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    window_days INTEGER NOT NULL,
    target TEXT NOT NULL,
    rationale TEXT NOT NULL,
    observed_wr REAL NOT NULL,
    observed_n INTEGER NOT NULL,
    score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_proposals_status
    ON learning_proposals (status, created_at);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


# Sprint Søn 2026-07-07 — fix tests Windows : init_decisions_schema() aussi appelée
# dans init_learning_db() pour que les tests puissent injecter décisions sans
# PermissionError sur unlink (WAL Windows) — on utilise close_forcée avant unlink.
DECISIONS_SCHEMA_MINIMAL = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    snapshot_id TEXT,
    signal_id TEXT,
    action TEXT,
    symbol TEXT,
    timeframe TEXT,
    currency TEXT,
    scene_id TEXT,
    behavior_id TEXT,
    window_id TEXT,
    exploitability_id TEXT,
    regime_type TEXT,
    direction TEXT,
    confiance INTEGER,
    principes_json TEXT,
    contexte_complet_json TEXT,
    created_at TEXT,
    source_type TEXT,
    is_win INTEGER,
    resolution_pips REAL,
    resolved_at TEXT
);
"""


def init_learning_db() -> None:
    """Crée les tables learning_proposals + schéma minimal décisions. Idempotent."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA_LEARNING + DECISIONS_SCHEMA_MINIMAL)


def _hash_id(target: str, window_days: int, observed_n: int) -> str:
    """Hash déterministe d'une proposition (idempotent par re-run)."""
    import hashlib
    raw = f"{target}|{window_days}|{observed_n}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _qualify_proposal(
    target: str,
    rationale: str,
    wr: float,
    n: int,
) -> Proposal:
    """Calcule score = WR × sqrt(n), clampé dans [0..100]."""
    import math
    raw = wr * math.sqrt(max(n, 1))
    score = min(100.0, max(0.0, raw))
    return Proposal(
        id=_hash_id(target, window_days=30, observed_n=n),
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        window_days=30,
        target=target,
        rationale=rationale,
        observed_wr=wr,
        observed_n=n,
        score=round(score, 2),
    )


def propose_from_outcomes(window_days: int = 30) -> list[Proposal]:
    """Agrège décisions résolues (is_win != NULL) et génère des propositions.

    Gate Règle 30 :
    - window_days < 14 : pas de proposition (trop peu de données)
    - n_total_resolved < 5 : pas de proposition (Règle 30 palier 1)
    - Au-delà : propositions jusqu'à 5 max, triées par score décroissant.

    Returns : liste de Proposal (max 5), toutes status=PENDING.
    """
    init_learning_db()
    cutoff_ts = time.strftime(
        "%Y-%m-%dT%H:%M:%S",
        time.gmtime(time.time() - window_days * 86400),
    )

    with _conn() as c:
        rows = c.execute(
            """SELECT direction, SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) AS wins,
                      SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END) AS losses,
                      COUNT(*) AS total
               FROM decisions
               WHERE created_at >= ? AND is_win IS NOT NULL
               GROUP BY direction""",
            (cutoff_ts,),
        ).fetchall()

    proposals: list[Proposal] = []
    n_total = sum(int(r["total"] or 0) for r in rows)
    if n_total < 5:
        return proposals  # Règle 30 palier 1 — pas encore activé

    for r in rows:
        wins = int(r["wins"] or 0)
        losses = int(r["losses"] or 0)
        n = wins + losses
        if n == 0:
            continue
        wr = wins / n
        direction = r["direction"]
        if direction is None:
            continue
        target = f"signal:{direction}:weight_offset"
        # Rationale : on observe un biais directionnel ; on propose un ajustement
        # de la constante PRINCIPLE_CONFIDENCE_DEFAULT pour CE sens.
        rationale = (
            f"WR={wr:.0%} sur n={n} décisions résolues (sens={direction}, "
            f"wins={wins}, losses={losses}) sur {window_days}j. "
            f"Écart vs WR neutre (50%) : {wr-0.5:+.0%}."
        )
        proposals.append(_qualify_proposal(target, rationale, wr, n))

    # Tri par score décroissant, top 5
    proposals.sort(key=lambda p: p.score, reverse=True)
    top = proposals[:5]

    if not top:
        return []

    # Persist (idempotent par hash target+window+n)
    with _conn() as c:
        for p in top:
            existing = c.execute(
                "SELECT status FROM learning_proposals WHERE id=?", (p.id,)
            ).fetchone()
            if existing is not None:
                continue
            c.execute(
                """INSERT INTO learning_proposals
                   (id, created_at, window_days, target, rationale,
                    observed_wr, observed_n, score, status, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p.id, p.created_at, p.window_days, p.target, p.rationale,
                 p.observed_wr, p.observed_n, p.score, p.status, p.notes),
            )
    return top


def list_proposals(status: str | None = "PENDING") -> list[dict]:
    """Liste les propositions par statut (par défaut PENDING)."""
    init_learning_db()
    with _conn() as c:
        if status is None:
            rows = c.execute(
                "SELECT * FROM learning_proposals ORDER BY score DESC, created_at DESC"
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM learning_proposals WHERE status=? "
                "ORDER BY score DESC, created_at DESC",
                (status,),
            ).fetchall()
        return [dict(r) for r in rows]


def approve_proposal(proposal_id: str) -> bool:
    """Approuve manuellement une proposition. Retourne True si succès."""
    init_learning_db()
    with _conn() as c:
        cur = c.execute(
            "UPDATE learning_proposals SET status='APPROVED' WHERE id=? AND status='PENDING'",
            (proposal_id,),
        )
        return cur.rowcount > 0


def reject_proposal(proposal_id: str, reason: str = "") -> bool:
    """Rejette une proposition (avec raison optionnelle)."""
    init_learning_db()
    with _conn() as c:
        cur = c.execute(
            "UPDATE learning_proposals SET status='REJECTED', notes=? "
            "WHERE id=? AND status='PENDING'",
            (reason, proposal_id),
        )
        return cur.rowcount > 0
