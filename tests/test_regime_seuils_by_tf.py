"""test_regime_seuils_by_tf.py — Régression motion CEO #10 §5 (2026-07-20).

Vérifie que :
  1. get_regime_seuils_for_tf() retourne les bons seuils par TF
  2. Override env fonctionne (REGIME_SEUIL_PALIER_M5=1.5 → 1.5)
  3. Fallback legacy pour TF inconnu
  4. D1.enabled = False (PALIER désactivé motion CEO #10 §4)

Doctrine : R7 (tests verts), R2 (ne modifie pas le détecteur runtime)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def test_default_seuils_by_tf():
    """Chaque TF connu a un seuil par défaut issu de l'audit Opus."""
    from core.v9.config import (
        REGIME_SEUILS_BY_TF, get_regime_seuils_for_tf,
    )
    # M5 : SEUIL_PALIER=0.9, N_MIN=2
    palier, cassure, nmin, rejet, enabled = get_regime_seuils_for_tf("M5")
    assert palier == 0.9
    assert cassure == 2.0
    assert nmin == 2
    assert rejet == 8.0
    assert enabled is True
    # Cohérence avec REGIME_SEUILS_BY_TF
    assert REGIME_SEUILS_BY_TF["M5"] == (0.9, 2.0, 2, 8.0, True)


def test_h4_override():
    """H4 a son N_MIN=1 selon l'audit Opus (override du 16/07 confirmé)."""
    from core.v9.config import get_regime_seuils_for_tf
    _, _, nmin, _, _ = get_regime_seuils_for_tf("H4")
    assert nmin == 1


def test_d1_palier_disabled():
    """D1 a PALIER désactivé (motion CEO #10 §4 : P50=0.02 → 72% faux)."""
    from core.v9.config import get_regime_seuils_for_tf
    palier, cassure, nmin, rejet, enabled = get_regime_seuils_for_tf("D1")
    assert enabled is False
    assert palier == 0.5
    assert cassure == 1.0


def test_env_override(monkeypatch):
    """Override env par TF (live tuning motion CEO §5)."""
    monkeypatch.setenv("REGIME_SEUIL_PALIER_M5", "1.5")
    monkeypatch.setenv("REGIME_N_MIN_M5", "1")
    from core.v9.config import get_regime_seuils_for_tf
    palier, cassure, nmin, rejet, enabled = get_regime_seuils_for_tf("M5")
    assert palier == 1.5
    assert nmin == 1
    # cassure/rejet restent ceux du dict
    assert cassure == 2.0
    assert rejet == 8.0
    assert enabled is True


def test_fallback_legacy_unknown_tf(monkeypatch):
    """TF inconnu → fallback sur les constantes globales legacy."""
    monkeypatch.delenv("REGIME_SEUIL_PALIER_XYZ", raising=False)
    from core.v9 import config
    palier, cassure, nmin, rejet, enabled = config.get_regime_seuils_for_tf("XYZ")
    assert palier == config.SEUIL_PALIER
    assert cassure == config.SEUIL_CASSURE
    assert nmin == config.REGIME_N_MIN
    assert rejet == config.SEUIL_REJET
    assert enabled is True


def test_env_disable_palier(monkeypatch):
    """Env REGIME_ENABLED_M5=0 désactive PALIER pour M5 (urgence live)."""
    monkeypatch.setenv("REGIME_ENABLED_M5", "0")
    from core.v9.config import get_regime_seuils_for_tf
    _, _, _, _, enabled = get_regime_seuils_for_tf("M5")
    assert enabled is False


def test_lowercase_timeframe():
    """TF en minuscule est normalisé en majuscule."""
    from core.v9.config import get_regime_seuils_for_tf
    p1, _, _, _, _ = get_regime_seuils_for_tf("m5")
    p2, _, _, _, _ = get_regime_seuils_for_tf("M5")
    assert p1 == p2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
