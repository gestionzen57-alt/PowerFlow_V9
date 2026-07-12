#!/usr/bin/env python3
"""v9_train_trader_mini_baseline.py — Entraîne + évalue la baseline
tabulaire V9-trader-mini (Brief Q1, 2026-07-12).

Usage :
    python scripts/v9_train_trader_mini_baseline.py \
        --dataset data/datasets/v9_trader_mini \
        --report docs/reports/V9_TRADER_MINI_BASELINE_20260712.json

GATE (brief) : accuracy test < 60% -> pas d'intégration Arbiter, rapport
docs/reports/ expliquant pourquoi (ce script écrit toujours le rapport,
l'intégration reste une décision séparée, voir core/v9/trader_mini_weigher.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.trader_mini_baseline import (  # noqa: E402
    LogisticRegressionSGD, build_schema, encode_record, evaluate, load_jsonl,
    schema_feature_names,
)

ACCURACY_GATE = 0.60


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Baseline tabulaire V9-trader-mini (Brief Q1)")
    parser.add_argument("--dataset", type=Path, default=ROOT_DIR / "data" / "datasets" / "v9_trader_mini")
    parser.add_argument("--report", type=Path,
                         default=ROOT_DIR / "docs" / "reports" / "V9_TRADER_MINI_BASELINE_20260712.json")
    parser.add_argument("--model-out", type=Path,
                         default=ROOT_DIR / "core" / "v9" / "models" / "trader_mini_baseline_v1.json")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--lr", type=float, default=0.05)
    args = parser.parse_args(argv)

    train_recs = load_jsonl(args.dataset / "train.jsonl")
    val_recs = load_jsonl(args.dataset / "val.jsonl")
    test_recs = load_jsonl(args.dataset / "test.jsonl")
    print(f"[..] train={len(train_recs)} val={len(val_recs)} test={len(test_recs)}")

    schema = build_schema(train_recs)
    feature_names = schema_feature_names(schema)
    print(f"[..] schema: {len(schema)} champs bruts -> {len(feature_names)} dimensions encodées")

    X_train = [encode_record(r, schema) for r in train_recs]
    y_train = [int(r["label"]) for r in train_recs]
    X_val = [encode_record(r, schema) for r in val_recs]
    y_val = [int(r["label"]) for r in val_recs]
    X_test = [encode_record(r, schema) for r in test_recs]
    y_test = [int(r["label"]) for r in test_recs]

    model = LogisticRegressionSGD(n_features=len(feature_names), lr=args.lr, epochs=args.epochs)
    model.fit(X_train, y_train)

    val_pred = model.predict(X_val)
    test_pred = model.predict(X_test)
    val_metrics = evaluate(y_val, val_pred)
    test_metrics = evaluate(y_test, test_pred)

    gate_passed = test_metrics["accuracy"] >= ACCURACY_GATE

    report = {
        "brief": "Q1",
        "date": "2026-07-12",
        "model": "LogisticRegressionSGD (stdlib, core/v9/trader_mini_baseline.py)",
        "dataset_dir": str(args.dataset),
        "n_features_raw": len(schema),
        "n_features_encoded": len(feature_names),
        "hyperparams": {"epochs": args.epochs, "lr": args.lr, "l2": 1e-4},
        "val_metrics": val_metrics,
        "test_metrics": test_metrics,
        "accuracy_gate": ACCURACY_GATE,
        "gate_passed": gate_passed,
        "note_accuracy_gate": (
            "La base rate (toujours predire WIN) est deja a "
            f"{test_metrics['majority_baseline_accuracy']:.1%} sur ce dataset "
            "desequilibre (~88.5% WIN global) - le seuil de gate 60% du brief est "
            "peu discriminant en accuracy brute. balanced_accuracy et f1 loss_class "
            "sont les criteres qualitatifs retenus pour juger d'une valeur ajoutee "
            "reelle au-dela du taux de base."
        ),
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if gate_passed:
        model_artifact = {
            "version": "trader_mini_baseline_v1",
            "trained": "2026-07-12",
            "brief": "Q1",
            "model_type": "LogisticRegressionSGD",
            "feature_names": feature_names,
            "schema": schema,
            "weights": model.weights,
            "bias": model.bias,
            "test_metrics": test_metrics,
        }
        args.model_out.parent.mkdir(parents=True, exist_ok=True)
        args.model_out.write_text(json.dumps(model_artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] modèle : {args.model_out}")

    print(f"[OK] val accuracy={val_metrics['accuracy']:.3f} balanced_acc={val_metrics['balanced_accuracy']:.3f}")
    print(f"[OK] test accuracy={test_metrics['accuracy']:.3f} balanced_acc={test_metrics['balanced_accuracy']:.3f} "
          f"f1_loss={test_metrics['loss_class']['f1']:.3f}")
    print(f"[OK] majority baseline (test) = {test_metrics['majority_baseline_accuracy']:.3f}")
    print(f"[{'OK' if gate_passed else 'GATE FAIL'}] gate accuracy>={ACCURACY_GATE:.0%}: "
          f"{'PASSED' if gate_passed else 'NOT PASSED'}")
    print(f"[OK] rapport : {args.report}")

    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
