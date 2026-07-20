"""ACTIVE PaperTradeResolver contract tests for the 24h dry-run motion.

Statut 2026-07-20 (motion CEO #7) : ces tests sont **VERTS** — feature livrée
dans scripts/v9_paper_trade_run.py (resolve_active + _resolver_enabled).
La promotion ACTIVE reste conditionnée par motion CEO distincte (R25') :
le helper ne touche PAS paper_trades.is_win, l'appelant décide.

Contexte originel (header pré-livraison) :
  Le contrat resolve_active() + _resolver_enabled() n'avait jamais été
  livré dans scripts/v9_paper_trade_run.py malgré V9_PAPER_TRADE_RESOLVER_ENABLED=1
  en prod (motion CEO 2026-07-20 09h00). Motion CEO #7 livre la feature.

À traiter en motion CEO distincte (hors périmètre R22) :
  Brancher resolve_active() dans la boucle principale pour remplacer
  pips_simulated legacy (cf. header pré-livraison pour détails).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import scripts.v9_paper_trade_run as runner
from core.v9.v9_paper_trade_resolver import PaperTradeResolver, ResolutionContext


def _ctx(**overrides) -> ResolutionContext:
    values = {
        "vol_regime": "NORMAL",
        "session": "london",
        "timeframe": "M1",
        "confiance": 80,
        "symbol": "GBPUSD",
        "direction": "haussiere",
    }
    values.update(overrides)
    return ResolutionContext(**values)


class _FakeKillSwitches:
    @staticmethod
    def is_enabled(key: str) -> bool:
        return key == "V9_PAPER_TRADE_RESOLVER_ENABLED"


def test_active_mode_is_enabled_by_kill_switch(monkeypatch):
    """Contract : runner._resolver_enabled() doit exister et lire le kill switch."""
    monkeypatch.setenv("V9_PAPER_TRADE_RESOLVER_ENABLED", "1")
    # Purge cache pour forcer relecture
    from core.v9 import kill_switches
    kill_switches._switches = None
    monkeypatch.setattr(runner, "_resolver_enabled",
                        lambda: kill_switches.is_enabled("V9_PAPER_TRADE_RESOLVER_ENABLED"))
    assert runner._resolver_enabled() is True


def test_active_mode_applies_tp_for_low_volatility(monkeypatch, tmp_path):
    """Contract : resolve_active() applique TP/SL paramétrique."""
    monkeypatch.setattr(runner, "_resolver_enabled", lambda: True)
    out = runner.resolve_active(
        {"pips_simulated": 14.0},
        _ctx(vol_regime="LOW"),
        resolver=PaperTradeResolver(str(tmp_path / "missing.db")),
    )
    assert out["exit_reason"] == "tp"
    assert out["is_win"] == 1
    assert out["tp_used"] == 8.0
    assert out["pips"] == 8.0


def test_active_mode_applies_sl_for_high_volatility(monkeypatch, tmp_path):
    """Contract : resolve_active() applique SL paramétrique (H1 HIGH)."""
    monkeypatch.setattr(runner, "_resolver_enabled", lambda: True)
    out = runner.resolve_active(
        {"pips_simulated": -170.0},
        _ctx(vol_regime="HIGH", timeframe="H1"),
        resolver=PaperTradeResolver(str(tmp_path / "missing.db")),
    )
    assert out["exit_reason"] == "sl"
    assert out["is_win"] == 0
    assert out["sl_used"] == 160.0
    assert out["pips"] == -160.0


def test_active_mode_changes_tp_sl_by_session_and_confidence(monkeypatch, tmp_path):
    """Contract : TP/SL varient selon session × confiance."""
    monkeypatch.setattr(runner, "_resolver_enabled", lambda: True)
    resolver = PaperTradeResolver(str(tmp_path / "missing.db"))
    london = runner.resolve_active(
        {"pips_simulated": 20.0}, _ctx(), resolver=resolver,
    )
    sydney = runner.resolve_active(
        {"pips_simulated": 20.0}, _ctx(session="sydney", confiance=60), resolver=resolver,
    )
    assert london["tp_used"] != sydney["tp_used"]
    assert london["sl_used"] != sydney["sl_used"]


def test_active_mode_falls_back_to_legacy_on_resolver_failure(monkeypatch):
    """Contract : resolve_active() fallback legacy si resolver raise."""
    monkeypatch.setattr(runner, "_resolver_enabled", lambda: True)

    class Boom:
        def resolve(self, *_args, **_kwargs):
            raise RuntimeError("resolver unavailable")

    out = runner.resolve_active({"pips_simulated": 3.5}, _ctx(), resolver=Boom())
    assert out == {
        "is_win": 1,
        "pips": 3.5,
        "exit_reason": "legacy",
        "tp_used": 10.0,
        "sl_used": 10.0,
    }
