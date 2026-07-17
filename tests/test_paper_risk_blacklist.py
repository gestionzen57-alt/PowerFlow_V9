"""Tests — Kill switch V9_BLACKLIST_SYMBOLS (paper_risk_manager).

Couvre :
  - is_symbol_tradable() lit l'env var (CSV)
  - défaut (env vide) : tout symbole tradable
  - symbole blacklisté → go=False avec raison_blocage='symbol_blacklisted'
  - autres symboles non affectés
  - case insensitive + whitespace robust

Motion CEO autopilot 2026-07-17 : USDCAD blacklisté (WR=15.8% n=19).
"""
from __future__ import annotations

from core.v9.paper_risk_manager import PaperRiskManager, is_symbol_tradable


# ---------- is_symbol_tradable (helper pur) ----------


def test_is_symbol_tradable_default_no_blacklist(monkeypatch):
    monkeypatch.delenv("V9_BLACKLIST_SYMBOLS", raising=False)
    assert is_symbol_tradable("GBPUSD") is True
    assert is_symbol_tradable("USDCAD") is True
    assert is_symbol_tradable("AUDUSD") is True


def test_is_symbol_tradable_blacklist_single(monkeypatch):
    monkeypatch.setenv("V9_BLACKLIST_SYMBOLS", "USDCAD")
    assert is_symbol_tradable("USDCAD") is False
    assert is_symbol_tradable("GBPUSD") is True
    assert is_symbol_tradable("AUDUSD") is True


def test_is_symbol_tradable_blacklist_csv(monkeypatch):
    monkeypatch.setenv("V9_BLACKLIST_SYMBOLS", "USDCAD,EURUSD")
    assert is_symbol_tradable("USDCAD") is False
    assert is_symbol_tradable("EURUSD") is False
    assert is_symbol_tradable("USDJPY") is True


def test_is_symbol_tradable_case_insensitive(monkeypatch):
    monkeypatch.setenv("V9_BLACKLIST_SYMBOLS", "usdcad")
    assert is_symbol_tradable("USDCAD") is False
    assert is_symbol_tradable("usdcad") is False


def test_is_symbol_tradable_whitespace_tolerated(monkeypatch):
    monkeypatch.setenv("V9_BLACKLIST_SYMBOLS", " USDCAD , EURUSD ")
    assert is_symbol_tradable("USDCAD") is False
    assert is_symbol_tradable("EURUSD") is False
    assert is_symbol_tradable("GBPUSD") is True


def test_is_symbol_tradable_none_or_empty(monkeypatch):
    monkeypatch.delenv("V9_BLACKLIST_SYMBOLS", raising=False)
    # Pas de symbole = ne pas bloquer (compat tests / snapshots sans symbol)
    assert is_symbol_tradable(None) is True
    assert is_symbol_tradable("") is True


# ---------- Integration PaperRiskManager.evaluate() ----------


def _arbiter(symbol: str = "GBPUSD") -> dict:
    return {
        "symbol": symbol,
        "direction": "haussiere",
        "confiance_arbitree": 85,
    }


def test_prm_evaluate_blocks_blacklisted_symbol(monkeypatch):
    """Si V9_BLACKLIST_SYMBOLS contient le symbole, evaluate() retourne
    go=False avec raison_blocage='symbol_blacklisted (...)' SANS appeler
    le RiskManager sous-jacent.
    """
    monkeypatch.setenv("V9_BLACKLIST_SYMBOLS", "USDCAD")
    prm = PaperRiskManager()
    result = prm.evaluate(_arbiter("USDCAD"), context={"symbol": "USDCAD"})
    assert result["go"] is False
    assert result["raison_blocage"] == "symbol_blacklisted (USDCAD)"
    assert result["position_size"] == 0.0
    assert result["rules_checked"] == ["symbol_blacklist"]
    assert result["rules_passed"] == []
    assert result["paper_risk_version"] == "1.1"


def test_prm_evaluate_allows_non_blacklisted_symbol(monkeypatch):
    monkeypatch.setenv("V9_BLACKLIST_SYMBOLS", "USDCAD")
    prm = PaperRiskManager()
    result = prm.evaluate(_arbiter("GBPUSD"), context={"symbol": "GBPUSD"})
    # Pas assert sur go (dépend du RiskManager interne), mais le court-circuit
    # symbol_blacklist ne doit PAS avoir été déclenché.
    assert result["raison_blocage"] != "symbol_blacklisted (GBPUSD)"
    assert "symbol_blacklist" not in result.get("rules_checked", [])


def test_prm_evaluate_blank_blacklist_is_permissive(monkeypatch):
    monkeypatch.delenv("V9_BLACKLIST_SYMBOLS", raising=False)
    prm = PaperRiskManager()
    # Tous symboles doivent passer le premier filtre.
    for sym in ["GBPUSD", "USDCAD", "AUDUSD", "USDJPY"]:
        result = prm.evaluate(_arbiter(sym), context={"symbol": sym})
        assert result["raison_blocage"] != f"symbol_blacklisted ({sym})"
