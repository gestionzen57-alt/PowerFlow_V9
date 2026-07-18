"""position_manager.py — Gestion active de position (niveau quantique P2).

Un stratège institutionnel ne pose pas un TP/SL puis attend passivement. Il
GÈRE la position pendant sa vie :

  1. Break-even : dès que le trade est à +30 % du TP, on remonte le SL à
     l'entrée. Le risque de perte est neutralisé — au pire on sort à zéro.
  2. Partial close : à +50 % du TP, on ferme une fraction de la position
     (défaut 50 %) pour verrouiller un gain partiel ; le reste court vers le TP.
  3. Time-based exit : si après N barres le trade STAGNE (n'a jamais atteint le
     seuil break-even), on coupe — le capital immobilisé sur un trade mort est
     un coût d'opportunité.

Ce module est un simulateur PUR (aucune DB) opérant sur la trajectoire de prix
future (`future_mids`), exactement comme `ExitSimulator`. Il réutilise ses
conventions pips/spread (spread soustrait du gain, ajouté à la perte ;
multiplicateur pips par symbole). Il s'intègre dans
`TradeEngine.close_open_trades()` derrière le kill switch
`V9_POSITION_MANAGER_ENABLED` (défaut OFF — R2 : ne casse pas la résolution
live existante, activation = décision CEO).

Doctrine :
  - R18 : code pur, stdlib uniquement
  - R2  : additif — simulateur isolé, wiring derrière kill switch défaut OFF
  - R6  : try/except au point d'intégration, jamais bloquant
"""
from __future__ import annotations

import enum
import os
from typing import Any

from core.v9.exit_simulator import pips_multiplier_for_symbol

POSITION_MANAGER_VERSION = "1.0"

# Kill switch d'intégration (défaut OFF — la résolution live reste ExitSimulator).
POSITION_MANAGER_ENV = "V9_POSITION_MANAGER_ENABLED"

# ── Paramètres par défaut (institutionnels) ────────────────────────
BREAK_EVEN_TRIGGER_RATIO = 0.30   # break-even à +30 % du TP
PARTIAL_CLOSE_TRIGGER_RATIO = 0.50  # partial close à +50 % du TP
PARTIAL_CLOSE_FRACTION = 0.50     # fraction de la position fermée au partial
STAGNATION_BARS = 12              # barres avant time-exit si jamais au break-even


def position_manager_enabled() -> bool:
    """Kill switch d'intégration. Défaut OFF."""
    return os.environ.get(POSITION_MANAGER_ENV, "0") in ("1", "true", "True")


class ManageReason(str, enum.Enum):
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    BREAK_EVEN_HIT = "break_even_hit"
    STAGNATION_EXIT = "stagnation_exit"
    TIME_END = "time_end"
    NO_DATA = "no_data"


class PositionResult:
    """Résultat structuré de la gestion active de position."""

    __slots__ = (
        "pips", "is_win", "exit_reason", "bars_held",
        "break_even_activated", "partial_closed", "partial_pips",
        "remaining_fraction", "max_favorable",
    )

    def __init__(
        self,
        pips: float,
        is_win: int,
        exit_reason: str,
        bars_held: int,
        break_even_activated: bool,
        partial_closed: bool,
        partial_pips: float,
        remaining_fraction: float,
        max_favorable: float,
    ) -> None:
        self.pips = pips
        self.is_win = is_win
        self.exit_reason = exit_reason
        self.bars_held = bars_held
        self.break_even_activated = break_even_activated
        self.partial_closed = partial_closed
        self.partial_pips = partial_pips
        self.remaining_fraction = remaining_fraction
        self.max_favorable = max_favorable

    def to_dict(self) -> dict[str, Any]:
        return {
            "pips": round(self.pips, 2),
            "is_win": self.is_win,
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
            "break_even_activated": self.break_even_activated,
            "partial_closed": self.partial_closed,
            "partial_pips": round(self.partial_pips, 2),
            "remaining_fraction": round(self.remaining_fraction, 3),
            "max_favorable": round(self.max_favorable, 2),
            "version": POSITION_MANAGER_VERSION,
        }

    def __repr__(self) -> str:
        return (
            f"PositionResult(pips={self.pips:+.1f}, reason={self.exit_reason}, "
            f"be={self.break_even_activated}, partial={self.partial_closed})"
        )


class PositionManager:
    """Gestion active de position sur une trajectoire de prix.

    Paramètres (tous optionnels, défauts institutionnels) :
        break_even_trigger_ratio : ratio du TP déclenchant le break-even (0.30)
        partial_close_trigger_ratio : ratio du TP déclenchant le partial (0.50)
        partial_close_fraction : fraction fermée au partial (0.50)
        stagnation_bars : barres avant time-exit si jamais au break-even (12)
        spread_pips : spread estimé (0.5, comme ExitSimulator)
    """

    def __init__(
        self,
        *,
        break_even_trigger_ratio: float = BREAK_EVEN_TRIGGER_RATIO,
        partial_close_trigger_ratio: float = PARTIAL_CLOSE_TRIGGER_RATIO,
        partial_close_fraction: float = PARTIAL_CLOSE_FRACTION,
        stagnation_bars: int = STAGNATION_BARS,
        spread_pips: float = 0.5,
    ) -> None:
        self.be_ratio = break_even_trigger_ratio
        self.partial_ratio = partial_close_trigger_ratio
        self.partial_fraction = partial_close_fraction
        self.stagnation_bars = stagnation_bars
        self.spread_pips = spread_pips

    def simulate(
        self,
        entry: float,
        direction: str,
        tp_pips: float,
        sl_pips: float,
        future_mids: list[float],
        symbol: str | None = None,
    ) -> PositionResult:
        """Simule la gestion active sur la trajectoire `future_mids`.

        Args:
            entry: prix d'entrée (mid)
            direction: "haussiere" ou "baissiere"
            tp_pips: take-profit de base (pips)
            sl_pips: stop-loss de base (pips)
            future_mids: prix futurs triés par timestamp ASC
            symbol: pour le multiplicateur pips (JPY vs 4 décimales)

        Returns:
            PositionResult (pips nets pondérés par les fermetures partielles).
        """
        if not future_mids:
            return PositionResult(
                pips=0.0, is_win=0, exit_reason=ManageReason.NO_DATA.value,
                bars_held=0, break_even_activated=False, partial_closed=False,
                partial_pips=0.0, remaining_fraction=1.0, max_favorable=0.0,
            )

        mult = pips_multiplier_for_symbol(symbol)
        sign = 1.0 if direction == "haussiere" else -1.0

        be_trigger = self.be_ratio * tp_pips
        partial_trigger = self.partial_ratio * tp_pips

        be_active = False
        partial_done = False
        partial_pips = 0.0
        remaining = 1.0
        max_fav = 0.0

        def favorable_pips(price: float) -> float:
            """Pips en notre faveur (signé : >0 = profit latent)."""
            return round(sign * (price - entry) * mult, 1)

        for i, price in enumerate(future_mids):
            fav = favorable_pips(price)
            if fav > max_fav:
                max_fav = fav

            # 1. Take-profit atteint → ferme le reste au TP.
            if fav >= tp_pips:
                exit_pips = tp_pips - self.spread_pips
                net = partial_pips + remaining * exit_pips
                return self._result(
                    net, ManageReason.TP_HIT, i + 1, be_active,
                    partial_done, partial_pips, remaining, max_fav,
                )

            # 2. Stop effectif atteint.
            #    - break-even actif → sortie à l'entrée (≈ -spread)
            #    - sinon → SL plein
            if be_active and fav <= 0.0:
                exit_pips = -self.spread_pips
                net = partial_pips + remaining * exit_pips
                return self._result(
                    net, ManageReason.BREAK_EVEN_HIT, i + 1, be_active,
                    partial_done, partial_pips, remaining, max_fav,
                )
            if not be_active and fav <= -sl_pips:
                exit_pips = -(sl_pips + self.spread_pips)
                net = partial_pips + remaining * exit_pips
                return self._result(
                    net, ManageReason.SL_HIT, i + 1, be_active,
                    partial_done, partial_pips, remaining, max_fav,
                )

            # 3. Partial close à +partial_trigger (verrouille une fraction).
            if not partial_done and fav >= partial_trigger:
                locked_pips_per_unit = partial_trigger - self.spread_pips
                partial_pips = self.partial_fraction * locked_pips_per_unit
                remaining -= self.partial_fraction
                partial_done = True

            # 4. Break-even à +be_trigger (remonte le SL à l'entrée).
            if not be_active and fav >= be_trigger:
                be_active = True

            # 5. Stagnation : jamais au break-even après N barres → on coupe.
            if not be_active and (i + 1) >= self.stagnation_bars:
                exit_pips = fav - self.spread_pips
                net = partial_pips + remaining * exit_pips
                return self._result(
                    net, ManageReason.STAGNATION_EXIT, i + 1, be_active,
                    partial_done, partial_pips, remaining, max_fav,
                )

        # Fin de trajectoire sans sortie déclenchée → sortie au dernier prix.
        last_fav = favorable_pips(future_mids[-1])
        exit_pips = last_fav - self.spread_pips
        net = partial_pips + remaining * exit_pips
        return self._result(
            net, ManageReason.TIME_END, len(future_mids), be_active,
            partial_done, partial_pips, remaining, max_fav,
        )

    @staticmethod
    def _result(
        net_pips: float,
        reason: ManageReason,
        bars: int,
        be_active: bool,
        partial_done: bool,
        partial_pips: float,
        remaining: float,
        max_fav: float,
    ) -> PositionResult:
        return PositionResult(
            pips=round(net_pips, 2),
            is_win=1 if net_pips > 0 else 0,
            exit_reason=reason.value,
            bars_held=bars,
            break_even_activated=be_active,
            partial_closed=partial_done,
            partial_pips=round(partial_pips, 2),
            remaining_fraction=round(remaining, 3),
            max_favorable=round(max_fav, 2),
        )
