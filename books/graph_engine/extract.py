from .schemas import BookNode
from books.googlebooks.client import fetch_book_data as gb_fetch_book_data
from books.openlibrary.client import fetch_work_data, fetch_cover_for_read_book

# Maximum number of books to fetch data for synchronously on upload.
# The rest are filled in by the background thread in background.py.
MAX_COVER_LOOKUPS = 10


def extract_books_from_df(df):
    """
    Converts a Goodreads dataframe into a list of BookNode objects.
    For the first MAX_COVER_LOOKUPS books, fetches cover + genre data immediately.
    Google Books is tried first (better genre data); OpenLibrary is the fallback.
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
            # Google Books: cover + genres
            gb_data = gb_fetch_book_data(title, author)
            if gb_data:
                book.cover_url = gb_data.get("cover_url")
                book.subjects = gb_data.get("genres", [])

            # OpenLibrary fallback for missing cover or genres
            if not book.cover_url or not book.subjects:
                ol_data = fetch_work_data(title, author)
                if ol_data:
                    if not book.cover_url:
                        book.cover_url = ol_data.get("cover_url")
                    if not book.subjects:
                        book.subjects = ol_data.get("subjects", [])

            # Last resort: OpenLibrary search-based cover
            if not book.cover_url:
                book.cover_url = fetch_cover_for_read_book(title, author)

        books.append(book)

    return books
