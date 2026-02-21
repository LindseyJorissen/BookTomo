import re

import requests
from django.conf import settings
from django.core.cache import cache

from books.openlibrary.client import normalize_title, safe_cache_key

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"

# Google Books categories to ignore — too vague to be useful as genre nodes
_GENERIC_TERMS = {"general", "fiction", "nonfiction", "juvenile fiction", "juvenile nonfiction"}


def _api_key():
    return getattr(settings, "GOOGLE_BOOKS_API_KEY", "")


def _parse_categories(raw_categories):
    """
    Flatten hierarchical Google Books categories into individual genre terms.
    "Fiction / Science Fiction / General" → ["Science Fiction"]
    "Biography & Autobiography / General" → ["Biography & Autobiography"]
    """
    genres = set()
    for cat in raw_categories:
        for part in cat.split("/"):
            part = part.strip()
            if part and part.lower() not in _GENERIC_TERMS:
                genres.add(part)
    return list(genres)[:8]


def _clean_cover_url(url):
    """Request a medium-sized flat cover image (no page-curl edge effect)."""
    if not url:
        return None
    url = url.replace("http://", "https://")
    url = re.sub(r"zoom=\d", "zoom=2", url)
    url = url.replace("&edge=curl", "")
    return url


def _is_non_english(volume_info):
    """
    Returns True only when the language field is explicitly set to a non-English value.
    Books with no language field are kept (we don't know, assume OK).
    """
    lang = volume_info.get("language", "")
    return bool(lang and lang != "en")


def fetch_book_data(title, author):
    """
    Fetch cover URL and genres for a single book from Google Books.
    Returns dict with: cover_url, genres (list), google_id — or None on failure.
    Cached 24h for found results; not cached on failure so it retries next time.
    """
    cache_key = safe_cache_key(f"gbooks_data::{title}::{author}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    clean_title = normalize_title(title)

    def _search(query):
        try:
            resp = requests.get(
                GOOGLE_BOOKS_URL,
                params={"q": query, "maxResults": 3, "key": _api_key()},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])
        except Exception:
            return []

    # Try exact match first, then looser query
    items = (
        _search(f'intitle:"{clean_title}" inauthor:"{author}"')
        or _search(f"intitle:{clean_title} inauthor:{author}")
    )

    if not items:
        return None  # don't cache — let it retry next request

    info = items[0].get("volumeInfo", {})
    image_links = info.get("imageLinks", {})
    cover_url = _clean_cover_url(
        image_links.get("thumbnail") or image_links.get("smallThumbnail")
    )

    data = {
        "google_id": items[0].get("id"),
        "cover_url": cover_url,
        "genres": _parse_categories(info.get("categories", [])),
    }

    cache.set(cache_key, data, 86400)
    return data


def fetch_books_by_genre(genre, limit=8):
    """
    Fetch books in a given genre from Google Books.
    Only skips results with an explicitly non-English language tag.
    Results cached 24h; empty results not cached so they retry.
    """
    cache_key = safe_cache_key(f"gbooks_genre_en::{genre}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            GOOGLE_BOOKS_URL,
            params={
                "q": f"subject:{genre}",
                "maxResults": limit + 5,  # small buffer for language filtering
                "orderBy": "relevance",
                "langRestrict": "en",
                "key": _api_key(),
            },
            timeout=5,
        )
        resp.raise_for_status()
    except Exception:
        return []  # don't cache errors — retry next time

    books = []
    for item in resp.json().get("items", []):
        info = item.get("volumeInfo", {})
        if _is_non_english(info):
            continue
        title = info.get("title")
        authors = info.get("authors", [])
        if not title or not authors:
            continue

        image_links = info.get("imageLinks", {})
        books.append({
            "title": title,
            "author": authors[0],
            "cover_url": _clean_cover_url(
                image_links.get("thumbnail") or image_links.get("smallThumbnail")
            ),
            "google_id": item.get("id"),
        })
        if len(books) >= limit:
            break

    if books:
        cache.set(cache_key, books, 86400)
    return books


def fetch_books_by_author(author, read_titles, limit=10):
    """
    Fetch unread books by a given author from Google Books.
    Only skips results with an explicitly non-English language tag.
    Full result list is cached; read_titles filter is applied after.
    Empty results not cached so they retry.
    """
    cache_key = safe_cache_key(f"gbooks_author_en::{author}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return [b for b in cached if normalize_title(b["title"]).lower() not in read_titles]

    try:
        resp = requests.get(
            GOOGLE_BOOKS_URL,
            params={"q": f'inauthor:"{author}"', "maxResults": limit + 5, "langRestrict": "en", "key": _api_key()},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        return []  # don't cache errors — retry next time

    all_books = []
    for item in resp.json().get("items", []):
        info = item.get("volumeInfo", {})
        if _is_non_english(info):
            continue
        title = info.get("title")
        if not title:
            continue

        image_links = info.get("imageLinks", {})
        all_books.append({
            "title": title,
            "author": author,
            "cover_url": _clean_cover_url(
                image_links.get("thumbnail") or image_links.get("smallThumbnail")
            ),
            "google_id": item.get("id"),
        })

    if all_books:
        cache.set(cache_key, all_books, 86400)
    return [b for b in all_books if normalize_title(b["title"]).lower() not in read_titles]
