import hashlib
import re

import requests
from django.core.cache import cache

BASE_URL = "https://openlibrary.org"


def safe_cache_key(raw_key: str) -> str:
    """Zet een willekeurige string om naar een veilige MD5-cachesleutel (geen spaties of speciale tekens)."""
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    """
    Verwijdert reeksinformatie en ondertitels voor betrouwbaarder vergelijken.
    Voorbeeld: "Dune (Dune, #1): The Beginning" → "Dune"
    """
    title = re.sub(r"\(.*?\)", "", title)  # Verwijder (Reeks, #nummer)
    title = title.split(":")[0]            # Verwijder ondertitel na dubbele punt
    return title.strip()


def fetch_cover_for_read_book(title, author):
    """
    Haalt een omslagfoto op voor een gelezen boek via de OpenLibrary zoekAPI.
    Probeert eerst de zoekresultaten, dan de editie-API als fallback.
    Slaat het resultaat 24 uur op in de cache (ook als er geen omslag gevonden wordt).
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
        # Directe omslagafbeelding beschikbaar in zoekresultaat
        cover_id = doc.get("cover_i")
        if cover_id:
            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
            cache.set(cache_key, cover_url, 86400)
            return cover_url

        # Fallback: haal omslag op via de editie-API
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


def fetch_work_data(title, author):
    """
    Haalt OpenLibrary-werkdata op voor één boek: onderwerpen, omslag en work-ID.
    Gebruikt genormaliseerde titel (zonder reeks/ondertitel) voor betere trefkans.
    Resultaat wordt 24 uur gecached.
    """
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
        "subjects": doc.get("subject", [])[:8],  # Max 8 onderwerpen
        "cover_url": cover_url,
    }

    cache.set(cache_key, data, 86400)
    return data


def fetch_books_by_subject(subject, limit=8):
    """
    Haalt boeken op via het OpenLibrary onderwerpen-eindpunt (/subjects/{slug}.json).
    Zet het onderwerp om naar een URL-vriendelijke slug (bijv. "Science Fiction" → "science_fiction").
    Resultaten worden 24 uur gecached. Geeft een lege lijst terug bij een fout.
    """
    cache_key = safe_cache_key(f"subject_books::{subject}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Zet het onderwerp om naar een URL-slug
    subject_slug = re.sub(r"[^a-z0-9]+", "_", subject.lower().strip()).strip("_")
    url = f"{BASE_URL}/subjects/{subject_slug}.json"

    try:
        response = requests.get(url, params={"limit": limit}, timeout=5)
        response.raise_for_status()
    except Exception:
        cache.set(cache_key, [], 86400)
        return []

    books = []
    for work in response.json().get("works", []):
        title = work.get("title")
        authors = work.get("authors", [])
        if not title or not authors:
            continue

        cover_id = work.get("cover_id")
        books.append({
            "title": title,
            "author": authors[0].get("name", ""),
            "cover_url": (
                f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                if cover_id
                else None
            ),
            "openlibrary_id": work.get("key"),
        })

    cache.set(cache_key, books, 86400)
    return books


def fetch_unread_books_by_author(author, read_titles, limit=10):
    """
    Haalt ongelezen boeken van dezelfde auteur op via OpenLibrary.
    Slaat de volledige resultatenlijst op in de cache, en past daarna het filter
    toe op read_titles — zo blijft de cache herbruikbaar ongeacht welke titels al gelezen zijn.
    Geeft een lege lijst terug bij een netwerkfout.
    """
    raw_key = f"unread_by_author::{author}::{limit}"
    cache_key = safe_cache_key(raw_key)

    cached = cache.get(cache_key)
    if cached is not None:
        # Filter al-gelezen titels na het ophalen uit de cache
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
