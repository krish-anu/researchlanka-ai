"""Tests for the author-email fetching helper script."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "processing" / "fetch_missing_author_emails.py"
SPEC = importlib.util.spec_from_file_location("fetch_missing_author_emails", SCRIPT_PATH)
assert SPEC and SPEC.loader
email_fetcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = email_fetcher
SPEC.loader.exec_module(email_fetcher)


def test_extract_emails_handles_encoded_and_obfuscated_addresses() -> None:
    text = (
        "Correspondence: mailto:Jane.Doe%40eng.pdn.ac.lk; "
        "or ravi [at] cse [dot] mrt [dot] ac [dot] lk. "
        "Ignore info@example.com."
    )

    assert email_fetcher.extract_emails(text) == (
        "jane.doe@eng.pdn.ac.lk",
        "ravi@cse.mrt.ac.lk",
    )


def test_extract_emails_from_pdf_like_bytes() -> None:
    data = b"%PDF-1.7\nCorresponding author: nalin@example.edu.lk\n%%EOF"

    assert email_fetcher.extract_emails_from_bytes(data) == ("nalin@example.edu.lk",)


def test_extract_emails_rejects_file_extension_false_positives() -> None:
    text = "Links: students@the.pdf students@the.pdf.jpg students@the.pdf.txt"

    assert email_fetcher.extract_emails(text) == ()


def test_extract_emails_rejects_scientific_at_phrases() -> None:
    text = "The IC50 at 0.26 mg/ml was observed in the assay."

    assert email_fetcher.extract_emails(text) == ()


def test_load_metadata_candidates_adds_pdf_urls_by_doi(tmp_path: Path) -> None:
    metadata_csv = tmp_path / "metadata.csv"
    with metadata_csv.open("w", newline="", encoding="utf-8") as metadata_file:
        writer = csv.DictWriter(metadata_file, fieldnames=["doi", "source_record_id", "url", "pdf_url"])
        writer.writeheader()
        writer.writerow(
            {
                "doi": "10.1234/example",
                "source_record_id": "record-1",
                "url": "https://doi.org/10.1234/example",
                "pdf_url": "https://repository.example.edu/bitstreams/example.pdf",
            }
        )

    rows = [
        {
            "doi": "10.1234/example",
            "source_record_id": "record-1",
            "url": "https://doi.org/10.1234/example",
            "author_emails": "",
        }
    ]

    extra = email_fetcher.load_metadata_url_candidates(
        rows,
        metadata_csv,
        metadata_url_columns=("pdf_url",),
    )
    jobs = email_fetcher.build_jobs(
        rows,
        url_columns=("url",),
        extra_url_candidates=extra,
        include_all_hosts=False,
        include_doi_hosts=False,
        host_contains=(),
        try_doi_urls=False,
        limit=None,
    )

    assert len(jobs) == 1
    assert jobs[0].candidates == (
        email_fetcher.UrlCandidate("https://repository.example.edu/bitstreams/example.pdf", "pdf_url"),
    )
