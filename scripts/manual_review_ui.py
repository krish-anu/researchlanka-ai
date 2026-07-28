"""Local browser UI for reviewing manual deduplication candidates.

The UI reads:
    data/processed/common/common_publications_manual_review_candidates.csv
    data/processed/common/common_publications_all_records.csv

It writes:
    data/processed/common/manual_review_decisions.csv

Run:
    python scripts/manual_review_ui.py

Then open:
    http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "processed" / "common"
DEFAULT_CANDIDATES_CSV = DEFAULT_DATA_DIR / "common_publications_manual_review_candidates.csv"
DEFAULT_ALL_RECORDS_CSV = DEFAULT_DATA_DIR / "common_publications_all_records.csv"
DEFAULT_DECISIONS_CSV = DEFAULT_DATA_DIR / "manual_review_decisions.csv"

DECISION_COLUMNS = [
    "candidate_group_number",
    "decision",
    "canonical_input_row_number",
    "notes",
    "decided_at",
]
VALID_DECISIONS = {"merge", "keep_separate", "needs_more_check", ""}

IMPORTANT_FIELDS = [
    "input_row_number",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "doi",
    "openalex_id",
    "title",
    "subtitle",
    "original_title",
    "publication_year",
    "publication_date",
    "type",
    "publication_type",
    "authors",
    "author_names",
    "author_count",
    "author_affiliations",
    "author_orcids",
    "sri_lankan_authors",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "publisher",
    "journal",
    "container_title",
    "source_name",
    "source_type",
    "issn",
    "volume",
    "issue",
    "page",
    "first_page",
    "last_page",
    "article_number",
    "language",
    "url",
    "landing_page_url",
    "pdf_url",
    "abstract",
    "keywords",
    "oa_status",
    "is_oa",
    "cited_by_count",
    "reference_count",
    "concepts",
    "topics",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "funder_name",
    "funder_doi",
    "funder_id",
    "funder_award",
    "source_set_specs",
    "raw_identifiers",
]


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().casefold() in {"", "nan", "none", "null", "na", "n/a"}
    return False


def clean_value(value: Any, *, max_length: int | None = None) -> str | None:
    if is_blank(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if max_length is not None and len(text) > max_length:
        return text[: max_length - 1].rstrip() + "…"
    return text


def parse_input_row_numbers(value: Any) -> list[int]:
    text = clean_value(value)
    if text is None:
        return []
    output: list[int] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        output.append(int(part))
    return output


def decision_label(value: str | None) -> str:
    labels = {
        "merge": "Merge",
        "keep_separate": "Keep Separate",
        "needs_more_check": "Needs More Check",
        "": "Unreviewed",
        None: "Unreviewed",
    }
    return labels.get(value, value or "Unreviewed")


class ReviewDataStore:
    def __init__(
        self,
        *,
        candidates_csv: Path,
        all_records_csv: Path,
        decisions_csv: Path,
    ) -> None:
        self.candidates_csv = candidates_csv
        self.all_records_csv = all_records_csv
        self.decisions_csv = decisions_csv
        self.candidates: list[dict[str, Any]] = []
        self.candidate_by_id: dict[int, dict[str, Any]] = {}
        self.records_by_row_number: dict[int, dict[str, Any]] = {}
        self.decisions: dict[int, dict[str, str]] = {}
        self.load()

    def load(self) -> None:
        self.candidates = self._load_candidates()
        self.candidate_by_id = {
            int(candidate["candidate_group_number"]): candidate for candidate in self.candidates
        }
        wanted_rows = {
            row_number
            for candidate in self.candidates
            for row_number in candidate["input_row_numbers_list"]
        }
        self.records_by_row_number = self._load_records(wanted_rows)
        self.decisions = self._load_decisions()

    def _load_candidates(self) -> list[dict[str, Any]]:
        if not self.candidates_csv.exists():
            raise FileNotFoundError(f"Missing candidate file: {self.candidates_csv}")

        frame = pd.read_csv(self.candidates_csv, dtype="object", low_memory=False)
        candidates: list[dict[str, Any]] = []
        for record in frame.to_dict(orient="records"):
            row_numbers = parse_input_row_numbers(record.get("input_row_numbers"))
            candidate = {
                key: clean_value(value) for key, value in record.items()
            }
            candidate["candidate_group_number"] = int(record["candidate_group_number"])
            candidate["input_record_count"] = int(record["input_record_count"])
            candidate["input_row_numbers_list"] = row_numbers
            candidate["title_preview"] = clean_value(record.get("titles"), max_length=180)
            candidate["author_preview"] = clean_value(record.get("authors"), max_length=120)
            candidate["source_preview"] = clean_value(record.get("source_datasets"), max_length=80)
            candidates.append(candidate)
        return candidates

    def _load_records(self, wanted_rows: set[int]) -> dict[int, dict[str, Any]]:
        if not self.all_records_csv.exists():
            raise FileNotFoundError(f"Missing all-records file: {self.all_records_csv}")

        wanted_indexes = {row_number - 1 for row_number in wanted_rows}
        records: dict[int, dict[str, Any]] = {}

        for chunk in pd.read_csv(
            self.all_records_csv,
            chunksize=50_000,
            dtype="object",
            low_memory=False,
        ):
            hit = chunk.loc[chunk.index.isin(wanted_indexes)].copy()
            if hit.empty:
                continue
            for index, row in hit.iterrows():
                input_row_number = int(index) + 1
                record: dict[str, Any] = {"input_row_number": input_row_number}
                for field in IMPORTANT_FIELDS:
                    if field == "input_row_number":
                        continue
                    if field in row.index:
                        value = clean_value(row[field])
                        if value is not None:
                            record[field] = value
                record["all_non_empty_fields"] = self._compact_non_empty_fields(row, input_row_number)
                records[input_row_number] = record

        return records

    def _compact_non_empty_fields(self, row: pd.Series, input_row_number: int) -> list[dict[str, str]]:
        fields = [{"field": "input_row_number", "value": str(input_row_number)}]
        for field, value in row.items():
            text = clean_value(value, max_length=5000)
            if text is not None:
                fields.append({"field": str(field), "value": text})
        return fields

    def _load_decisions(self) -> dict[int, dict[str, str]]:
        if not self.decisions_csv.exists():
            return {}

        decisions: dict[int, dict[str, str]] = {}
        with self.decisions_csv.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                candidate_id = int(row["candidate_group_number"])
                decisions[candidate_id] = {
                    "candidate_group_number": str(candidate_id),
                    "decision": row.get("decision", ""),
                    "canonical_input_row_number": row.get("canonical_input_row_number", ""),
                    "notes": row.get("notes", ""),
                    "decided_at": row.get("decided_at", ""),
                }
        return decisions

    def save_decision(
        self,
        *,
        candidate_group_number: int,
        decision: str,
        canonical_input_row_number: str,
        notes: str,
    ) -> dict[str, str]:
        if candidate_group_number not in self.candidate_by_id:
            raise KeyError(f"Unknown candidate group: {candidate_group_number}")
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Unsupported decision: {decision}")

        if decision == "":
            self.decisions.pop(candidate_group_number, None)
            self._write_decisions()
            return {
                "candidate_group_number": str(candidate_group_number),
                "decision": "",
                "canonical_input_row_number": "",
                "notes": "",
                "decided_at": "",
            }

        decision_row = {
            "candidate_group_number": str(candidate_group_number),
            "decision": decision,
            "canonical_input_row_number": canonical_input_row_number.strip(),
            "notes": notes.strip(),
            "decided_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.decisions[candidate_group_number] = decision_row
        self._write_decisions()
        return decision_row

    def _write_decisions(self) -> None:
        self.decisions_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.decisions_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=DECISION_COLUMNS)
            writer.writeheader()
            for candidate_id in sorted(self.decisions):
                writer.writerow(self.decisions[candidate_id])

    def candidate_summary(self, candidate: dict[str, Any]) -> dict[str, Any]:
        candidate_id = int(candidate["candidate_group_number"])
        decision = self.decisions.get(candidate_id, {})
        decision_value = decision.get("decision", "")
        return {
            "candidate_group_number": candidate_id,
            "review_method": candidate.get("review_method"),
            "input_record_count": candidate.get("input_record_count"),
            "titles": candidate.get("titles"),
            "title_preview": candidate.get("title_preview"),
            "publication_years": candidate.get("publication_years"),
            "authors": candidate.get("authors"),
            "author_preview": candidate.get("author_preview"),
            "source_datasets": candidate.get("source_datasets"),
            "source_preview": candidate.get("source_preview"),
            "input_row_numbers": candidate.get("input_row_numbers"),
            "decision": decision_value,
            "decision_label": decision_label(decision_value),
        }

    def get_candidate(self, candidate_group_number: int) -> dict[str, Any]:
        candidate = self.candidate_by_id[candidate_group_number]
        decision = self.decisions.get(candidate_group_number, {})
        records = [
            self.records_by_row_number[row_number]
            for row_number in candidate["input_row_numbers_list"]
            if row_number in self.records_by_row_number
        ]
        return {
            **self.candidate_summary(candidate),
            "review_reason": candidate.get("review_reason"),
            "candidate_key": candidate.get("candidate_key"),
            "source_record_ids": candidate.get("source_record_ids"),
            "openalex_ids": candidate.get("openalex_ids"),
            "normalized_dois": candidate.get("normalized_dois"),
            "journals": candidate.get("journals"),
            "urls": candidate.get("urls"),
            "records": records,
            "saved_decision": {
                "decision": decision.get("decision", ""),
                "canonical_input_row_number": decision.get("canonical_input_row_number", ""),
                "notes": decision.get("notes", ""),
                "decided_at": decision.get("decided_at", ""),
            },
        }

    def list_candidates(
        self,
        *,
        query: str = "",
        decision_filter: str = "all",
        method_filter: str = "all",
        page: int = 1,
        page_size: int = 60,
    ) -> dict[str, Any]:
        query = query.casefold().strip()
        filtered: list[dict[str, Any]] = []

        for candidate in self.candidates:
            candidate_id = int(candidate["candidate_group_number"])
            decision = self.decisions.get(candidate_id, {}).get("decision", "")
            method = candidate.get("review_method") or ""

            if decision_filter == "unreviewed" and decision:
                continue
            if decision_filter in {"merge", "keep_separate", "needs_more_check"} and decision != decision_filter:
                continue
            if method_filter != "all" and method != method_filter:
                continue
            if query:
                haystack = " ".join(
                    clean_value(candidate.get(field)) or ""
                    for field in [
                        "titles",
                        "authors",
                        "publication_years",
                        "source_datasets",
                        "source_record_ids",
                        "urls",
                        "input_row_numbers",
                    ]
                ).casefold()
                if query not in haystack:
                    continue
            filtered.append(self.candidate_summary(candidate))

        total = len(filtered)
        page = max(1, page)
        page_size = max(10, min(page_size, 200))
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "items": filtered[start:end],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    def stats(self) -> dict[str, Any]:
        decisions_by_value = {"merge": 0, "keep_separate": 0, "needs_more_check": 0}
        for decision in self.decisions.values():
            value = decision.get("decision", "")
            if value in decisions_by_value:
                decisions_by_value[value] += 1

        reviewed = sum(decisions_by_value.values())
        total = len(self.candidates)
        return {
            "total_candidates": total,
            "reviewed": reviewed,
            "unreviewed": total - reviewed,
            "decisions": decisions_by_value,
            "candidate_records": sum(int(candidate["input_record_count"]) for candidate in self.candidates),
            "records_loaded": len(self.records_by_row_number),
            "decisions_csv": str(self.decisions_csv),
        }


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def text_response(
    handler: BaseHTTPRequestHandler,
    payload: str,
    *,
    content_type: str = "text/html; charset=utf-8",
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    data = payload.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class ReviewRequestHandler(BaseHTTPRequestHandler):
    store: ReviewDataStore

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                text_response(self, HTML_PAGE)
                return
            if parsed.path == "/api/stats":
                json_response(self, self.store.stats())
                return
            if parsed.path == "/api/candidates":
                params = parse_qs(parsed.query)
                payload = self.store.list_candidates(
                    query=params.get("q", [""])[0],
                    decision_filter=params.get("decision", ["all"])[0],
                    method_filter=params.get("method", ["all"])[0],
                    page=int(params.get("page", ["1"])[0]),
                    page_size=int(params.get("page_size", ["60"])[0]),
                )
                json_response(self, payload)
                return
            match = re.fullmatch(r"/api/candidates/(\d+)", parsed.path)
            if match:
                json_response(self, self.store.get_candidate(int(match.group(1))))
                return
            text_response(self, "Not found", status=HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no cover - browser-facing guard
            json_response(self, {"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            match = re.fullmatch(r"/api/candidates/(\d+)/decision", parsed.path)
            if not match:
                text_response(self, "Not found", status=HTTPStatus.NOT_FOUND)
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            decision = self.store.save_decision(
                candidate_group_number=int(match.group(1)),
                decision=payload.get("decision", ""),
                canonical_input_row_number=str(payload.get("canonical_input_row_number", "")),
                notes=str(payload.get("notes", "")),
            )
            json_response(self, {"saved": decision, "stats": self.store.stats()})
        except Exception as exc:  # pragma: no cover - browser-facing guard
            json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)


HTML_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manual Deduplication Review</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dde5;
      --muted: #687181;
      --text: #18202f;
      --accent: #176b87;
      --accent-soft: #e7f3f7;
      --good: #1f7a4f;
      --warn: #986b00;
      --bad: #a23b3b;
      --shadow: 0 1px 2px rgba(16, 24, 40, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    button, input, select, textarea { font: inherit; }
    .app {
      height: 100vh;
      display: grid;
      grid-template-columns: 380px minmax(0, 1fr);
      grid-template-rows: 58px minmax(0, 1fr);
    }
    header {
      grid-column: 1 / 3;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      gap: 18px;
      padding: 0 18px;
    }
    h1 { font-size: 18px; margin: 0; font-weight: 680; }
    .stats {
      display: flex;
      align-items: center;
      gap: 14px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .stat strong { color: var(--text); }
    aside {
      border-right: 1px solid var(--line);
      background: #ffffff;
      min-height: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
    }
    .filters {
      padding: 12px;
      border-bottom: 1px solid var(--line);
      display: grid;
      gap: 10px;
    }
    .filters input, .filters select, textarea, .canonical {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      background: #fff;
      color: var(--text);
    }
    .filter-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .candidate-list {
      overflow: auto;
      min-height: 0;
    }
    .candidate {
      width: 100%;
      text-align: left;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: #fff;
      padding: 12px;
      cursor: pointer;
      display: grid;
      gap: 7px;
    }
    .candidate:hover, .candidate.active { background: var(--accent-soft); }
    .candidate-title {
      font-size: 13px;
      line-height: 1.35;
      font-weight: 650;
    }
    .candidate-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 7px;
      background: #fff;
      color: var(--muted);
      min-height: 22px;
    }
    .badge.merge { color: var(--good); border-color: #b7d9c8; background: #eef8f2; }
    .badge.keep_separate { color: var(--bad); border-color: #e2bcbc; background: #fff1f1; }
    .badge.needs_more_check { color: var(--warn); border-color: #dfcc95; background: #fff8df; }
    .pager {
      border-top: 1px solid var(--line);
      padding: 10px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
    }
    .pager button, .decision-actions button, .record-top a {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      padding: 7px 10px;
      cursor: pointer;
      text-decoration: none;
    }
    .pager button:disabled { opacity: 0.45; cursor: default; }
    main {
      min-width: 0;
      min-height: 0;
      overflow: auto;
      padding: 16px;
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .empty {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px;
      color: var(--muted);
      box-shadow: var(--shadow);
    }
    .candidate-header {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 14px;
      display: grid;
      gap: 10px;
    }
    .candidate-header h2 { margin: 0; font-size: 18px; line-height: 1.35; }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .summary-item {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      min-width: 0;
    }
    .label {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
      margin-bottom: 5px;
    }
    .value {
      font-size: 13px;
      overflow-wrap: anywhere;
      line-height: 1.35;
    }
    .review-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 330px;
      gap: 14px;
      align-items: start;
    }
    .records {
      display: grid;
      gap: 12px;
      min-width: 0;
    }
    .record {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-width: 0;
    }
    .record-top {
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--line);
      padding: 11px 12px;
    }
    .record-title { font-weight: 700; font-size: 14px; overflow-wrap: anywhere; }
    .record-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      padding: 12px;
    }
    .span-2 { grid-column: span 2; }
    .span-3 { grid-column: span 3; }
    details {
      border-top: 1px solid var(--line);
      padding: 10px 12px;
    }
    summary {
      cursor: pointer;
      color: var(--accent);
      font-weight: 650;
      font-size: 13px;
    }
    .field-table {
      margin-top: 10px;
      display: grid;
      grid-template-columns: 210px minmax(0, 1fr);
      border: 1px solid var(--line);
      border-bottom: 0;
    }
    .field-table div {
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .field-name {
      background: #f7f8fa;
      color: var(--muted);
      font-weight: 650;
    }
    .decision-panel {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 12px;
      display: grid;
      gap: 10px;
      position: sticky;
      top: 16px;
    }
    .decision-panel h3 { margin: 0; font-size: 15px; }
    .decision-options {
      display: grid;
      gap: 7px;
    }
    .radio-row {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 9px;
      display: flex;
      gap: 8px;
      align-items: center;
      cursor: pointer;
    }
    textarea {
      min-height: 110px;
      resize: vertical;
    }
    .decision-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .decision-actions .primary {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .save-status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 980px) {
      .app { grid-template-columns: 1fr; grid-template-rows: auto 360px minmax(0, 1fr); }
      header { grid-column: 1; flex-wrap: wrap; min-height: 58px; padding: 10px 14px; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .review-grid { grid-template-columns: 1fr; }
      .decision-panel { position: static; }
      .summary-grid, .record-grid { grid-template-columns: 1fr; }
      .span-2, .span-3 { grid-column: span 1; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <h1>Manual Deduplication Review</h1>
      <div class="stats" id="stats"></div>
    </header>
    <aside>
      <div class="filters">
        <input id="search" placeholder="Search title, author, source, URL, row number">
        <div class="filter-row">
          <select id="decisionFilter">
            <option value="all">All decisions</option>
            <option value="unreviewed">Unreviewed</option>
            <option value="merge">Merge</option>
            <option value="keep_separate">Keep separate</option>
            <option value="needs_more_check">Needs more check</option>
          </select>
          <select id="methodFilter">
            <option value="all">All methods</option>
            <option value="title_year_first_author">Title + year + author</option>
            <option value="title_year">Title + year</option>
          </select>
        </div>
      </div>
      <div class="candidate-list" id="candidateList"></div>
      <div class="pager">
        <button id="prevPage">Previous</button>
        <span id="pageInfo"></span>
        <button id="nextPage">Next</button>
      </div>
    </aside>
    <main id="detail">
      <div class="empty">Loading candidates…</div>
    </main>
  </div>
  <script>
    const state = {
      page: 1,
      pageSize: 60,
      totalPages: 1,
      selectedId: null,
      currentCandidate: null,
      debounce: null,
    };

    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));

    function badgeClass(decision) {
      return decision || "";
    }

    function field(label, value, span = "") {
      if (value === undefined || value === null || value === "") return "";
      return `<div class="${span}"><div class="label">${esc(label)}</div><div class="value">${linkify(value)}</div></div>`;
    }

    function linkify(value) {
      const text = esc(value);
      if (/^https?:\/\//i.test(String(value))) {
        return `<a href="${text}" target="_blank" rel="noreferrer">${text}</a>`;
      }
      return text;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, options);
      const payload = await response.json();
      if (!response.ok || payload.error) throw new Error(payload.error || "Request failed");
      return payload;
    }

    async function loadStats() {
      const stats = await api("/api/stats");
      $("stats").innerHTML = `
        <span class="stat"><strong>${stats.total_candidates}</strong> groups</span>
        <span class="stat"><strong>${stats.reviewed}</strong> reviewed</span>
        <span class="stat"><strong>${stats.unreviewed}</strong> open</span>
        <span class="stat"><strong>${stats.candidate_records}</strong> records</span>
      `;
    }

    async function loadCandidates({ keepSelection = true } = {}) {
      const params = new URLSearchParams({
        q: $("search").value,
        decision: $("decisionFilter").value,
        method: $("methodFilter").value,
        page: state.page,
        page_size: state.pageSize,
      });
      const payload = await api(`/api/candidates?${params}`);
      state.totalPages = payload.total_pages;
      $("pageInfo").textContent = `${payload.page} / ${payload.total_pages} · ${payload.total} groups`;
      $("prevPage").disabled = payload.page <= 1;
      $("nextPage").disabled = payload.page >= payload.total_pages;
      renderCandidateList(payload.items);
      if (!keepSelection || !state.selectedId || !payload.items.some((item) => item.candidate_group_number === state.selectedId)) {
        if (payload.items[0]) selectCandidate(payload.items[0].candidate_group_number);
        else $("detail").innerHTML = `<div class="empty">No matching candidates.</div>`;
      }
    }

    function renderCandidateList(items) {
      $("candidateList").innerHTML = items.map((item) => `
        <button class="candidate ${item.candidate_group_number === state.selectedId ? "active" : ""}" data-id="${item.candidate_group_number}">
          <div class="candidate-title">${esc(item.title_preview || item.titles || "Untitled")}</div>
          <div class="candidate-meta">
            <span class="badge">#${item.candidate_group_number}</span>
            <span class="badge">${item.input_record_count} records</span>
            <span class="badge">${esc(item.publication_years || "No year")}</span>
            <span class="badge ${badgeClass(item.decision)}">${esc(item.decision_label)}</span>
          </div>
          <div class="candidate-meta">
            <span>${esc(item.author_preview || "No author")}</span>
          </div>
          <div class="candidate-meta">
            <span>${esc(item.source_preview || "No source")}</span>
          </div>
        </button>
      `).join("");
      document.querySelectorAll(".candidate").forEach((button) => {
        button.addEventListener("click", () => selectCandidate(Number(button.dataset.id)));
      });
    }

    async function selectCandidate(id) {
      state.selectedId = id;
      document.querySelectorAll(".candidate").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.id) === id);
      });
      const candidate = await api(`/api/candidates/${id}`);
      state.currentCandidate = candidate;
      renderDetail(candidate);
    }

    function renderDetail(candidate) {
      $("detail").innerHTML = `
        <section class="candidate-header">
          <h2>${esc(candidate.titles || "Untitled candidate group")}</h2>
          <div class="summary-grid">
            ${field("Candidate", `#${candidate.candidate_group_number}`)}
            ${field("Method", candidate.review_method)}
            ${field("Records", candidate.input_record_count)}
            ${field("Input Rows", candidate.input_row_numbers)}
            ${field("Years", candidate.publication_years)}
            ${field("Authors", candidate.authors, "span-2")}
            ${field("Sources", candidate.source_datasets)}
            ${field("Journals", candidate.journals, "span-2")}
            ${field("Reason", candidate.review_reason, "span-2")}
          </div>
        </section>
        <section class="review-grid">
          <div class="records">
            ${candidate.records.map(renderRecord).join("")}
          </div>
          ${renderDecisionPanel(candidate)}
        </section>
      `;
      const saved = candidate.saved_decision || {};
      const decision = saved.decision || "";
      document.querySelectorAll("input[name=decision]").forEach((input) => {
        input.checked = input.value === decision;
      });
      $("canonicalInput").value = saved.canonical_input_row_number || "";
      $("notes").value = saved.notes || "";
      $("saveDecision").addEventListener("click", saveDecision);
      $("clearDecision").addEventListener("click", clearDecision);
    }

    function renderRecord(record) {
      const url = record.url || record.landing_page_url || record.pdf_url;
      return `
        <article class="record">
          <div class="record-top">
            <div>
              <div class="record-title">${esc(record.title || "Untitled record")}</div>
              <div class="candidate-meta">
                <span class="badge">Row ${record.input_row_number}</span>
                <span class="badge">${esc(record.source_dataset || "No source")}</span>
                <span class="badge">${esc(record.publication_year || "No year")}</span>
              </div>
            </div>
            ${url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">Open URL</a>` : ""}
          </div>
          <div class="record-grid">
            ${field("DOI", record.doi)}
            ${field("Source Record ID", record.source_record_id)}
            ${field("OpenAlex ID", record.openalex_id)}
            ${field("Publication Date", record.publication_date)}
            ${field("Type", record.publication_type || record.type)}
            ${field("Language", record.language)}
            ${field("Authors", record.author_names || record.authors, "span-2")}
            ${field("Affiliations", record.author_affiliations)}
            ${field("Publisher", record.publisher)}
            ${field("Journal", record.journal || record.container_title, "span-2")}
            ${field("ISSN", record.issn)}
            ${field("Volume / Issue / Pages", [record.volume, record.issue, record.page || [record.first_page, record.last_page].filter(Boolean).join("-")].filter(Boolean).join(" · "))}
            ${field("Citation Count", record.cited_by_count)}
            ${field("Reference Count", record.reference_count)}
            ${field("OA Status", record.oa_status)}
            ${field("Keywords", record.keywords, "span-3")}
            ${field("Topics", record.topics || record.concepts, "span-3")}
            ${field("Abstract", record.abstract, "span-3")}
            ${field("Raw Identifiers", record.raw_identifiers, "span-3")}
          </div>
          <details>
            <summary>All non-empty fields</summary>
            <div class="field-table">
              ${record.all_non_empty_fields.map((item) => `
                <div class="field-name">${esc(item.field)}</div>
                <div>${linkify(item.value)}</div>
              `).join("")}
            </div>
          </details>
        </article>
      `;
    }

    function renderDecisionPanel(candidate) {
      const canonicalOptions = candidate.records.map((record) =>
        `<option value="${record.input_row_number}">Row ${record.input_row_number} · ${esc(record.source_dataset || "")}</option>`
      ).join("");
      return `
        <aside class="decision-panel">
          <h3>Decision</h3>
          <div class="decision-options">
            ${radio("merge", "Merge")}
            ${radio("keep_separate", "Keep separate")}
            ${radio("needs_more_check", "Needs more check")}
          </div>
          <div>
            <div class="label">Canonical Row</div>
            <select id="canonicalInput" class="canonical">
              <option value="">No canonical row</option>
              ${canonicalOptions}
            </select>
          </div>
          <div>
            <div class="label">Notes</div>
            <textarea id="notes"></textarea>
          </div>
          <div class="decision-actions">
            <button class="primary" id="saveDecision">Save</button>
            <button id="clearDecision">Clear</button>
          </div>
          <div class="save-status" id="saveStatus">${candidate.saved_decision?.decided_at ? `Saved ${esc(candidate.saved_decision.decided_at)}` : ""}</div>
        </aside>
      `;
    }

    function radio(value, label) {
      return `<label class="radio-row"><input type="radio" name="decision" value="${value}"><span>${label}</span></label>`;
    }

    async function saveDecision() {
      const selected = document.querySelector("input[name=decision]:checked");
      if (!selected) {
        $("saveStatus").textContent = "Select a decision.";
        return;
      }
      $("saveStatus").textContent = "Saving…";
      const payload = {
        decision: selected.value,
        canonical_input_row_number: $("canonicalInput").value,
        notes: $("notes").value,
      };
      const response = await api(`/api/candidates/${state.selectedId}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      $("saveStatus").textContent = `Saved ${response.saved.decided_at}`;
      await loadStats();
      await loadCandidates({ keepSelection: true });
    }

    async function clearDecision() {
      $("saveStatus").textContent = "Clearing…";
      await api(`/api/candidates/${state.selectedId}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: "", canonical_input_row_number: "", notes: "" }),
      });
      await loadStats();
      await loadCandidates({ keepSelection: true });
      await selectCandidate(state.selectedId);
    }

    function resetAndLoad() {
      state.page = 1;
      loadCandidates({ keepSelection: false }).catch(showError);
    }

    function showError(error) {
      $("detail").innerHTML = `<div class="empty">${esc(error.message || error)}</div>`;
    }

    $("search").addEventListener("input", () => {
      clearTimeout(state.debounce);
      state.debounce = setTimeout(resetAndLoad, 250);
    });
    $("decisionFilter").addEventListener("change", resetAndLoad);
    $("methodFilter").addEventListener("change", resetAndLoad);
    $("prevPage").addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        loadCandidates().catch(showError);
      }
    });
    $("nextPage").addEventListener("click", () => {
      if (state.page < state.totalPages) {
        state.page += 1;
        loadCandidates().catch(showError);
      }
    });

    loadStats().then(() => loadCandidates({ keepSelection: false })).catch(showError);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the manual deduplication review UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--candidates-csv", type=Path, default=DEFAULT_CANDIDATES_CSV)
    parser.add_argument("--all-records-csv", type=Path, default=DEFAULT_ALL_RECORDS_CSV)
    parser.add_argument("--decisions-csv", type=Path, default=DEFAULT_DECISIONS_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Loading manual-review data...", flush=True)
    store = ReviewDataStore(
        candidates_csv=args.candidates_csv,
        all_records_csv=args.all_records_csv,
        decisions_csv=args.decisions_csv,
    )
    ReviewRequestHandler.store = store
    server = ThreadingHTTPServer((args.host, args.port), ReviewRequestHandler)
    print(f"Loaded {len(store.candidates):,} candidate groups.", flush=True)
    print(f"Loaded {len(store.records_by_row_number):,} candidate source records.", flush=True)
    print(f"Decisions file: {args.decisions_csv}", flush=True)
    print(f"Open http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
