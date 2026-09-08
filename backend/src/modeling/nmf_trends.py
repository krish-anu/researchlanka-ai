"""NMF topic trend analysis (k=25 production artifacts).

Linear-regression slopes and emerging/declining classification match
``ResearchLanka_NMF_Trend_Forecast_Analysis.ipynb``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def topic_trend_slopes(shares_df: pd.DataFrame) -> pd.DataFrame:
    """Linear-regression slope of each topic's year-share against year."""
    years = shares_df.index.values.astype(float)
    rows = []
    for topic in shares_df.columns:
        values = shares_df[topic].values.astype(float)
        if len(years) < 3 or np.all(np.isnan(values)):
            continue
        slope, _intercept, r_value, p_value, _se = stats.linregress(years, values)
        rows.append(
            {
                "topic_name": topic,
                "slope_per_year": float(slope),
                "r_value": float(r_value),
                "p_value": float(p_value),
                "mean_share": float(np.nanmean(values)),
                "first_year_share": float(values[0]),
                "last_year_share": float(values[-1]),
            }
        )
    return pd.DataFrame(rows).sort_values("slope_per_year", ascending=False).reset_index(drop=True)


def classify_trend(slope_df: pd.DataFrame, *, alpha: float = 0.10) -> pd.DataFrame:
    """Label topics as emerging, declining, or stable."""
    classified = slope_df.copy()
    classified["trend"] = np.where(
        (classified["p_value"] < alpha) & (classified["slope_per_year"] > 0),
        "emerging",
        np.where(
            (classified["p_value"] < alpha) & (classified["slope_per_year"] < 0),
            "declining",
            "stable",
        ),
    )
    return classified


def trend_time_series(
    counts_df: pd.DataFrame,
    shares_df: pd.DataFrame,
    *,
    topic_names: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[dict[str, object]]:
    """Return long-format yearly counts and shares for NMF topics."""
    selected = topic_names or list(shares_df.columns)
    rows: list[dict[str, object]] = []
    for topic_name in selected:
        if topic_name not in shares_df.columns:
            continue
        for year in shares_df.index:
            year_value = int(year)
            if year_min is not None and year_value < year_min:
                continue
            if year_max is not None and year_value > year_max:
                continue
            count = int(counts_df.at[year, topic_name]) if topic_name in counts_df.columns else 0
            share = float(shares_df.at[year, topic_name])
            rows.append(
                {
                    "topic_name": topic_name,
                    "year": year_value,
                    "publication_count": count,
                    "share": share,
                }
            )
    return rows
