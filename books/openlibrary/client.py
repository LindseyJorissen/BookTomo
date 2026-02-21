import hashlib
import re

import requests
from django.core.cache import cache

BASE_URL = "https://openlibrary.org"


def safe_cache_key(raw_key: str) -> str:
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    # remove series info and subtitles
    title = re.sub(r"\(.*?\)", "", title)  # remove (Series, #)
    title = title.split(":")[0]  # remove subtitles
    return title.strip()


def fetch_cover_for_read_book(title, author):
    """
    Fetch a best-effort cover for a READ book.
    Uses author-based search for robustness.
    """
    raw_key = f"read_cover::{title}::{author}"
    cache_key = safe_cache_key(raw_key)
    clean_title = normalize_title(title)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/search.json"
    params = {
        "title": clean_title,
        "author": author,
        "limit": 5,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
    except Exception:
        cache.set(cache_key, None, 86400)
        return None

    docs = response.json().get("docs", [])

    for doc in docs:
        cover_id = doc.get("cover_i")
        if cover_id:
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
            cache.set(cache_key, cover_url, 86400)
            return cover_url

        edition_keys = doc.get("edition_key", [])
        if not edition_keys:
            continue

        edition_id = edition_keys[0]
        edition_url = f"https://openlibrary.org/books/{edition_id}.json"

        try:
            edition_resp = requests.get(edition_url, timeout=5)
            if edition_resp.status_code != 200:
                continue

            edition_data = edition_resp.json()
            covers = edition_data.get("covers")
            if covers:
                cover_url = f"https://covers.openlibrary.org/b/id/{covers[0]}-M.jpg"
                cache.set(cache_key, cover_url, 86400)
                return cover_url
        except Exception:
            continue

    cache.set(cache_key, None, 86400)
    return None


def search_by_author(author_name, limit=10):
    cache_key = f"openlibrary_author_{author_name}_{limit}"

    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"{BASE_URL}/search.json"
    params = {
        "author": author_name,
        "limit": limit,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = normalize_books(response.json())

    cache.set(cache_key, data, timeout=60 * 60 * 24)

    return data


def normalize_books(openlibrary_json):
    books = []

    for doc in openlibrary_json.get("docs", []):
        title = doc.get("title")
        authors = doc.get("author_name", [])
        cover_id = doc.get("cover_i")

        if not title or not authors:
            continue

        books.append({
            "title": title,
            "author": authors[0],
            "cover_url": (
                f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                if cover_id
                else None
            ),
            "openlibrary_id": doc.get("key"),  # e.g. /works/OL123W
            "first_publish_year": doc.get("first_publish_year"),
        })

    return books


def fetch_work_data(title, author):
    cache_key = f"openlibrary_work::{safe_cache_key(title + author)}"
    clean_title = normalize_title(title)
    cached = cache.get(cache_key)
    if cached:
        return cached
    try:
        response = requests.get(
            f"{BASE_URL}/search.json",
            params={"title": clean_title, "author": author, "limit": 1},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    docs = response.json().get("docs", [])
    if not docs:
        cache.set(cache_key, None, 86400)
        return None

    doc = docs[0]
    work_id = doc.get("key")
    cover_id = doc.get("cover_i")

    cover_url = (
        f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
        if cover_id
        else None
    )

    data = {
        "openlibrary_id": work_id,
        "subjects": doc.get("subject", [])[:8],
        "cover_url": cover_url,
    }

    cache.set(cache_key, data, 86400)
    return data


def fetch_unread_books_by_author(author, read_titles, limit=10):
    """
    Fetch unread books by the same author from Open Library.
    Filters out already-read titles.
    """
    raw_key = f"unread_by_author::{author}::{limit}"
    cache_key = safe_cache_key(raw_key)

    cached = cache.get(cache_key)
    if cached is not None:
        return [b for b in cached if normalize_title(b["title"]).lower() not in read_titles]

    url = f"{BASE_URL}/search.json"
    params = {
        "author": author,
        "limit": limit,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
    except Exception:
        return []

    all_books = []
    for doc in response.json().get("docs", []):
        title = doc.get("title")
        if not title:
            continue

        all_books.append({
            "title": title,
            "author": author,
            "cover_url": (
                f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
                if doc.get("cover_i")
                else None
            ),
            "openlibrary_id": doc.get("key"),
        })

    cache.set(cache_key, all_books, 86400)

    return [b for b in all_books if normalize_title(b["title"]).lower() not in read_titles]
