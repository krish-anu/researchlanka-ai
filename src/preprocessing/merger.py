import pandas as pd


def merge_datasets(
    openalex_df: pd.DataFrame,
    crossref_df: pd.DataFrame,
):

    merged = openalex_df.merge(
        crossref_df,
        left_on="doi",
        right_on="doi",
        how="left",
        suffixes=(
            "_oa",
            "_cr",
        ),
    )

    merged["language"] = merged["language_oa"].fillna(merged["language_cr"])

    merged["publisher"] = merged["publisher_oa"].fillna(merged["publisher_cr"])

    return merged
