from books.openlibrary.client import fetch_cover_for_read_book
from books.graph_engine import state


def load_remaining_covers():
    """
    Background job that fills in missing cover_url for books.
    """
    for book in state.BOOK_NODES:
        if book.cover_url:
            continue

        cover = fetch_cover_for_read_book(book.title, book.author)
        if cover:
            book.cover_url = cover
