from .schemas import BookNode
from books.openlibrary.client import fetch_work_data, fetch_cover_for_read_book
from books.inventaire.client import fetch_cover as inventaire_fetch_cover

# Maximum number of books to fetch data for synchronously on upload.
# The rest are filled in by the background thread in background.py.
MAX_COVER_LOOKUPS = 10


def extract_books_from_df(df):
    """
    Converts a Goodreads dataframe into a list of BookNode objects.
    For the first MAX_COVER_LOOKUPS books, fetches cover + subject data immediately.

    Strategy (all results are DB-cached with a 30-day TTL):
      1. OpenLibrary work data — subjects + cover
      2. OpenLibrary cover search — cover only, if still missing
      3. Inventaire — cover only, as last resort
    """
    books = []

    for i, (_, row) in enumerate(df.iterrows()):
        title = row.get("Title")
        author = row.get("Author")

        if not title or not author:
            continue

        rating = row.get("My Rating")
        if rating == 0:
            rating = None  # Goodreads stores unrated books as 0

        book = BookNode(
            id=f"{title}::{author}",
            title=title,
            author=author,
            rating=rating,
        )

        if i < MAX_COVER_LOOKUPS:
            # 1. OpenLibrary: subjects + cover
            ol_data = fetch_work_data(title, author)
            if ol_data:
                if not book.cover_url and ol_data.get("cover_url"):
                    book.cover_url = ol_data["cover_url"]
                if not book.subjects and ol_data.get("subjects"):
                    book.subjects = ol_data["subjects"]
                if not book.openlibrary_id and ol_data.get("openlibrary_id"):
                    book.openlibrary_id = ol_data["openlibrary_id"]

            # 2. OpenLibrary cover search fallback
            if not book.cover_url:
                book.cover_url = fetch_cover_for_read_book(title, author)

            # 3. Inventaire cover fallback
            if not book.cover_url:
                book.cover_url = inventaire_fetch_cover(title, author)

        books.append(book)

    return books
