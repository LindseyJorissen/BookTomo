from books.openlibrary.client import fetch_cover_for_read_book, fetch_work_data
from books.inventaire.client import fetch_cover as inventaire_fetch_cover
from books.graph_engine import state
from books.graph_engine.extract import _apply_ol_data, _apply_gb_genres


def load_remaining_covers():
    """
    Background task: fetch covers, metadata, and genres for every book in the library.
    Started as a daemon thread from upload_goodreads so the initial response isn't blocked.

    Runs for ALL books — not just the first MAX_COVER_LOOKUPS fetched synchronously.
    DB lookups are instant for books already stored; only missing data triggers network calls.

    Per-book strategy:
      1. OpenLibrary work data  — subjects, awards, cover, description, metadata (DB-first)
      2. OpenLibrary cover search — cover only, if still missing
      3. Inventaire             — cover only, last resort
      4. Google Books genres    — stored permanently in CachedBook.google_books_genres

    After all books are processed the genre graph and community clusters are rebuilt
    so the Reading Universe reflects the full subject data rather than just the first
    10 books that were processed synchronously during upload.
    """
    total = len(state.BOOK_NODES)
    state.BACKGROUND_PROGRESS = {"current": 0, "total": total, "done": False}

    for i, book in enumerate(state.BOOK_NODES, 1):
        try:
            needs_cover = not book.cover_url
            needs_subjects = not book.subjects

            # Steps 1–3: only hit the network if cover or subjects are missing.
            # fetch_work_data returns instantly from DB if already stored.
            if needs_cover or needs_subjects:
                ol_data = fetch_work_data(book.title, book.author, is_read=True)
                _apply_ol_data(book, ol_data)

                needs_cover = not book.cover_url

                # 2. OL cover search fallback
                if needs_cover:
                    cover = fetch_cover_for_read_book(book.title, book.author, is_read=True)
                    if cover:
                        book.cover_url = cover
                        needs_cover = False

                # 3. Inventaire cover fallback
                if needs_cover:
                    cover = inventaire_fetch_cover(book.title, book.author)
                    if cover:
                        book.cover_url = cover

            # Step 4: Google Books genres — always runs; DB-cached so instant on repeat uploads.
            _apply_gb_genres(book)

        except Exception:
            pass  # Never let a single book stall the whole background thread

        state.BACKGROUND_PROGRESS["current"] = i

    # Rebuild graph and communities now that all subjects are populated.
    # This replaces the initial clusters that were built with only the first 10 books.
    try:
        from books.graph_engine.builder import build_author_graph, build_genre_graph
        from books.graph_engine.universe import detect_communities
        state.GRAPH = build_author_graph(state.BOOK_NODES)
        genre_graph = build_genre_graph(state.BOOK_NODES)
        state.COMMUNITIES = detect_communities(genre_graph)
        state.UNIVERSE_VERSION += 1
    except Exception:
        pass

    state.BACKGROUND_PROGRESS["done"] = True
