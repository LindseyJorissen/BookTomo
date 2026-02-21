from .schemas import BookNode
from books.openlibrary.client import (
    fetch_work_data,
    fetch_cover_for_read_book,
)

# Maximaal aantal boeken waarvoor covers direct worden ophaald bij het uploaden.
# De rest wordt achteraf ingeladen via het achtergrondproces in background.py.
MAX_COVER_LOOKUPS = 10


def extract_books_from_df(df):
    """
    Verwerkt een Goodreads-dataframe naar een lijst van BookNode-objecten.
    Haalt voor de eerste MAX_COVER_LOOKUPS (10) boeken ook OpenLibrary-data op
    (omslagfoto en onderwerpen). De rest krijgt covers via het achtergrondproces.
    """
    books = []

    for i, (_, row) in enumerate(df.iterrows()):
        title = row.get("Title")
        author = row.get("Author")

        # Sla rijen zonder titel of auteur over
        if not title or not author:
            continue

        rating = row.get("My Rating")
        if rating == 0:
            rating = None  # Goodreads slaat onbeoordeelde boeken op als 0

        book = BookNode(
            id=f"{title}::{author}",
            title=title,
            author=author,
            rating=rating,
        )

        # Haal OpenLibrary-data op voor de eerste x boeken om de laadtijd beperkt te houden
        if i < MAX_COVER_LOOKUPS:
            work = fetch_work_data(title, author)
            if work:
                book.openlibrary_id = work.get("openlibrary_id")
                book.cover_url = work.get("cover_url")

            # Fallback: zoek omslag via auteur-gebaseerde zoekopdracht
            if not book.cover_url:
                book.cover_url = fetch_cover_for_read_book(title, author)

        books.append(book)

    return books
