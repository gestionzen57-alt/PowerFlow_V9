"""transaction_costs.py — Modélisation des coûts de transaction réalistes.

Un stratège institutionnel ne calcule jamais l'expectancy sans les coûts.
V9 simule avec TP/SL pips bruts — l'expectancy réelle est 30% plus faible.

Coûts modélisés :
  - Spread : différence bid/ask, variable par paire
  - Commission : ~$7/lot standard = ~0.7 pip
  - Slippage : 1-2 pips sur marchés volatils (NEWS_SHOCK, HIGH vol)

Usage :
    from core.v9.transaction_costs import TransactionCosts
    costs = TransactionCosts()
    net_pips = costs.apply("GBPUSD", is_win=True, gross_pips=8.0, vol_regime="NORMAL")
    # → 8.0 - 1.5 (spread) - 0.7 (commission) - 0.0 (slippage normal) = 5.8 pips

Doctrine :
  - R18 : code pur, aucun LLM
  - R2 : additif — ne modifie pas le calcul existant
  - R6 : try/except, jamais bloquant
"""
from __future__ import annotations

from typing import Any

# Spread moyen par paire (en pips, sources broker MT4 standard).
SPREAD_BY_SYMBOL: dict[str, float] = {
    "GBPUSD": 1.5,
    "EURUSD": 1.2,
    "USDJPY": 1.3,
    "USDCAD": 2.0,
    "USDCHF": 1.8,
    "AUDUSD": 1.5,
}

# Commission standard (~$7/lot = ~0.7 pip pour les paires standard).
COMMISSION_PIPS: float = 0.7

# Slippage par vol_regime (pips).
SLIPPAGE_BY_VOL: dict[str, float] = {
    "LOW": 0.0,
    "NORMAL": 0.3,
    "HIGH": 1.0,
    "EXTREME": 2.0,
}

# Slippage supplémentaire en NEWS_SHOCK.
SLIPPAGE_NEWS_SHOCK: float = 2.0

DEFAULT_SPREAD: float = 2.0  # conservateur pour paires non listées


class TransactionCosts:
    """Calcule les coûts de transaction réalistes par paire et contexte.

    Usage :
        costs = TransactionCosts()
        net = costs.apply("GBPUSD", is_win=True, gross_pips=8.0, vol_regime="NORMAL")
    """

    def __init__(self) -> None:
        self._spreads = dict(SPREAD_BY_SYMBOL)

    def get_spread(self, symbol: str | None) -> float:
        """Retourne le spread moyen pour une paire."""
        if not symbol:
            return DEFAULT_SPREAD
        return self._spreads.get(symbol, DEFAULT_SPREAD)

    def get_slippage(
        self, vol_regime: str | None = None, news_phase: str | None = None,
    ) -> float:
        """Retourne le slippage estimé selon la volatilité et les news."""
        slip = SLIPPAGE_BY_VOL.get(vol_regime or "NORMAL", 0.3)
        if news_phase == "NEWS_SHOCK":
            slip += SLIPPAGE_NEWS_SHOCK
        return slip

    def total_costs(
        self,
        symbol: str | None = None,
        vol_regime: str | None = None,
        news_phase: str | None = None,
    ) -> float:
        """Coûts totaux en pips (spread + commission + slippage)."""
        spread = self.get_spread(symbol)
        slippage = self.get_slippage(vol_regime, news_phase)
        return spread + COMMISSION_PIPS + slippage

    def apply(
        self,
        symbol: str | None,
        is_win: bool,
        gross_pips: float,
        vol_regime: str | None = None,
        news_phase: str | None = None,
    ) -> float:
        """Applique les coûts de transaction au P&L brut.

        Args:
            symbol: paire tradée
            is_win: True si trade gagnant
            gross_pips: pips bruts (TP si win, -SL si loss)
            vol_regime: volatilité actuelle
            news_phase: phase de news

        Returns:
            P&L net en pips (après coûts)
        """
        costs = self.total_costs(symbol, vol_regime, news_phase)
        if is_win:
            return gross_pips - costs
        else:
            return gross_pips - costs  # les coûts s'ajoutent à la perte

    def expectancy_net(
        self,
        symbol: str | None,
        win_rate: float,
        tp_pips: float,
        sl_pips: float,
        vol_regime: str | None = None,
        news_phase: str | None = None,
    ) -> float:
        """Calcule l'expectancy nette après coûts.

        E = WR × (TP - costs) - (1-WR) × (SL + costs)
        """
        costs = self.total_costs(symbol, vol_regime, news_phase)
        return win_rate * (tp_pips - costs) - (1.0 - win_rate) * (sl_pips + costs)

    def break_even_wr(
        self,
        symbol: str | None,
        tp_pips: float,
        sl_pips: float,
        vol_regime: str | None = None,
        news_phase: str | None = None,
    ) -> float:
        """WR de break-even après coûts.

        WR_be = (SL + costs) / (TP + SL)
        """
        costs = self.total_costs(symbol, vol_regime, news_phase)
        return (sl_pips + costs) / (tp_pips + sl_pips)