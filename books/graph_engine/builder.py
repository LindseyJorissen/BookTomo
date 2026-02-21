import networkx as nx


def build_author_graph(books):
    """
    Bouwt een NetworkX-graaf vanuit een lijst van BookNode-objecten.

    Knooppunttypen:
      - book::     Gelezen boek (met titel, auteur, beoordeling)
      - author::   Auteur (verbindt meerdere boeken van dezelfde schrijver)
      - subject::  Onderwerp uit OpenLibrary (alleen voor boeken waarvoor data is opgehaald)

    gewichten:
      - Boek → auteur: 1.0, verhoogd met beoordelingsmultiplier (max 1.2 bij beoordeling 5)
      - Boek → onderwerp: 0.8
    """
    G = nx.Graph()

    for book in books:
        book_node = f"book::{book.id}"
        author_node = f"author::{book.author}"

        G.add_node(
            book_node,
            type="book",
            title=book.title,
            author=book.author,
            rating=book.rating
        )
        G.add_node(author_node, type="author", name=book.author)

        # Verbind het boek met elk onderwerp als er OpenLibrary-data beschikbaar is
        for subject in book.subjects:
            subject_node = f"subject::{subject}"

            if not G.has_node(subject_node):
                G.add_node(
                    subject_node,
                    type="subject",
                    name=subject
                )

            G.add_edge(
                book_node,
                subject_node,
                weight=0.8
            )

        # Beoordelingsmultiplier: beoordeling 3 = neutraal (1.0), beoordeling 5 = max (1.2)
        rating_multiplier = 1.0
        if book.rating:
            rating_multiplier = min(1.0 + ((book.rating - 3) * 0.1), 1.2)

        G.add_edge(
            book_node,
            author_node,
            weight=1.0 * rating_multiplier
        )

    return G
