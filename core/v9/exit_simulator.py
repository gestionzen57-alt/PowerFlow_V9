"""ExitSimulator — Stratégies de sortie professionnelles (Phase 13.2).

Simule des stratégies de sortie réalistes pour le paper-trading :
  - TP_SL       : Take-profit et stop-loss fixes
  - TRAILING    : Trailing stop (accroche les gains)
  - TIME_BASED  : Sortie à horizon fixe (H1, H4, etc.)
  - MFE_ONLY    : MFE pur (backward compat, référence académique)

Chaque stratégie prend les prix futurs et retourne le résultat simulé
(pips, is_win, sortie_raison, prix_sortie).

Usage :
    simulator = ExitSimulator(strategy="TP_SL", tp_pips=20, sl_pips=10)
    result = simulator.simulate(entry=1.3368, direction="baissiere", future_mids=[...])
    # → {"pips": 15.2, "is_win": 1, "exit_reason": "tp_hit", "exit_price": 1.33528, ...}
"""
from __future__ import annotations

import enum
from typing import Any


class ExitStrategy(str, enum.Enum):
    """Stratégies de sortie supportées."""
    TP_SL = "TP_SL"               # Take-profit + Stop-loss fixes
    TRAILING = "TRAILING"         # Trailing stop
    TIME_BASED = "TIME_BASED"     # Sortie à horizon fixe
    MFE_ONLY = "MFE_ONLY"         # MFE pur (référence, backward compat)


# ── Résultat de simulation ─────────────────────────────────────────

class ExitResult:
    """Résultat structuré d'une simulation de sortie.

    Attributs :
        pips (float)        : Pips réalisés (positif = gain, négatif = perte)
        is_win (int)        : 1 si gain > 0, 0 sinon
        exit_reason (str)   : Raison de sortie (tp_hit, sl_hit, trailing_stop, time_exit, mfe_end)
        exit_price (float)  : Prix de sortie simulé
        entry_price (float) : Prix d'entrée
        max_favorable (float): Plus haut/bas atteint (valeur absolue en pips)
        max_adverse (float) : Plus bas/haut adverse (valeur absolue en pips)
        bars_held (int)     : Nombre de barres avant sortie
    """
    __slots__ = (
        "pips", "is_win", "exit_reason", "exit_price",
        "entry_price", "max_favorable", "max_adverse", "bars_held",
    )

    def __init__(
        self,
        pips: float,
        is_win: int,
        exit_reason: str,
        exit_price: float,
        entry_price: float,
        max_favorable: float,
        max_adverse: float,
        bars_held: int,
    ) -> None:
        self.pips = pips
        self.is_win = is_win
        self.exit_reason = exit_reason
        self.exit_price = exit_price
        self.entry_price = entry_price
        self.max_favorable = max_favorable
        self.max_adverse = max_adverse
        self.bars_held = bars_held

    def to_dict(self) -> dict[str, Any]:
        return {
            "pips": self.pips,
            "is_win": self.is_win,
            "exit_reason": self.exit_reason,
            "exit_price": self.exit_price,
            "entry_price": self.entry_price,
            "max_favorable": self.max_favorable,
            "max_adverse": self.max_adverse,
            "bars_held": self.bars_held,
        }

    def __repr__(self) -> str:
        return (
            f"ExitResult(pips={self.pips:+.1f}, win={self.is_win}, "
            f"reason={self.exit_reason}, held={self.bars_held})"
        )


# ── Convertisseur prix ↔ pips ─────────────────────────────────────

PIPS_MULTIPLIER = 10000  # GBPUSD 4 décimales


def price_to_pips(price_diff: float) -> float:
    """Convertit une différence de prix en pips (GBPUSD 4 décimales)."""
    return round(price_diff * PIPS_MULTIPLIER, 1)


# ── Simulateur principal ───────────────────────────────────────────

class ExitSimulator:
    """Simulateur de stratégies de sortie.

    Paramètres :
        strategy (str)      : Stratégie parmi ExitStrategy
        tp_pips (float)     : Take-profit en pips (défaut 20.0)
        sl_pips (float)     : Stop-loss en pips (défaut 10.0)
        trailing_dist (float): Distance du trailing stop en pips (défaut 15.0)
        time_bars (int)     : Nombre de barres max pour TIME_BASED (défaut 4)
        spread_pips (float) : Spread estimé en pips (défaut 0.5)
    """
    def __init__(
        self,
        strategy: str = "TP_SL",
        *,
        tp_pips: float = 20.0,
        sl_pips: float = 10.0,
        trailing_dist: float = 15.0,
        time_bars: int = 4,
        spread_pips: float = 0.5,
    ) -> None:
        if strategy not in [e.value for e in ExitStrategy]:
            valid = ", ".join(e.value for e in ExitStrategy)
            raise ValueError(f"Stratégie inconnue : {strategy}. Valides : {valid}")
        self.strategy = strategy
        self.tp_pips = tp_pips
        self.sl_pips = sl_pips
        self.trailing_dist = trailing_dist
        self.time_bars = time_bars
        self.spread_pips = spread_pips

    def simulate(
        self,
        entry: float,
        direction: str,
        future_mids: list[float],
    ) -> ExitResult:
        """Simule la sortie selon la stratégie configurée.

        Args:
            entry: Prix d'entrée (mid)
            direction: "haussiere" ou "baissiere"
            future_mids: Liste des prix futurs (triés par timestamp ASC)

        Returns:
            ExitResult structuré
        """
        if not future_mids:
            return ExitResult(
                pips=0.0, is_win=0, exit_reason="no_data",
                exit_price=entry, entry_price=entry,
                max_favorable=0.0, max_adverse=0.0, bars_held=0,
            )

        if self.strategy == ExitStrategy.MFE_ONLY:
            return self._simulate_mfe(entry, direction, future_mids)
        elif self.strategy == ExitStrategy.TP_SL:
            return self._simulate_tp_sl(entry, direction, future_mids)
        elif self.strategy == ExitStrategy.TRAILING:
            return self._simulate_trailing(entry, direction, future_mids)
        elif self.strategy == ExitStrategy.TIME_BASED:
            return self._simulate_time_based(entry, direction, future_mids)
        else:
            # Fallback MFE
            return self._simulate_mfe(entry, direction, future_mids)

    # ── MFE (Maximum Favorable Excursion) — référence académique ──

    def _simulate_mfe(
        self, entry: float, direction: str, mids: list[float],
    ) -> ExitResult:
        """MFE pur : prend le meilleur prix atteint."""
        if direction == "haussiere":
            best = max(mids)
            worst = min(mids)
            pips_raw = best - entry
        else:
            best = min(mids)
            worst = max(mids)
            pips_raw = entry - best

        pips = price_to_pips(pips_raw) - self.spread_pips
        mfe = price_to_pips(abs(best - entry))
        mae = price_to_pips(abs(worst - entry))

        return ExitResult(
            pips=pips,
            is_win=1 if pips > 0 else 0,
            exit_reason="mfe_end",
            exit_price=best,
            entry_price=entry,
            max_favorable=mfe,
            max_adverse=mae,
            bars_held=len(mids),
        )

    # ── TP/SL fixes ──────────────────────────────────────────────

    def _simulate_tp_sl(
        self, entry: float, direction: str, mids: list[float],
    ) -> ExitResult:
        """TP et SL fixes. Sortie au premier atteint.

        Règles de marché :
          - Haussière : TP = entry + tp_pips_px, SL = entry - sl_pips_px
          - Baissière : TP = entry - tp_pips_px, SL = entry + sl_pips_px
          - Le spread est soustrait du gain (ajouté à la perte)
        """
        tp_px = self.tp_pips / PIPS_MULTIPLIER
        sl_px = self.sl_pips / PIPS_MULTIPLIER
        spread_px = self.spread_pips / PIPS_MULTIPLIER

        if direction == "haussiere":
            tp_level = entry + tp_px
            sl_level = entry - sl_px
            for i, price in enumerate(mids):
                if price >= tp_level:
                    # TP touché : gain = tp_pips - spread
                    gain = self.tp_pips - self.spread_pips
                    return ExitResult(
                        pips=gain, is_win=1, exit_reason="tp_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=self.tp_pips,
                        max_adverse=price_to_pips(max(0, entry - min(mids[:i+1]))),
                        bars_held=i + 1,
                    )
                if price <= sl_level:
                    # SL touché : perte = sl_pips + spread
                    loss = -(self.sl_pips + self.spread_pips)
                    return ExitResult(
                        pips=loss, is_win=0, exit_reason="sl_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=price_to_pips(max(0, max(mids[:i+1]) - entry)),
                        max_adverse=self.sl_pips,
                        bars_held=i + 1,
                    )
        else:  # baissiere
            tp_level = entry - tp_px
            sl_level = entry + sl_px
            for i, price in enumerate(mids):
                if price <= tp_level:
                    gain = self.tp_pips - self.spread_pips
                    return ExitResult(
                        pips=gain, is_win=1, exit_reason="tp_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=self.tp_pips,
                        max_adverse=price_to_pips(max(0, max(mids[:i+1]) - entry)),
                        bars_held=i + 1,
                    )
                if price >= sl_level:
                    loss = -(self.sl_pips + self.spread_pips)
                    return ExitResult(
                        pips=loss, is_win=0, exit_reason="sl_hit",
                        exit_price=price, entry_price=entry,
                        max_favorable=price_to_pips(max(0, entry - min(mids[:i+1]))),
                        max_adverse=self.sl_pips,
                        bars_held=i + 1,
                    )

        # Ni TP ni SL touché → sortie au dernier prix
        last = mids[-1]
        if direction == "haussiere":
            pips_raw = last - entry
        else:
            pips_raw = entry - last
        pips = price_to_pips(pips_raw) - self.spread_pips
        mfe = price_to_pips(abs((max(mids) if direction == "haussiere" else min(mids)) - entry))
        mae = price_to_pips(abs((min(mids) if direction == "haussiere" else max(mids)) - entry))

        return ExitResult(
            pips=pips, is_win=1 if pips > 0 else 0,
            exit_reason="time_end",
            exit_price=last, entry_price=entry,
            max_favorable=mfe, max_adverse=mae,
            bars_held=len(mids),
        )

    # ── Trailing Stop ───────────────────────────────────────────

    def _simulate_trailing(
        self, entry: float, direction: str, mids: list[float],
    ) -> ExitResult:
        """Trailing stop : le stop suit le prix en sa faveur.

        Principe :
          - Haussière : trailing_stop = max(seen) - trailing_dist_px
          - Baissière : trailing_stop = min(seen) + trailing_dist_px
          - Sortie quand le prix repasse le trailing stop
        """
        trail_px = self.trailing_dist / PIPS_MULTIPLIER
        spread_px = self.spread_pips / PIPS_MULTIPLIER

        if direction == "haussiere":
            best = entry
            for i, price in enumerate(mids):
                if price > best:
                    best = price  # monte le trailing
                trail_level = best - trail_px
                if price <= trail_level:
                    pips_raw = price - entry
                    pips = price_to_pips(pips_raw) - self.spread_pips
                    return ExitResult(
                        pips=pips, is_win=1 if pips > 0 else 0,
                        exit_reason="trailing_stop",
                        exit_price=price, entry_price=entry,
                        max_favorable=price_to_pips(best - entry),
                        max_adverse=price_to_pips(entry - min(mids[:i+1])),
                        bars_held=i + 1,
                    )
        else:  # baissiere
            best = entry
            for i, price in enumerate(mids):
                if price < best:
                    best = price  # baisse le trailing
                trail_level = best + trail_px
                if price >= trail_level:
                    pips_raw = entry - price
                    pips = price_to_pips(pips_raw) - self.spread_pips
                    return ExitResult(
                        pips=pips, is_win=1 if pips > 0 else 0,
                        exit_reason="trailing_stop",
                        exit_price=price, entry_price=entry,
                        max_favorable=price_to_pips(entry - best),
                        max_adverse=price_to_pips(max(mids[:i+1]) - entry),
                        bars_held=i + 1,
                    )

        # Jamais sorti par le trailing → sortie au dernier prix
        last = mids[-1]
        if direction == "haussiere":
            pips_raw = last - entry
        else:
            pips_raw = entry - last
        pips = price_to_pips(pips_raw) - self.spread_pips
        mfe = price_to_pips(abs((max(mids) if direction == "haussiere" else min(mids)) - entry))
        mae = price_to_pips(abs((min(mids) if direction == "haussiere" else max(mids)) - entry))

        return ExitResult(
            pips=pips, is_win=1 if pips > 0 else 0,
            exit_reason="time_end",
            exit_price=last, entry_price=entry,
            max_favorable=mfe, max_adverse=mae,
            bars_held=len(mids),
        )

    # ── Time-based ──────────────────────────────────────────────

    def _simulate_time_based(
        self, entry: float, direction: str, mids: list[float],
    ) -> ExitResult:
        """Sortie après N barres (indépendant du prix)."""
        n = min(self.time_bars, len(mids))
        price = mids[n - 1]

        if direction == "haussiere":
            pips_raw = price - entry
        else:
            pips_raw = entry - price
        pips = price_to_pips(pips_raw) - self.spread_pips
        mfe = price_to_pips(abs((max(mids[:n]) if direction == "haussiere" else min(mids[:n])) - entry))
        mae = price_to_pips(abs((min(mids[:n]) if direction == "haussiere" else max(mids[:n])) - entry))

        return ExitResult(
            pips=pips, is_win=1 if pips > 0 else 0,
            exit_reason="time_exit",
            exit_price=price, entry_price=entry,
            max_favorable=mfe, max_adverse=mae,
            bars_held=n,
        )
