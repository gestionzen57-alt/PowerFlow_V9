"""learning_offset_applier.py — Application effective des weight_offset APPROVED.

Phase 14 (CEO autopilot, 2026-07-15) : ferme la boucle R30 apprentissage.
`core/v9/learning_loop.py` génère et trace des propositions
`target=signal:<direction>:weight_offset` (cf. Règle 30 palier 50) mais
`approve_proposal()` est une traçabilité strictement — aucune modification
runtime. Le présent module COMPLÈTE la boucle : il lit les propositions
APPROVED, calcule un multiplicateur par direction, et le rend disponible au
caller (typiquement `core/v9/arbiter.py::consolidate()`).

Doctrine respectée (R25' strict + R18 + R6) :
- 0 LLM, lecture seule sur `v9_forces.db` (`learning_proposals`).
- Kill switch dédié `V9_LEARNING_OFFSET_ENABLED` (défaut OFF — R25' strict,
  activation = motion CEO explicite datée, comme `V9_TRADER_MINI_ENABLED`).
- Bornes dures [0.85, 1.15] — magnitude volontairement limitée (signal
  empirique haussier WR=94% est fort mais biaisé par marché fermé post 14/07,
  on garde une pondération discrète).
- Calcul multiplicateur = `1.0 + cap(observed_wr - 0.5, -0.15, 0.15)` :
  - WR=50% neutre -> mult=1.0
  - WR=70% (cas haussier actuel 94% tronqué à 1.15) -> mult=1.15
  - WR=40% (cas baissier 67% actuel 1.0+0.17 clampé à 1.15) -> mult=1.0
- Magnitude réelle au moment de la livraison §2.1 : `cf7955b1be08` WR=94%
  -> multiplier haussier = 1.0 + clamp(0.94-0.5, -0.15, 0.15) = 1.15 max.
  `49f65b2cb806` WR=67% -> 1.0 + clamp(0.67-0.5, -0.15, 0.15) = 1.0 + 0.15
  = 1.15 (clampé aussi).
- Si 0 proposition APPROVED pour une direction -> multiplier 1.0 (neutre).
- Si 1+ propositions APPROVED pour une direction -> on prend la MEILLEURE
  score (winning WR, le plus grand magnitude).

Attention : si plusieurs propositions APPROVED pour la même direction
par accident (cf. §2.1 anti-doublons), la plus haute WR l'emporte.

Backward-compatible : sans proposition APPROVED, ou kill switch OFF, ou
`learning_proposals` table absente -> neutre, aucun crash (R6).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Final

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection

# Kill switch discret (R25' strict, défaut OFF).
LEARNING_OFFSET_ENABLED_ENV: Final = "V9_LEARNING_OFFSET_ENABLED"

# Bornes dures — magnitude limitée pour ne pas écraser le scorer O2 / Q1 / R29.
LEARNING_OFFSET_MULT_NEUTRAL: Final = 1.0
LEARNING_OFFSET_MULT_BOUNDS: Final = (0.85, 1.15)
LEARNING_OFFSET_WR_BASELINE: Final = 0.50  # WR "neutre" = pas d'ajustement


def learning_offset_enabled() -> bool:
    """Kill switch V9_LEARNING_OFFSET_ENABLED (défaut '0' = OFF, R25' strict)."""
    return os.environ.get(LEARNING_OFFSET_ENABLED_ENV, "0") == "1"


def _compute_multiplier_from_wr(observed_wr: float) -> float:
    """Convertit un WR observé en multiplicateur dans [0.85, 1.15].

    Mapping linéaire tronqué autour de 50% (neutre) :
    - WR=50% -> mult=1.00
    - WR=65% -> mult=1.15 (cap)
    - WR=35% -> mult=0.85 (cap bas)
    - WR=42% -> mult=0.92
    - WR=80% -> mult=1.15 (cap, signal déjà saturé)
    """
    delta = observed_wr - LEARNING_OFFSET_WR_BASELINE
    delta = max(-0.15, min(0.15, delta))
    mult = LEARNING_OFFSET_MULT_NEUTRAL + delta
    lo, hi = LEARNING_OFFSET_MULT_BOUNDS
    return max(lo, min(hi, mult))


class LearningOffsetApplier:
    """Lit les propositions APPROVED `weight_offset` et les condense par direction.

    État par direction = multiplicateur dominant (meilleure WR observée).
    Lecture pure, 0 mutation, idempotent (re-appel = même résultat tant que
    `learning_proposals` n'a pas changé).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DB_PATH

    def _connect(self) -> sqlite3.Connection:
        conn = get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_approved_offsets(
        self, conn: sqlite3.Connection,
    ) -> dict[str, dict]:
        """Charge les propositions APPROVED par direction.

        Returns: dict[direction -> dict(observed_wr, observed_n, score,
                                            multiplier, rationale)].
        Si plusieurs propositions pour la même direction, garde la
        MEILLEURE par WR observé (= magnitude maximale, qui correspond aussi
        au score le plus élevé en pratique car WR + n sont les 2 composantes).
        """
        try:
            rows = conn.execute(
                "SELECT id, target, observed_wr, observed_n, score "
                "FROM learning_proposals "
                "WHERE status = 'APPROVED' "
                "AND target LIKE 'signal:%:weight_offset'",
            ).fetchall()
        except sqlite3.Error:
            # Table absente (DB fraîche ou autre) -> vide, pas de plantage.
            return {}

        result: dict[str, dict] = {}
        for r in rows:
            target = r["target"]
            # Cible : "signal:<direction>:weight_offset"
            parts = target.split(":")
            if len(parts) != 3 or parts[0] != "signal" or parts[2] != "weight_offset":
                continue
            direction = parts[1]
            if not direction:
                continue
            observed_wr = float(r["observed_wr"] or 0.0)
            mult = _compute_multiplier_from_wr(observed_wr)
            existing = result.get(direction)
            # Garde la plus forte WR observée (= signal le plus informatif).
            if existing is None or observed_wr > existing["observed_wr"]:
                result[direction] = {
                    "observed_wr": observed_wr,
                    "observed_n": int(r["observed_n"] or 0),
                    "score": float(r["score"] or 0.0),
                    "multiplier": mult,
                    "proposal_id": r["id"],
                }
        return result

    def compute_offset_for_direction(self, direction: str | None) -> tuple[float, str]:
        """Retourne (multiplier, basis) pour la direction donnée.

        basis ∈ {"approved", "neutral"}.
        - Kill switch OFF -> (1.0, "neutral")
        - 0 APPROVED pour cette direction -> (1.0, "neutral")
        - APPROVED présente -> (1.0 + cap, "approved")
        - direction=None / "neutre" -> (1.0, "neutral") (pas d'offset neutre)
        - Erreur DB -> (1.0, "neutral"), pas d'exception (R6)

        Idempotent, lecture seule, R18 respecté.
        """
        if not direction or direction == "neutre":
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"
        if not learning_offset_enabled():
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"

        try:
            conn = self._connect()
            try:
                offsets = self._load_approved_offsets(conn)
            finally:
                conn.close()
        except Exception:
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"

        entry = offsets.get(direction)
        if not entry:
            return LEARNING_OFFSET_MULT_NEUTRAL, "neutral"
        return float(entry["multiplier"]), "approved"
