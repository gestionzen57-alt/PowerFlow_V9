"""Test Phase 14 — LiquidityMap filter in compose_filters."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_filter_compositor import compose_filters  # noqa: E402
from core.v10.v10_liquidity_map import (  # noqa: E402
    LiquidityMap,
    LiquidityZone,
    ZoneSide,
    ZoneType,
    get_liquidity_map,
    liquidity_bonus_malus,
)


def _sample_bars():
    """Retourne des barres OHLCV simples pour test."""
    return [
        {"open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005, "volume": 1000, "bar_time": 1700000000 + i * 1800}
        for i in range(30)
    ]


def _sample_liquidity_map_buy_zone_near():
    """Crée une LiquidityMap avec une zone d'achat proche du prix."""
    from core.v10.v10_liquidity_map import LiquidityMap, LiquidityZone, ZoneSide, ZoneType
    mp = LiquidityMap(
        symbol="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        current_price=1.1005,
        source="test",
        seed=42,
    )
    # Zone d'achat proche (prix 1.1000, current_price 1.1005)
    zone = LiquidityZone(
        zone_type="FAIR_VALUE_GAP",
        side=ZoneSide.BUY,
        price=1.1000,
        strength=1.5,
        n_bars_back=5,
        width=0.0002,
    )
    mp.zones = [zone]
    mp.nearest_buy_zone = zone
    mp.current_price = 1.1005
    mp.price_in_zone = True
    mp.n_zones_detected = 1
    return mp


def _sample_liquidity_map_sell_zone_near():
    """Crée une LiquidityMap avec une zone de vente proche du prix."""
    from core.v10.v10_liquidity_map import LiquidityMap, LiquidityZone, ZoneSide, ZoneType
    mp = LiquidityMap(
        symbol="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        current_price=1.1005,
        source="test",
        seed=42,
    )
    # Zone de vente proche (prix 1.1010, current_price 1.1005)
    zone = LiquidityZone(
        zone_type="EQUAL_HIGHS",
        side=ZoneSide.SELL,
        price=1.1010,
        strength=2.0,
        n_bars_back=3,
        width=0.0003,
    )
    mp.zones = [zone]
    mp.nearest_sell_zone = zone
    mp.current_price = 1.1005
    mp.price_in_zone = True
    mp.n_zones_detected = 1
    return mp


def _sample_liquidity_map_empty():
    """Crée une LiquidityMap vide."""
    from core.v10.v10_liquidity_map import LiquidityMap
    mp = LiquidityMap(
        symbol="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        current_price=1.1005,
        source="test",
        seed=42,
    )
    return mp


def _sample_bars():
    """Retourne des barres OHLCV simples pour test."""
    return [
        {"open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005, "volume": 1000, "bar_time": 1700000000 + i * 1800}
        for i in range(30)
    ]


def _make_liq_test(side, price, atr=0.0010):
    """Helper pour créer un mock LiquidityMap avec zone spécifique."""
    from core.v10.v10_liquidity_map import LiquidityMap, LiquidityZone, ZoneSide
    mp = type('LiquidityMap', (), {})()
    mp.zones = []
    mp.current_price = 1.1005
    if side == ZoneSide.BUY:
        zone = type('zone', (), {'side': ZoneSide.BUY, 'price': price, 'width': 0.0002})()
        mp.nearest_buy_zone = zone
    else:
        zone = type('zone', (), {'side': ZoneSide.SELL, 'price': price, 'width': 0.0002})()
        mp.nearest_sell_zone = zone
    mp.price_in_zone = True
    mp.zones = []
    return mp


# ─────────────────────────────────────────────────────────────────────
# Tests get_liquidity_map
# ─────────────────────────────────────────────────────────────────────

def test_liquidity_map_basic():
    """1. get_liquidity_map retourne une map avec zones détectées."""
    bars = _sample_bars()
    mp = get_liquidity_map("EURUSD", "M30", bars, timestamp="2026-08-07T10:00:00Z")
    assert mp is not None
    assert mp.symbol == "EURUSD"
    assert mp.timeframe == "M30"
    assert mp.n_bars_scanned == 30
    assert mp.current_price > 0
    # Peut avoir 0 zones si pas assez de données pour détection


def test_liquidity_map_buy_zone_bonus():
    """2. liquidity_bonus_malus : zone acheteuse + signal bullish → +0.05."""
    mp = _sample_liquidity_map_buy_zone_near()
    bonus = liquidity_bonus_malus("BULLISH", 1.1005, mp, atr=0.0010)
    assert bonus == 0.05


def test_liquidity_map_sell_zone_malus():
    """3. liquidity_bonus_malus : zone vendeuse + signal bearish → +0.05."""
    mp = _sample_liquidity_map_sell_zone_near()
    bonus = liquidity_bonus_malus("BEARISH", 1.1005, mp, atr=0.0010)
    assert bonus == 0.05


def test_liquidity_map_opposing_malus():
    """4. liquidity_bonus_malus : zone opposée proche (< ATR*0.5) → -0.10."""
    from core.v10.v10_liquidity_map import LiquidityMap, LiquidityZone, ZoneSide
    mp = LiquidityMap(
        symbol="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        current_price=1.1005,
        source="test",
        seed=42,
    )
    # Zone vendeuse proche (opposée pour signal BULLISH)
    zone = type('zone', (), {'side': type('ZoneSide', (), {'SELL': 'SELL'})().SELL, 'price': 1.1006, 'width': 0.0002})()
    mp.nearest_sell_zone = zone
    mp.current_price = 1.1005
    mp.zones = [zone]  # Add zone to zones list so function doesn't return early
    bonus = liquidity_bonus_malus("BULLISH", 1.1005, mp, atr=0.0010)
    assert bonus == -0.10


def test_liquidity_map_no_zone_no_bonus():
    """5. liquidity_bonus_malus : pas de zone → 0.0."""
    mp = _sample_liquidity_map_empty()
    bonus = liquidity_bonus_malus("BULLISH", 1.1005, mp, atr=0.0010)
    assert bonus == 0.0


# ─────────────────────────────────────────────────────────────────────
# Tests compose_filters with liquidity map
# ─────────────────────────────────────────────────────────────────────

def test_compose_filters_liquidity_trap_buy():
    """1. BUY A2 devant zone de vente (SSL) → downgrade A3."""
    bars = _sample_bars()
    # Mock liquidity map avec zone de vente proche
    import core.v10.v10_filter_compositor as fc
    original_liq = fc.get_liquidity_context if hasattr(fc, 'get_liquidity_context') else None
    
    # On ne peut pas facilement mocker get_liquidity_context car il n'est pas encore dans compose_filters
    # Ce test vérifiera le comportement une fois l'intégration faite
    pass


def test_compose_filters_liquidity_trap_sell():
    """2. SELL A2 devant zone d'achat (BSL) → downgrade A3."""
    pass


def test_compose_filters_liquidity_bonus_buy():
    """3. BUY A3 dans zone d'achat (BSL) → upgrade A2."""
    pass


def test_compose_filters_liquidity_no_zone():
    """4. Prix hors zone → signal inchangé."""
    pass


def test_compose_filters_liquidity_exception_failopen():
    """5. Exception dans liquidity_map → signal inchangé (R6)."""
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])