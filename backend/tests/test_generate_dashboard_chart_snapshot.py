import json

from src.pipeline.generate_dashboard_chart_snapshot import generate_snapshot, publication_year


def test_publication_year_falls_back_to_publication_date():
    assert publication_year({"publication_date": "2024-03-15"}) == 2024


def test_generate_snapshot_uses_publication_date_when_year_column_is_absent(tmp_path):
    all_records_csv = tmp_path / "all_records.csv"
    final_csv = tmp_path / "final.csv"
    model_csv = tmp_path / "model_comparison.csv"
    output_json = tmp_path / "datasetCharts.json"

    all_records_csv.write_text(
        "source_dataset,publication_year,doi,title\n"
        "openalex,2024,10.1000/a,First paper\n",
        encoding="utf-8",
    )
    final_csv.write_text(
        "source_dataset,publication_date\n"
        "openalex,2024-03-15\n"
        "crossref; openalex,2025\n",
        encoding="utf-8",
    )
    model_csv.write_text(
        "model_family,accuracy,macro_f1,weighted_f1\n"
        "linear_svm,0.9,0.8,0.85\n",
        encoding="utf-8",
    )

    snapshot = generate_snapshot(
        all_records_csv=all_records_csv,
        final_csv=final_csv,
        model_comparison_csv=model_csv,
        output_json=output_json,
        year_min=2024,
        year_max=2025,
    )

    assert snapshot["publicationsByYear"] == [
        {"label": "2024", "value": 1},
        {"label": "2025", "value": 1},
    ]
    assert snapshot["multiSourceCombinations"] == [
        {"label": "OpenAlex", "value": 1},
        {"label": "Crossref + OpenAlex", "value": 1},
    ]
    assert json.loads(output_json.read_text(encoding="utf-8")) == snapshot
