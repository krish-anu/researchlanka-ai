from __future__ import annotations

import pandas as pd

from src.ai_relevance.human_verification_metrics import calculate_human_verification_metrics


def test_calculate_human_verification_metrics_excludes_review_and_blank_rows() -> None:
    frame = pd.DataFrame(
        [
            {"ai_llm_label": "AI", "human_label": True},
            {"ai_llm_label": "AI", "human_label": False},
            {"ai_llm_label": "NON_AI", "human_label": True},
            {"ai_llm_label": "NON_AI", "human_label": False},
            {"ai_llm_label": "REVIEW", "human_label": True},
            {"ai_llm_label": "AI", "human_label": ""},
        ]
    )

    metrics = calculate_human_verification_metrics(frame)

    assert metrics.total_rows == 6
    assert metrics.verified_rows == 5
    assert metrics.blank_human_label_rows == 1
    assert metrics.model_review_rows == 1
    assert metrics.model_review_rows_with_human_label == 1
    assert metrics.evaluated_rows == 4
    assert metrics.true_positive == 1
    assert metrics.true_negative == 1
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.accuracy == 0.5
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f1_score == 0.5
