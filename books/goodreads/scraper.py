import json
import re
import time

import requests

# Polite delay between Goodreads requests (personal use only)
_DELAY = 1.5

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_genres_from_apollo(apollo_state: dict) -> list:
    """Pull genre names out of a Goodreads Apollo GraphQL cache dict.

    Goodreads embeds all page data in a __NEXT_DATA__ JSON block. Inside it,
    the Apollo cache holds keys like "Book:12345" with a "bookGenres" list
    where each entry is {"genre": {"__ref": "Genre:fantasy"}}. Genre objects
    at the top level of the cache hold the human-readable "name".
    """
    genres = []
    for value in apollo_state.values():
        if not isinstance(value, dict):
            continue
        book_genres = value.get("bookGenres")
        if not book_genres:
            continue
        for bg in book_genres:
            if not isinstance(bg, dict):
                continue
            ref = bg.get("genre", {}).get("__ref", "")
            if ref and ref in apollo_state:
                name = apollo_state[ref].get("name", "")
                if name:
                    genres.append(name)
        # Stop after the first book entry that has genres (avoid duplicates
        # from different cache shapes Goodreads sometimes produces)
        if genres:
            break
    return genres


def _genres_from_cachedbook(title: str, author: str) -> list:
    """Pull genres from CachedBook as a fallback (Google Books data)."""
    if not title or not author:
        return []
    try:
        from books.models import CachedBook
        obj = CachedBook.objects.filter(title=title, author=author).first()
        if obj is None:
            return []
        # Prefer google_books_genres; fall back to OL subjects
        return obj.google_books_genres or obj.subjects or []
    except Exception:
        return []


def fetch_genres(goodreads_id: str, title: str = "", author: str = "") -> list:
    """Return crowd-sourced genre tags for a book from Goodreads.

    Checks the permanent BookGenres table first. If not yet stored (or stored
    empty), scrapes the Goodreads book page and extracts genres from the
    embedded __NEXT_DATA__ JSON. If that also returns nothing, falls back to
    CachedBook.google_books_genres so BookGenres always has something useful.

    Returns an empty list on any failure (network error, blocked, page changed).
    """
    from books.models import BookGenres

    gid = str(goodreads_id).strip()
    if not gid or gid in ("0", "nan", ""):
        return []

    # ── Permanent DB lookup ────────────────────────────────────────────────────
    try:
        record = BookGenres.objects.get(goodreads_id=gid)
        if record.genres:
            return record.genres
        # Record exists but empty — try to backfill from CachedBook
        fallback = _genres_from_cachedbook(title, author)
        if fallback:
            record.genres = fallback
            record.save(update_fields=["genres"])
        return record.genres
    except BookGenres.DoesNotExist:
        pass

    # ── Scrape Goodreads book page ─────────────────────────────────────────────
    genres = []
    try:
        time.sleep(_DELAY)
        url = f"https://www.goodreads.com/book/show/{gid}"
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        print(f"[Goodreads] {title!r} (id={gid}) → HTTP {resp.status_code}")
        if resp.status_code == 200:
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                resp.text,
                re.DOTALL,
            )
            if not match:
                print(f"[Goodreads] {title!r} — __NEXT_DATA__ block not found")
            else:
                data = json.loads(match.group(1))
                apollo = (
                    data.get("props", {})
                        .get("pageProps", {})
                        .get("apolloState", {})
                )
                if not apollo:
                    print(f"[Goodreads] {title!r} — apolloState missing")
                else:
                    genres = _extract_genres_from_apollo(apollo)
                    if not genres:
                        # Log Apollo keys to help debug structure changes
                        book_keys = [k for k in apollo if k.startswith("Book:")]
                        print(f"[Goodreads] {title!r} — no genres found; Book keys: {book_keys[:3]}")
                    else:
                        print(f"[Goodreads] {title!r} → genres={genres}")
        else:
            print(f"[Goodreads] {title!r} — HTTP {resp.status_code}, skipping")
    except Exception as e:
        print(f"[Goodreads] {title!r} (id={gid}) — exception: {e}")

    # ── Fallback to CachedBook if Goodreads found nothing ─────────────────────
    if not genres:
        genres = _genres_from_cachedbook(title, author)

    # ── Persist permanently ────────────────────────────────────────────────────
    try:
        BookGenres.objects.update_or_create(
            goodreads_id=gid,
            defaults={"genres": genres, "title": title[:500], "author": author[:300]},
        )
    except Exception:
        pass

    return genres
