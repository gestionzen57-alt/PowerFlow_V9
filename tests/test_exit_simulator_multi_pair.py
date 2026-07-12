"""Tests — Brief Q4 (multi-paires, 2026-07-13) : core/v9/exit_simulator.py.

Aucun test existant ne couvrait ExitSimulator avant ce brief (vérifié :
`grep -rl "ExitSimulator" tests/` ne retournait rien) — ces tests servent
donc à la fois de couverture Q4 ET de première régression de base pour ce
module.

Contrainte dure du brief : le comportement GBPUSD (implicite, symbol=None)
doit être STRICTEMENT inchangé. La preuve la plus forte possible sans
dépendre de valeurs codées en dur : charger le module TEL QU'IL ÉTAIT
avant modification (backup R8 MD5 posé avant édition,
docs/calibration/backups/2026-07-13_multi_pair_q4/exit_simulator.py.bak)
sous un nom différent, et comparer ses résultats bit-à-bit à la version
actuelle sur une batterie de scénarios — pas juste relire le code et
espérer que le raisonnement est correct.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.exit_simulator import (  # noqa: E402
    ExitSimulator,
    price_to_pips,
    pips_multiplier_for_symbol,
)

BACKUP_PATH = ROOT / "docs" / "calibration" / "backups" / "2026-07-13_multi_pair_q4" / "exit_simulator.py.bak"


def _load_pre_q4_module():
    """Charge la version pré-Brief-Q4 du module sous un nom isolé (pas
    d'interférence avec `core.v9.exit_simulator` déjà importé)."""
    loader = importlib.machinery.SourceFileLoader("exit_simulator_pre_q4", str(BACKUP_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# Scénarios variés : stratégie, tp/sl, spread, direction, série de prix.
SCENARIOS = [
    dict(strategy="TP_SL", tp_pips=10.0, sl_pips=15.0, spread_pips=0.5,
         entry=1.3050, direction="haussiere",
         future_mids=[1.3055, 1.3060, 1.3040, 1.3070, 1.3030, 1.3080]),
    dict(strategy="TP_SL", tp_pips=8.0, sl_pips=15.0, spread_pips=0.5,
         entry=1.2900, direction="baissiere",
         future_mids=[1.2895, 1.2910, 1.2880, 1.2920, 1.2860]),
    dict(strategy="TRAILING", trailing_dist=15.0, spread_pips=0.5,
         entry=1.3000, direction="haussiere",
         future_mids=[1.3010, 1.3025, 1.3015, 1.3005, 1.2995]),
    dict(strategy="TIME_BASED", time_bars=4, spread_pips=0.5,
         entry=1.3000, direction="baissiere",
         future_mids=[1.2990, 1.2985, 1.2995, 1.3005]),
    dict(strategy="MFE_ONLY", spread_pips=0.5,
         entry=1.3000, direction="haussiere",
         future_mids=[1.3010, 1.3005, 1.3020]),
    dict(strategy="DYNAMIC", spread_pips=0.5,
         entry=1.3000, direction="haussiere", session_marche="asie",
         future_mids=[1.3005, 1.3012, 1.3008, 1.3015, 1.3002]),
    dict(strategy="DYNAMIC", spread_pips=0.5,
         entry=1.3000, direction="baissiere", session_marche="new_york",
         future_mids=[1.2998, 1.2990, 1.2985, 1.2995, 1.3005]),
]


def _run(module, params: dict):
    sim_kwargs = {k: v for k, v in params.items()
                  if k not in ("entry", "direction", "future_mids", "session_marche", "utc_hour")}
    sim = module.ExitSimulator(**sim_kwargs)
    return sim.simulate(
        entry=params["entry"],
        direction=params["direction"],
        future_mids=params["future_mids"],
        session_marche=params.get("session_marche"),
        utc_hour=params.get("utc_hour"),
    )


# ---------- Régression GBPUSD (symbol=None) : identique à la version pré-Q4 ----------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["strategy"] for s in SCENARIOS])
def test_default_symbol_matches_pre_q4_output_exactly(scenario: dict):
    """Preuve empirique (pas juste théorique) que le comportement par
    défaut (symbol=None, GBPUSD implicite) est strictement inchangé :
    exécute le même scénario sur le module pré-Q4 (backup R8) et sur le
    module actuel, compare pips/exit_reason/mfe/mae/bars_held."""
    pre_q4 = _load_pre_q4_module()
    before = _run(pre_q4, scenario)
    after = _run(sys.modules["core.v9.exit_simulator"], scenario)

    assert after.pips == before.pips
    assert after.exit_reason == before.exit_reason
    assert after.max_favorable == before.max_favorable
    assert after.max_adverse == before.max_adverse
    assert after.bars_held == before.bars_held
    assert after.is_win == before.is_win


def test_price_to_pips_default_multiplier_unchanged():
    assert price_to_pips(0.0015) == 15.0  # comportement historique : *10000


def test_exit_simulator_no_symbol_arg_defaults_to_10000_multiplier():
    sim = ExitSimulator(strategy="TP_SL")
    assert sim._pips_multiplier == 10000
    assert sim.symbol is None


# ---------- Multiplicateur pips par symbole (nouveau, Brief Q4) ----------


@pytest.mark.parametrize("symbol,expected", [
    (None, 10000), ("GBPUSD", 10000), ("EURUSD", 10000),
    ("USDJPY", 100), ("GBPJPY", 100),
])
def test_pips_multiplier_for_symbol(symbol, expected):
    assert pips_multiplier_for_symbol(symbol) == expected


@pytest.mark.parametrize("symbol", ["USDJPY", "GBPJPY"])
def test_exit_simulator_jpy_symbol_uses_multiplier_100(symbol):
    sim = ExitSimulator(strategy="TP_SL", symbol=symbol)
    assert sim._pips_multiplier == 100


def test_price_to_pips_jpy_multiplier_gives_correct_pip_count():
    # 0.15 de mouvement de prix sur une paire JPY (pip=0.01) = 15 pips,
    # PAS 1500 (ce que donnerait le multiplicateur 10000, faux pour JPY).
    assert price_to_pips(0.15, multiplier=100) == 15.0
    assert price_to_pips(0.15, multiplier=10000) == 1500.0  # démontre le bug qu'on évite


def test_jpy_symbol_tp_hit_at_correct_price_distance():
    """Avec symbol=USDJPY, tp_pips=10 doit correspondre à 0.10 de prix
    (10 pips * 0.01), pas 0.001 (ce que donnerait le multiplicateur GBPUSD)."""
    sim_jpy = ExitSimulator(strategy="TP_SL", tp_pips=10.0, sl_pips=50.0, spread_pips=0.0, symbol="USDJPY")
    # Entry 150.00, TP à 150.10 (10 pips JPY) — la bougie suivante l'atteint tout juste.
    result = sim_jpy.simulate(entry=150.00, direction="haussiere", future_mids=[150.05, 150.11, 150.20])
    assert result.exit_reason == "tp_hit"
    assert result.pips == pytest.approx(10.0, abs=0.5)


def test_gbpusd_symbol_explicit_matches_default_none():
    """symbol='GBPUSD' explicite doit donner exactement le même multiplicateur
    que symbol=None (défaut) — GBPUSD n'est dans aucune table spéciale."""
    sim_explicit = ExitSimulator(strategy="TP_SL", symbol="GBPUSD")
    sim_default = ExitSimulator(strategy="TP_SL")
    assert sim_explicit._pips_multiplier == sim_default._pips_multiplier == 10000


# ---------- config.py : registre SUPPORTED_SYMBOLS (Brief Q4) ----------


def test_config_supported_symbols_includes_gbpusd_and_new_pairs():
    from core.v9.config import SUPPORTED_SYMBOLS

    assert "GBPUSD" in SUPPORTED_SYMBOLS
    for pair in ("EURUSD", "USDJPY", "GBPJPY"):
        assert pair in SUPPORTED_SYMBOLS


def test_config_supported_symbols_consistent_with_jpy_quoted_symbols():
    from core.v9.config import SUPPORTED_SYMBOLS
    from core.v9.exit_simulator import JPY_QUOTED_SYMBOLS

    assert JPY_QUOTED_SYMBOLS.issubset(set(SUPPORTED_SYMBOLS))
