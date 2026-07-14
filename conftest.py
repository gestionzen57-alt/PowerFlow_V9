"""conftest.py — racine pytest.

Charge config/v9_kill_switches.env (gitignored) au demarrage de pytest
pour que les tests voient l'etat runtime des kill switches
(V9_TRADER_MINI_ENABLED, V9_AUTO_CALIBRATOR_ENABLED, etc.).

Origine : motion CEO 2026-07-14, commit 5049d48 a adapte les tests pour
l'etat ON par defaut (Brief Q1 + Q2 actifs). Sans ce conftest, pytest
ne charge pas le .env et les tests echouent (env vide).

Doctrine :
- R8 : additif, pas de modif core/v9/* ou des tests existants.
- R18 : pas de LLM / reseau.
- R25' : les kill switches restent OFF par defaut dans le code ;
  ce conftest ne fait que poser l'env var au niveau du process pytest.

Si le .env est absent (machine sans activation, tests sur CI, etc.),
le conftest ne fait rien (defaut OFF, comportement code original).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / "config" / "v9_kill_switches.env"


def _load_kill_switches() -> int:
    """Charge KEY=VALUE depuis config/v9_kill_switches.env dans os.environ.

    Ignore les lignes vides, les commentaires (#) et les espaces autour
    du =. Retourne le nombre de variables chargees.
    """
    if not ENV_FILE.exists():
        return 0
    loaded = 0
    with ENV_FILE.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            os.environ[key] = value
            loaded += 1
    return loaded


# Chargement immediat a l'import du conftest (donc au demarrage pytest).
_LOADED = _load_kill_switches()
if _LOADED:
    print(
        f"[conftest] {_LOADED} kill switch(es) charge(s) depuis {ENV_FILE}",
        file=sys.stderr,
    )
