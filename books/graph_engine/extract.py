from .schemas import BookNode
from . import state
from books.openlibrary.client import fetch_work_data, fetch_cover_for_read_book
from books.inventaire.client import fetch_cover as inventaire_fetch_cover

# Maximum number of books to fetch data for synchronously on upload.
# The rest are filled in by the background thread in background.py.
MAX_COVER_LOOKUPS = 10


def _apply_ol_data(book, ol_data):
    """Copy OpenLibrary fields from the fetch_work_data result dict onto a BookNode."""
    if not ol_data:
        return
    if not book.cover_url and ol_data.get("cover_url"):
        book.cover_url = ol_data["cover_url"]
    if not book.subjects and ol_data.get("subjects"):
        book.subjects = ol_data["subjects"]
    if not book.award_slugs and ol_data.get("award_slugs"):
        book.award_slugs = ol_data["award_slugs"]
    if not book.openlibrary_id and ol_data.get("openlibrary_id"):
        book.openlibrary_id = ol_data["openlibrary_id"]
    if not book.description and ol_data.get("description"):
        book.description = ol_data["description"]
    if not book.page_count and ol_data.get("page_count"):
        book.page_count = ol_data["page_count"]
    if not book.first_publish_year and ol_data.get("first_publish_year"):
        book.first_publish_year = ol_data["first_publish_year"]
    if not book.ol_ratings_average and ol_data.get("ol_ratings_average"):
        book.ol_ratings_average = ol_data["ol_ratings_average"]


def extract_books_from_df(df):
    """
    Converts a Goodreads dataframe into a list of BookNode objects.
    For the first MAX_COVER_LOOKUPS books, fetches data immediately.

    Strategy (all results are DB-cached with a 30-day TTL):
      1. OpenLibrary work data — subjects, awards, cover, description, metadata
      2. OpenLibrary cover search — cover only, if still missing
      3. Inventaire — cover only, as last resort
    """
    books = []
    total_rows = len(df)
    state.UPLOAD_PROGRESS["total"] = total_rows
    state.UPLOAD_PROGRESS["current"] = 0
    state.UPLOAD_PROGRESS["phase"] = "fetching"

    for i, (_, row) in enumerate(df.iterrows()):
        title = row.get("Title")
        author = row.get("Author")

        if not title or not author:
            continue

        rating = row.get("My Rating")
        if rating == 0:
            rating = None

        book = BookNode(
            id=f"{title}::{author}",
            title=title,
            author=author,
            rating=rating,
        )

        if i < MAX_COVER_LOOKUPS:
            # 1. OpenLibrary: full metadata
            _apply_ol_data(book, fetch_work_data(title, author))

            # 2. OL cover search fallback
            if not book.cover_url:
                book.cover_url = fetch_cover_for_read_book(title, author)

            # 3. Inventaire cover fallback
            if not book.cover_url:
                book.cover_url = inventaire_fetch_cover(title, author)

        books.append(book)
        state.UPLOAD_PROGRESS["current"] = i + 1

    return books
