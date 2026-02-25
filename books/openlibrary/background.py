from books.openlibrary.client import fetch_cover_for_read_book, fetch_work_data
from books.inventaire.client import fetch_cover as inventaire_fetch_cover
from books.graph_engine import state


def load_remaining_covers():
    """
    Background task that fills in missing covers and subjects after upload.
    Started as a daemon thread from upload_goodreads so the initial response
    isn't slowed down.

    Strategy:
      1. OpenLibrary work data — subjects + cover (DB-cached, 30-day TTL)
      2. OpenLibrary cover search — cover only (DB-cached)
      3. Inventaire — cover only (DB-cached, 30-day TTL)

    All results are persisted to CachedBook so each book is never fetched
    more than once per 30-day period.
    """
    for book in state.BOOK_NODES:
        needs_cover = not book.cover_url
        needs_subjects = not book.subjects

        if not needs_cover and not needs_subjects:
            continue

        # 1. OpenLibrary: subjects + cover in one call
        if needs_subjects or needs_cover:
            ol_data = fetch_work_data(book.title, book.author)
            if ol_data:
                if not book.cover_url and ol_data.get("cover_url"):
                    book.cover_url = ol_data["cover_url"]
                if not book.subjects and ol_data.get("subjects"):
                    book.subjects = ol_data["subjects"]
                if not book.openlibrary_id and ol_data.get("openlibrary_id"):
                    book.openlibrary_id = ol_data["openlibrary_id"]
                needs_cover = not book.cover_url
                needs_subjects = not book.subjects

        # 2. OpenLibrary cover search (different endpoint — searches by title+author)
        if needs_cover:
            cover = fetch_cover_for_read_book(book.title, book.author)
            if cover:
                book.cover_url = cover
                needs_cover = False

        # 3. Inventaire fallback for cover
        if needs_cover:
            cover = inventaire_fetch_cover(book.title, book.author)
            if cover:
                book.cover_url = cover
