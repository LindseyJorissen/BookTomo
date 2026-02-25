import hashlib
import re

import requests
from django.core.cache import cache

BASE_URL = "https://openlibrary.org"

# Fields to request from OL search in a single call
_SEARCH_FIELDS = (
    "key,cover_i,subject,ratings_average,ratings_count,"
    "want_to_read_count,first_publish_year,number_of_pages_median"
)

# Subject prefixes that are internal OL metadata, not human-readable genres
_NOISE_PREFIXES = ("nyt:", "new york times", "in library", "overdrive", "accessible book")


def safe_cache_key(raw_key: str) -> str:
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    title = re.sub(r"\(.*?\)", "", title)
    title = title.split(":")[0]
    return title.strip()


def _clean_subjects(raw_subjects):
    """
    Split OL subjects into (clean_subjects, award_slugs).

    Removes noise entries (nyt:*, "in library", etc.) from the subject list.
    Extracts award entries like "award:hugo_award=1966" into a slug list.

    Returns:
        clean_subjects: list of plain display strings (max 12)
        award_slugs:    list of award slug strings e.g. ["hugo_award", "nebula_award"]
    """
    clean = []
    awards = {}
    for s in raw_subjects:
        s_lower = s.lower()
        if s.startswith("award:"):
            slug = s.replace("award:", "").split("=")[0].strip()
            if slug:
                awards[slug] = True
        elif any(s_lower.startswith(p) for p in _NOISE_PREFIXES):
            continue
        else:
            clean.append(s)
    return clean[:12], list(awards.keys())


def fetch_cover_for_read_book(title, author):
    """
    Fetches a cover URL via the OL search API (title + author query, limit 5).
    Falls back to the edition API if no cover_i is present in search results.

    DB-cached: if a cover is already stored (from any source) it is returned
    immediately. If OL was already tried and found nothing, returns None.
    """
    from books.models import CachedBook

    try:
        cached = CachedBook.objects.get(title=title, author=author)
        if cached.cover_url:
            return cached.cover_url
        if cached.openlibrary_fetched and not cached.is_stale():
            return None
    except CachedBook.DoesNotExist:
        pass

    clean_title = normalize_title(title)
    try:
        response = requests.get(
            f"{BASE_URL}/search.json",
            params={"title": clean_title, "author": author, "limit": 5},
            timeout=10,
        )
        response.raise_for_status()
    except Exception:
        obj, _ = CachedBook.objects.get_or_create(title=title, author=author)
        obj.openlibrary_fetched = True
        obj.save(update_fields=["openlibrary_fetched", "fetched_at"])
        return None

    docs = response.json().get("docs", [])
    cover_url = None

    for doc in docs:
        cover_id = doc.get("cover_i")
        if cover_id:
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
            break

        edition_keys = doc.get("edition_key", [])
        if not edition_keys:
            continue

        edition_id = edition_keys[0]
        try:
            edition_resp = requests.get(f"{BASE_URL}/books/{edition_id}.json", timeout=5)
            if edition_resp.status_code != 200:
                continue
            covers = edition_resp.json().get("covers")
            if covers:
                cover_url = f"https://covers.openlibrary.org/b/id/{covers[0]}-M.jpg"
                break
        except Exception:
            continue

    obj, _ = CachedBook.objects.get_or_create(title=title, author=author)
    if not obj.cover_url and cover_url:
        obj.cover_url = cover_url
    obj.openlibrary_fetched = True
    obj.save()
    return cover_url


def fetch_work_data(title, author):
    """
    Fetch enriched OpenLibrary data for a single book.

    Single search call (using the `fields` param) returns:
      subjects, award_slugs, cover_url, ratings, want_to_read_count,
      first_publish_year, page_count.

    A second call to /works/{id}.json fetches the description.

    All results are persisted to CachedBook (30-day TTL) so each book is
    only looked up once per month.

    Returns a dict with all fetched fields, or None on failure/miss.
    """
    from books.models import CachedBook

    # DB cache check
    try:
        cached = CachedBook.objects.get(title=title, author=author)
        if cached.openlibrary_fetched and not cached.is_stale():
            if not cached.openlibrary_id:
                return None
            return {
                "openlibrary_id": cached.openlibrary_id,
                "subjects": cached.subjects,
                "award_slugs": cached.award_slugs,
                "cover_url": cached.cover_url or None,
                "description": cached.description,
                "page_count": cached.page_count,
                "first_publish_year": cached.first_publish_year,
                "ol_ratings_average": cached.ol_ratings_average,
                "ol_ratings_count": cached.ol_ratings_count,
                "want_to_read_count": cached.want_to_read_count,
            }
    except CachedBook.DoesNotExist:
        pass

    clean_title = normalize_title(title)

    try:
        response = requests.get(
            f"{BASE_URL}/search.json",
            params={
                "title": clean_title,
                "author": author,
                "limit": 1,
                "fields": _SEARCH_FIELDS,
            },
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    docs = response.json().get("docs", [])
    if not docs:
        obj, _ = CachedBook.objects.get_or_create(title=title, author=author)
        obj.openlibrary_fetched = True
        obj.save(update_fields=["openlibrary_fetched", "fetched_at"])
        return None

    doc = docs[0]
    work_id = doc.get("key", "")
    cover_id = doc.get("cover_i")
    cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None

    clean_subjects, award_slugs = _clean_subjects(doc.get("subject", []))

    # Fetch description from the Works endpoint (one extra call)
    description = ""
    if work_id:
        try:
            work_resp = requests.get(f"{BASE_URL}{work_id}.json", timeout=5)
            if work_resp.status_code == 200:
                raw_desc = work_resp.json().get("description", "")
                description = raw_desc.get("value", "") if isinstance(raw_desc, dict) else raw_desc
        except Exception:
            pass

    data = {
        "openlibrary_id": work_id,
        "subjects": clean_subjects,
        "award_slugs": award_slugs,
        "cover_url": cover_url,
        "description": description,
        "page_count": doc.get("number_of_pages_median"),
        "first_publish_year": doc.get("first_publish_year"),
        "ol_ratings_average": doc.get("ratings_average"),
        "ol_ratings_count": doc.get("ratings_count"),
        "want_to_read_count": doc.get("want_to_read_count"),
    }

    # Persist to DB — never overwrite a cover already found by a different source
    obj, _ = CachedBook.objects.get_or_create(title=title, author=author)
    obj.openlibrary_id = work_id
    obj.subjects = clean_subjects
    obj.award_slugs = award_slugs
    obj.openlibrary_fetched = True
    if not obj.cover_url and cover_url:
        obj.cover_url = cover_url
    if not obj.description and description:
        obj.description = description
    if obj.page_count is None and data["page_count"]:
        obj.page_count = data["page_count"]
    if obj.first_publish_year is None and data["first_publish_year"]:
        obj.first_publish_year = data["first_publish_year"]
    if obj.ol_ratings_average is None and data["ol_ratings_average"]:
        obj.ol_ratings_average = data["ol_ratings_average"]
    if obj.ol_ratings_count is None and data["ol_ratings_count"]:
        obj.ol_ratings_count = data["ol_ratings_count"]
    if obj.want_to_read_count is None and data["want_to_read_count"]:
        obj.want_to_read_count = data["want_to_read_count"]
    obj.save()

    return data


def fetch_books_by_subject(subject, limit=8):
    """
    Fetch popular books for a subject from the OL search API.
    Sorted by want_to_read_count descending. Cached for 24 hours.
    """
    cache_key = safe_cache_key(f"subject_books::{subject}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            f"{BASE_URL}/search.json",
            params={
                "subject": subject,
                "fields": "key,title,author_name,cover_i,want_to_read_count",
                "sort": "want_to_read_count desc",
                "limit": limit,
            },
            timeout=5,
        )
        response.raise_for_status()
    except Exception:
        return []

    books = []
    for doc in response.json().get("docs", []):
        title = doc.get("title")
        authors = doc.get("author_name", [])
        if not title or not authors:
            continue
        cover_id = doc.get("cover_i")
        books.append({
            "title": title,
            "author": authors[0],
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
            "want_to_read_count": doc.get("want_to_read_count", 0),
            "openlibrary_id": doc.get("key"),
        })

    if books:
        cache.set(cache_key, books, 86400)
    return books


def fetch_books_by_award(award_slug, limit=6):
    """
    Fetch popular award-winning books from OL by award slug.
    Uses OL's subject search with the "award:{slug}" convention.
    Results sorted by want_to_read_count. Cached for 24 hours.
    """
    cache_key = safe_cache_key(f"ol_award::{award_slug}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            f"{BASE_URL}/search.json",
            params={
                "subject": f"award:{award_slug}",
                "fields": "key,title,author_name,cover_i,want_to_read_count",
                "sort": "want_to_read_count desc",
                "limit": limit + 5,
            },
            timeout=8,
        )
        resp.raise_for_status()
    except Exception:
        return []

    books = []
    for doc in resp.json().get("docs", []):
        title = doc.get("title")
        authors = doc.get("author_name", [])
        if not title or not authors:
            continue
        cover_id = doc.get("cover_i")
        books.append({
            "title": title,
            "author": authors[0],
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
            "want_to_read_count": doc.get("want_to_read_count", 0),
            "openlibrary_id": doc.get("key"),
        })
        if len(books) >= limit:
            break

    if books:
        cache.set(cache_key, books, 86400)
    return books


def fetch_books_by_era(decade_start, primary_subject, limit=6):
    """
    Fetch popular books published in a given decade, optionally filtered by subject.

    Uses a Solr range query on first_publish_year, then filters client-side to
    ensure the decade bounds are respected. Falls back to a broader search
    (no subject filter) if the subject-filtered result has fewer than 3 books.

    Cached for 24 hours.
    """
    decade_end = decade_start + 9
    cache_key = safe_cache_key(f"ol_era::{decade_start}::{primary_subject}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _search(subject):
        params = {
            "fields": "key,title,author_name,cover_i,want_to_read_count,first_publish_year",
            "sort": "want_to_read_count desc",
            "limit": 60,
            "q": f"first_publish_year:[{decade_start} TO {decade_end}]",
        }
        if subject:
            params["subject"] = subject
        try:
            resp = requests.get(f"{BASE_URL}/search.json", params=params, timeout=8)
            resp.raise_for_status()
        except Exception:
            return []

        results = []
        for doc in resp.json().get("docs", []):
            pub_year = doc.get("first_publish_year")
            if pub_year is None or not (decade_start <= pub_year <= decade_end):
                continue
            title = doc.get("title")
            authors = doc.get("author_name", [])
            if not title or not authors:
                continue
            cover_id = doc.get("cover_i")
            results.append({
                "title": title,
                "author": authors[0],
                "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
                "want_to_read_count": doc.get("want_to_read_count", 0),
                "openlibrary_id": doc.get("key"),
                "first_publish_year": pub_year,
            })
            if len(results) >= limit:
                break
        return results

    books = _search(primary_subject) if primary_subject else []
    if len(books) < 3:
        books = _search(None)

    if books:
        cache.set(cache_key, books, 86400)
    return books


def fetch_unread_books_by_author(author, read_titles, limit=10):
    """
    Fetch unread books by a given author from OL.
    Full result list is cached; read_titles filter is applied after retrieval.
    """
    raw_key = f"unread_by_author::{author}::{limit}"
    cache_key = safe_cache_key(raw_key)

    cached = cache.get(cache_key)
    if cached is not None:
        return [b for b in cached if normalize_title(b["title"]).lower() not in read_titles]

    try:
        response = requests.get(
            f"{BASE_URL}/search.json",
            params={"author": author, "limit": limit},
            timeout=10,
        )
        response.raise_for_status()
    except Exception:
        return []

    all_books = []
    for doc in response.json().get("docs", []):
        title = doc.get("title")
        if not title:
            continue
        cover_id = doc.get("cover_i")
        all_books.append({
            "title": title,
            "author": author,
            "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None,
            "openlibrary_id": doc.get("key"),
        })

    cache.set(cache_key, all_books, 86400)
    return [b for b in all_books if normalize_title(b["title"]).lower() not in read_titles]
