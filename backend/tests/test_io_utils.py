"""Tests for the shared dataset load/save helpers in ``src/utils/io_utils``."""

import pandas as pd
import pytest

from src.utils.io_utils import (
    check_common_schema,
    common_schema_columns,
    load_dataset,
    save_dataset,
)


def test_csv_round_trip_preserves_identifier_like_strings(tmp_path):
    # DOIs, ORCIDs and the literal "NA" are the values pandas most often
    # mangles on a default read; they must survive unchanged.
    frame = pd.DataFrame(
        {
            "doi": ["10.1234/abc", "10.5678/def"],
            "orcid": ["0000-0001-2345-6789", ""],
            "country": ["NA", "LK"],
            "record_number": ["001", "002"],
        }
    )
    target = tmp_path / "round_trip.csv"

    save_dataset(frame, target)
    reloaded = load_dataset(target)

    pd.testing.assert_frame_equal(frame, reloaded)
    assert reloaded.loc[0, "country"] == "NA"
    assert reloaded.loc[0, "record_number"] == "001"


def test_parquet_round_trip(tmp_path):
    frame = pd.DataFrame({"title": ["A", "B"], "publication_year": ["2020", "2021"]})
    target = tmp_path / "round_trip.parquet"

    save_dataset(frame, target)

    pd.testing.assert_frame_equal(frame, load_dataset(target))


def test_save_dataset_creates_missing_parent_directories(tmp_path):
    target = tmp_path / "nested" / "deeper" / "out.csv"

    result = save_dataset(pd.DataFrame({"title": ["A"]}), target)

    assert result == target
    assert target.exists()


def test_save_dataset_never_writes_the_index(tmp_path):
    frame = pd.DataFrame({"title": ["A", "B"]}, index=[7, 9])
    target = tmp_path / "no_index.csv"

    save_dataset(frame, target)

    assert list(load_dataset(target).columns) == ["title"]


def test_load_dataset_reports_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_dataset(tmp_path / "absent.csv")


def test_unsupported_extension_is_rejected_rather_than_guessed(tmp_path):
    target = tmp_path / "data.xlsx"
    target.write_text("not really a spreadsheet", encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot infer a dataset format"):
        load_dataset(target)


def test_compression_suffix_is_looked_past(tmp_path):
    frame = pd.DataFrame({"title": ["A"]})
    target = tmp_path / "data.csv.gz"

    save_dataset(frame, target)

    pd.testing.assert_frame_equal(frame, load_dataset(target))


def test_required_columns_check_names_what_is_missing(tmp_path):
    target = tmp_path / "partial.csv"
    save_dataset(pd.DataFrame({"title": ["A"]}), target)

    with pytest.raises(ValueError, match="authors"):
        load_dataset(target, required_columns=["title", "authors"])


def test_required_columns_check_passes_when_all_present(tmp_path):
    target = tmp_path / "ok.csv"
    save_dataset(pd.DataFrame({"title": ["A"], "authors": ["Perera, A."]}), target)

    frame = load_dataset(target, required_columns=["title"])

    assert list(frame.columns) == ["title", "authors"]


def test_full_schema_check_accepts_a_complete_common_schema_frame():
    columns = common_schema_columns()
    frame = pd.DataFrame([{column: "" for column in columns}])

    assert check_common_schema(frame) == columns


def test_full_schema_check_truncates_a_long_missing_list():
    # Only the first 10 names are shown, with a count for the remainder, so the
    # error stays readable when an entirely wrong file is passed.
    frame = pd.DataFrame({"title": ["A"]})

    with pytest.raises(ValueError, match=r"more\)"):
        check_common_schema(frame)


def test_common_schema_columns_returns_a_defensive_copy():
    first = common_schema_columns()
    first.append("injected")

    assert "injected" not in common_schema_columns()
