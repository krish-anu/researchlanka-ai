"""Tests for AI relevance sampling, Gemini output handling, and evaluation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.ai_relevance.evaluation import (
    GeminiHumanEvaluationConfig,
    evaluate_gemini_against_human,
)
from src.ai_relevance.fields import normalize_multivalue, publication_metadata
from src.ai_relevance.gemini_client import (
    GeminiClassificationResult,
    GeminiUsage,
    OllamaAIClient,
    estimated_cost,
)
from src.ai_relevance.config import GeminiConfig
from src.ai_relevance.prompt import build_classification_prompt
from src.ai_relevance.review import HumanReviewConfig, build_human_review_sample
from src.ai_relevance.runner import GeminiRunConfig, run_gemini_classification
from src.ai_relevance.sampling import CandidateSamplingConfig, build_candidate_sample
from src.ai_relevance.schema import AIClassification, validate_ai_response


def write_publications(path: Path) -> None:
    rows = [
        {
            "record_number": "1",
            "title": "Deep learning for tea disease detection",
            "abstract": "A convolutional neural network detects crop disease.",
            "keywords": "deep learning; agriculture",
            "topics": "Computer vision",
            "concepts": "Machine learning",
            "primary_topic": "Computer Vision",
            "primary_field": "Agricultural and Biological Sciences",
            "primary_subfield": "Agronomy",
            "primary_domain": "Life Sciences",
        },
        {
            "record_number": "2",
            "title": "Networking protocols for campus systems",
            "abstract": "A conventional protocol evaluation.",
            "keywords": "networking",
            "topics": "Computer Networks",
            "concepts": "Computer networking",
            "primary_topic": "Networks",
            "primary_field": "Computer Science",
            "primary_subfield": "Networks",
            "primary_domain": "Physical Sciences",
        },
        {
            "record_number": "3",
            "title": "Rainfall prediction with statistical regression",
            "abstract": "Prediction using ordinary least squares.",
            "keywords": "forecasting",
            "topics": "Hydrology",
            "concepts": "",
            "primary_topic": "Rainfall",
            "primary_field": "Environmental Science",
            "primary_subfield": "Water Science",
            "primary_domain": "Physical Sciences",
        },
        {
            "record_number": "4",
            "title": "Students perception of ChatGPT in higher education",
            "abstract": "",
            "keywords": "ChatGPT; education",
            "topics": "",
            "concepts": "",
            "primary_topic": "Education",
            "primary_field": "Social Sciences",
            "primary_subfield": "Education",
            "primary_domain": "Social Sciences",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_publication_metadata_handles_missing_and_nan() -> None:
    metadata = publication_metadata(
        {"record_number": "7", "title": float("nan"), "keywords": "['AI', 'ethics']"}
    )
    assert metadata.publication_id == "7"
    assert metadata.title == ""
    assert metadata.keywords == "AI; ethics"
    assert normalize_multivalue(None) == ""


def test_validate_ai_response_enforces_labels_and_categories() -> None:
    result = validate_ai_response(
        {
            "label": "AI",
            "confidence": 0.91,
            "ai_category": "Deep Learning",
            "reason": "The study applies a neural network.",
            "evidence": ["neural network"],
        }
    )
    assert result.label == "AI"
    with pytest.raises(ValueError):
        validate_ai_response(
            {
                "label": "MAYBE",
                "confidence": 0.5,
                "ai_category": "Unclear",
                "reason": "bad",
                "evidence": [],
            }
        )
    with pytest.raises(ValueError):
        validate_ai_response(
            {
                "label": "NON_AI",
                "confidence": 0.8,
                "ai_category": "Machine Learning",
                "reason": "bad",
                "evidence": [],
            }
        )


def test_prompt_v2_calls_ocr_recognition_ai_related() -> None:
    metadata = publication_metadata(
        {
            "publication_id": "https://openalex.org/W2910892492",
            "title": "Optical Braille Recognition Platform for Sinhala",
            "topics": "Tactile and Sensory Interactions",
            "concepts": "Optical character recognition; Artificial intelligence",
        }
    )

    prompt = build_classification_prompt(metadata)

    assert "optical character recognition" in prompt
    assert "Recognition tasks are AI-related" in prompt


def test_prompt_v2_calls_fuzzy_topsis_a_hard_negative() -> None:
    metadata = publication_metadata(
        {
            "publication_id": "fuzzy-topsis-example",
            "title": "Assessing the Supplier Selection Criteria based on Minimising Pre-Consumer Fabric Waste",
            "abstract": "Multi-Criteria Decision Making using Intuitionistic Fuzzy TOPSIS.",
            "keywords": "Intuitionistic Fuzzy TOPSIS; supplier selection; decision-making",
        }
    )

    prompt = build_classification_prompt(metadata)

    assert "Fuzzy TOPSIS alone is NON_AI" in prompt
    assert "Intuitionistic Fuzzy TOPSIS alone is NON_AI" in prompt
    assert "Correct label: NON_AI" in prompt
    assert "does not develop or apply an AI/ML system" in prompt


def test_ollama_client_sends_deterministic_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "message": {
                    "content": (
                        '{"label":"AI","confidence":0.8,"ai_category":"OCR",'
                        '"reason":"Central OCR recognition task.",'
                        '"evidence":["Optical character recognition"]}'
                    )
                },
                "prompt_eval_count": 10,
                "eval_count": 5,
            }

    class FakeRequests:
        @staticmethod
        def post(url, *, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return FakeResponse()

    client = OllamaAIClient(GeminiConfig(provider="ollama", model="llama3.1:8b", ollama_seed=123))
    client._requests = FakeRequests

    result = client.classify(publication_metadata({"publication_id": "1", "title": "OCR paper"}))

    assert result.classification.label == "AI"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["options"] == {
        "temperature": 0,
        "top_k": 1,
        "top_p": 1,
        "seed": 123,
    }


def test_candidate_sampling_is_deterministic_and_deduplicated(tmp_path: Path) -> None:
    input_path = tmp_path / "publications.csv"
    first_output = tmp_path / "candidates1.csv"
    second_output = tmp_path / "candidates2.csv"
    write_publications(input_path)

    first = build_candidate_sample(
        CandidateSamplingConfig(input_path=input_path, output_path=first_output, target_size=4)
    )
    second = build_candidate_sample(
        CandidateSamplingConfig(input_path=input_path, output_path=second_output, target_size=4)
    )

    assert first["publication_id"].tolist() == second["publication_id"].tolist()
    assert first["publication_id"].is_unique
    assert "sampling_bucket" in first.columns


class FakeGeminiClient:
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, publication):
        self.calls += 1
        return GeminiClassificationResult(
            classification=AIClassification(
                label="AI",
                confidence=0.8,
                ai_category="Machine Learning",
                reason="Metadata contains an AI method.",
                evidence=("machine learning",),
            ),
            usage=GeminiUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            raw_response="{}",
        )


def test_runner_processes_exactly_10_and_resume_skips_successes(tmp_path: Path) -> None:
    candidates = pd.DataFrame(
        [
            {
                "publication_id": str(index),
                "record_number": str(index),
                "title": f"Machine learning paper {index}",
                "abstract": "Uses machine learning.",
                "keywords": "",
                "topics": "",
                "concepts": "",
                "primary_topic": "",
                "primary_field": "Computer Science",
                "primary_subfield": "",
                "primary_domain": "Physical Sciences",
                "sampling_bucket": f"bucket-{index % 3}",
            }
            for index in range(12)
        ]
    )
    input_path = tmp_path / "candidates.csv"
    output_path = tmp_path / "predictions.csv"
    ids_path = tmp_path / "ids.csv"
    candidates.to_csv(input_path, index=False)

    client = FakeGeminiClient()
    result = run_gemini_classification(
        GeminiRunConfig(
            input_path=input_path,
            output_path=output_path,
            selected_ids_output=ids_path,
            limit=10,
            first_test=True,
        ),
        client=client,
    )
    assert client.calls == 10
    assert result.attempted == 10
    assert result.successful == 10
    assert len(pd.read_csv(output_path)) == 10
    assert len(pd.read_csv(ids_path)) == 10

    resumed_client = FakeGeminiClient()
    resumed = run_gemini_classification(
        GeminiRunConfig(
            input_path=input_path,
            output_path=output_path,
            selected_ids_output=ids_path,
            limit=10,
            first_test=True,
            resume=True,
        ),
        client=resumed_client,
    )
    assert resumed_client.calls == 0
    assert resumed.skipped_existing == 10


def test_first_test_requires_limit_10(tmp_path: Path) -> None:
    input_path = tmp_path / "candidates.csv"
    pd.DataFrame({"publication_id": ["1"], "title": ["AI"], "sampling_bucket": ["x"]}).to_csv(
        input_path,
        index=False,
    )
    with pytest.raises(ValueError):
        run_gemini_classification(
            GeminiRunConfig(
                input_path=input_path,
                output_path=tmp_path / "out.csv",
                selected_ids_output=tmp_path / "ids.csv",
                limit=1,
                first_test=True,
            ),
            client=FakeGeminiClient(),
        )


def test_cost_calculation() -> None:
    cost = estimated_cost(
        GeminiUsage(input_tokens=1_000_000, output_tokens=500_000, total_tokens=1_500_000),
        input_price_per_million=0.10,
        output_price_per_million=0.40,
    )
    assert cost == pytest.approx(0.30)


def test_human_review_sample_and_metrics(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.csv"
    review = tmp_path / "review.csv"
    pd.DataFrame(
        [
            {
                "publication_id": "1",
                "title": "Deep learning",
                "sampling_bucket": "strong_ai_text",
                "ai_llm_label": "AI",
                "ai_llm_confidence": "0.9",
                "ai_llm_category": "Deep Learning",
                "ai_llm_reason": "AI method.",
                "human_label": "AI",
            },
            {
                "publication_id": "2",
                "title": "Regression rainfall",
                "sampling_bucket": "borderline_ambiguous",
                "ai_llm_label": "AI",
                "ai_llm_confidence": "0.6",
                "ai_llm_category": "Other AI",
                "ai_llm_reason": "Ambiguous.",
                "human_label": "NON_AI",
            },
        ]
    ).to_csv(predictions, index=False)

    sample = build_human_review_sample(
        HumanReviewConfig(input_path=predictions, output_path=review, sample_size=2)
    )
    assert "human_label" in sample.columns
    assert "human_notes" in sample.columns

    metrics = evaluate_gemini_against_human(
        GeminiHumanEvaluationConfig(input_path=predictions, output_dir=tmp_path)
    )
    assert metrics["rows"] == 2
    assert metrics["ai_precision"] == pytest.approx(0.5)
    assert (tmp_path / "gemini_ai_relevance_false_positives.csv").exists()
