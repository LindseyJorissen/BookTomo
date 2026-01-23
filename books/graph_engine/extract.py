from .schemas import BookNode
from books.openlibrary.client import fetch_work_data


def extract_books_from_df(df):
    books = []

    MAX_ENRICH = 25
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

        books.append(book)

    return books
