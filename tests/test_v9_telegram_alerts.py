"""Tests pour v9_telegram_alerts.

2026-07-17 motion CEO « hedge fund mondial ».
"""
from __future__ import annotations

import pytest

from core.v9.v9_telegram_alerts import TelegramAlerter


def test_telegram_alerter_init() -> None:
    """Init : token + chat_id + cooldown_seconds."""
    alerter = TelegramAlerter(token="test:TOKEN", chat_id="12345", cooldown_seconds=60)
    assert alerter.token == "test:TOKEN"
    assert alerter.chat_id == "12345"
    assert alerter.cooldown_seconds == 60
    assert len(alerter.history) == 0


def test_telegram_alerter_alert_dd_protection() -> None:
    """alert_dd_protection envoie un message et l'enregistre."""
    alerter = TelegramAlerter(token="t", chat_id="c", cooldown_seconds=0)
    result = alerter.alert_dd_protection("halt_24h", 0.12)
    assert result is True
    assert len(alerter.history) == 1
    record = alerter.history[0]
    assert record.kind == "dd_protection"
    assert "halt_24h" in record.title


def test_telegram_alerter_alert_trade_milestone() -> None:
    """alert_trade_milestone détecte les paliers 100/500/1000/5000."""
    alerter = TelegramAlerter(token="t", chat_id="c", cooldown_seconds=0)
    # _is_milestone retourne le palier (int) si match, None sinon
    assert alerter._is_milestone(100) == 100
    assert alerter._is_milestone(500) == 500
    assert alerter._is_milestone(1000) == 1000
    assert alerter._is_milestone(5000) == 5000
    assert alerter._is_milestone(250) is None
    assert alerter._is_milestone(4750) is None
    result = alerter.alert_trade_milestone(1000, 500.0)
    assert result is True
    assert len(alerter.history) == 1


def test_telegram_alerter_alert_drawdown() -> None:
    """alert_drawdown envoie si DD > seuil (paliers 50/100/200/500 pips)."""
    alerter = TelegramAlerter(token="t", chat_id="c", cooldown_seconds=0)
    # DD = 0 → pas d'alerte
    result = alerter.alert_drawdown(current_dd=0, peak_dd=200)
    assert result is False
    # DD = 30 → sous le 1er seuil (50) → pas d'alerte
    result = alerter.alert_drawdown(current_dd=30, peak_dd=200)
    assert result is False
    # DD = 50 → atteint le 1er seuil → alerte
    result = alerter.alert_drawdown(current_dd=50, peak_dd=200)
    assert result is True
    assert len(alerter.history) >= 1


def test_telegram_alerter_cooldown() -> None:
    """Cooldown : 2 alertes rapprochées → 1 seule envoyée."""
    alerter = TelegramAlerter(token="t", chat_id="c", cooldown_seconds=60)
    alerter.alert_dd_protection("halt_24h", 0.12)
    alerter.alert_dd_protection("halt_forever", 0.20)
    # Seule la 1ère doit être dans l'history (cooldown)
    assert len(alerter.history) == 1


def test_telegram_alerter_clear_history() -> None:
    """clear_history vide l'history."""
    alerter = TelegramAlerter(token="t", chat_id="c", cooldown_seconds=0)
    alerter.alert_dd_protection("halt_24h", 0.12)
    alerter.clear_history()
    assert len(alerter.history) == 0


def test_telegram_alerter_get_history() -> None:
    """get_history retourne l'history (liste sérialisable)."""
    alerter = TelegramAlerter(token="t", chat_id="c", cooldown_seconds=0)
    alerter.alert_trade_milestone(100, 50.0)
    h = alerter.get_history()
    assert len(h) == 1
    # get_history retourne des dicts sérialisables
    if isinstance(h[0], dict):
        # kind peut être "milestone" ou "trade_milestone" selon version
        assert h[0]["kind"] in ("milestone", "trade_milestone")
    else:
        assert h[0].kind in ("milestone", "trade_milestone")


def test_telegram_alerter_live_mode_off_by_default() -> None:
    """live_mode=False par défaut → dry mode."""
    alerter = TelegramAlerter(token="t", chat_id="c")
    assert alerter.live_mode is False
    # dry mode : pas d'envoi réel, mais history enregistrée
    alerter.alert_dd_protection("halt_24h", 0.12)
    assert len(alerter.history) == 1


def test_telegram_alerter_live_mode_explicit() -> None:
    """live_mode=True active l'envoi réel (échoue avec token fake)."""
    alerter = TelegramAlerter(
        token="t", chat_id="c", cooldown_seconds=0, live_mode=True,
    )
    assert alerter.live_mode is True