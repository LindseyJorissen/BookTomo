from books.openlibrary.client import fetch_cover_for_read_book
from books.graph_engine import state


def load_remaining_covers():
    """
    Achtergrondtaak die ontbrekende omslagfoto's aanvult na het uploaden.
    Wordt als daemon-thread gestart vanuit upload_goodreads, zodat de
    initiële respons niet vertraagd wordt door extra API-verzoeken.
    Werkt de cover_url direct bij op het BookNode-object in state.BOOK_NODES.
    """
    for book in state.BOOK_NODES:
        if book.cover_url:
            continue  # Omslag al bekend, overslaan

        cover = fetch_cover_for_read_book(book.title, book.author)
        if cover:
            book.cover_url = cover
