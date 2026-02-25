from books.openlibrary.client import fetch_cover_for_read_book, fetch_work_data
from books.inventaire.client import fetch_cover as inventaire_fetch_cover
from books.graph_engine import state
from books.graph_engine.extract import _apply_ol_data


def load_remaining_covers():
    """
    Background task that fills in missing covers and metadata after upload.
    Started as a daemon thread from upload_goodreads so the initial response
    isn't slowed down.

    Strategy:
      1. OpenLibrary work data — subjects, awards, cover, description, metadata
      2. OpenLibrary cover search — cover only (different endpoint, better fallback)
      3. Inventaire — cover only as last resort

    All results are DB-cached so each book is never re-fetched within 30 days.
    """
    for book in state.BOOK_NODES:
        needs_cover = not book.cover_url
        needs_subjects = not book.subjects

        if not needs_cover and not needs_subjects:
            continue

        # 1. OpenLibrary full metadata
        ol_data = fetch_work_data(book.title, book.author)
        _apply_ol_data(book, ol_data)

        needs_cover = not book.cover_url

        # 2. OL cover search fallback
        if needs_cover:
            cover = fetch_cover_for_read_book(book.title, book.author)
            if cover:
                book.cover_url = cover
                needs_cover = False

        # 3. Inventaire cover fallback
        if needs_cover:
            cover = inventaire_fetch_cover(book.title, book.author)
            if cover:
                book.cover_url = cover
