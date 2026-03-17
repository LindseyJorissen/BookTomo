import requests
from django.conf import settings

_BASE = "https://www.googleapis.com/books/v1/volumes"


def _mark_fetched(title: str, author: str, genres: list) -> None:
    try:
        from books.models import CachedBook
        obj, _ = CachedBook.objects.get_or_create(title=title, author=author)
        obj.google_books_genres = genres
        obj.google_books_fetched = True
        obj.save(update_fields=["google_books_genres", "google_books_fetched"])
    except Exception:
        pass


def fetch_categories(title: str, author: str) -> list:
    """Fetch genre categories for a book from the Google Books API.

    Results are stored permanently in CachedBook.google_books_genres.
    Returns an empty list on failure or if no categories are found.

    Google Books returns categories like "Fiction / Fantasy / General".
    Each slash-separated segment is split and deduplicated to give
    clean tags like ["Fiction", "Fantasy", "General"].
    """
    from books.models import CachedBook

    # ── Permanent DB lookup ────────────────────────────────────────────────────
    try:
        record = CachedBook.objects.get(title=title, author=author)
        if record.google_books_fetched:
            return record.google_books_genres
    except CachedBook.DoesNotExist:
        pass

    # ── Google Books API call ──────────────────────────────────────────────────
    params = {
        "q": f'intitle:"{title}" inauthor:"{author}"',
        "maxResults": 1,
        "fields": "items/volumeInfo/categories",
        "langRestrict": "en",
    }
    api_key = getattr(settings, "GOOGLE_BOOKS_API_KEY", "")
    if api_key:
        params["key"] = api_key

    try:
        resp = requests.get(_BASE, params=params, timeout=8)
        if resp.status_code != 200:
            # Mark as fetched anyway so we don't retry on every upload
            _mark_fetched(title, author, [])
            return []
        items = resp.json().get("items", [])
        if not items:
            _mark_fetched(title, author, [])
            return []
        raw_categories = items[0].get("volumeInfo", {}).get("categories", [])
    except Exception:
        return []

    # Split "Fiction / Fantasy / General" into individual tags
    seen: set = set()
    genres: list = []
    for cat in raw_categories:
        for part in cat.split("/"):
            tag = part.strip()
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                genres.append(tag)

    _mark_fetched(title, author, genres)
    return genres
