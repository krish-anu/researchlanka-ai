"""Tests for the common evaluation pipeline and the Naive Bayes baseline."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.modeling.evaluation import (
    ConfusionMatrix,
    evaluate_model_file,
    evaluate_predictions,
    evaluate_predictions_csv,
    per_class_rows,
    render_evaluation,
    run_name_from_path,
    write_comparison,
    write_evaluation_artifacts,
)
from src.modeling.training import (
    MODEL_FAMILY_MULTINOMIAL_NB,
    SUPPORTED_MODEL_FAMILIES,
    TextTrainingConfig,
    build_classifier,
    build_pipeline,
    family_hyperparameters,
    resolved_config,
    train_multinomial_nb_classifier,
    train_text_classifier,
    validate_config,
)


# --- evaluate_predictions ---------------------------------------------------


def test_evaluation_scores_a_perfect_run():
    result = evaluate_predictions(["a", "b", "a"], ["a", "b", "a"], run_name="perfect")

    assert result.accuracy == 1.0
    assert result.macro_f1 == 1.0
    assert result.balanced_accuracy == 1.0
    assert result.rows == 3
    assert result.class_count == 2
    assert result.confusion.off_diagonal() == []


def test_evaluation_counts_every_cell_of_the_confusion_matrix():
    result = evaluate_predictions(
        ["a", "a", "b", "b", "c"],
        ["a", "b", "b", "a", "a"],
        run_name="mixed",
    )

    assert result.confusion.labels == ("a", "b", "c")
    assert result.confusion.counts == ((1, 1, 0), (1, 1, 0), (1, 0, 0))
    assert result.confusion.off_diagonal()[0] in {("a", "b", 1), ("b", "a", 1), ("c", "a", 1)}
    assert result.accuracy == pytest.approx(2 / 5)


def test_confusion_matrix_rows_carry_support_and_row_accuracy():
    result = evaluate_predictions(["a", "a", "b"], ["a", "b", "b"])
    rows = {row["true_label"]: row for row in result.confusion.rows()}

    assert rows["a"]["support"] == 2
    assert rows["a"]["correct"] == 1
    assert rows["a"]["accuracy"] == 0.5
    assert rows["a"]["b"] == 1
    assert result.confusion.fieldnames == ["true_label", "support", "correct", "accuracy", "a", "b"]


def test_per_class_results_name_the_class_each_one_leaks_to():
    result = evaluate_predictions(
        ["a", "a", "a", "b", "b"],
        ["b", "b", "a", "b", "b"],
    )
    by_label = {row["label"]: row for row in per_class_rows(result)}

    assert by_label["a"]["support"] == 3
    assert by_label["a"]["correct"] == 1
    # Row values are rounded for the CSV artifact.
    assert by_label["a"]["recall"] == pytest.approx(1 / 3, abs=1e-4)
    assert by_label["a"]["most_confused_with"] == "b"
    assert by_label["a"]["most_confused_count"] == 2
    assert by_label["b"]["most_confused_with"] == ""


def test_a_class_the_model_never_predicts_still_gets_a_row():
    result = evaluate_predictions(["a", "b"], ["a", "a"])
    labels = [metrics.label for metrics in result.per_class]

    assert labels == ["a", "b"]
    missing = next(metrics for metrics in result.per_class if metrics.label == "b")
    assert missing.support == 1
    assert missing.predicted == 0
    assert missing.f1 == 0.0


def test_explicit_label_order_is_respected():
    result = evaluate_predictions(["a", "b"], ["a", "b"], labels=["b", "a", "c"])
    assert result.confusion.labels == ("b", "a", "c")
    assert result.class_count == 3


def test_worst_class_is_the_one_to_look_at_first():
    result = evaluate_predictions(
        ["a", "a", "b", "b"],
        ["a", "a", "a", "a"],
    )
    assert result.worst_class is not None
    assert result.worst_class.label == "b"
    assert result.summary()["worst_class"] == "b"


def test_mismatched_or_empty_prediction_sets_are_rejected():
    with pytest.raises(ValueError, match="same length"):
        evaluate_predictions(["a", "b"], ["a"])
    with pytest.raises(ValueError, match="empty"):
        evaluate_predictions([], [])


def test_rendered_evaluation_lists_classes_and_confusions():
    result = evaluate_predictions(["a", "a", "b"], ["a", "b", "b"], run_name="demo")
    rendered = render_evaluation(result)

    assert "Evaluation: demo" in rendered
    assert "accuracy:" in rendered
    assert "Per-class results:" in rendered
    assert "a -> b: 1" in rendered


def test_off_diagonal_is_sorted_by_weight():
    matrix = ConfusionMatrix(labels=("a", "b", "c"), counts=((0, 1, 3), (2, 0, 0), (0, 0, 0)))
    assert matrix.off_diagonal() == [("a", "c", 3), ("b", "a", 2), ("a", "b", 1)]


# --- artifacts --------------------------------------------------------------


def test_evaluation_artifacts_are_written_as_three_files(tmp_path: Path):
    result = evaluate_predictions(["a", "a", "b"], ["a", "b", "b"], run_name="run1")
    written = write_evaluation_artifacts(result, directory=tmp_path)

    assert written["confusion_matrix"].name == "run1_confusion_matrix.csv"
    assert written["per_class"].name == "run1_per_class.csv"
    assert written["evaluation"].name == "run1_evaluation.json"

    matrix_rows = list(csv.DictReader(written["confusion_matrix"].open(encoding="utf-8")))
    assert {row["true_label"] for row in matrix_rows} == {"a", "b"}

    per_class = list(csv.DictReader(written["per_class"].open(encoding="utf-8")))
    assert {row["label"] for row in per_class} == {"a", "b"}

    payload = json.loads(written["evaluation"].read_text(encoding="utf-8"))
    assert payload["summary"]["run"] == "run1"
    assert payload["confusion_matrix"]["labels"] == ["a", "b"]
    assert payload["top_confusions"][0] == {
        "true_label": "a",
        "predicted_label": "b",
        "count": 1,
    }


def test_comparison_puts_one_row_per_run(tmp_path: Path):
    first = evaluate_predictions(["a", "b"], ["a", "b"], run_name="nb")
    second = evaluate_predictions(["a", "b"], ["a", "a"], run_name="logreg")
    path = write_comparison(tmp_path / "model_comparison.csv", [first, second])

    rows = {row["run"]: row for row in csv.DictReader(path.open(encoding="utf-8"))}
    assert set(rows) == {"nb", "logreg"}
    assert float(rows["nb"]["accuracy"]) == 1.0
    assert float(rows["logreg"]["accuracy"]) == 0.5


def test_evaluating_a_predictions_csv(tmp_path: Path):
    predictions_csv = tmp_path / "demo_predictions.csv"
    with predictions_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_row", "label", "prediction"])
        writer.writeheader()
        writer.writerows(
            [
                {"source_row": 0, "label": "a", "prediction": "a"},
                {"source_row": 1, "label": "b", "prediction": "a"},
            ]
        )

    result = evaluate_predictions_csv(predictions_csv)
    assert result.run_name == "demo"
    assert result.accuracy == 0.5
    assert result.metadata["predictions_csv"] == str(predictions_csv)


def test_evaluating_a_predictions_csv_without_the_expected_columns(tmp_path: Path):
    path = tmp_path / "bad_predictions.csv"
    path.write_text("source_row,guess\n1,a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no 'label' column"):
        evaluate_predictions_csv(path)


def test_run_name_drops_the_artifact_suffix():
    assert run_name_from_path(Path("a/multinomial_nb_domain_predictions.csv")) == (
        "multinomial_nb_domain"
    )
    assert run_name_from_path(Path("a/multinomial_nb_domain.joblib")) == "multinomial_nb_domain"


# --- Multinomial Naive Bayes ------------------------------------------------


def test_both_model_families_are_supported():
    assert SUPPORTED_MODEL_FAMILIES == ("logistic_regression", "multinomial_nb")


def test_naive_bayes_classifier_gets_its_own_hyperparameters():
    classifier = build_classifier(
        MODEL_FAMILY_MULTINOMIAL_NB,
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
        alpha=0.3,
        fit_prior=False,
    )
    assert classifier.__class__.__name__ == "MultinomialNB"
    assert classifier.alpha == 0.3
    assert classifier.fit_prior is False


def test_an_unknown_model_family_is_rejected():
    with pytest.raises(ValueError, match="Unsupported model_family"):
        build_classifier(
            "random_forest",
            class_weight=None,
            max_iter=1,
            random_state=0,
            alpha=1.0,
            fit_prior=True,
        )
    with pytest.raises(ValueError, match="Unsupported model_family"):
        validate_config(TextTrainingConfig(model_family="random_forest"))


def test_naive_bayes_pipeline_keeps_tfidf_and_swaps_the_classifier():
    pipeline = build_pipeline(
        max_features=100,
        min_df=1,
        max_df=1.0,
        ngram_max=1,
        keep_stop_words=True,
        class_weight=None,
        max_iter=100,
        random_state=0,
        model_family=MODEL_FAMILY_MULTINOMIAL_NB,
    )
    assert [name for name, _ in pipeline.steps] == ["tfidf", "classifier"]
    assert pipeline.named_steps["classifier"].__class__.__name__ == "MultinomialNB"


def test_class_weight_is_cleared_for_naive_bayes_rather_than_carried_along():
    config = resolved_config(
        TextTrainingConfig(model_family=MODEL_FAMILY_MULTINOMIAL_NB, class_weight="balanced")
    )
    assert config.class_weight is None
    assert "class_weight" not in family_hyperparameters(config)
    assert family_hyperparameters(config)["alpha"] == 1.0
    assert family_hyperparameters(config)["fit_prior"] is True


def test_logistic_regression_keeps_its_own_hyperparameters():
    config = resolved_config(TextTrainingConfig())
    hyperparameters = family_hyperparameters(config)
    assert hyperparameters["class_weight"] == "balanced"
    assert hyperparameters["max_iter"] == 1000
    assert "alpha" not in hyperparameters


def test_naive_bayes_rejects_non_positive_smoothing():
    with pytest.raises(ValueError, match="alpha must be greater than 0"):
        validate_config(
            resolved_config(TextTrainingConfig(model_family=MODEL_FAMILY_MULTINOMIAL_NB, alpha=0))
        )


def test_naive_bayes_artifacts_are_named_after_the_family():
    config = resolved_config(
        TextTrainingConfig(model_family=MODEL_FAMILY_MULTINOMIAL_NB, label_column="primary_domain")
    )
    assert config.model_output.name == "multinomial_nb_primary_domain.joblib"
    assert config.confusion_matrix_output.name == (
        "multinomial_nb_primary_domain_confusion_matrix.csv"
    )
    assert config.per_class_output.name == "multinomial_nb_primary_domain_per_class.csv"


# --- training end to end ----------------------------------------------------


TRAINING_ROWS = [
    ("machine learning for tea leaf disease detection", "computer science"),
    ("deep learning models for crop image classification", "computer science"),
    ("neural networks applied to rainfall prediction", "computer science"),
    ("a survey of software testing practices", "computer science"),
    ("supervised learning for text categorisation", "computer science"),
    ("prevalence of dengue fever in coastal districts", "medicine"),
    ("clinical outcomes after cardiac surgery", "medicine"),
    ("maternal health and antenatal care access", "medicine"),
    ("antibiotic resistance in hospital patients", "medicine"),
    ("a randomised trial of diabetes treatment", "medicine"),
]


@pytest.fixture()
def training_csv(tmp_path: Path) -> Path:
    path = tmp_path / "publications.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "abstract", "keywords", "primary_domain"])
        writer.writeheader()
        for title, domain in TRAINING_ROWS:
            writer.writerow(
                {
                    "title": title,
                    "abstract": f"{title} study",
                    "keywords": domain,
                    "primary_domain": domain,
                }
            )
    return path


def test_training_the_naive_bayes_baseline_writes_every_artifact(
    training_csv: Path, tmp_path: Path
):
    result = train_multinomial_nb_classifier(
        input_path=training_csv,
        model_output=tmp_path / "nb.joblib",
        metrics_output=tmp_path / "nb_metrics.txt",
        label_counts_output=tmp_path / "nb_labels.csv",
        predictions_output=tmp_path / "nb_predictions.csv",
        manifest_output=tmp_path / "nb_manifest.json",
        confusion_matrix_output=tmp_path / "nb_confusion_matrix.csv",
        per_class_output=tmp_path / "nb_per_class.csv",
        test_size=0.4,
        min_class_count=2,
        min_df=1,
        max_df=1.0,
    )

    assert result.model_output.is_file()
    assert result.confusion_matrix_output.is_file()
    assert result.per_class_output.is_file()
    assert result.class_count == 2
    assert 0.0 <= result.accuracy <= 1.0
    assert result.balanced_accuracy > 0
    assert result.model_sha256

    metrics_text = result.metrics_output.read_text(encoding="utf-8")
    assert "model_family: multinomial_nb" in metrics_text
    assert "alpha: 1.0" in metrics_text
    assert "Per-class results:" in metrics_text

    matrix_rows = list(csv.DictReader(result.confusion_matrix_output.open(encoding="utf-8")))
    assert {row["true_label"] for row in matrix_rows} <= {"computer science", "medicine"}
    per_class = list(csv.DictReader(result.per_class_output.open(encoding="utf-8")))
    assert {row["label"] for row in per_class} == {"computer science", "medicine"}


def test_the_manifest_records_the_evaluation_artifacts(training_csv: Path, tmp_path: Path):
    result = train_multinomial_nb_classifier(
        input_path=training_csv,
        model_output=tmp_path / "nb.joblib",
        metrics_output=tmp_path / "nb_metrics.txt",
        label_counts_output=tmp_path / "nb_labels.csv",
        predictions_output=tmp_path / "nb_predictions.csv",
        manifest_output=tmp_path / "nb_manifest.json",
        confusion_matrix_output=tmp_path / "nb_confusion_matrix.csv",
        per_class_output=tmp_path / "nb_per_class.csv",
        test_size=0.4,
        min_class_count=2,
        min_df=1,
        max_df=1.0,
    )

    manifest = json.loads(result.manifest_output.read_text(encoding="utf-8"))
    assert manifest["config"]["model_family"] == "multinomial_nb"
    assert manifest["artifacts"]["confusion_matrix"]["sha256"]
    assert manifest["artifacts"]["per_class"]["sha256"]


def test_both_families_produce_artifacts_the_same_evaluation_can_read(
    training_csv: Path, tmp_path: Path
):
    results = {}
    for family in SUPPORTED_MODEL_FAMILIES:
        results[family] = train_text_classifier(
            TextTrainingConfig(
                input_path=training_csv,
                model_family=family,
                model_output=tmp_path / f"{family}.joblib",
                metrics_output=tmp_path / f"{family}_metrics.txt",
                label_counts_output=tmp_path / f"{family}_labels.csv",
                predictions_output=tmp_path / f"{family}_predictions.csv",
                manifest_output=tmp_path / f"{family}_manifest.json",
                confusion_matrix_output=tmp_path / f"{family}_confusion_matrix.csv",
                per_class_output=tmp_path / f"{family}_per_class.csv",
                test_size=0.4,
                min_class_count=2,
                min_df=1,
                max_df=1.0,
            )
        )

    # The point of a baseline: the two runs are directly comparable because they
    # were scored by the same code from identically shaped artifacts.
    evaluations = [
        evaluate_predictions_csv(result.predictions_output, run_name=family)
        for family, result in results.items()
    ]
    comparison = write_comparison(tmp_path / "model_comparison.csv", evaluations)
    rows = {row["run"]: row for row in csv.DictReader(comparison.open(encoding="utf-8"))}

    assert set(rows) == set(SUPPORTED_MODEL_FAMILIES)
    for family, result in results.items():
        assert float(rows[family]["accuracy"]) == pytest.approx(result.accuracy, abs=1e-4)


def test_scoring_a_saved_model_against_a_dataset(training_csv: Path, tmp_path: Path):
    result = train_multinomial_nb_classifier(
        input_path=training_csv,
        model_output=tmp_path / "nb.joblib",
        metrics_output=tmp_path / "nb_metrics.txt",
        label_counts_output=tmp_path / "nb_labels.csv",
        predictions_output=tmp_path / "nb_predictions.csv",
        manifest_output=tmp_path / "nb_manifest.json",
        confusion_matrix_output=tmp_path / "nb_confusion_matrix.csv",
        per_class_output=tmp_path / "nb_per_class.csv",
        test_size=0.4,
        min_class_count=2,
        min_df=1,
        max_df=1.0,
    )

    evaluation = evaluate_model_file(
        result.model_output,
        training_csv,
        label_column="primary_domain",
        text_columns=["title", "abstract", "keywords"],
        run_name="nb_full",
    )
    assert evaluation.rows == len(TRAINING_ROWS)
    assert evaluation.run_name == "nb_full"
    assert evaluation.metadata["model"] == str(result.model_output)


def test_scoring_a_model_against_a_dataset_missing_its_columns(
    training_csv: Path, tmp_path: Path
):
    result = train_multinomial_nb_classifier(
        input_path=training_csv,
        model_output=tmp_path / "nb.joblib",
        metrics_output=tmp_path / "nb_metrics.txt",
        label_counts_output=tmp_path / "nb_labels.csv",
        predictions_output=tmp_path / "nb_predictions.csv",
        manifest_output=tmp_path / "nb_manifest.json",
        confusion_matrix_output=tmp_path / "nb_confusion_matrix.csv",
        per_class_output=tmp_path / "nb_per_class.csv",
        test_size=0.4,
        min_class_count=2,
        min_df=1,
        max_df=1.0,
    )
    other_csv = tmp_path / "other.csv"
    other_csv.write_text("title,primary_domain\nsomething,medicine\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing text columns"):
        evaluate_model_file(
            result.model_output,
            other_csv,
            label_column="primary_domain",
            text_columns=["title", "abstract"],
        )
