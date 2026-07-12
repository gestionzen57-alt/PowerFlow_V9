"""trader_mini_baseline.py — Baseline tabulaire V9-trader-mini (Brief Q1, 2026-07-12).

PÉRIMÈTRE : baseline tabulaire (régression logistique, 0 dépendance pip,
cohérent avec la doctrine stdlib-only du projet) sur le dataset exporté par
`scripts/v9_export_dataset.py`. Le brief impose de tester une baseline
tabulaire AVANT tout fine-tuning séquentiel — un modèle 4B fine-tuné n'a de
sens que si la baseline échoue (accuracy test < 60%) ou qu'un gain mesurable
est démontré.

R18 respectée : inférence 100% locale, stdlib only (pas de pip, pas de
réseau), jamais dans le chemin décisionnel direct — module d'analyse/
pondération uniquement (branché en Étape 3 si le gate est franchi).
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

# Champs à exclure explicitement : identifiants uniques (aucun pouvoir de
# généralisation) et champ texte libre `point_de_rupture_declencheur` (haute
# cardinalité, encodage source corrompu observé — mojibake sur accents).
EXCLUDE_KEYS = frozenset({
    "behavior_id", "scene_id", "exploitability_id", "window_id",
    "symbol", "point_de_rupture_declencheur",
})

MAX_CATEGORIES_PER_FIELD = 6
MIN_CATEGORY_CARDINALITY_FOR_TEXT_GUARD = 30


def flatten_features(record: dict) -> dict[str, Any]:
    """Aplati `features.context` + `metadata.timeframe`/`session_marche` en un
    seul dict de features candidates, IDs et texte libre exclus."""
    features = record.get("features", {})
    context = features.get("context", {}) or {}
    flat: dict[str, Any] = {
        k: v for k, v in context.items() if k not in EXCLUDE_KEYS
    }
    for k, v in features.items():
        if k in EXCLUDE_KEYS or k in ("context",):
            continue
        flat.setdefault(k, v)
    metadata = record.get("metadata", {}) or {}
    if "timeframe" in metadata:
        flat["timeframe"] = metadata["timeframe"]
    if "session_marche" in metadata:
        flat["session_marche"] = metadata["session_marche"]
    return flat


def _classify_field(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "boolean"  # champ toujours vide -> traité comme flag neutre
    if all(isinstance(v, bool) for v in non_null):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return "numeric"
    return "categorical"


def build_schema(records: list[dict]) -> dict[str, dict]:
    """Construit le schéma d'encodage à partir du SPLIT TRAIN uniquement
    (évite toute fuite val/test dans le choix des catégories)."""
    flats = [flatten_features(r) for r in records]
    all_keys: set[str] = set()
    for f in flats:
        all_keys.update(f.keys())

    schema: dict[str, dict] = {}
    for key in sorted(all_keys):
        values = [f.get(key) for f in flats]
        ftype = _classify_field(values)
        if ftype == "categorical":
            non_null_str = [str(v) for v in values if v is not None]
            cardinality = len(set(non_null_str))
            if cardinality > MIN_CATEGORY_CARDINALITY_FOR_TEXT_GUARD:
                # Cardinalité trop élevée pour un one-hot raisonnable (texte
                # libre non détecté par le nom de champ) -> champ ignoré.
                continue
            freq: dict[str, int] = {}
            for v in non_null_str:
                freq[v] = freq.get(v, 0) + 1
            top = sorted(freq, key=lambda k: (-freq[k], k))[:MAX_CATEGORIES_PER_FIELD]
            schema[key] = {"type": "categorical", "categories": top}
        else:
            schema[key] = {"type": ftype}
    return schema


def schema_feature_names(schema: dict[str, dict]) -> list[str]:
    names: list[str] = []
    for key in sorted(schema):
        spec = schema[key]
        if spec["type"] == "categorical":
            for cat in spec["categories"]:
                names.append(f"{key}={cat}")
            names.append(f"{key}=OTHER")
            names.append(f"{key}=NONE")
        else:
            names.append(key)
    return names


def encode_record(record: dict, schema: dict[str, dict]) -> list[float]:
    flat = flatten_features(record)
    vec: list[float] = []
    for key in sorted(schema):
        spec = schema[key]
        val = flat.get(key)
        if spec["type"] == "boolean":
            vec.append(0.5 if val is None else (1.0 if val else 0.0))
        elif spec["type"] == "numeric":
            vec.append(0.0 if val is None else float(val))
        else:
            cats = spec["categories"]
            one_hot = [0.0] * (len(cats) + 2)  # + OTHER + NONE
            if val is None:
                one_hot[-1] = 1.0
            else:
                sval = str(val)
                if sval in cats:
                    one_hot[cats.index(sval)] = 1.0
                else:
                    one_hot[-2] = 1.0
            vec.extend(one_hot)
    return vec


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class LogisticRegressionSGD:
    """Régression logistique, descente de gradient stochastique par
    échantillon, régularisation L2. 0 dépendance pip (stdlib only, R18)."""

    def __init__(self, n_features: int, lr: float = 0.05, l2: float = 1e-4,
                 epochs: int = 12, seed: int = 42) -> None:
        self.n_features = n_features
        self.lr = lr
        self.l2 = l2
        self.epochs = epochs
        self._rng = random.Random(seed)
        self.weights = [0.0] * n_features
        self.bias = 0.0

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0:
            ez = math.exp(-z)
            return 1.0 / (1.0 + ez)
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def _score(self, x: list[float]) -> float:
        z = self.bias
        w = self.weights
        for i, xi in enumerate(x):
            if xi:
                z += w[i] * xi
        return z

    def fit(self, X: list[list[float]], y: list[int]) -> None:
        n = len(X)
        indices = list(range(n))
        for _ in range(self.epochs):
            self._rng.shuffle(indices)
            for idx in indices:
                x = X[idx]
                target = y[idx]
                pred = self._sigmoid(self._score(x))
                error = pred - target
                w = self.weights
                for i, xi in enumerate(x):
                    if xi:
                        w[i] -= self.lr * (error * xi + self.l2 * w[i])
                self.bias -= self.lr * error

    def predict_proba(self, X: list[list[float]]) -> list[float]:
        return [self._sigmoid(self._score(x)) for x in X]

    def predict(self, X: list[list[float]], threshold: float = 0.5) -> list[int]:
        return [1 if p >= threshold else 0 for p in self.predict_proba(X)]


def majority_baseline_accuracy(y: list[int]) -> float:
    if not y:
        return 0.0
    n_pos = sum(y)
    majority_correct = max(n_pos, len(y) - n_pos)
    return majority_correct / len(y)


def evaluate(y_true: list[int], y_pred: list[int]) -> dict[str, Any]:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    n = len(y_true)
    accuracy = (tp + tn) / n if n else 0.0

    precision_win = tp / (tp + fp) if (tp + fp) else 0.0
    recall_win = tp / (tp + fn) if (tp + fn) else 0.0
    f1_win = (2 * precision_win * recall_win / (precision_win + recall_win)
              if (precision_win + recall_win) else 0.0)

    precision_loss = tn / (tn + fn) if (tn + fn) else 0.0
    recall_loss = tn / (tn + fp) if (tn + fp) else 0.0
    f1_loss = (2 * precision_loss * recall_loss / (precision_loss + recall_loss)
               if (precision_loss + recall_loss) else 0.0)

    balanced_accuracy = (recall_win + recall_loss) / 2

    return {
        "n": n,
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "win_class": {"precision": precision_win, "recall": recall_win, "f1": f1_win},
        "loss_class": {"precision": precision_loss, "recall": recall_loss, "f1": f1_loss},
        "majority_baseline_accuracy": majority_baseline_accuracy(y_true),
    }
