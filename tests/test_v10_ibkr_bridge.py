"""Tests for V10 IBKR Bridge."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_ibkr_bridge import (
    V10IBKRBridge,
    IBKRConfig,
    OrderRequest,
    OrderResult,
    create_ibkr_bridge,
    V9_EXECUTION_ENABLED,
)


class TestIBKRBridgeConfig:
    """Test IBKR configuration."""

    def test_default_config(self):
        config = IBKRConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 7497
        assert config.client_id == 10
        assert config.readonly is True

    def test_custom_config(self):
        config = IBKRConfig(host="192.168.1.100", port=7496, client_id=20, readonly=False)
        assert config.host == "192.168.1.100"
        assert config.port == 7496
        assert config.client_id == 20
        assert config.readonly is False


class TestOrderRequest:
    """Test OrderRequest dataclass."""

    def test_basic_order(self):
        req = OrderRequest(
            symbol="EURUSD",
            action="BUY",
            quantity=0.01,
        )
        assert req.symbol == "EURUSD"
        assert req.action == "BUY"
        assert req.quantity == 0.01
        assert req.order_type == "MKT"

    def test_limit_order(self):
        req = OrderRequest(
            symbol="GBPUSD",
            action="SELL",
            quantity=0.05,
            order_type="LMT",
            limit_price=1.3000,
        )
        assert req.order_type == "LMT"
        assert req.limit_price == 1.3000


class TestV10IBKRBridge:
    """Test V10IBKRBridge (mock mode)."""

    def test_create_bridge(self):
        bridge = create_ibkr_bridge()
        assert isinstance(bridge, V10IBKRBridge)
        assert bridge.config.readonly is True

    def test_bridge_disconnected(self):
        """Test order when bridge is not connected and not in SHADOW mode."""
        import core.v10.v10_ibkr_bridge as ibkr_module
        original_flag = ibkr_module.V9_EXECUTION_ENABLED
        ibkr_module.V9_EXECUTION_ENABLED = True
        try:
            bridge = create_ibkr_bridge()
            # Not connected, should return error
            req = OrderRequest(symbol="EURUSD", action="BUY", quantity=0.01)
            result = bridge.place_order(req)
            assert result.success is False
            assert "Not connected" in result.error
        finally:
            ibkr_module.V9_EXECUTION_ENABLED = original_flag

    def test_shadow_mode_order(self):
        """Test order in SHADOW mode (V9_EXECUTION_ENABLED=False)."""
        bridge = create_ibkr_bridge()
        # Manually set connected to test SHADOW path
        bridge.connected = True
        req = OrderRequest(symbol="EURUSD", action="BUY", quantity=0.01)
        result = bridge.place_order(req)
        # Should succeed in SHADOW mode
        assert result.success is True
        assert "SHADOW" in result.order_id
        assert result.filled == 0.01
        assert "SHADOW mode" in result.error

    def test_make_contract(self):
        bridge = create_ibkr_bridge()
        contract = bridge._make_contract("EURUSD")
        # Should create a Forex contract
        assert contract is not None


class TestOrderResult:
    """Test OrderResult dataclass."""

    def test_success_result(self):
        result = OrderResult(
            success=True,
            order_id="12345",
            filled=0.01,
            avg_fill_price=1.1000,
            commission=0.50
        )
        assert result.success is True
        assert result.order_id == "12345"

    def test_error_result(self):
        result = OrderResult(success=False, error="Connection failed")
        assert result.success is False
        assert "Connection failed" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])