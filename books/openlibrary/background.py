from books.googlebooks.client import fetch_book_data as gb_fetch_book_data
from books.openlibrary.client import fetch_cover_for_read_book
from books.graph_engine import state


def load_remaining_covers():
    """
    Background task that fills in missing covers and genres after upload.
    Started as a daemon thread from upload_goodreads so the initial response
    isn't slowed down. Google Books is tried first; OpenLibrary is the fallback.
    Also populates book.subjects if they're still empty, so the graph has
    richer genre data for all books.
    """
    for book in state.BOOK_NODES:
        needs_cover = not book.cover_url
        needs_subjects = not book.subjects

        if not needs_cover and not needs_subjects:
            continue

        # Google Books: cover + genres in one call
        gb_data = gb_fetch_book_data(book.title, book.author)
        if gb_data:
            if needs_cover and gb_data.get("cover_url"):
                book.cover_url = gb_data["cover_url"]
                needs_cover = False
            if needs_subjects and gb_data.get("genres"):
                book.subjects = gb_data["genres"]
                needs_subjects = False

        # OpenLibrary fallback for cover only
        if needs_cover:
            cover = fetch_cover_for_read_book(book.title, book.author)
            if cover:
                book.cover_url = cover
