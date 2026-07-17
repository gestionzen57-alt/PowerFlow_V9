"""test_transaction_costs.py — Tests pour core/v9/transaction_costs.py.

Vérifie que les coûts de transaction sont correctement modélisés :
- Spread par paire
- Commission fixe
- Slippage par vol_regime
- Slippage supplémentaire en NEWS_SHOCK
- Expectancy nette après coûts
- Break-even WR après coûts
"""
from __future__ import annotations

from core.v9.transaction_costs import TransactionCosts, SPREAD_BY_SYMBOL, COMMISSION_PIPS


def test_spread_by_symbol():
    costs = TransactionCosts()
    assert costs.get_spread("GBPUSD") == 1.5
    assert costs.get_spread("USDJPY") == 1.3
    assert costs.get_spread("USDCAD") == 2.0
    assert costs.get_spread("UNKNOWN") == 2.0  # défaut conservateur
    assert costs.get_spread(None) == 2.0


def test_slippage_by_vol():
    costs = TransactionCosts()
    assert costs.get_slippage("LOW") == 0.0
    assert costs.get_slippage("NORMAL") == 0.3
    assert costs.get_slippage("HIGH") == 1.0
    assert costs.get_slippage("EXTREME") == 2.0


def test_slippage_news_shock():
    costs = TransactionCosts()
    assert costs.get_slippage("NORMAL", "NEWS_SHOCK") == 2.3  # 0.3 + 2.0
    assert costs.get_slippage("HIGH", "NEWS_SHOCK") == 3.0  # 1.0 + 2.0


def test_total_costs():
    costs = TransactionCosts()
    # GBPUSD normal : 1.5 (spread) + 0.7 (commission) + 0.3 (slippage) = 2.5
    total = costs.total_costs("GBPUSD", "NORMAL", "NEUTRE")
    assert total == 2.5


def test_apply_win():
    costs = TransactionCosts()
    # WIN GBPUSD +8 pips normal → 8 - 2.5 = 5.5
    net = costs.apply("GBPUSD", is_win=True, gross_pips=8.0, vol_regime="NORMAL")
    assert net == 5.5


def test_apply_loss():
    costs = TransactionCosts()
    # LOSS GBPUSD -15 pips normal → -15 - 2.5 = -17.5
    net = costs.apply("GBPUSD", is_win=False, gross_pips=-15.0, vol_regime="NORMAL")
    assert net == -17.5


def test_expectancy_net():
    costs = TransactionCosts()
    # WR=50%, TP=8, SL=15, GBPUSD normal
    # net = 0.5 × (8 - 2.5) - 0.5 × (15 + 2.5) = 2.75 - 8.75 = -6.0
    exp = costs.expectancy_net("GBPUSD", 0.50, 8.0, 15.0, "NORMAL")
    assert exp == -6.0


def test_break_even_wr():
    costs = TransactionCosts()
    # TP=8, SL=15, GBPUSD normal, costs=2.5
    # WR_be = (15 + 2.5) / (8 + 15) = 17.5 / 23 = 0.7609
    wr = costs.break_even_wr("GBPUSD", 8.0, 15.0, "NORMAL")
    assert abs(wr - 17.5 / 23.0) < 0.001


def test_break_even_wr_with_drm():
    """Avec DRM (TP=13, SL=8), le break-even WR est plus bas."""
    costs = TransactionCosts()
    # TP=13, SL=8, GBPUSD normal, costs=2.5
    # WR_be = (8 + 2.5) / (13 + 8) = 10.5 / 21 = 0.5
    wr = costs.break_even_wr("GBPUSD", 13.0, 8.0, "NORMAL")
    assert abs(wr - 10.5 / 21.0) < 0.001


def test_high_vol_increases_costs():
    costs = TransactionCosts()
    normal = costs.total_costs("GBPUSD", "NORMAL")
    high = costs.total_costs("GBPUSD", "HIGH")
    assert high > normal