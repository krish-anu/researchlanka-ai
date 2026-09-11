#!/usr/bin/env python3
"""Train hierarchical Linear SVM: primary_field → primary_subfield.

Thin wrapper around src.modeling.hierarchical_linear_svm (2 levels only).
Best defaults: ngram_max=3, C=1.0, class_weight=balanced.
"""

from __future__ import annotations

from src.modeling.hierarchical_linear_svm import main


if __name__ == "__main__":
    main()
