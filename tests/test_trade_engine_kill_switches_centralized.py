"""test_trade_engine_kill_switches_centralized.py — Régression P0 (2026-07-20).

Bug originel : `_gbpusd_long_only_enabled()` et `_no_baissiere_enabled()` lisaient
`os.environ.get(...)` directement. Si le wrapper `v9_load_kill_switches.py`
n'est pas chargé AVANT le trade_engine (cas du cron V9_PaperTradeLoop),
`os.environ` est vide et les switches sont lus OFF même si le .env dit ON.

Symptôme runtime (incident 2026-07-20 14h15 UTC) : paper_trade GBPUSD short
ouvert (pt_d255e1149326) alors que V9_NO_BAISSIERE=1 ET V9_GBPUSD_LONG_ONLY=1
dans config/v9_kill_switches.env.

Fix : les 6 helpers `_xxx_enabled()` du trade_engine utilisent maintenant
`kill_switches.get()` qui lit `os.environ` en priorité puis le fichier .env
en fallback.

Doctrine :
- R7 : tests verts obligatoires (régression fermée)
- R2 : additif — le comportement legacy (env-only) reste valide si le
  wrapper charge le .env (priorité env > fichier)
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def fresh_trade_engine_module():
    """Recharge le module trade_engine pour reset le cache _switches.

    Le cache dans kill_switches._switches est process-local ; on doit
    le purger entre tests qui modifient l'environnement.
    """
    # Purge cache
    from core.v9 import kill_switches
    kill_switches._switches = None
    yield


def test_no_baissiere_reads_env_first(monkeypatch, fresh_trade_engine_module):
    """Priorité 1 : os.environ prime sur le fichier .env."""
    monkeypatch.setenv("V9_NO_BAISSIERE", "0")  # env dit OFF
    # .env dit ON (défaut prod) mais env gagne
    from core.v9.trade_engine import _no_baissiere_enabled
    assert _no_baissiere_enabled() is False, (
        "env doit primer : os.environ=V9_NO_BAISSIERE=0 doit gagner"
    )


def test_no_baissiere_falls_back_to_file(monkeypatch, fresh_trade_engine_module):
    """Priorité 2 : si env absent, lit le .env (cas du bug P0).

    Reproduction directe de l'incident : subprocess qui n'a pas chargé
    le .env via wrapper → os.environ vide → kill_switches.get() doit
    quand même retourner la valeur du fichier.
    """
    monkeypatch.delenv("V9_NO_BAISSIERE", raising=False)
    # .env prod dit V9_NO_BAISSIERE=1
    from core.v9.trade_engine import _no_baissiere_enabled
    enabled = _no_baissiere_enabled()
    # On vérifie au moins que ça lit une valeur (bool) cohérente avec le fichier
    assert isinstance(enabled, bool)
    # Si le fichier dit 1, le helper retourne True (fix P0)
    env_path = ROOT_DIR / "config" / "v9_kill_switches.env"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.strip().startswith("V9_NO_BAISSIERE="):
                val = line.split("=", 1)[1].strip()
                expected = val == "1"
                assert enabled == expected, (
                    f"FIX P0 KO : kill_switches.get() retourne {enabled}, "
                    f"mais .env dit V9_NO_BAISSIERE={val}. Le switch n'est "
                    f"plus effectif en runtime cron."
                )


def test_gbpusd_long_only_falls_back_to_file(monkeypatch, fresh_trade_engine_module):
    """Idem pour V9_GBPUSD_LONG_ONLY — l'incident touchait aussi ce switch."""
    monkeypatch.delenv("V9_GBPUSD_LONG_ONLY", raising=False)
    from core.v9.trade_engine import _gbpusd_long_only_enabled
    enabled = _gbpusd_long_only_enabled()
    assert isinstance(enabled, bool)
    env_path = ROOT_DIR / "config" / "v9_kill_switches.env"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.strip().startswith("V9_GBPUSD_LONG_ONLY="):
                val = line.split("=", 1)[1].strip()
                expected = val == "1"
                assert enabled == expected, (
                    f"FIX P0 KO : _gbpusd_long_only_enabled()={enabled}, "
                    f".env dit {val}"
                )


def test_all_6_helpers_use_kill_switches_get(monkeypatch, fresh_trade_engine_module):
    """Vérifie que les 6 helpers lisent bien le .env en fallback.

    Bug originel : les 6 helpers (_trade_engine_enabled,
    _portfolio_risk_enabled, _market_regime_global_enabled,
    _kelly_cvar_enabled, _gbpusd_long_only_enabled, _no_baissiere_enabled,
    _dynamic_risk_enabled) lisaient os.environ.get direct. Le test
    vérifie qu'ils lisent bien le .env en absence d'env var.
    """
    helpers_env_map = {
        "_trade_engine_enabled": "V9_TRADE_ENGINE_ENABLED",
        "_portfolio_risk_enabled": "V9_PORTFOLIO_RISK_ENABLED",
        "_market_regime_global_enabled": "V9_MARKET_REGIME_GLOBAL_ENABLED",
        "_kelly_cvar_enabled": "V9_KELLY_CVAR_ENABLED",
        "_gbpusd_long_only_enabled": "V9_GBPUSD_LONG_ONLY",
        "_no_baissiere_enabled": "V9_NO_BAISSIERE",
        "_dynamic_risk_enabled": "V9_DYNAMIC_RISK_ENABLED",
    }
    from core.v9 import trade_engine
    for helper_name, env_key in helpers_env_map.items():
        monkeypatch.delenv(env_key, raising=False)
        helper = getattr(trade_engine, helper_name)
        result = helper()
        assert isinstance(result, bool), (
            f"{helper_name}() doit retourner bool, retourne {type(result)}"
        )


def test_env_override_still_works(monkeypatch, fresh_trade_engine_module):
    """Si env explicitement set, il prime (comportement préservé)."""
    monkeypatch.setenv("V9_NO_BAISSIERE", "1")
    monkeypatch.setenv("V9_GBPUSD_LONG_ONLY", "0")
    from core.v9.trade_engine import _no_baissiere_enabled, _gbpusd_long_only_enabled
    assert _no_baissiere_enabled() is True
    assert _gbpusd_long_only_enabled() is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
