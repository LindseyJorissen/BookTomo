import networkx as nx


def build_author_graph(books):
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

        rating_multiplier = 1.0
        if book.rating:
            rating_multiplier = min(1.0 + ((book.rating - 3) * 0.1), 1.2)

        G.add_edge(
            book_node,
            author_node,
            weight=1.0 * rating_multiplier
        )
    return G
