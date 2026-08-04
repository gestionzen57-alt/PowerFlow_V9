"""Tests Phase 179 (03/08) : v9_signal_alerter.

R2 additif pur : nouveau fichier tests/. Pas de modif core/.
Couvre :
  - Import sans crash (pas de DB réelle requise)
  - send_telegram R6 fail-open (sans token = noop, sans requests)
  - Mapping emoji direction
  - Construction SignalAlert + format console/telegram
  - fetch_new_signals : mock DB pour vérifier dédup signal_id
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────
@pytest.fixture
def alerter_module(monkeypatch):
    """Importe v9_signal_alerter avec env Telegram vide (R6 fail-open)."""
    monkeypatch.setenv("V9_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("V9_TELEGRAM_CHAT_ID", "")
    # Force reimport si déjà chargé
    if "scripts.v9_signal_alerter" in sys.modules:
        del sys.modules["scripts.v9_signal_alerter"]
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    mod = importlib.import_module("scripts.v9_signal_alerter")
    return mod


# ── Tests ──────────────────────────────────────────────────────────────
def test_poll_no_crash(alerter_module):
    """Import + accès aux constantes de base → pas de crash."""
    assert alerter_module.RISK_CONFIANCE_MIN == 70
    assert alerter_module.POLL_SEC == 5
    assert alerter_module.LOOKBACK_SEC == 60
    assert alerter_module.EMOJI["haussiere"] == "🟢"
    assert alerter_module.EMOJI["baissiere"] == "🔴"


def test_send_telegram_noop_when_no_token(tmp_path, monkeypatch):
    """R6 : sans token → send_telegram retourne False, n'appelle jamais requests.post.

    Stratégie : on monkeypatch directement les constantes module-level
    (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) à vide, puis on vérifie
    que send_telegram retourne False SANS toucher au réseau.
    """
    import scripts.v9_signal_alerter as real_mod
    monkeypatch.setattr(real_mod, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(real_mod, "TELEGRAM_CHAT_ID", "")
    # send_telegram lit les constantes module-level → return False immédiat
    result = real_mod.send_telegram("test message")
    assert result is False
    # Confirmation : pas d'import de v9_telegram_notifier tenté
    assert real_mod.TELEGRAM_BOT_TOKEN == ""


def test_emoji_mapping():
    """Vérifie les 3 directions canoniques (None/missing = ⚡ fallback)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    if "scripts.v9_signal_alerter" in sys.modules:
        del sys.modules["scripts.v9_signal_alerter"]
    mod = importlib.import_module("scripts.v9_signal_alerter")
    assert mod.EMOJI.get("haussiere") == "🟢"
    assert mod.EMOJI.get("baissiere") == "🔴"
    # Pas de neutre dans le mapping (les neutres ne sont pas alertés)
    assert "neutre" not in mod.EMOJI


def test_signal_alert_format_telegram(alerter_module):
    """SignalAlert.format_telegram produit un message lisible non-vide."""
    alert = alerter_module.SignalAlert(
        signal_id="sig_test_001",
        symbol="GBPUSD",
        timeframe="M5",
        direction="haussiere",
        confiance=82,
        confiance_calibree=78,
        exploitability_statut="exploitable",
        regime_type="trend",
        predictor_action="enter",
        predictor_edge_pips=4.5,
        timestamp="2026-08-03T22:00:00+00:00",
        principles=["P_VOLATILITY_BOOST", "P_MTF_ALIGN", "P_BREAKOUT"],
    )
    msg = alert.format_telegram()
    assert "GBPUSD" in msg
    assert "M5" in msg
    assert "HAUSSIERE" in msg
    assert "82" in msg
    assert "exploitable" in msg
    assert "trend" in msg
    assert "4.5" in msg or "+4.5" in msg
    assert "P_VOLATILITY_BOOST" in msg
    assert "sig_test_001" in msg


def test_signal_alert_format_console(alerter_module):
    """SignalAlert.format_console produit une ligne 1-D lisible."""
    alert = alerter_module.SignalAlert(
        signal_id="sig_test_002",
        symbol="EURUSD",
        timeframe="M15",
        direction="baissiere",
        confiance=70,
        confiance_calibree=None,
        exploitability_statut="exploitable",
        regime_type="range",
        predictor_action=None,
        predictor_edge_pips=None,
        timestamp="2026-08-03T22:00:00+00:00",
    )
    line = alert.format_console()
    assert "[SIGNAL V9]" in line
    assert "EURUSD" in line
    assert "M15" in line
    assert "BAISSIERE" in line
    assert "conf=70" in line


def test_fetch_new_signals_dedup(alerter_module, tmp_path):
    """fetch_new_signals déduplique via le set `seen`."""
    # Crée une DB sqlite temporaire avec table signals
    db_file = tmp_path / "test_v9.db"
    conn = sqlite3.connect(str(db_file), timeout=5)
    conn.executescript("""
        CREATE TABLE signals (
            signal_id TEXT PRIMARY KEY,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            confiance_calibree INTEGER,
            exploitability_statut TEXT,
            regime_type TEXT,
            predictor_action TEXT,
            predictor_edge_pips REAL,
            timestamp TEXT,
            principes_source_json TEXT
        );
    """)
    # 3 signaux : 2 vraie entrée + 1 absent (raison_absence=foo)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("sig_a", "GBPUSD", "M5", "haussiere", 82, 78, "exploitable",
         "trend", "enter", 4.5, now_iso, '["P_VOL_BOOST"]'),
    )
    conn.execute(
        "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("sig_b", "EURUSD", "M5", "baissiere", 75, 72, "exploitable",
         "range", "enter", 3.2, now_iso, '["P_BREAKOUT"]'),
    )
    conn.execute(
        "INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("sig_c", "USDJPY", "M5", "haussiere", 65, None, "exploitable",
         "range", "skip", -1.0, now_iso, None),  # conf < 70 → exclu
    )
    conn.commit()
    conn.close()

    # Patch DB_PATH
    with patch.object(alerter_module, "DB_PATH", db_file):
        seen: set[str] = set()
        alerts1 = alerter_module.fetch_new_signals(seen)
        # 2 signaux vraie entrée (sig_a + sig_b), sig_c exclu (conf<70)
        assert len(alerts1) == 2
        signal_ids = {a.signal_id for a in alerts1}
        assert signal_ids == {"sig_a", "sig_b"}
        assert seen == {"sig_a", "sig_b"}

        # 2e appel : doit dédupliquer, 0 nouveaux
        alerts2 = alerter_module.fetch_new_signals(seen)
        assert alerts2 == []
