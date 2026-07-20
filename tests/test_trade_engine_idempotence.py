"""Tests de non-régression — idempotence du hook paper-trade (fix P0 2026-07-20).

Bug (catastrophe 17/07, récidive 19-20/07) : la garde d'idempotence de
`TradeEngine` ne comptait que les trades ENCORE ouverts (`closed_at IS NULL`).
Dès qu'un trade était clôturé (par `close_open_trades()` en fin de batch), le
même `snapshot_id` redevenait éligible et le hook `post_decision_hook` — qui
instancie une `TradeEngine` fraîche par snapshot — le ré-ouvrait au passage
suivant, empilant jusqu'à 7 paper_trades clôturés sur un seul snapshot.

Ces tests garantissent :
  1. `_trade_already_open` détecte un trade DÉJÀ CLÔTURÉ (le cœur du fix) ;
  2. `process()` est strictement idempotent à travers un cycle
     ouverture → clôture → re-traitement (aucun doublon en DB).

Doctrine : R6 (défensif), R26 (tests verts avant commit).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

import core.v9.trade_engine as _te_mod
from core.v9.trade_engine import (
    GBPUSD_LONG_ONLY_ENV,
    NO_BAISSIERE_ENV,
    TradeEngine,
)


def _empty_db() -> Path:
    """DB temporaire avec le schéma minimal consommé par les helpers réels."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE paper_trades (trade_id TEXT, snapshot_id TEXT, "
        "direction TEXT, opened_at TEXT, closed_at TEXT, pips_simulated REAL);"
        "CREATE TABLE decisions (decision_id TEXT, snapshot_id TEXT, "
        "symbol TEXT, timestamp TEXT, regime_type TEXT, exploitability_id TEXT);"
    )
    conn.commit()
    conn.close()
    return path


# ── 1. Primitive : _trade_already_open détecte un trade clôturé ──────────────

def test_trade_already_open_detects_closed_trade() -> None:
    """Le cœur du fix : un trade CLÔTURÉ compte comme déjà tradé.

    Avant le fix, la clause `AND closed_at IS NULL` faisait retourner False
    pour un trade fermé → ré-ouverture en boucle.
    """
    path = _empty_db()
    try:
        conn = sqlite3.connect(str(path))
        conn.execute(
            "INSERT INTO paper_trades "
            "(trade_id, snapshot_id, direction, opened_at, closed_at, pips_simulated) "
            "VALUES ('t1', 'snap-A', 'baissiere', '2026-07-20T10:00:00', "
            "'2026-07-20T10:05:00', -15.5)",  # <- CLÔTURÉ
        )
        conn.commit()
        conn.close()

        engine = TradeEngine(db_path=path)
        # Même couple (snapshot, direction), trade déjà clôturé → True.
        assert engine._trade_already_open("snap-A", "baissiere") is True
        # Direction différente sur le même snapshot → pas de doublon → False.
        assert engine._trade_already_open("snap-A", "haussiere") is False
        # Snapshot jamais tradé → False.
        assert engine._trade_already_open("snap-B", "baissiere") is False
    finally:
        path.unlink(missing_ok=True)


# ── 2. Bout-en-bout : process() reste idempotent après clôture ───────────────

class _ArbiterStub:
    def consolidate(self, snapshot_id: str) -> dict:
        return {
            "direction": "haussiere",
            "confiance_arbitree": 80,
            "confiance_arbitree_boosted": 80,
            "principes_source": [],
            "regime_type": "NEUTRE",
            "snapshot_id": snapshot_id,
        }


class _RiskStub:
    capital = 10000.0

    def evaluate(self, _arb, _ctx, _open):
        return {
            "go": True, "raison_blocage": None,
            "risk_amount": 100.0, "position_size": 1.0,
        }


class _CascadesStub:
    def get_active_cascades(self): return []
    def get_cascade_for_snapshot(self, *_a, **_kw): return []
    def apply_cascade_confidence_boost(self, arb, _casc): return arb


class _PyramidingStub:
    def evaluate(self, *_a, **_kw):
        return {"pyramiding_allowed": False, "multiplier": 1.0}


class _InsertingLogger:
    """Logger de test qui écrit RÉELLEMENT dans paper_trades.

    Nécessaire pour que la garde réelle `_trade_already_open` (interrogée au
    2ᵉ passage) voie le trade du 1ᵉʳ passage.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.opens = 0

    def log_open(self, arbiter_result: dict, context: dict) -> str:
        self.opens += 1
        trade_id = f"trade-{self.opens}"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT INTO paper_trades "
            "(trade_id, snapshot_id, direction, opened_at, closed_at, pips_simulated) "
            "VALUES (?, ?, ?, '2026-07-20T10:00:00', NULL, NULL)",
            (trade_id, context.get("snapshot_id"), arbiter_result.get("direction")),
        )
        conn.commit()
        conn.close()
        return trade_id


def _make_engine(monkeypatch: pytest.MonkeyPatch, path: Path) -> TradeEngine:
    monkeypatch.setattr(_te_mod, "infer_session_from_hour", lambda _h: "london")
    # Neutralise les couches non testées ici (PRM, DRM, overrides).
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "0")
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "0")
    monkeypatch.setenv("V9_KELLY_CVAR_ENABLED", "0")
    monkeypatch.delenv("V9_PAPER_TRADE_HALT", raising=False)
    monkeypatch.delenv(NO_BAISSIERE_ENV, raising=False)
    monkeypatch.delenv(GBPUSD_LONG_ONLY_ENV, raising=False)

    eng = TradeEngine(db_path=path)
    eng._arbiter = _ArbiterStub()
    eng._risk_mgr = _RiskStub()
    eng._cascade = _CascadesStub()
    eng._pyramiding = _PyramidingStub()
    eng._logger = _InsertingLogger(path)
    eng._get_open_trades = lambda: []
    eng._build_context = lambda sid, _sess: {"symbol": "GBPUSD", "snapshot_id": sid}
    eng._resolve_symbol_and_decision = lambda _sid: ("GBPUSD", None)
    eng._fetch_signal_recommendation = lambda _sid: {
        "tp_pips_recommended": None, "sl_pips_recommended": None,
        "exit_strategy_recommended": "DYNAMIC",
    }
    eng._load_full_context = lambda _sid: None
    eng._attach_bear_perception_shadow = lambda *a, **k: None
    # NB : _trade_already_open n'est PAS stubbé — on teste la garde réelle.
    return eng


def _count_trades(path: Path, snapshot_id: str) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def test_process_idempotent_across_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ouverture → clôture → re-traitement du MÊME snapshot ne crée pas de
    doublon. C'est exactement la boucle qui a produit 7 trades/snapshot."""
    path = _empty_db()
    snap = "v9-GBPUSD-M15-1784327640-000001"
    try:
        eng = _make_engine(monkeypatch, path)

        # 1ᵉʳ passage : ouverture normale.
        r1 = eng.process(snap)
        assert r1["action"] == "open", r1
        assert _count_trades(path, snap) == 1

        # Clôture (simule close_open_trades en fin de batch).
        conn = sqlite3.connect(str(path))
        conn.execute(
            "UPDATE paper_trades SET closed_at = '2026-07-20T10:05:00' "
            "WHERE snapshot_id = ?",
            (snap,),
        )
        conn.commit()
        conn.close()

        # 2ᵉ passage sur le même snapshot : le hook DOIT skipper.
        r2 = eng.process(snap)
        assert r2["action"] == "skip", r2
        assert r2["raison_blocage"] == "snapshot_deja_trade", r2

        # Aucun doublon : toujours un seul paper_trade pour ce snapshot.
        assert _count_trades(path, snap) == 1
    finally:
        path.unlink(missing_ok=True)
