"""Tests du filtre devise constitutive à la source (Tâche 2).

Mission baissier 2/2. Cause racine : un principe scope="ALL" était évalué
pour les 8 DEVISES, produisant 6 lignes sur des devises NON constitutives du
symbole. Le fix borne la boucle de `evaluate_principles` aux seules devises
(base, quote) du symbole → ratio currency ∈ {base,quote} / total = 100%.

Deux niveaux :
  1. Unitaire — `_constitutive_currencies` (les 3 cas nommés).
  2. Intégration — `evaluate_principles` avec un principe factice ALL-scope,
     seams DB monkeypatchés, pour vérifier le ratio réel.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9.principle_engine import PrincipleEngine, _constitutive_currencies


# ── 1. Unitaire : _constitutive_currencies ────────────────────────────


def test_principle_engine_currency_filter_gbpusd() -> None:
    """GBPUSD → {GBP, USD} ; les devises tierces sont exclues."""
    cur = _constitutive_currencies("GBPUSD")
    assert cur == {"GBP", "USD"}
    for foreign in ("EUR", "JPY", "AUD", "NZD", "CAD", "CHF"):
        assert foreign not in cur


def test_principle_engine_currency_filter_eurusd() -> None:
    """EURUSD → {EUR, USD}."""
    cur = _constitutive_currencies("EURUSD")
    assert cur == {"EUR", "USD"}
    assert "GBP" not in cur


def test_principle_engine_currency_filter_aud_nzd_disabled() -> None:
    """Pour GBPUSD, AUD et NZD sont désactivés (non constitutifs). Pour un
    cross AUDNZD, seules AUD/NZD survivent et USD est désactivé — preuve que
    le filtre est piloté par le symbole, pas par une liste fixe."""
    gbpusd = _constitutive_currencies("GBPUSD")
    assert "AUD" not in gbpusd and "NZD" not in gbpusd
    audnzd = _constitutive_currencies("AUDNZD")
    assert audnzd == {"AUD", "NZD"}
    assert "USD" not in audnzd
    # R6 : symbole non standard → pas de filtrage (None), comportement legacy.
    assert _constitutive_currencies("XAU") is None
    assert _constitutive_currencies(None) is None


# ── 2. Intégration : ratio réel via evaluate_principles ────────────────


class _FakePrinciple:
    """Principe factice scope=ALL, non émetteur (conditions vides).

    matches_scope renvoie toujours True (comme un scope_currencies="ALL"),
    ce qui, SANS le fix, produirait 8 évaluations. Avec le fix source, seules
    les devises constitutives survivent.
    """

    principle_id = "FAKE_ALL_SCOPE"
    v9_status = "ACTIVE"
    kind = "descriptif"
    anti_signal_bias = 0
    conditions: list = []
    emits: dict = {}
    bounds: dict = {}

    def matches_scope(self, symbol: str, timeframe: str, currency: str) -> bool:
        return True


def _make_engine_with_snapshot(symbol: str) -> tuple[PrincipleEngine, Path, str]:
    """Construit un PrincipleEngine sur DB temp + insère 1 forces_snapshot
    avec les 8 colonnes force_xxx. Retourne (engine, path, snapshot_id)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(tmp.name)
    tmp.close()
    engine = PrincipleEngine(db_path=path)  # init_principle_db + YAML
    snap = f"v9-{symbol}-M15-1784327640-000999"
    conn = sqlite3.connect(str(path))
    # forces_snapshots avec les colonnes force_<devise> lues par la boucle.
    cols = ", ".join(f"force_{d}" for d in
                     ("eur", "usd", "gbp", "jpy", "aud", "nzd", "cad", "chf"))
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS forces_snapshots ("
        f"id INTEGER PRIMARY KEY, snapshot_id TEXT, symbol TEXT, timeframe TEXT, "
        f"mid REAL, stale INTEGER, {cols})"
    )
    vals = ", ".join(["50.0"] * 8)
    conn.execute(
        f"INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, mid, "
        f"stale, {cols}) VALUES (?, ?, 'M15', 1.34, 0, {vals})",
        (snap, symbol),
    )
    conn.commit()
    conn.close()
    return engine, path, snap


def _patch_seams(engine: PrincipleEngine, symbol: str, monkeypatch) -> None:
    """Neutralise les dépendances lourdes, garde la boucle devise réelle."""
    monkeypatch.setattr(
        engine, "_load_shared_context",
        lambda conn, snap: {"symbol": symbol, "timeframe": "M15", "context": {}},
    )
    monkeypatch.setattr(engine, "_load_per_currency_rows", lambda conn, table, snap: {})
    monkeypatch.setattr(
        engine, "_build_currency_context",
        lambda base, cur, reg, zone, fv: {"currency": cur},
    )
    monkeypatch.setattr(engine, "_write_evaluations_to_db", lambda conn, evals: None)
    engine.principles = [_FakePrinciple()]


def test_principle_engine_currency_filter_ratio_gbpusd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kill switch ON → evaluate_principles ne produit QUE GBP/USD → 100%."""
    # Le filtre est gaté (défaut OFF) pour préserver l'invariant 8-devises
    # (couche diversify). On l'active explicitement ici.
    monkeypatch.setenv("V9_CONSTITUTIVE_CURRENCY_FILTER", "1")
    engine, path, snap = _make_engine_with_snapshot("GBPUSD")
    try:
        _patch_seams(engine, "GBPUSD", monkeypatch)
        evals = engine.evaluate_principles(snap)
        currencies = {e["currency"] for e in evals}
        # Exactement 2 devises constitutives (1 principe × {GBP, USD}).
        assert currencies == {"GBP", "USD"}
        # Ratio constitutif = 100% (aucune devise tierce).
        constitutive = {"GBP", "USD"}
        in_scope = sum(1 for e in evals if e["currency"] in constitutive)
        assert in_scope == len(evals) == 2
    finally:
        path.unlink(missing_ok=True)
