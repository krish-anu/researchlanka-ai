from __future__ import annotations

import json
from typing import Any


PUBLICATION_CATEGORIES = {
    "journal-article": "journal",
    "proceedings-article": "conference",
    "book-chapter": "book",
    "book": "book",
    "posted-content": "preprint",
    "report": "report",
    "dissertation": "thesis",
    "dataset": "dataset",
}


def normalize_crossref(work: dict[str, Any]) -> dict:

    event = work.get("event", {})

    funders = []

    for f in work.get("funder", []):
        funders.append(
            {
                "name": f.get("name"),
                "doi": f.get("DOI"),
                "award": f.get("award"),
            }
        )

    licenses = work.get("license", [])

    return {
        "doi": work.get("DOI"),
        "publisher": work.get("publisher"),
        "issn": work.get("ISSN"),
        "volume": work.get("volume"),
        "issue": work.get("issue"),
        "page": work.get("page"),
        "language": work.get("language"),
        "publication_category": PUBLICATION_CATEGORIES.get(
            work.get("type"),
            "other",
        ),
        "reference_count": work.get("reference-count"),
        "conference_name": event.get("name"),
        "conference_location": event.get("location"),
        "conference_acronym": event.get("acronym"),
        "funders": json.dumps(
            funders,
            ensure_ascii=False,
        ),
        "license_url": licenses[0]["URL"] if licenses else None,
        "references_json": json.dumps(
            work.get(
                "reference",
                [],
            ),
            ensure_ascii=False,
        ),
    }
