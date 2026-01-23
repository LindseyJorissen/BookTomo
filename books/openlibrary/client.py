import requests
from django.core.cache import cache

BASE_URL = "https://openlibrary.org"

import hashlib


def safe_cache_key(raw_key: str) -> str:
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


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
    raw_key = f"openlibrary_work::{title}::{author}"
    cache_key = f"openlibrary_work::{safe_cache_key(raw_key)}"

    cached = cache.get(cache_key)
    if cached:
        return cached

    url = f"{BASE_URL}/search.json"
    params = {
        "title": title,
        "author": author,
        "limit": 1,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    docs = response.json().get("docs", [])
    if not docs:
        cache.set(cache_key, None, 60 * 60 * 24)
        return None

    doc = docs[0]

    data = {
        "openlibrary_id": doc.get("key"),  # /works/OL...
        "subjects": doc.get("subject", [])[:8],  # cap for sanity
        "cover_id": doc.get("cover_i"),
        "cover_url": (
            f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
            if doc.get("cover_i")
            else None
        ),
        "first_publish_year": doc.get("first_publish_year"),
    }

    cache.set(cache_key, data, timeout=60 * 60 * 24)
    return data


def fetch_unread_books_by_author(author, read_titles, limit=10):
    """
    Fetch unread books by the same author from Open Library.
    Filters out already-read titles.
    """
    url = f"{BASE_URL}/search.json"
    params = {
        "author": author,
        "limit": limit,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    unread = []

    for doc in response.json().get("docs", []):
        title = doc.get("title")
        if not title:
            continue

        # normalize for comparison
        normalized = title.lower().strip()
        if normalized in read_titles:
            continue

        unread.append({
            "title": title,
            "author": author,
            "cover_url": (
                f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg"
                if doc.get("cover_i")
                else None
            ),
            "openlibrary_id": doc.get("key"),
        })

    return unread
