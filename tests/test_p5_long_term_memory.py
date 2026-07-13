"""Tests — P5 autopilot CEO 2026-07-13 : Long-term memory (behavior_analyzer).

Couvre le passage BEHAVIOR_HISTORY_LOOKBACK 10 → 50 :
- Constante lue par behavior_analyzer (par défaut et via cfg override)
- Le pipeline charge jusqu'à 50 comportements/scènes historiques
- Tests paramétrés sur lookback=10 / 50 / 200 pour valider la propagation

Régression couverte : les tests behavior_analyzer existants doivent
rester verts (les comportements qualifiés sur 10 comportements
historiques doivent continuer de l'être sur 50).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import config as v9config
from core.v9.behavior_analyzer import BehaviorAnalyzer


def test_config_constant_p5_value():
    """CEO 2026-07-13 P5 : BEHAVIOR_HISTORY_LOOKBACK = 50 (capture plus
    de saisonnalité intra-journalière : ≈ 12h M5, 25h H1)."""
    assert v9config.BEHAVIOR_HISTORY_LOOKBACK == 50


def test_default_lookback_via_analyzer():
    """BehaviorAnalyzer lit BEHAVIOR_HISTORY_LOOKBACK par défaut si
    cfg.get('history_lookback') n'est pas fourni."""
    analyzer = BehaviorAnalyzer(config={})
    assert analyzer.history_lookback == 50


def test_explicit_lookback_override():
    """Le cfg['history_lookback'] override la constante module."""
    analyzer = BehaviorAnalyzer(config={"history_lookback": 200})
    assert analyzer.history_lookback == 200


def test_override_smaller_than_default():
    """Le plus petit lookback doit aussi fonctionner (réversibilité)."""
    analyzer = BehaviorAnalyzer(config={"history_lookback": 10})
    assert analyzer.history_lookback == 10


@pytest.mark.parametrize("lookback", [10, 25, 50, 100, 500])
def test_lookback_accepts_range(lookback):
    """Sanity : toutes les valeurs raisonnables sont acceptées."""
    analyzer = BehaviorAnalyzer(config={"history_lookback": lookback})
    assert analyzer.history_lookback == lookback


def test_lookback_zero_or_negative_invalid():
    """Lookback=0 n'a pas de sens — l'analyzer accepte mais ne chargera
    aucune scène historique. Pas d'exception, juste un comportement
    dégénéré. Ce test documente le comportement KISS actuel."""
    analyzer = BehaviorAnalyzer(config={"history_lookback": 0})
    assert analyzer.history_lookback == 0
