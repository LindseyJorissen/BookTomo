import requests
from books.openlibrary.client import safe_cache_key, normalize_title

INVENTAIRE_URL = "https://inventaire.io/api/entities"


def _image_url(raw):
    """Convert a relative Inventaire image path to an absolute URL."""
    if not raw:
        return None
    return f"https://inventaire.io{raw}" if raw.startswith("/") else raw


def _search(query, limit=3):
    """Raw search against the Inventaire entities API. Returns result list."""
    try:
        resp = requests.get(
            INVENTAIRE_URL,
            params={"action": "search", "search": query, "types": "works", "lang": "en", "limit": limit},
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return []


def fetch_cover(title, author):
    """
    Fetch a cover image from Inventaire for a book.

    Checks the CachedBook DB first. On a miss, calls the Inventaire search API,
    saves the result (or the fact that nothing was found) to the DB, and returns
    the cover URL (or None). This ensures each book is only ever looked up once
    per 30-day period.
    """
    from books.models import CachedBook

    # DB cache check
    try:
        cached = CachedBook.objects.get(title=title, author=author)
        if cached.cover_url:
            return cached.cover_url
        if cached.inventaire_fetched and not cached.is_stale():
            return None  # Already tried; nothing found
    except CachedBook.DoesNotExist:
        pass

    clean_title = normalize_title(title)
    results = (
        _search(f"{clean_title} {author}")
        or _search(clean_title)
    )

    cover_url = None
    inventaire_uri = ""
    for entity in results:
        url = _image_url(entity.get("image", {}).get("url"))
        if url:
            cover_url = url
            inventaire_uri = entity.get("uri", "")
            break

    obj, _ = CachedBook.objects.get_or_create(title=title, author=author)
    if not obj.cover_url and cover_url:
        obj.cover_url = cover_url
    if not obj.inventaire_uri and inventaire_uri:
        obj.inventaire_uri = inventaire_uri
    obj.inventaire_fetched = True
    obj.save()

    return cover_url


def fetch_books_by_subject(subject, limit=8):
    """
    Fetch books in a given subject/genre from Inventaire.
    Results are cached in memory (Django cache) for 24 hours.
    Returns a list of dicts with title, author, cover_url, inventaire_uri.
    Note: Inventaire search results do not always include the author name;
    those entries are omitted so downstream code has consistent data.
    """
    from django.core.cache import cache

    cache_key = safe_cache_key(f"inventaire_subject::{subject}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results = _search(subject, limit=limit + 5)

    books = []
    for entity in results:
        label = entity.get("label", "").strip()
        if not label:
            continue

        # Descriptions often look like "novel by Author Name" — extract author best-effort
        description = entity.get("description", "")
        author = ""
        if " by " in description:
            author = description.split(" by ", 1)[-1].strip()

        if not author:
            continue  # Skip entries we can't attribute

        books.append({
            "title": label,
            "author": author,
            "cover_url": _image_url(entity.get("image", {}).get("url")),
            "inventaire_uri": entity.get("uri"),
        })

        if len(books) >= limit:
            break

    if books:
        cache.set(cache_key, books, 86400)
    return books


def fetch_books_by_author(author, read_titles, limit=10):
    """
    Fetch unread books by a given author from Inventaire.
    Full result list is cached for 24 hours; read_titles filter is applied after.
    """
    from django.core.cache import cache

    cache_key = safe_cache_key(f"inventaire_author::{author}::{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return [b for b in cached if normalize_title(b["title"]).lower() not in read_titles]

    results = _search(f"{author}", limit=limit + 5)

    all_books = []
    for entity in results:
        label = entity.get("label", "").strip()
        if not label:
            continue
        all_books.append({
            "title": label,
            "author": author,
            "cover_url": _image_url(entity.get("image", {}).get("url")),
            "inventaire_uri": entity.get("uri"),
        })

    if all_books:
        cache.set(cache_key, all_books, 86400)
    return [b for b in all_books if normalize_title(b["title"]).lower() not in read_titles]
