#!/usr/bin/env python3
"""Train flat Linear SVM on primary_domain (thin wrapper).

Uses best defaults from src.modeling.linear_svm_training:
  label=primary_domain, ngram_max=3, C∈{0.1,1,10}, class_weight=balanced
"""

from __future__ import annotations

from src.modeling.linear_svm_training import main


if __name__ == "__main__":
    main()


# cd researchlanka-ai/backend
# PYTHONPATH=. python scripts/modeling/linear_svm_hierarchical.py \
#   --input data/processed/common/common_publications_final.csv \
#   --predict-output data/processed/common/common_publications_final_with_linearsvm.csv
