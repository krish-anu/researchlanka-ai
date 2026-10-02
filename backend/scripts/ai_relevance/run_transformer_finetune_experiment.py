#!/usr/bin/env python3
"""Fine-tune a Hugging Face transformer on the AI relevance human split.

This is an experimental runner. It uses the same selection directory produced by
run_validated_human_model_selection.py, trains on selection_training_dataset.csv,
selects by validation macro F1, and reports once on frozen_human_test_set.csv.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.embedding_experiment import (  # noqa: E402
    DEFAULT_SELECTION_DIR,
    LABELS,
    load_experiment_frames,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/models/ai_relevance/transformer_finetune_experiment"


@dataclass(frozen=True)
class Config:
    selection_dir: Path = DEFAULT_SELECTION_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    model_name: str = "allenai/scibert_scivocab_uncased"
    epochs: float = 3.0
    learning_rate: float = 2e-5
    batch_size: int = 8
    max_length: int = 256
    weight_decay: float = 0.01
    random_state: int = 42


def load_transformer_dependencies() -> dict[str, Any]:
    try:
        import torch
        from torch.utils.data import Dataset
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            DataCollatorWithPadding,
            Trainer,
            TrainingArguments,
            set_seed,
        )
    except Exception as exc:
        raise RuntimeError(
            "Transformer fine-tuning requires optional packages: torch and "
            "transformers. Install them in the backend environment, then rerun "
            "this script."
        ) from exc
    return {
        "torch": torch,
        "Dataset": Dataset,
        "AutoModelForSequenceClassification": AutoModelForSequenceClassification,
        "AutoTokenizer": AutoTokenizer,
        "DataCollatorWithPadding": DataCollatorWithPadding,
        "Trainer": Trainer,
        "TrainingArguments": TrainingArguments,
        "set_seed": set_seed,
    }


def labels_to_ids(labels: pd.Series) -> list[int]:
    return labels.map({"NON_AI": 0, "AI": 1}).astype(int).tolist()


def ids_to_labels(values: np.ndarray) -> list[str]:
    return ["AI" if int(value) == 1 else "NON_AI" for value in values]


def evaluate(labels: pd.Series, predictions: list[str]) -> dict[str, Any]:
    return {
        "accuracy": float(accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(labels, predictions, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(labels, predictions, average="weighted", zero_division=0)),
        "classification_report": classification_report(
            labels,
            predictions,
            labels=list(LABELS),
            zero_division=0,
            output_dict=True,
        ),
        "confusion_matrix_labels": list(LABELS),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=list(LABELS)).tolist(),
    }


def make_dataset_class(dataset_base: type[Any]) -> type[Any]:
    class TextDataset(dataset_base):  # type: ignore[misc, valid-type]
        def __init__(self, encodings: dict[str, Any], labels: list[int]) -> None:
            self.encodings = encodings
            self.labels = labels

        def __len__(self) -> int:
            return len(self.labels)

        def __getitem__(self, index: int) -> dict[str, Any]:
            item = {
                key: value[index]
                for key, value in self.encodings.items()
            }
            item["labels"] = self.labels[index]
            return item

    return TextDataset


def run(config: Config) -> dict[str, Any]:
    deps = load_transformer_dependencies()
    deps["set_seed"](config.random_state)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    train, validation, test = load_experiment_frames(config.selection_dir)
    tokenizer = deps["AutoTokenizer"].from_pretrained(config.model_name)
    model = deps["AutoModelForSequenceClassification"].from_pretrained(
        config.model_name,
        num_labels=2,
        id2label={0: "NON_AI", 1: "AI"},
        label2id={"NON_AI": 0, "AI": 1},
    )

    def tokenize(frame: pd.DataFrame) -> dict[str, Any]:
        return tokenizer(
            frame["text"].astype(str).tolist(),
            truncation=True,
            max_length=config.max_length,
        )

    dataset_class = make_dataset_class(deps["Dataset"])
    train_dataset = dataset_class(tokenize(train), labels_to_ids(train["label"]))
    validation_dataset = dataset_class(tokenize(validation), labels_to_ids(validation["label"]))
    test_dataset = dataset_class(tokenize(test), labels_to_ids(test["label"]))
    data_collator = deps["DataCollatorWithPadding"](tokenizer=tokenizer)

    def compute_metrics(eval_prediction: Any) -> dict[str, float]:
        logits, label_ids = eval_prediction
        pred_ids = np.argmax(logits, axis=1)
        labels = ids_to_labels(np.asarray(label_ids))
        preds = ids_to_labels(pred_ids)
        return {
            "accuracy": float(accuracy_score(labels, preds)),
            "macro_f1": float(f1_score(labels, preds, average="macro", zero_division=0)),
            "ai_precision": float(
                classification_report(
                    labels,
                    preds,
                    labels=list(LABELS),
                    zero_division=0,
                    output_dict=True,
                )["AI"]["precision"]
            ),
        }

    training_kwargs: dict[str, Any] = {
        "output_dir": str(config.output_dir / "trainer"),
        "learning_rate": config.learning_rate,
        "per_device_train_batch_size": config.batch_size,
        "per_device_eval_batch_size": config.batch_size,
        "num_train_epochs": config.epochs,
        "weight_decay": config.weight_decay,
        "save_strategy": "epoch",
        "load_best_model_at_end": True,
        "metric_for_best_model": "macro_f1",
        "greater_is_better": True,
        "report_to": [],
        "seed": config.random_state,
    }
    training_signature = inspect.signature(deps["TrainingArguments"].__init__)
    if "evaluation_strategy" in training_signature.parameters:
        training_kwargs["evaluation_strategy"] = "epoch"
    else:
        training_kwargs["eval_strategy"] = "epoch"
    training_args = deps["TrainingArguments"](**training_kwargs)

    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": training_args,
        "train_dataset": train_dataset,
        "eval_dataset": validation_dataset,
        "data_collator": data_collator,
        "compute_metrics": compute_metrics,
    }
    trainer_signature = inspect.signature(deps["Trainer"].__init__)
    if "tokenizer" in trainer_signature.parameters:
        trainer_kwargs["tokenizer"] = tokenizer
    elif "processing_class" in trainer_signature.parameters:
        trainer_kwargs["processing_class"] = tokenizer
    trainer = deps["Trainer"](**trainer_kwargs)
    trainer.train()

    validation_output = trainer.predict(validation_dataset)
    validation_pred_ids = np.argmax(validation_output.predictions, axis=1)
    validation_predictions = ids_to_labels(validation_pred_ids)
    validation_metrics = evaluate(validation["label"], validation_predictions)

    test_output = trainer.predict(test_dataset)
    test_logits = np.asarray(test_output.predictions)
    test_pred_ids = np.argmax(test_logits, axis=1)
    test_predictions = ids_to_labels(test_pred_ids)
    test_scores = deps["torch"].softmax(
        deps["torch"].tensor(test_logits),
        dim=1,
    )[:, 1].numpy()
    test_metrics = evaluate(test["label"], test_predictions)

    model_dir = config.output_dir / "best_model"
    trainer.save_model(str(model_dir))
    tokenizer.save_pretrained(str(model_dir))

    predictions = test[
        [
            column
            for column in ("record_key", "label", "label_source", "title", "doi", "text")
            if column in test.columns
        ]
    ].copy()
    predictions["prediction"] = test_predictions
    predictions["ai_score"] = [f"{float(score):.6f}" for score in test_scores]
    predictions["correct"] = predictions["label"].eq(predictions["prediction"])
    predictions_path = config.output_dir / "transformer_frozen_test_predictions.csv"
    predictions.to_csv(predictions_path, index=False)

    report = test_metrics["classification_report"]
    comparison_path = config.output_dir / "transformer_comparison.csv"
    pd.DataFrame(
        [
            {
                "model_family": f"transformer_finetune:{config.model_name}",
                "frozen_test_accuracy": test_metrics["accuracy"],
                "frozen_test_macro_f1": test_metrics["macro_f1"],
                "ai_precision": report["AI"]["precision"],
                "ai_recall": report["AI"]["recall"],
                "non_ai_recall": report["NON_AI"]["recall"],
                "model_path": str(model_dir),
                "predictions_path": str(predictions_path),
            }
        ]
    ).to_csv(comparison_path, index=False)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "experiment_type": "transformer_finetune",
        "config": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
        "rows": {
            "train": int(len(train)),
            "validation": int(len(validation)),
            "frozen_test": int(len(test)),
        },
        "validation_metrics": validation_metrics,
        "frozen_test_metrics": test_metrics,
        "comparison_csv": str(comparison_path),
        "predictions_path": str(predictions_path),
        "model_path": str(model_dir),
    }
    summary_path = config.output_dir / "transformer_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    metrics_path = config.output_dir / "transformer_metrics.txt"
    metrics_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def render_text(summary: dict[str, Any]) -> str:
    test = summary["frozen_test_metrics"]
    report = test["classification_report"]
    return "\n".join(
        [
            "Transformer fine-tuning AI relevance experiment",
            "",
            f"model_name: {summary['config']['model_name']}",
            f"train_rows: {summary['rows']['train']}",
            f"validation_rows: {summary['rows']['validation']}",
            f"frozen_test_rows: {summary['rows']['frozen_test']}",
            "",
            f"frozen_test_accuracy: {test['accuracy']:.4f}",
            f"frozen_test_macro_f1: {test['macro_f1']:.4f}",
            f"frozen_test_ai_precision: {report['AI']['precision']:.4f}",
            f"frozen_test_ai_recall: {report['AI']['recall']:.4f}",
            f"frozen_test_non_ai_recall: {report['NON_AI']['recall']:.4f}",
            f"frozen_test_confusion_matrix_AI_NON_AI: {test['confusion_matrix']}",
            "",
            f"comparison_csv: {summary['comparison_csv']}",
            f"model_path: {summary['model_path']}",
        ]
    ) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-dir", type=Path, default=DEFAULT_SELECTION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default="allenai/scibert_scivocab_uncased")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run(
        Config(
            selection_dir=args.selection_dir,
            output_dir=args.output_dir,
            model_name=args.model_name,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            batch_size=args.batch_size,
            max_length=args.max_length,
            weight_decay=args.weight_decay,
            random_state=args.random_state,
        )
    )
    print(render_text(summary), end="")


if __name__ == "__main__":
    main()
