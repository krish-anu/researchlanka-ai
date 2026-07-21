from typing import Any

def reduce_work(work: dict[str, Any]) -> dict[str, Any]:

    event = work.get("event", {})

    return {
        "reference-count": work.get("reference-count"),
        "publisher": work.get("publisher"),
        "issue": work.get("issue"),
        "abstract": work.get("abstract"),
        "DOI": work.get("DOI"),
        "type": work.get("type"),
        "is-referenced-by-count": work.get("is-referenced-by-count"),
        "title": work.get("title"),
        "volume": work.get("volume"),
        "author": work.get("author"),
        "container-title": work.get("container-title"),
        "URL": work.get("URL"),
        "ISSN": work.get("ISSN"),
        "issued.date-parts": work.get("issued", {}).get("date-parts"),
        "published.date-parts": work.get("published", {}).get("date-parts"),
        "created.date-parts": work.get("created", {}).get("date-parts"),
        "license": work.get("license"),
        "page": work.get("page"),
        "reference": work.get("reference"),
        "event.name": event.get("name"),
        "event.location": event.get("location"),
        "event.start.date-parts": event.get("start", {}).get("date-parts"),
        "event.end.date-parts": event.get("end", {}).get("date-parts"),
        "language": work.get("language"),
        "editor": work.get("editor"),
        "funder": work.get("funder"),
        "article-number": work.get("article-number"),
        "publisher-location": work.get("publisher-location"),
        "event.acronym": event.get("acronym"),
        "group-title": work.get("group-title"),
        "subtype": work.get("subtype"),
        "event.sponsor": event.get("sponsor"),
        "original-title": work.get("original-title"),
        "subtitle": work.get("subtitle"),
    }
