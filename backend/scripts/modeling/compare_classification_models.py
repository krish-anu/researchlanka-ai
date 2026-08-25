#!/usr/bin/env python3
"""Compare Logistic Regression vs Linear SVM on primary_field (thin wrapper).

Promotes the winner to data/models/final/publication_field_classifier.joblib.
"""

from __future__ import annotations

from src.modeling.classification_comparison import main


if __name__ == "__main__":
    main()
