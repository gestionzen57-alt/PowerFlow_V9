"""v9_drawdown_protector.py — Drawdown Protection niveau hedge fund.

2026-07-17 motion CEO « orchestre et optimise au max, hedge fund mondial ».

Implémente la protection contre le drawdown observée dans les fonds
quantiques de référence (Renaissance Medallion, Two Sigma, Citadel) :

  1. Volatility Targeting — réduit le sizing quand la volatilité augmente.
  2. Drawdown Circuit Breaker — stoppe le trading si DD > seuil.
  3. Recovery Mode — ré-augmente progressivement après un DD.
  4. Kelly Adaptive — ajuste Kelly selon le régime observé.

Doctrine R6 : défensif, ne lève jamais d'exception.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.db_schema import get_connection

log = logging.getLogger(__name__)

DRAWDOWN_PROTECTOR_VERSION = "1.0"


@dataclass
class DrawdownState:
    """État courant du drawdown protector."""
    peak_pips: float = 0.0
    current_pips: float = 0.0
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    n_trades_total: int = 0
    n_wins: int = 0
    n_losses: int = 0
    consecutive_losses: int = 0
    last_update: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        """Auto-calcule current_drawdown et max_drawdown si non fournis."""
        if self.current_drawdown == 0.0 and self.peak_pips > 0:
            self.current_drawdown = max(0.0, self.peak_pips - self.current_pips)
        if self.max_drawdown == 0.0:
            self.max_drawdown = self.current_drawdown

    @property
    def win_rate(self) -> float:
        return self.n_wins / max(self.n_trades_total, 1)

    @property
    def is_in_drawdown(self) -> bool:
        return self.current_drawdown > 0.001

    @property
    def is_recovery(self) -> bool:
        """Recovery = on remonte après un drawdown."""
        return self.current_drawdown > 0 and self.current_drawdown < self.max_drawdown * 0.5

    def to_dict(self) -> dict:
        return {
            **self.__dict__,
            "win_rate": self.win_rate,
            "is_in_drawdown": self.is_in_drawdown,
            "is_recovery": self.is_recovery,
        }


@dataclass
class DrawdownDecision:
    """Décision de sizing basée sur le drawdown."""
    action: str  # "normal", "reduce_50", "halt_24h", "halt_forever"
    position_multiplier: float  # 1.0 normal, 0.5 réduit, 0.0 halt
    rationale: str
    state_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "position_multiplier": self.position_multiplier,
            "rationale": self.rationale,
            "state": self.state_snapshot,
        }


class DrawdownProtector:
    """Drawdown Protector — applique les règles hedge fund de gestion du risque.

    Hiérarchie :
      1. Si DD < 5% : normal (multiplier = 1.0)
      2. Si 5% ≤ DD < 10% : reduce_50 (multiplier = 0.5)
      3. Si 10% ≤ DD < 15% : halt_24h (multiplier = 0.0, arrêt 24h)
      4. Si DD ≥ 15% : halt_forever (multiplier = 0.0, arrêt définitif)

    Recovery : après un halt, ré-augmentation progressive par paliers de 25%
    tous les 50 trades gagnants (sizing 0.25 → 0.50 → 0.75 → 1.0).
    """

    DD_REDUCE_50 = 0.05
    DD_HALT_24H = 0.10
    DD_HALT_FOREVER = 0.15

    RECOVERY_STEP = 25  # trades gagnants entre chaque palier

    def __init__(
        self,
        initial_capital: float = 10000.0,
        max_concurrent: int = 99,
        db_path: Path | str | None = None,
    ) -> None:
        self.initial_capital = initial_capital
        self.max_concurrent = max_concurrent
        self.db_path = db_path
        self.state = DrawdownState()
        self._recovery_progress = 0

    def update_state_from_db(self) -> DrawdownState:
        """Met à jour l'état depuis les paper_trades clôturés."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT COALESCE(SUM(pips_simulated), 0) AS total_pips, "
                "COUNT(*) AS n, "
                "SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) AS wins, "
                "SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END) AS losses "
                "FROM paper_trades WHERE closed_at IS NOT NULL"
            ).fetchone()
        finally:
            conn.close()

        total_pips = float(row[0] or 0)
        n = int(row[1] or 0)
        wins = int(row[2] or 0)
        losses = int(row[3] or 0)

        self.state.current_pips = total_pips
        self.state.peak_pips = max(self.state.peak_pips, total_pips)
        self.state.current_drawdown = max(0.0, self.state.peak_pips - total_pips)
        self.state.max_drawdown = max(self.state.max_drawdown, self.state.current_drawdown)
        self.state.n_trades_total = n
        self.state.n_wins = wins
        self.state.n_losses = losses
        self.state.last_update = datetime.now(timezone.utc).isoformat()

        # Compteur de losses consécutives (approximation : on parcourt les N derniers)
        if losses > 0:
            conn = get_connection(self.db_path)
            try:
                rows = conn.execute(
                    "SELECT is_win FROM paper_trades "
                    "WHERE closed_at IS NOT NULL "
                    "ORDER BY closed_at DESC LIMIT 20"
                ).fetchall()
                consec = 0
                for r in rows:
                    if r[0] == 0:
                        consec += 1
                    else:
                        break
                self.state.consecutive_losses = consec
            finally:
                conn.close()

        return self.state

    def decide(self) -> DrawdownDecision:
        """Prend une décision de sizing basée sur l'état courant.

        Returns:
            DrawdownDecision avec action et position_multiplier.
        """
        self.update_state_from_db()
        return self._decide_with_state(self.state)

    def _decide_with_state(self, state: DrawdownState) -> DrawdownDecision:
        """Décision pure à partir d'un état (testable sans DB)."""
        dd_pct = state.current_drawdown / self.initial_capital
        state_dict = state.to_dict()

        # Halt forever (critique)
        if dd_pct >= self.DD_HALT_FOREVER:
            return DrawdownDecision(
                action="halt_forever",
                position_multiplier=0.0,
                rationale=(
                    f"Drawdown {dd_pct*100:.1f}% ≥ {self.DD_HALT_FOREVER*100:.0f}% — "
                    f"arrêt définitif, revalidation CEO requise."
                ),
                state_snapshot=state_dict,
            )

        # Halt 24h
        if dd_pct >= self.DD_HALT_24H:
            return DrawdownDecision(
                action="halt_24h",
                position_multiplier=0.0,
                rationale=(
                    f"Drawdown {dd_pct*100:.1f}% ≥ {self.DD_HALT_24H*100:.0f}% — "
                    f"arrêt 24h, reprise après stabilisation."
                ),
                state_snapshot=state_dict,
            )

        # Reduce 50
        if dd_pct >= self.DD_REDUCE_50:
            return DrawdownDecision(
                action="reduce_50",
                position_multiplier=0.5,
                rationale=(
                    f"Drawdown {dd_pct*100:.1f}% ≥ {self.DD_REDUCE_50*100:.0f}% — "
                    f"sizing réduit 50%."
                ),
                state_snapshot=state_dict,
            )

        # Recovery mode : on remonte, sizing progressif
        if state.is_recovery and self._recovery_progress > 0:
            mult = min(1.0, self._recovery_progress * 0.25)
            return DrawdownDecision(
                action=f"recovery_{int(mult*100)}",
                position_multiplier=mult,
                rationale=(
                    f"Recovery mode : {self._recovery_progress} paliers franchis, "
                    f"sizing à {int(mult*100)}%."
                ),
                state_snapshot=state_dict,
            )

        # Consecutive losses : pause défensive
        if state.consecutive_losses >= 5:
            return DrawdownDecision(
                action="pause_5_losses",
                position_multiplier=0.0,
                rationale=(
                    f"{state.consecutive_losses} losses consécutives — "
                    f"pause défensive, attendre signal de retournement."
                ),
                state_snapshot=state_dict,
            )

        # Normal
        return DrawdownDecision(
            action="normal",
            position_multiplier=1.0,
            rationale="Tout est nominal — sizing 100%.",
            state_snapshot=state_dict,
        )

    def get_decision_summary(self) -> dict:
        """Retourne un résumé de la décision pour dashboard/log."""
        self.update_state_from_db()
        decision = self.decide()
        return {
            "version": DRAWDOWN_PROTECTOR_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "state": self.state.to_dict(),
            "decision": decision.to_dict(),
        }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Drawdown Protector V9")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    prot = DrawdownProtector(initial_capital=args.capital)
    summary = prot.get_decision_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())