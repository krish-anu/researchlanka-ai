"""Route dispatch for author profiles, shared by both API transports.

Three audiences, three guards:

* `/researchers/profiles...` is public and read-only — approved profiles only.
* `/author/...` is the signed-in author's own workspace. It needs the backend
  admin token (only the frontend server holds it) plus the actor headers that
  name the account; the service then checks the actor owns what they touch.
* `/admin/authors/...` is the review queue. The token proves the frontend sent
  it; the frontend has already checked the actor holds admin rights.

Each function returns None for a path it does not own, so callers fall
through to the rest of their routing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote

from src.api.core.constants import API_PREFIX
from src.api.core.query import first, parse_positive_int
from src.api.services import author_profiles as authors
from src.api.services import author_reference as reference
from src.api.services.incremental_admin import require_admin_api_token


PUBLIC_PROFILES_PATH = f"{API_PREFIX}/researchers/profiles"
AUTHOR_PREFIX = f"{API_PREFIX}/author"
ADMIN_AUTHORS_PREFIX = f"{API_PREFIX}/admin/authors"
# Public, read-only reference lookups behind the author forms.
LOOKUP_PREFIX = f"{API_PREFIX}/lookup"
PROFILE_PATH_PATTERN = re.compile(rf"{re.escape(PUBLIC_PROFILES_PATH)}/([^/]+)(/publications)?")


def owns_path(path: str) -> bool:
    return (
        path == PUBLIC_PROFILES_PATH
        or path.startswith(f"{PUBLIC_PROFILES_PATH}/")
        or path == AUTHOR_PREFIX
        or path.startswith(f"{AUTHOR_PREFIX}/")
        or path.startswith(f"{ADMIN_AUTHORS_PREFIX}/")
        or path.startswith(f"{LOOKUP_PREFIX}/")
    )


def _optional(query: Mapping[str, list[str]], key: str) -> str | None:
    value = first(dict(query), key)
    return value or None


def route_author_get(
    service: Any,
    path: str,
    query: dict[str, list[str]],
    headers: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    if not owns_path(path):
        return None
    meta = service._meta()

    if path == PUBLIC_PROFILES_PATH:
        limit = parse_positive_int(query, "limit", default=20)
        data = authors.with_connection(
            lambda connection: authors.list_public_profiles(
                connection,
                name=_optional(query, "name"),
                q=_optional(query, "q"),
                limit=limit,
            )
        )
        return {"data": data, "meta": meta}

    if path.startswith(f"{LOOKUP_PREFIX}/"):
        return _route_lookup(path, query, meta)

    match = PROFILE_PATH_PATTERN.fullmatch(path)
    if match:
        slug = unquote(match.group(1))
        if match.group(2):
            page = parse_positive_int(query, "page", default=1)
            page_size = min(parse_positive_int(query, "page_size", default=25), 100)
            return authors.with_connection(
                lambda connection: authors.public_profile_publications(
                    connection, slug, page=page, page_size=page_size, meta=meta
                )
            )
        return {
            "data": authors.with_connection(lambda connection: authors.public_profile(connection, slug)),
            "meta": meta,
        }

    require_admin_api_token(headers)
    actor = authors.actor_from_headers(headers)

    if path == f"{AUTHOR_PREFIX}/me":
        data = authors.with_connection(lambda connection: authors.get_author_workspace(connection, actor))
        return {"data": data, "meta": meta}
    if path == f"{AUTHOR_PREFIX}/publication":
        publication_key = str(_optional(query, "publication_key") or "")
        data = authors.with_connection(
            lambda connection: authors.get_editable_publication(connection, actor, publication_key)
        )
        return {"data": data, "meta": meta}
    if path == f"{AUTHOR_PREFIX}/lookup/doi":
        doi = str(_optional(query, "doi") or "")
        authors.require_actor(actor)
        data = authors.with_connection(lambda connection: authors.lookup_publication_doi(connection, doi))
        return {"data": data, "meta": meta}

    if path == f"{ADMIN_AUTHORS_PREFIX}/summary":
        return {"data": authors.with_connection(authors.admin_summary), "meta": meta}
    if path == f"{ADMIN_AUTHORS_PREFIX}/applications":
        status = _optional(query, "status")
        page = parse_positive_int(query, "page", default=1)
        page_size = parse_positive_int(query, "page_size", default=20)
        data = authors.with_connection(
            lambda connection: authors.list_applications(
                connection,
                status=None if status == "all" else (status or "pending"),
                page=page,
                page_size=page_size,
            )
        )
        return {"data": data, "meta": meta}
    if path == f"{ADMIN_AUTHORS_PREFIX}/claims":
        page = parse_positive_int(query, "page", default=1)
        data = authors.with_connection(lambda connection: authors.list_claim_requests(connection, page=page))
        return {"data": data, "meta": meta}
    if path == f"{ADMIN_AUTHORS_PREFIX}/contributions":
        status = _optional(query, "status")
        page = parse_positive_int(query, "page", default=1)
        page_size = parse_positive_int(query, "page_size", default=20)
        data = authors.with_connection(
            lambda connection: authors.list_contributions(
                connection,
                status=None if status == "all" else (status or "pending"),
                contribution_type=_optional(query, "type"),
                page=page,
                page_size=page_size,
            )
        )
        return {"data": data, "meta": meta}
    return None


def _route_lookup(path: str, query: dict[str, list[str]], meta: dict[str, Any]) -> dict[str, Any] | None:
    term = str(_optional(query, "q") or "")
    if path == f"{LOOKUP_PREFIX}/authors":
        data = authors.with_connection(lambda connection: reference.lookup_author_names(connection, term))
    elif path == f"{LOOKUP_PREFIX}/institutions":
        data = authors.with_connection(lambda connection: reference.lookup_institutions(connection, term))
    elif path == f"{LOOKUP_PREFIX}/categories":
        data = authors.with_connection(reference.category_options)
    elif path == f"{LOOKUP_PREFIX}/claimed-names":
        names = list(query.get("name", []))
        data = authors.with_connection(lambda connection: authors.profiles_by_names(connection, names))
    else:
        return None
    return {"data": data, "meta": meta}


AUTHOR_POST_ROUTES = {
    f"{AUTHOR_PREFIX}/applications": authors.submit_application,
    f"{AUTHOR_PREFIX}/profile": authors.update_profile,
    f"{AUTHOR_PREFIX}/claims": authors.request_claims,
    f"{AUTHOR_PREFIX}/claims/remove": authors.remove_claim,
    f"{AUTHOR_PREFIX}/contributions/edit": authors.propose_edit,
    f"{AUTHOR_PREFIX}/contributions/new": authors.submit_new_publication,
    f"{AUTHOR_PREFIX}/contributions/withdraw": authors.withdraw_contribution,
    f"{ADMIN_AUTHORS_PREFIX}/applications/decide": authors.decide_application,
    f"{ADMIN_AUTHORS_PREFIX}/claims/decide": authors.decide_claims,
    f"{ADMIN_AUTHORS_PREFIX}/contributions/decide": authors.decide_contribution,
}


def route_author_post(
    service: Any,
    path: str,
    payload: dict[str, Any],
    headers: Mapping[str, str] | None,
) -> dict[str, Any] | None:
    handler = AUTHOR_POST_ROUTES.get(path)
    if handler is None:
        return None
    meta = service._meta()
    require_admin_api_token(headers)
    actor = authors.actor_from_headers(headers)
    data = authors.with_connection(lambda connection: handler(connection, actor, payload))
    return {"data": data, "meta": meta}
