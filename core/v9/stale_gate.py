"""STALE_GATE — péremption bloquante par timeframe.

Doctrine FREE-FIRST : une donnée périmée est marquée `stale`, jamais
supprimée ni ignorée à l'insertion. Le rejet éventuel appartient aux
couches consommatrices (Scènes), pas à la capture.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Union

from core.v9.config import STALE_THRESHOLDS_MS

log = logging.getLogger("v9.stale_gate")

Timestamp = Union[str, int, float]


def to_epoch_ms(timestamp: Timestamp) -> int:
    """Convertit un timestamp (ISO8601 UTC ou epoch ms/s) en epoch ms."""
    if isinstance(timestamp, str):
        ts = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    value = float(timestamp)
    # Epoch en secondes plutôt qu'en millisecondes (heuristique large).
    if value < 10_000_000_000:
        value *= 1000
    return int(value)


class StaleGate:
    """Calcule la fraîcheur d'une donnée et compte les cas de péremption."""

    def __init__(self, thresholds: dict[str, int] | None = None) -> None:
        self.thresholds = dict(thresholds) if thresholds else dict(STALE_THRESHOLDS_MS)
        self._stale_counts: dict[str, int] = {}
        self._total_counts: dict[str, int] = {}

    def check_freshness(
        self,
        timestamp: Timestamp,
        timeframe: str,
        now_ms: int | None = None,
    ) -> dict:
        """Retourne {age_ms, stale, stale_threshold_ms} pour ce timeframe.

        La donnée n'est jamais rejetée ici : stale=True est un signal,
        pas un blocage d'insertion.
        """
        threshold = self.thresholds.get(timeframe)
        if threshold is None:
            raise ValueError(f"timeframe inconnu pour STALE_GATE: {timeframe!r}")

        now = now_ms if now_ms is not None else int(time.time() * 1000)
        age_ms = now - to_epoch_ms(timestamp)
        stale = age_ms > threshold

        self._total_counts[timeframe] = self._total_counts.get(timeframe, 0) + 1
        if stale:
            self._stale_counts[timeframe] = self._stale_counts.get(timeframe, 0) + 1
            log.warning(
                "STALE_GATE: donnée périmée timeframe=%s age_ms=%d seuil_ms=%d",
                timeframe, age_ms, threshold,
            )

        return {
            "age_ms": age_ms,
            "stale": stale,
            "stale_threshold_ms": threshold,
        }

    def stale_stats(self) -> dict[str, dict[str, int]]:
        """Compte de snapshots stale / total par timeframe."""
        return {
            tf: {
                "stale": self._stale_counts.get(tf, 0),
                "total": self._total_counts.get(tf, 0),
            }
            for tf in self._total_counts
        }
