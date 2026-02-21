from .schemas import BookNode
from books.openlibrary.client import (
    fetch_work_data,
    fetch_cover_for_read_book,
)

MAX_COVER_LOOKUPS = 10


def extract_books_from_df(df):
    books = []

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
            work = fetch_work_data(title, author)
            if work:
                book.openlibrary_id = work.get("openlibrary_id")
                book.cover_url = work.get("cover_url")

            if not book.cover_url:
                book.cover_url = fetch_cover_for_read_book(title, author)

        books.append(book)

    return books
