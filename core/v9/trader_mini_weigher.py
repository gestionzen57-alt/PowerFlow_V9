"""trader_mini_weigher.py — Pondération Arbiter par la baseline V9-trader-mini
(Brief Q1, 2026-07-12).

Même pattern que PrincipleScorer/Brief O2 (core/v9/principle_scorer.py +
son intégration dans core/v9/arbiter.py) : module de PONDÉRATION, jamais
décisionnaire. Lecture seule, inférence 100% locale (stdlib, aucun réseau,
R18), jamais de blocage — toute erreur retombe sur un multiplicateur neutre
(règle 6).

Le modèle (régression logistique stdlib, `core/v9/trader_mini_baseline.py`)
a été entraîné sur 6595 décisions (Brief Q1) : accuracy test 85.9%,
balanced_accuracy 62.1%, f1 classe LOSS 0.33 — signal réel mais modeste
sur la classe minoritaire (perdants). Bornes du multiplicateur volontairement
BEAUCOUP plus resserrées que celles du PrincipleScorer (O2, [0.5,1.5]) pour
refléter honnêtement cette force de signal plus faible.

Kill switch : V9_TRADER_MINI_ENABLED (défaut '0' = OFF — brief Q1 explicite,
inverse de la convention V9_ARBITER_SCORER_ENABLED qui est ON par défaut).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from core.v9.trader_mini_baseline import encode_record

TRADER_MINI_ENABLED_ENV = "V9_TRADER_MINI_ENABLED"

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "trader_mini_baseline_v1.json"

# Bornes dures — resserrées (signal faible, cf. docstring module).
TRADER_MINI_MULT_BOUNDS = (0.85, 1.05)
TRADER_MINI_MULT_LOSS = 0.85   # proba(win) basse -> réduction prudente
TRADER_MINI_MULT_WIN = 1.05    # proba(win) haute -> boost prudent
TRADER_MINI_MULT_NEUTRAL = 1.0

# Seuils de décision sur proba(win) — zone centrale = neutre (le modèle
# n'est pas assez discriminant pour trancher, cf. balanced_accuracy 62%).
PROBA_LOSS_THRESHOLD = 0.35
PROBA_WIN_THRESHOLD = 0.92


def trader_mini_enabled() -> bool:
    """Kill switch V9_TRADER_MINI_ENABLED (défaut '0' = OFF)."""
    return os.environ.get(TRADER_MINI_ENABLED_ENV, "0") == "1"


class TraderMiniWeigher:
    """Charge le modèle baseline (une fois) et calcule un multiplicateur de
    confiance par snapshot, sur le même modèle que PrincipleScorer."""

    def __init__(self, model_path: Path | str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self._model: dict[str, Any] | None = None
        self._load_error = False
        self._try_load()

    def _try_load(self) -> None:
        try:
            if not self.model_path.exists():
                self._load_error = True
                return
            self._model = json.loads(self.model_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            self._load_error = True
            self._model = None

    @staticmethod
    def _sigmoid(z: float) -> float:
        import math
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def _predict_proba_win(self, record_like: dict) -> float | None:
        if self._model is None:
            return None
        schema = self._model["schema"]
        weights = self._model["weights"]
        bias = self._model["bias"]
        try:
            x = encode_record(record_like, schema)
        except Exception:
            return None
        if len(x) != len(weights):
            return None
        z = bias
        for wi, xi in zip(weights, x):
            if xi:
                z += wi * xi
        return self._sigmoid(z)

    def compute_multiplier(
        self, snapshot_id: str, conn: sqlite3.Connection,
        principle_engine: Any = None,
    ) -> tuple[float, str]:
        """Calcule (multiplicateur, basis) pour un snapshot.

        basis in {'disabled', 'no_model', 'predicted_loss', 'predicted_win',
        'neutral', 'context_unavailable'}. Ne lève jamais — toute erreur
        retombe sur neutre (règle 6).
        """
        if not trader_mini_enabled():
            return TRADER_MINI_MULT_NEUTRAL, "disabled"
        if self._model is None or self._load_error:
            return TRADER_MINI_MULT_NEUTRAL, "no_model"

        try:
            if principle_engine is None:
                from core.v9.principle_engine import PrincipleEngine
                principle_engine = PrincipleEngine(db_path=Path(conn.execute("PRAGMA database_list").fetchone()[2]))
            features = principle_engine._load_shared_context(conn, snapshot_id)
        except Exception:
            return TRADER_MINI_MULT_NEUTRAL, "context_unavailable"

        record_like = {"features": features, "metadata": {}}
        nested_context = features.get("context") if isinstance(features, dict) else None
        if isinstance(nested_context, dict):
            record_like["metadata"]["session_marche"] = nested_context.get("session_marche")

        proba_win = self._predict_proba_win(record_like)
        if proba_win is None:
            return TRADER_MINI_MULT_NEUTRAL, "context_unavailable"

        lo, hi = TRADER_MINI_MULT_BOUNDS
        if proba_win < PROBA_LOSS_THRESHOLD:
            return max(lo, min(hi, TRADER_MINI_MULT_LOSS)), "predicted_loss"
        if proba_win > PROBA_WIN_THRESHOLD:
            return max(lo, min(hi, TRADER_MINI_MULT_WIN)), "predicted_win"
        return TRADER_MINI_MULT_NEUTRAL, "neutral"
