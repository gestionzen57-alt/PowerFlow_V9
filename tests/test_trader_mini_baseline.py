"""Tests — core/v9/trader_mini_baseline.py (Brief Q1, 2026-07-12).

Baseline tabulaire stdlib-only (régression logistique) pour V9-trader-mini.
Couvre : encodage de features, schéma (train-only, garde-fou cardinalité),
apprentissage sur données synthétiques séparables, métriques d'évaluation.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.v9.trader_mini_baseline import (
    LogisticRegressionSGD,
    build_schema,
    encode_record,
    evaluate,
    flatten_features,
    load_jsonl,
    majority_baseline_accuracy,
    schema_feature_names,
)


def _record(label: int, **context_overrides) -> dict:
    context = {
        "qualification": "bascule",
        "confiance_qualification": 80,
        "bascule_detectee": True,
        "heure_utc": 8,
        "point_de_rupture_declencheur": "texte libre corrompu �",
        "behavior_id": "beh_xyz",
    }
    context.update(context_overrides)
    return {
        "features": {"context": context, "scene_id": "scene1", "window_id": "win1"},
        "metadata": {"timeframe": "M15", "session_marche": "london"},
        "label": label,
        "pips": 5.0 if label else -10.0,
    }


def test_flatten_features_excludes_ids_and_freetext():
    rec = _record(1)
    flat = flatten_features(rec)
    assert "behavior_id" not in flat
    assert "scene_id" not in flat
    assert "window_id" not in flat
    assert "point_de_rupture_declencheur" not in flat
    assert flat["timeframe"] == "M15"
    assert flat["session_marche"] == "london"
    assert flat["qualification"] == "bascule"


def test_build_schema_classifies_field_types():
    records = [_record(1), _record(0), _record(1, heure_utc=14)]
    schema = build_schema(records)
    assert schema["confiance_qualification"]["type"] == "numeric"
    assert schema["bascule_detectee"]["type"] == "boolean"
    assert schema["qualification"]["type"] == "categorical"
    assert "point_de_rupture_declencheur" not in schema


def test_build_schema_high_cardinality_categorical_excluded():
    # 40 valeurs distinctes -> au-dessus du garde-fou (30), champ ignoré
    # (protège contre un champ texte non détecté par son nom).
    records = [_record(1, some_free_text=f"unique_value_{i}") for i in range(40)]
    schema = build_schema(records)
    assert "some_free_text" not in schema


def test_build_schema_categorical_caps_at_max_categories():
    records = [_record(1, qualification=f"q{i % 10}") for i in range(50)]
    schema = build_schema(records)
    assert len(schema["qualification"]["categories"]) <= 6


def test_encode_record_vector_length_matches_schema_feature_names():
    records = [_record(1), _record(0)]
    schema = build_schema(records)
    names = schema_feature_names(schema)
    vec = encode_record(records[0], schema)
    assert len(vec) == len(names)


def test_encode_record_handles_missing_and_none_values():
    records = [_record(1), _record(0, heure_utc=None)]
    schema = build_schema(records)
    # Un record sans le champ du tout doit s'encoder sans lever.
    minimal = {"features": {"context": {}}, "metadata": {}}
    vec = encode_record(minimal, schema)
    assert len(vec) == len(schema_feature_names(schema))
    assert all(isinstance(v, float) for v in vec)


def test_load_jsonl_roundtrip(tmp_path: Path):
    records = [_record(1), _record(0)]
    p = tmp_path / "sample.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    loaded = load_jsonl(p)
    assert len(loaded) == 2
    assert loaded[0]["label"] == 1


def test_logistic_regression_learns_linearly_separable_pattern():
    # Un seul feature numérique parfaitement corrélé au label -> le modèle
    # doit apprendre à séparer avec une accuracy quasi parfaite.
    X = [[float(i)] for i in range(-20, 20)]
    y = [1 if x[0] > 0 else 0 for x in X]
    model = LogisticRegressionSGD(n_features=1, lr=0.1, epochs=50, seed=1)
    model.fit(X, y)
    preds = model.predict(X)
    accuracy = sum(1 for p, t in zip(preds, y) if p == t) / len(y)
    assert accuracy >= 0.95


def test_majority_baseline_accuracy():
    y = [1, 1, 1, 1, 0]
    assert majority_baseline_accuracy(y) == 0.8


def test_evaluate_confusion_matrix_and_metrics():
    y_true = [1, 1, 0, 0, 1]
    y_pred = [1, 0, 0, 1, 1]
    result = evaluate(y_true, y_pred)
    cm = result["confusion_matrix"]
    assert cm["tp"] == 2
    assert cm["tn"] == 1
    assert cm["fp"] == 1
    assert cm["fn"] == 1
    assert result["accuracy"] == 3 / 5
    assert 0.0 <= result["balanced_accuracy"] <= 1.0
    assert result["majority_baseline_accuracy"] == majority_baseline_accuracy(y_true)


def test_evaluate_empty_input_never_raises():
    result = evaluate([], [])
    assert result["n"] == 0
    assert result["accuracy"] == 0.0
