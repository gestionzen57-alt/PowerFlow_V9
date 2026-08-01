"""v9_circuit_breaker.py — Phase 75 motion CEO 48H (P2.1 audit Perplexity).

Circuit-breaker sur erreur DB repetee dans la boucle auto-perpetuante.
Si MAX_CONSECUTIVE_ERRORS atteint, alerte Telegram + pause 5min.

Auteur : Hermes (Phase 75 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

log = logging.getLogger("v9.circuit_breaker")

MAX_CONSECUTIVE_ERRORS_DEFAULT = 10
PAUSE_SECONDS_DEFAULT = 300  # 5 minutes


class CircuitBreaker:
    """Compteur d'erreurs consecutives avec auto-pause + alerte.

    Usage :
        cb = CircuitBreaker(max_errors=10, pause=300, on_trip=send_telegram_alert)
        for item in items:
            try:
                cb.record_success()
                process(item)
            except Exception as exc:
                cb.record_error(exc)
    """

    def __init__(
        self,
        max_errors: int = MAX_CONSECUTIVE_ERRORS_DEFAULT,
        pause_seconds: int = PAUSE_SECONDS_DEFAULT,
        on_trip: Callable[[str], None] | None = None,
    ) -> None:
        self.max_errors = max_errors
        self.pause_seconds = pause_seconds
        self.on_trip = on_trip
        self._error_streak = 0
        self._total_errors = 0
        self._total_trips = 0
        self._last_error_msg: str | None = None

    def record_success(self) -> None:
        """Reset le compteur d'erreurs consecutives."""
        if self._error_streak > 0:
            log.debug(
                "circuit_breaker: streak reset after %d errors",
                self._error_streak,
            )
        self._error_streak = 0

    def record_error(self, exc: Exception | str) -> bool:
        """Enregistre une erreur. Retourne True si trip declenche.

        Si trip declenche, appelle on_trip(msg) puis sleep pause_seconds.
        R6 : ne leve jamais d'exception (try/except sur on_trip).
        """
        self._error_streak += 1
        self._total_errors += 1
        self._last_error_msg = str(exc)
        if self._error_streak >= self.max_errors:
            self._total_trips += 1
            msg = (
                f"[CIRCUIT_BREAKER] {self._error_streak} erreurs consecutives : "
                f"{self._last_error_msg}"
            )
            log.error(msg)
            if self.on_trip is not None:
                try:
                    self.on_trip(msg)
                except Exception as cb_exc:
                    log.warning("circuit_breaker: on_trip failed: %s", cb_exc)
            time.sleep(self.pause_seconds)
            self._error_streak = 0
            return True
        return False

    @property
    def is_open(self) -> bool:
        """True si en pause apres trip."""
        return False  # Apres sleep, on reset donc is_open=False

    def status(self) -> dict[str, Any]:
        """Snapshot lecture seule."""
        return {
            "error_streak": self._error_streak,
            "total_errors": self._total_errors,
            "total_trips": self._total_trips,
            "max_errors": self.max_errors,
            "last_error": self._last_error_msg,
        }


def make_db_circuit_breaker(
    on_trip: Callable[[str], None] | None = None,
) -> CircuitBreaker:
    """Factory specialisee erreurs DB."""
    return CircuitBreaker(
        max_errors=MAX_CONSECUTIVE_ERRORS_DEFAULT,
        pause_seconds=PAUSE_SECONDS_DEFAULT,
        on_trip=on_trip,
    )


def main(argv=None) -> int:
    """Demo : 12 erreurs consecutives, trip au 10e."""
    print("=" * 70)
    print("V9 CIRCUIT BREAKER (Phase 75)")
    print("=" * 70)
    tripped = []

    def fake_trip(msg: str) -> None:
        tripped.append(msg)
        print(f"[TRIP] {msg}")

    cb = CircuitBreaker(max_errors=10, pause_seconds=0, on_trip=fake_trip)
    for i in range(1, 13):
        cb.record_error(f"DB lock timeout iteration {i}")
        print(f"  iter {i:2d} : streak={cb._error_streak} total_trips={cb._total_trips}")
    print(f"Status final : {cb.status()}")
    print(f"Tripped events : {len(tripped)}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    import sys
    sys.exit(main())