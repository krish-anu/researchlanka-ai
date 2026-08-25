#!/usr/bin/env python3
"""Train flat Linear SVM on primary_field (thin wrapper).

Uses best defaults from src.modeling.linear_svm_training:
  label=primary_field, ngram_max=3, C∈{0.1,1,10}, class_weight=balanced
"""

from __future__ import annotations

from src.modeling.linear_svm_training import main


if __name__ == "__main__":
    main()
