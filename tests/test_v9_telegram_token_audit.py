"""tests/test_v9_telegram_token_audit.py — Tests de l'audit tokens Telegram.

Doctrine : R8 (traçabilité), R22 (audit lecture seule).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_telegram_token_audit import (  # noqa: E402
    TOKEN_PATTERN,
    _redact,
    _scan_local,
)


def test_token_pattern_format():
    """Pattern Telegram bot token : 8-10 chiffres : 35 chars base64."""
    valid = "8790798269:AAETtvTwuJrxcF_LYDRKcJQrfgBZcf8ZDXE"
    invalid_short = "123:abc"
    invalid_nodigit = "abcdefghij:Axxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    assert TOKEN_PATTERN.search(valid) is not None
    assert TOKEN_PATTERN.search(invalid_short) is None
    assert TOKEN_PATTERN.search(invalid_nodigit) is None


def test_redact_keeps_structure():
    """La rédaction préserve la structure mais masque le token."""
    text = "TELEGRAM_BOT_TOKEN=8790798269:AAETtvTwuJrxcF_LYDRKcJQrfgBZcf8ZDXE"
    redacted = _redact(text)
    assert "8790798269" not in redacted
    assert "REDACTED" in redacted
    assert "TELEGRAM_BOT_TOKEN=" in redacted


def test_redact_no_token_unchanged():
    """Texte sans token → inchangé."""
    text = "TELEGRAM_BOT_TOKEN=TON_TOKEN_ICI"
    assert _redact(text) == text


def test_scan_local_returns_findings():
    """Scan local retourne la liste des fichiers vérifiés."""
    findings = _scan_local()
    assert isinstance(findings, list)
    assert len(findings) >= 4  # .env, telegram.json, .bak.20260717, .example
    paths = [f["path"] for f in findings]
    assert any(".env" in p for p in paths)
    assert any("telegram.json" in p for p in paths)
    # Chaque finding a 'exists' et 'tokens' (ou 'error')
    for f in findings:
        assert "exists" in f
