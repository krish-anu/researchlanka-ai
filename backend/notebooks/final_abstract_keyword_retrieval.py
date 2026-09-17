# ============================================================
# FINAL ABSTRACT + KEYWORDS RETRIEVAL PIPELINE
#
# Single script, single pass. For every record missing an
# abstract, tries sources in order of reliability:
#
#   1. Direct DOI resolve (publisher page)          - free, fast
#   2. Crossref API                                  - free, fast
#   3. OpenAlex API                                   - free, fast
#   4. Europe PMC API                                 - free, fast
#   5. OA links returned by Crossref/OpenAlex         - free
#   6. Google search -> ResearchGate/arXiv/Zenodo/etc - free
#   7. Semantic Scholar API (LAST, rate-limit safe)   - free tier,
#                                                        paced +
#                                                        backoff
#
# Every page fetch pulls BOTH abstract and keywords in the
# same request (no separate keyword pass).
#
# Verifies each candidate (DOI match, or title+author match)
# before accepting it, exactly like your original two scripts.
#
# Output: ONE Excel file = original dataset + filled-in
# abstract/keywords columns + audit columns.
# ============================================================

import re
import json
import time
import random
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


# ============================================================
# CONFIG - edit these paths/settings
# ============================================================

INPUT_FILE = "/home/asma/Projects/researchlanka-ai/backend/data/processed/common/final_ai_corpus_human_audit_sample_stratified.xlsx"

OUTPUT_FILE = "/home/asma/Projects/researchlanka-ai/backend/data/processed/common/final_ai_corpus_FINAL_filled.xlsx"

AUDIT_FILE = "/home/asma/Projects/researchlanka-ai/backend/data/processed/common/final_ai_corpus_FINAL_audit.xlsx"
# Reliable sources run in parallel - safe to keep higher.
MAX_WORKERS = 8

# Semantic Scholar (free/unauthenticated tier) is only used as a
# last resort, and is called from a single dedicated worker with
# pacing, so this does NOT need to be low - it only affects the
# other sources.
REQUEST_TIMEOUT = 20

# Semantic Scholar free tier: keep this >= 1.0s between calls.
# If you get an API key later, drop this to ~0.1s and add the
# key below.
SEMANTIC_SCHOLAR_DELAY = 1.2
SEMANTIC_SCHOLAR_API_KEY = ""  # optional, leave blank for free tier

MAX_GOOGLE_RESULTS = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

ALLOWED_SEARCH_DOMAINS = [
    "researchgate.net",
    "arxiv.org",
    "zenodo.org",
    "springer.com",
    "link.springer.com",
    "sciencedirect.com",
    "mdpi.com",
    "frontiersin.org",
    "wiley.com",
    "tandfonline.com",
    "ieeexplore.ieee.org",
    "semanticscholar.org",
]


# ============================================================
# LOAD DATA
# ============================================================

df = pd.read_excel(INPUT_FILE)
print(f"Total records: {len(df):,}")


def find_column(possible_names):
    lower_columns = {str(col).lower().strip(): col for col in df.columns}
    for name in possible_names:
        if name.lower() in lower_columns:
            return lower_columns[name.lower()]
    return None


DOI_COL = find_column(["doi_url", "doi", "DOI"])
TITLE_COL = find_column(["title", "Title"])
AUTHOR_COL = find_column(["authors", "author", "Authors", "Author"])
KEYWORDS_COL = find_column(
    ["keywords", "keyword", "Keywords", "author_keywords", "author keywords"]
)
ABSTRACT_COL = find_column(["abstract", "Abstract"])

print("\nDetected columns:")
print("DOI      :", DOI_COL)
print("Title    :", TITLE_COL)
print("Authors  :", AUTHOR_COL)
print("Keywords :", KEYWORDS_COL)
print("Abstract :", ABSTRACT_COL)

if DOI_COL is None:
    raise ValueError("Could not find DOI column.")
if TITLE_COL is None:
    raise ValueError("Could not find title column.")
if ABSTRACT_COL is None:
    raise ValueError("Could not find abstract column.")

# If there is no keywords column, we still create one so scraped
# keywords are never lost.
if KEYWORDS_COL is None:
    KEYWORDS_COL = "keywords"
    if KEYWORDS_COL not in df.columns:
        df[KEYWORDS_COL] = None


# ============================================================
# TEXT NORMALIZATION
# ============================================================


def clean_text(text):
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    text = str(text)
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def normalize_doi(doi):
    if doi is None or (isinstance(doi, float) and pd.isna(doi)):
        return None
    doi = str(doi).strip()
    if not doi:
        return None
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    doi = doi.strip().rstrip(".,;:)]}")
    return doi.lower()


def normalize_title(title):
    title = clean_text(title)
    if not title:
        return ""
    title = title.lower().replace("–", "-").replace("—", "-")
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def normalize_author(author):
    author = clean_text(author)
    if not author:
        return ""
    author = author.lower()
    author = re.sub(r"[^\w\s]", " ", author)
    return re.sub(r"\s+", " ", author).strip()


def first_author(value):
    if not value:
        return ""
    parts = re.split(r";|\||\n", str(value))
    return parts[0].strip() if parts else str(value).strip()


def valid_abstract(text):
    text = clean_text(text)
    if not text or len(text) < 80:
        return False
    bad = [
        "abstract not available",
        "no abstract available",
        "abstract unavailable",
        "coming soon",
    ]
    return text.lower() not in bad


# ============================================================
# HTML METADATA EXTRACTION (abstract + keywords together)
# ============================================================


def extract_metadata_from_html(html):
    result = {"title": None, "doi": None, "authors": None, "abstract": None, "keywords": None}
    if not html:
        return result

    soup = BeautifulSoup(html, "html.parser")

    meta = {}
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or tag.get("itemprop") or "").lower().strip()
        content = tag.get("content")
        if name and content:
            meta.setdefault(name, []).append(clean_text(content))

    # ---- Title ----
    for key in ["citation_title", "dc.title", "og:title", "title"]:
        if key in meta and meta[key]:
            result["title"] = meta[key][0]
            break
    if not result["title"]:
        title_tag = soup.find("title")
        if title_tag:
            result["title"] = clean_text(title_tag.get_text())

    # ---- DOI ----
    for key in ["citation_doi", "dc.identifier", "doi"]:
        if key in meta:
            for value in meta[key]:
                doi = normalize_doi(value)
                if doi and "10." in doi:
                    result["doi"] = doi
                    break
        if result["doi"]:
            break

    # ---- Authors ----
    author_values = []
    for key in ["citation_author", "dc.creator", "author", "article:author"]:
        if key in meta:
            author_values.extend(meta[key])
    if author_values:
        result["authors"] = "; ".join(dict.fromkeys(x for x in author_values if x))

    # ---- Abstract ----
    for key in ["citation_abstract", "dc.description", "description", "abstract"]:
        if key in meta:
            for value in meta[key]:
                if valid_abstract(value):
                    result["abstract"] = value
                    break
        if result["abstract"]:
            break

    # ---- Keywords ----
    keyword_values = []
    for key in ["citation_keywords", "keywords", "keyword", "dc.subject"]:
        if key in meta:
            keyword_values.extend(meta[key])
    if keyword_values:
        result["keywords"] = "; ".join(dict.fromkeys(x for x in keyword_values if x))

    # ---- JSON-LD (fills any still-missing fields) ----
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
            objects = data if isinstance(data, list) else [data]
            for obj in objects:
                if not isinstance(obj, dict):
                    continue

                if not result["title"]:
                    result["title"] = clean_text(obj.get("headline") or obj.get("name"))

                if not result["doi"]:
                    doi_val = obj.get("sameAs") or obj.get("identifier")
                    if isinstance(doi_val, str):
                        normalized = normalize_doi(doi_val)
                        if normalized and "10." in normalized:
                            result["doi"] = normalized

                if not result["abstract"]:
                    abstract = obj.get("abstract") or obj.get("description")
                    if valid_abstract(abstract):
                        result["abstract"] = clean_text(abstract)

                if not result["authors"]:
                    authors = obj.get("author")
                    if isinstance(authors, list):
                        names = []
                        for a in authors:
                            name = a.get("name") if isinstance(a, dict) else str(a)
                            if name:
                                names.append(clean_text(name))
                        if names:
                            result["authors"] = "; ".join(names)
                    elif isinstance(authors, dict):
                        result["authors"] = clean_text(authors.get("name"))

                if not result["keywords"]:
                    keywords = obj.get("keywords")
                    if isinstance(keywords, list):
                        result["keywords"] = "; ".join(clean_text(x) for x in keywords if x)
                    elif keywords:
                        result["keywords"] = clean_text(keywords)
        except Exception:
            pass

    # ---- HTML abstract section fallback ----
    if not result["abstract"]:
        selectors = ['[class*="abstract"]', '[id*="abstract"]', '[class*="Abstract"]', '[id*="Abstract"]']
        for selector in selectors:
            for element in soup.select(selector):
                text = clean_text(element.get_text(" ", strip=True))
                if text and text.lower() not in ["abstract", "abstract:"] and valid_abstract(text):
                    result["abstract"] = text
                    break
            if result["abstract"]:
                break

    # ---- HTML keywords section fallback ----
    if not result["keywords"]:
        selectors = ['[class*="keyword"]', '[id*="keyword"]', '[class*="Keyword"]', '[id*="Keyword"]']
        for selector in selectors:
            for element in soup.select(selector):
                text = clean_text(element.get_text(" ", strip=True))
                if text and 3 < len(text) < 500 and text.lower() not in ["keywords", "keywords:"]:
                    result["keywords"] = text
                    break
            if result["keywords"]:
                break

    return result


# ============================================================
# HTTP HELPERS
# ============================================================


def fetch_page(url, extra_headers=None):
    try:
        headers = {**HEADERS, **(extra_headers or {})}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return response
    except Exception:
        return None


def get_with_backoff(url, headers=None, params=None, max_retries=4, base_delay=2.0):
    """Generic retrying GET with exponential backoff + Retry-After support."""
    merged_headers = {**HEADERS, **(headers or {})}
    response = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=merged_headers, params=params, timeout=REQUEST_TIMEOUT)
        except Exception:
            time.sleep(base_delay * (attempt + 1))
            continue

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else base_delay * (2 ** attempt)
            wait += random.uniform(0, 1.0)
            time.sleep(wait)
            continue

        return response
    return response


# ============================================================
# SOURCE 1: DIRECT DOI RESOLVE
# ============================================================


def fetch_doi_source(doi_url):
    response = fetch_page(doi_url)
    if response is None or response.status_code in (403, 202) or response.status_code != 200:
        return None
    metadata = extract_metadata_from_html(response.text)
    if valid_abstract(metadata["abstract"]):
        return {**metadata, "source_url": response.url, "source_type": "DOI"}
    return None


# ============================================================
# SOURCE 2: CROSSREF
# ============================================================


def fetch_crossref(doi):
    if not doi:
        return None, []
    try:
        url = "https://api.crossref.org/works/" + quote(doi, safe="")
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None, []
        message = response.json().get("message", {})

        links = [l.get("URL") for l in message.get("link", []) if l.get("URL")]

        abstract = clean_text(message.get("abstract"))
        if not valid_abstract(abstract):
            return None, links

        titles = message.get("title", [])
        title = titles[0] if titles else None

        authors = []
        for a in message.get("author", []):
            name = f"{a.get('given', '')} {a.get('family', '')}".strip()
            if name:
                authors.append(name)

        subjects = message.get("subject", [])
        keywords = "; ".join(subjects) if subjects else None

        return {
            "doi": normalize_doi(message.get("DOI")),
            "title": clean_text(title),
            "authors": "; ".join(authors),
            "abstract": abstract,
            "keywords": keywords,
            "source_url": url,
            "source_type": "Crossref",
        }, links
    except Exception:
        return None, []


# ============================================================
# SOURCE 3: OPENALEX
# ============================================================


def fetch_openalex(doi):
    if not doi:
        return None, []
    try:
        url = "https://api.openalex.org/works/https://doi.org/" + quote(doi, safe="")
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None, []
        data = response.json()

        links = []
        for loc in data.get("locations", []):
            landing = loc.get("landing_page_url")
            if landing:
                links.append(landing)
        best = data.get("best_oa_location")
        if best and best.get("landing_page_url"):
            links.append(best["landing_page_url"])
        links = list(dict.fromkeys(links))

        inverted = data.get("abstract_inverted_index")
        if not inverted:
            return None, links

        words = []
        for word, positions in inverted.items():
            for position in positions:
                words.append((position, word))
        words.sort()
        abstract = clean_text(" ".join(word for _, word in words))
        if not valid_abstract(abstract):
            return None, links

        title = clean_text(data.get("title"))
        authors = []
        for a in data.get("authorships", []):
            name = a.get("author", {}).get("display_name")
            if name:
                authors.append(name)

        keywords_list = [k.get("display_name") for k in data.get("keywords", []) if k.get("display_name")]
        keywords = "; ".join(keywords_list) if keywords_list else None

        return {
            "doi": normalize_doi(doi),
            "title": title,
            "authors": "; ".join(authors),
            "abstract": abstract,
            "keywords": keywords,
            "source_url": data.get("id"),
            "source_type": "OpenAlex",
        }, links
    except Exception:
        return None, []


# ============================================================
# SOURCE 4: EUROPE PMC
# ============================================================


def fetch_europe_pmc(doi):
    if not doi:
        return None
    try:
        query = f'DOI:"{doi}"'
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=" + quote(query) + "&format=json"
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return None
        results = response.json().get("resultList", {}).get("result", [])
        if not results:
            return None
        paper = results[0]
        abstract = clean_text(paper.get("abstractText", ""))
        if not valid_abstract(abstract):
            return None
        return {
            "doi": normalize_doi(paper.get("doi", "")),
            "title": clean_text(paper.get("title", "")),
            "authors": paper.get("authorString", ""),
            "abstract": abstract,
            "keywords": None,
            "source_url": url,
            "source_type": "EuropePMC",
        }
    except Exception:
        return None


# ============================================================
# SOURCE 5: OA LINKS (from Crossref/OpenAlex)
# ============================================================


def fetch_oa_links(links):
    for link in links[:5]:
        response = fetch_page(link)
        if response is None or response.status_code != 200:
            continue
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            continue
        metadata = extract_metadata_from_html(response.text)
        if valid_abstract(metadata["abstract"]):
            return {**metadata, "source_url": response.url, "source_type": "OA_LINK"}
    return None


# ============================================================
# SOURCE 6: GOOGLE SEARCH -> ResearchGate / arXiv / Zenodo / etc
# ============================================================


def google_search(query):
    url = "https://www.google.com/search?q=" + quote(query) + f"&num={MAX_GOOGLE_RESULTS}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue
            if href.startswith("/url?q="):
                href = href.split("/url?q=", 1)[1].split("&", 1)[0]
            if href.startswith("http"):
                urls.append(href)
        return list(dict.fromkeys(urls))
    except Exception:
        return []


def fetch_from_web_search(title, doi, authors):
    queries = []
    first = first_author(authors)

    if doi:
        queries += [f'"{doi}"', f'"{doi}" ResearchGate']
    if title:
        queries += [f'"{title}"', f'"{title}" ResearchGate']
    if title and first:
        queries += [f'"{title}" "{first}"']
    if doi:
        queries += [f'site:zenodo.org "{doi}"', f'site:arxiv.org "{doi}"']
    if title:
        queries += [f'site:zenodo.org "{title}"', f'site:arxiv.org "{title}"']

    seen = set()
    for query in queries:
        for url in google_search(query):
            if url in seen:
                continue
            seen.add(url)

            lower = url.lower()
            if not any(domain in lower for domain in ALLOWED_SEARCH_DOMAINS):
                continue

            response = fetch_page(url)
            if response is None or response.status_code != 200:
                continue

            metadata = extract_metadata_from_html(response.text)
            if valid_abstract(metadata["abstract"]):
                metadata["source_url"] = response.url
                metadata["source_type"] = "WebSearch:" + urlparse(url).netloc
                return metadata
    return None


# ============================================================
# SOURCE 7: SEMANTIC SCHOLAR (LAST RESORT, RATE-LIMIT SAFE)
# ============================================================

_semantic_scholar_lock_time = [0.0]  # shared mutable timestamp


def fetch_semantic_scholar(doi):
    if not doi:
        return None

    # Pace globally across all threads: never call more than once
    # every SEMANTIC_SCHOLAR_DELAY seconds. This is the actual fix
    # for the earlier 429 storm - one shared throttle instead of
    # N threads all hitting the endpoint at once.
    now = time.time()
    wait = _semantic_scholar_lock_time[0] + SEMANTIC_SCHOLAR_DELAY - now
    if wait > 0:
        time.sleep(wait)
    _semantic_scholar_lock_time[0] = time.time()

    url = "https://api.semanticscholar.org/graph/v1/paper/" + quote("DOI:" + doi, safe="")
    params = {"fields": "title,authors,abstract,externalIds,url"}
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    response = get_with_backoff(url, headers=headers, params=params, max_retries=3, base_delay=2.0)
    if response is None or response.status_code != 200:
        return None

    try:
        data = response.json()
    except Exception:
        return None

    abstract = clean_text(data.get("abstract", ""))
    if not valid_abstract(abstract):
        return None

    authors = "; ".join(a.get("name", "") for a in data.get("authors", []) if a.get("name"))

    return {
        "doi": normalize_doi(data.get("externalIds", {}).get("DOI", "")),
        "title": clean_text(data.get("title", "")),
        "authors": authors,
        "abstract": abstract,
        "keywords": None,
        "source_url": data.get("url", url),
        "source_type": "SemanticScholar",
    }


# ============================================================
# CANDIDATE SEARCH (tries sources in order, stops at first hit)
# ============================================================


def find_candidate(doi_url, doi, title, authors):
    # 1. Direct DOI resolve
    if doi_url:
        candidate = fetch_doi_source(doi_url)
        if candidate:
            return candidate

    # 2. Crossref (also collects OA links for step 5)
    crossref_candidate, crossref_links = fetch_crossref(doi)
    if crossref_candidate:
        return crossref_candidate

    # 3. OpenAlex (also collects OA links for step 5)
    openalex_candidate, openalex_links = fetch_openalex(doi)
    if openalex_candidate:
        return openalex_candidate

    # 4. Europe PMC
    candidate = fetch_europe_pmc(doi)
    if candidate:
        return candidate

    # 5. OA links gathered above
    oa_links = list(dict.fromkeys(crossref_links + openalex_links))
    if oa_links:
        candidate = fetch_oa_links(oa_links)
        if candidate:
            return candidate

    # 6. Google / ResearchGate / arXiv / Zenodo search
    candidate = fetch_from_web_search(title, doi, authors)
    if candidate:
        return candidate

    # 7. Semantic Scholar - last resort, paced
    candidate = fetch_semantic_scholar(doi)
    if candidate:
        return candidate

    return None


# ============================================================
# VERIFICATION
# ============================================================


def authors_match(original_authors, candidate_authors):
    if not original_authors or not candidate_authors:
        return False
    return normalize_author(original_authors) == normalize_author(candidate_authors)


def title_match(original_title, candidate_title):
    if not original_title or not candidate_title:
        return False
    return normalize_title(original_title) == normalize_title(candidate_title)


def verify_candidate(original_doi, original_title, original_author, candidate):
    original_doi_norm = normalize_doi(original_doi)
    candidate_doi = normalize_doi(candidate.get("doi"))
    candidate_title = clean_text(candidate.get("title"))
    candidate_authors = clean_text(candidate.get("authors"))

    if original_doi_norm and candidate_doi:
        if original_doi_norm == candidate_doi:
            return ("MATCHED", "DOI_EXACT_MATCH")
        return ("ABSTRACT_FOUND_RECORD_NOT_MATCHED", "DOI_MISMATCH")

    # No candidate DOI (or no original DOI) -> require title+author match
    title_ok = title_match(original_title, candidate_title)
    author_ok = authors_match(original_author, candidate_authors)
    if title_ok and author_ok:
        return ("MATCHED", "TITLE_AUTHOR_EXACT_MATCH")

    return ("ABSTRACT_FOUND_RECORD_NOT_MATCHED", "NO_VALID_MATCH")


# ============================================================
# PROCESS ONE RECORD
# ============================================================


def process_row(idx):
    row = df.loc[idx]
    doi_url = row[DOI_COL]
    doi = normalize_doi(doi_url)
    title = clean_text(row[TITLE_COL])
    authors = clean_text(row[AUTHOR_COL]) if AUTHOR_COL else None

    candidate = find_candidate(doi_url, doi, title, authors)

    if not candidate:
        return {
            "idx": idx,
            "status": "NOT_FOUND",
            "match_type": None,
            "scraped_doi": None,
            "scraped_title": None,
            "scraped_authors": None,
            "scraped_abstract": None,
            "scraped_keywords": None,
            "source_url": None,
            "source_type": None,
        }

    status, match_type = verify_candidate(doi_url, title, authors, candidate)

    return {
        "idx": idx,
        "status": status,
        "match_type": match_type,
        "scraped_doi": candidate.get("doi"),
        "scraped_title": candidate.get("title"),
        "scraped_authors": candidate.get("authors"),
        "scraped_abstract": candidate.get("abstract"),
        "scraped_keywords": candidate.get("keywords"),
        "source_url": candidate.get("source_url"),
        "source_type": candidate.get("source_type"),
    }


# ============================================================
# FIND RECORDS NEEDING ABSTRACT
# ============================================================

missing_abstract = df[ABSTRACT_COL].isna() | df[ABSTRACT_COL].astype(str).str.strip().eq("")
doi_available = df[DOI_COL].notna() & df[DOI_COL].astype(str).str.strip().ne("")
work_indices = df.index[missing_abstract & doi_available].tolist()

print(f"\nRecords needing abstract: {len(work_indices):,}")


# ============================================================
# RUN
# ============================================================

results = []

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {executor.submit(process_row, idx): idx for idx in work_indices}
    for future in tqdm(as_completed(futures), total=len(futures), desc="Retrieving abstracts + keywords"):
        idx = futures[future]
        try:
            results.append(future.result())
        except Exception as e:
            results.append({
                "idx": idx,
                "status": "ERROR",
                "match_type": str(e),
                "scraped_doi": None,
                "scraped_title": None,
                "scraped_authors": None,
                "scraped_abstract": None,
                "scraped_keywords": None,
                "source_url": None,
                "source_type": None,
            })

results_df = pd.DataFrame(results)


# ============================================================
# SUMMARY
# ============================================================

matched = (results_df["status"] == "MATCHED").sum()
not_matched = (results_df["status"] == "ABSTRACT_FOUND_RECORD_NOT_MATCHED").sum()
not_found = (results_df["status"] == "NOT_FOUND").sum()
errors = (results_df["status"] == "ERROR").sum()
kw_recovered = results_df["scraped_keywords"].notna().sum()

print()
print("=" * 60)
print("FINAL RETRIEVAL RESULT")
print("=" * 60)
print(f"Total processed                 : {len(results_df):,}")
print(f"Matched + abstract added        : {matched:,}")
print(f"Abstract found but NOT matched   : {not_matched:,}")
print(f"Not found                       : {not_found:,}")
print(f"Errors                          : {errors:,}")
print(f"Keywords recovered (of matched) : {kw_recovered:,}")
print("=" * 60)
print()
print("Match types:")
print(results_df[results_df["status"] == "MATCHED"]["match_type"].value_counts())
print()
print("Source types (matched only):")
print(results_df[results_df["status"] == "MATCHED"]["source_type"].value_counts())


# ============================================================
# MERGE BACK INTO ORIGINAL DATASET
# ============================================================

df_final = df.copy()

df_final["abstract_source_url"] = None
df_final["abstract_source_type"] = None
df_final["abstract_match_type"] = None
df_final["abstract_verification_status"] = None
df_final["scraped_doi"] = None
df_final["scraped_title"] = None
df_final["scraped_authors"] = None

for _, result in results_df.iterrows():
    idx = result["idx"]

    # Audit info saved for every attempted record
    df_final.at[idx, "abstract_source_url"] = result["source_url"]
    df_final.at[idx, "abstract_source_type"] = result["source_type"]
    df_final.at[idx, "abstract_match_type"] = result["match_type"]
    df_final.at[idx, "abstract_verification_status"] = result["status"]
    df_final.at[idx, "scraped_doi"] = result["scraped_doi"]
    df_final.at[idx, "scraped_title"] = result["scraped_title"]
    df_final.at[idx, "scraped_authors"] = result["scraped_authors"]

    # Only verified matches get written into the real columns
    if result["status"] == "MATCHED":
        if valid_abstract(result["scraped_abstract"]):
            df_final.at[idx, ABSTRACT_COL] = result["scraped_abstract"]

        scraped_keywords = result["scraped_keywords"]
        if scraped_keywords:
            current_keywords = df_final.at[idx, KEYWORDS_COL]
            if pd.isna(current_keywords) or str(current_keywords).strip() == "":
                df_final.at[idx, KEYWORDS_COL] = scraped_keywords


# ============================================================
# SAVE — ONE FINAL FILE, MERGED INTO ORIGINAL DATASET
# ============================================================

df_final.to_excel(OUTPUT_FILE, index=False)
print(f"\nFinal merged dataset saved:\n{OUTPUT_FILE}")

# Separate audit trail (optional but useful for QA)
audit_rows = []
for _, result in results_df.iterrows():
    idx = result["idx"]
    row = df.loc[idx]
    audit_rows.append({
        "original_index": idx,
        "original_doi": row[DOI_COL],
        "original_title": row[TITLE_COL],
        "original_authors": row[AUTHOR_COL] if AUTHOR_COL else None,
        "original_keywords": row[KEYWORDS_COL] if KEYWORDS_COL in row else None,
        "scraped_doi": result["scraped_doi"],
        "scraped_title": result["scraped_title"],
        "scraped_authors": result["scraped_authors"],
        "scraped_keywords": result["scraped_keywords"],
        "scraped_abstract": result["scraped_abstract"],
        "source_url": result["source_url"],
        "source_type": result["source_type"],
        "status": result["status"],
        "match_type": result["match_type"],
    })

audit_df = pd.DataFrame(audit_rows)
audit_df.to_excel(AUDIT_FILE, index=False)
print(f"Audit file saved:\n{AUDIT_FILE}")
