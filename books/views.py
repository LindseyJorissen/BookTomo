import datetime
import re
import threading

import pandas as pd
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from books.graph_engine import state
from books.graph_engine.extract import extract_books_from_df
from books.graph_engine.schemas import BookNode
from books.graph_engine.universe import detect_communities, render_universe_graph, render_cluster_graph
from books.graph_engine.visualize_interactive import visualize_book_ego_graph_interactive
from books.openlibrary.background import load_remaining_covers
from books.openlibrary.client import (
    fetch_books_by_award,
    fetch_books_by_era,
    fetch_books_by_subject,
    fetch_unread_books_by_author,
    fetch_work_data,
    normalize_title,
)
from books.inventaire.client import (
    fetch_books_by_subject as inventaire_fetch_by_subject,
    fetch_books_by_author as inventaire_fetch_by_author,
)

_AWARD_DISPLAY = {
    "hugo_award": "Hugo Award",
    "nebula_award": "Nebula Award",
    "pulitzer_prize": "Pulitzer Prize",
    "national_book_award": "National Book Award",
    "booker_prize": "Booker Prize",
    "world_fantasy_award": "World Fantasy Award",
    "locus_award": "Locus Award",
    "edgar_allan_poe_award": "Edgar Award",
}

# Approximate similarity scores per recommendation type
_SIMILARITY_SCORES = {
    "author": 0.88,
    "genre": 0.74,
    "award": 0.68,
    "era": 0.60,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def compute_cadence(date_series):
    """Calculate average, median, fastest, and slowest days between books."""
    dates = (
        date_series.dropna()
        .dt.date
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    if len(dates) < 2:
        return None
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    return {
        "avg_days": round(sum(gaps) / len(gaps), 1),
        "median_days": sorted(gaps)[len(gaps) // 2],
        "fastest_days": min(gaps),
        "slowest_days": max(gaps),
        "first_finished": dates[0].isoformat(),
        "last_finished": dates[-1].isoformat(),
    }


def compute_stats(subset):
    """Calculate summary statistics (books, pages, rating, top author) for a dataframe subset."""
    if subset.empty:
        return {"total_books": 0, "total_pages": 0, "avg_rating": 0, "top_author": None}

    avg_rating = 0
    if "My Rating" in subset.columns:
        rated = subset[subset["My Rating"] > 0]
        if not rated.empty:
            avg_rating = round(rated["My Rating"].mean(), 2)

    total_pages = int(subset["Number of Pages"].fillna(0).sum())
    top_author = subset["Author"].mode()[0] if "Author" in subset.columns else None

    return {
        "total_books": len(subset),
        "total_pages": total_pages,
        "avg_rating": avg_rating,
        "top_author": top_author,
    }


def compute_book_lengths(subset):
    """Calculate page stats: average pages, longest book, and histogram by page range."""
    pages = subset["Number of Pages"].dropna()
    if pages.empty:
        return None

    longest = subset.loc[pages.idxmax()]
    bins = [
        (0, 200, "0-200"),
        (200, 300, "200-300"),
        (300, 400, "300-400"),
        (400, 500, "400-500"),
        (500, float("inf"), "500+"),
    ]
    histogram = [
        {"range": label, "count": int(pages[(pages >= low) & (pages < high)].count())}
        for low, high, label in bins
    ]
    return {
        "average_pages": int(pages.mean()),
        "longest_book": {
            "title": longest.get("Title"),
            "author": longest.get("Author"),
            "pages": int(longest.get("Number of Pages")),
        },
        "histogram": histogram,
    }


def _detect_series(title_a: str, title_b: str) -> bool:
    """Return True if two titles appear to belong to the same series.

    Checks two signals:
      1. Titles share 2+ leading words (e.g. "Harry Potter and…" / "Harry Potter: …")
      2. Stripping trailing series numbers/subtitles leaves identical base titles
    """
    def base(t: str) -> str:
        t = re.sub(r'\s*[#(]\d+[)\s].*$', '', t)   # strip "#1", "(1)"
        t = t.split(":")[0]                          # strip ": subtitle"
        return t.lower().strip()

    if len(base(title_a)) < 4:
        return False
    if base(title_a) == base(title_b):
        return True

    words_a = title_a.lower().split()
    words_b = title_b.lower().split()
    common = sum(1 for w1, w2 in zip(words_a, words_b) if w1 == w2)
    return common >= 2


# ── Views ─────────────────────────────────────────────────────────────────────

@csrf_exempt
def upload_goodreads(request):
    """Process an uploaded Goodreads CSV and return reading statistics as JSON.
    Also builds the global graph, computes communities, and starts cover loading.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    df = pd.read_csv(file)
    read_df = df
    if "Exclusive Shelf" in df.columns:
        read_df = df[df["Exclusive Shelf"] == "read"]

    state.UPLOAD_PROGRESS = {"phase": "parsing", "current": 0, "total": 0}
    state.UNIVERSE_VERSION = 0
    read_books = extract_books_from_df(read_df)
    state.BOOK_NODES = read_books

    # Extract to-read / currently-reading as lightweight BookNodes (metadata fetched in background)
    wtr_books = []
    if "Exclusive Shelf" in df.columns:
        wtr_df = df[df["Exclusive Shelf"].isin(["to-read", "currently-reading"])]
        for _, wtr_row in wtr_df.iterrows():
            wt = wtr_row.get("Title")
            wa = wtr_row.get("Author")
            if not wt or not wa:
                continue
            raw_gid = wtr_row.get("Book Id")
            try:
                wgid = str(int(raw_gid)) if raw_gid and str(raw_gid) not in ("", "nan") else None
            except (ValueError, TypeError):
                wgid = None
            wtr_books.append(BookNode(id=f"{wt}::{wa}", title=wt, author=wa, goodreads_id=wgid))
    state.WANT_TO_READ_NODES = wtr_books

    state.UPLOAD_PROGRESS["phase"] = "building"
    from books.graph_engine.builder import build_author_graph, build_genre_graph
    state.GRAPH = build_author_graph(read_books)
    genre_graph = build_genre_graph(read_books)
    state.COMMUNITIES = detect_communities(genre_graph)
    state.UPLOAD_PROGRESS["phase"] = "done"

    df["Date Read"] = pd.to_datetime(df.get("Date Read"), errors="coerce")
    df["Year Read"] = df["Date Read"].dt.year
    df["Month Read"] = df["Date Read"].dt.month

    current_year = datetime.date.today().year
    df_current_year = df[df["Year Read"] == current_year]

    yearly_counts = df["Year Read"].dropna().value_counts().sort_index().to_dict()
    monthly_counts = (
        df_current_year["Month Read"].dropna().value_counts().sort_index().to_dict()
        if not df_current_year.empty else {}
    )

    pub_counts_all, pub_counts_this_year = {}, {}
    oldest_pub_year = None
    if "Original Publication Year" in df.columns:
        df["Original Publication Year"] = pd.to_numeric(
            df["Original Publication Year"], errors="coerce"
        )
        years = df["Original Publication Year"].dropna()
        if not years.empty:
            oldest_pub_year = int(years.min())
        pub_counts_all = years.astype(int).value_counts().sort_index().to_dict()
        pub_counts_this_year = (
            df_current_year["Original Publication Year"].dropna()
            .astype(int).value_counts().sort_index().to_dict()
            if not df_current_year.empty else {}
        )

    scatter_points_all = [
        {"pub_year": int(row["Original Publication Year"]), "read_value": int(row["Year Read"])}
        for _, row in df[["Original Publication Year", "Year Read"]].dropna().iterrows()
    ]
    scatter_points_this_year = [
        {"pub_year": int(row["Original Publication Year"]), "read_value": int(row["Month Read"])}
        for _, row in df_current_year[["Original Publication Year", "Month Read"]].dropna().iterrows()
    ]

    stats = {
        "overall": {**compute_stats(read_df), "cadence": compute_cadence(df["Date Read"])},
        "this_year": {
            **compute_stats(df_current_year),
            "cadence": compute_cadence(df_current_year["Date Read"]),
        },
        "yearly_books": yearly_counts,
        "monthly_books": monthly_counts,
        "publication_years_overall": pub_counts_all,
        "publication_years_this_year": pub_counts_this_year,
        "scatter_publication_vs_read_all": scatter_points_all,
        "scatter_publication_vs_read_year": scatter_points_this_year,
        "book_lengths": {
            "overall": compute_book_lengths(read_df),
            "this_year": compute_book_lengths(
                df_current_year[df_current_year["Exclusive Shelf"] == "read"]
                if "Exclusive Shelf" in df_current_year.columns
                else df_current_year
            ),
        },
        "oldest_pub_year": oldest_pub_year,
        "books": [
            {"id": book.id, "title": book.title, "author": book.author, "cover_url": book.cover_url}
            for book in read_books
        ],
    }

    threading.Thread(target=load_remaining_covers, daemon=True).start()
    return JsonResponse(stats)


def upload_progress_view(request):
    """Return current upload progress for the frontend progress bar."""
    return JsonResponse(state.UPLOAD_PROGRESS)


def book_covers_view(request):
    """Return all known book covers and current universe version for frontend polling."""
    return JsonResponse({
        "covers": [
            {"id": book.id, "cover_url": book.cover_url}
            for book in state.BOOK_NODES
            if book.cover_url
        ],
        "universe_version": state.UNIVERSE_VERSION,
        "background_progress": state.BACKGROUND_PROGRESS,
    })


def universe_graph_view(request):
    """Render the Reading Universe overview graph with taste cluster nodes.

    Uses cached community detection results (computed at upload time).
    Falls back to a friendly message if fewer than 2 clusters were found.
    """
    if state.GRAPH is None:
        return HttpResponse("Graph not built yet", status=400)

    clusters = state.COMMUNITIES
    if not clusters or len(clusters) < 2:
        # Try computing on demand (e.g. if state was reset)
        clusters = detect_communities(state.GRAPH)

    if not clusters or len(clusters) < 2:
        return HttpResponse("""
        <html><body style="
          font-family:Arial; color:#4c483c;
          display:flex; align-items:center; justify-content:center;
          height:100%; background:#faf9f6; text-align:center;">
          <div style="opacity:0.7; padding:2rem;">
            <p style="font-size:1.1rem; margin-bottom:0.5rem;">
              Your Reading Universe is taking shape.
            </p>
            <p style="font-size:0.9rem;">
              Select a book from the list to explore recommendations.
            </p>
          </div>
        </body></html>
        """)

    return HttpResponse(render_universe_graph(clusters, state.GRAPH))


def cluster_graph_view(request):
    """Render a PyVis graph of books within a single taste cluster.

    Accepts a GET param `nodes` — a JSON-encoded list of book node ID strings
    (e.g. ["book::Title::Author", ...]).
    """
    if state.GRAPH is None:
        return HttpResponse("Graph not built yet", status=400)

    import json as _json
    raw = request.GET.get("nodes", "[]")
    try:
        book_nodes = _json.loads(raw)
    except Exception:
        return HttpResponse("Invalid nodes param", status=400)

    if not book_nodes:
        return HttpResponse("No book nodes provided", status=400)

    cover_map = {f"book::{b.id}": b.cover_url for b in state.BOOK_NODES if b.cover_url}
    html = render_cluster_graph(book_nodes, state.GRAPH, cover_map=cover_map)
    return HttpResponse(html)


def full_network_view(request):
    """Render a PyVis graph of all read books and their connections."""
    if state.GRAPH is None:
        return HttpResponse("Graph not built yet", status=400)

    from books.graph_engine.full_network import render_full_network
    cover_map = {f"book::{b.id}": b.cover_url for b in state.BOOK_NODES if b.cover_url}
    html = render_full_network(state.GRAPH, communities=state.COMMUNITIES, cover_map=cover_map)
    return HttpResponse(html)


def book_graph_view(request, book_id):
    """Generate an interactive ego-graph around the selected book with recommendations.

    Adds four types of recommendations (author, genre, award, era) and
    annotates each with a similarity_score so the frontend panel can explain it.

    Accepts optional filter query params: genres, authors, year_min, year_max.
    Returns a PyVis HTML visualization.
    """
    if state.GRAPH is None:
        return HttpResponse("Graph not built yet", status=400)

    graph = state.GRAPH.copy()

    read_titles = {
        normalize_title(data["title"]).lower()
        for _, data in graph.nodes(data=True)
        if data.get("type") == "book" and not data.get("unread")
    }

    author = graph.nodes.get(book_id, {}).get("author")
    if not author:
        return HttpResponse("Author not found", status=400)

    min_similarity = float(request.GET.get("min_similarity", 0.5))
    hide_started_series = request.GET.get("hide_started_series", "false").lower() == "true"
    all_read_titles = [b.title for b in state.BOOK_NODES]

    # Score genres by sum of ratings of their connected read books
    genre_scores: dict = {}
    for node, data in graph.nodes(data=True):
        if data.get("type") != "subject":
            continue
        genre_name = data.get("name", "")
        for neighbor in graph.neighbors(node):
            nb_data = graph.nodes.get(neighbor, {})
            if nb_data.get("type") == "book" and not nb_data.get("unread"):
                genre_scores[genre_name] = genre_scores.get(genre_name, 0) + (nb_data.get("rating") or 3)

    # Fetch OL metadata for the selected book
    book_title = graph.nodes.get(book_id, {}).get("title", "")
    book_genres, book_award_slugs, book_first_publish_year = [], [], None
    if book_title:
        ol_data = fetch_work_data(book_title, author)
        if ol_data:
            book_genres = ol_data.get("subjects", [])
            book_award_slugs = ol_data.get("award_slugs", [])
            book_first_publish_year = ol_data.get("first_publish_year")

    ranked_genres = sorted(book_genres, key=lambda g: genre_scores.get(g, 0), reverse=True)[:3]

    already_added: set = set()

    # --- Want-to-read: author matches (from user's own Goodreads to-read list) ---
    if _SIMILARITY_SCORES["author"] >= min_similarity:
        for wtr in state.WANT_TO_READ_NODES:
            if wtr.author.lower() != author.lower():
                continue
            norm = normalize_title(wtr.title).lower()
            if norm in read_titles or norm in already_added:
                continue
            if hide_started_series and any(_detect_series(rt, wtr.title) for rt in all_read_titles):
                continue
            unread_node = f"rec::{wtr.title}::{wtr.author}"
            if not graph.has_node(unread_node):
                signals = [{"label": "Author", "value": author}, {"label": "Source", "value": "Your to-read list"}]
                if ranked_genres:
                    signals.append({"label": "Genres", "value": ", ".join(ranked_genres[:2])})
                graph.add_node(
                    unread_node,
                    type="book",
                    title=wtr.title,
                    author=wtr.author,
                    unread=True,
                    cover_url=wtr.cover_url or "",
                    reason=f"Same author as {author}",
                    signals=signals,
                    similarity_score=_SIMILARITY_SCORES["author"],
                )
            graph.add_edge(book_id, unread_node, type="recommendation", weight=0.6)
            author_node = f"author::{author}"
            if not graph.has_node(author_node):
                graph.add_node(author_node, type="author", name=author)
            graph.add_edge(unread_node, author_node, weight=0.4)
            already_added.add(norm)

    # --- Author-based recommendations (API fallback) ---
    unread_books = fetch_unread_books_by_author(author=author, read_titles=read_titles, limit=8)
    if not unread_books:
        unread_books = inventaire_fetch_by_author(author=author, read_titles=read_titles, limit=8)

    for book in unread_books:
        if _SIMILARITY_SCORES["author"] < min_similarity:
            break
        if hide_started_series and any(_detect_series(rt, book["title"]) for rt in all_read_titles):
            continue
        unread_node = f"rec::{book['title']}::{book['author']}"
        if not graph.has_node(unread_node):
            signals = [{"label": "Author", "value": author}]
            if ranked_genres:
                signals.append({"label": "Genres", "value": ", ".join(ranked_genres[:2])})
            if book_title and _detect_series(book_title, book["title"]):
                signals.append({"label": "Series", "value": "Same series"})
            graph.add_node(
                unread_node,
                type="book",
                title=book["title"],
                author=book["author"],
                unread=True,
                cover_url=book["cover_url"],
                reason=f"Same author as {author}",
                signals=signals,
                similarity_score=_SIMILARITY_SCORES["author"],
            )
        graph.add_edge(book_id, unread_node, type="recommendation", weight=0.6)
        author_node = f"author::{author}"
        if not graph.has_node(author_node):
            graph.add_node(author_node, type="author", name=author)
        graph.add_edge(unread_node, author_node, weight=0.4)

    already_added |= {normalize_title(b["title"]).lower() for b in unread_books}

    # --- Want-to-read: genre matches (only once background has enriched subjects) ---
    if _SIMILARITY_SCORES["genre"] >= min_similarity:
        for wtr in state.WANT_TO_READ_NODES:
            norm = normalize_title(wtr.title).lower()
            if norm in read_titles or norm in already_added or not wtr.subjects:
                continue
            shared = [g for g in ranked_genres if g in wtr.subjects]
            if not shared:
                continue
            if hide_started_series and any(_detect_series(rt, wtr.title) for rt in all_read_titles):
                continue
            match_genre = shared[0]
            genre_node = f"subject::{match_genre}"
            if not graph.has_node(genre_node):
                graph.add_node(genre_node, type="subject", name=match_genre)
            if not graph.has_edge(book_id, genre_node):
                graph.add_edge(book_id, genre_node, weight=0.8)
            unread_node = f"rec::{wtr.title}::{wtr.author}"
            if not graph.has_node(unread_node):
                graph.add_node(
                    unread_node,
                    type="book",
                    title=wtr.title,
                    author=wtr.author,
                    unread=True,
                    cover_url=wtr.cover_url or "",
                    reason=f"Shares genre: {match_genre}",
                    signals=[
                        {"label": "Genre", "value": match_genre},
                        {"label": "Source", "value": "Your to-read list"},
                    ],
                    similarity_score=_SIMILARITY_SCORES["genre"],
                )
                graph.add_edge(unread_node, genre_node, type="recommendation", weight=0.5)
            already_added.add(norm)

    # --- Genre-based recommendations ---
    for genre in ranked_genres:
        if _SIMILARITY_SCORES["genre"] < min_similarity:
            break
        genre_node = f"subject::{genre}"
        if not graph.has_node(genre_node):
            graph.add_node(genre_node, type="subject", name=genre)
        if not graph.has_edge(book_id, genre_node):
            graph.add_edge(book_id, genre_node, weight=0.8)

        genre_books = fetch_books_by_subject(genre, limit=5) or inventaire_fetch_by_subject(genre, limit=5)
        for book in genre_books:
            norm = normalize_title(book["title"]).lower()
            if norm in read_titles or norm in already_added:
                continue
            if hide_started_series and any(_detect_series(rt, book["title"]) for rt in all_read_titles):
                continue
            unread_node = f"rec::{book['title']}::{book['author']}"
            if not graph.has_node(unread_node):
                graph.add_node(
                    unread_node,
                    type="book",
                    title=book["title"],
                    author=book.get("author", ""),
                    unread=True,
                    cover_url=book["cover_url"],
                    reason=f"Shares genre: {genre}",
                    signals=[{"label": "Genre", "value": genre}],
                    similarity_score=_SIMILARITY_SCORES["genre"],
                )
            graph.add_edge(unread_node, genre_node, type="recommendation", weight=0.5)
            already_added.add(norm)

    # --- Award-based recommendations ---
    if _SIMILARITY_SCORES["award"] >= min_similarity:
        for slug in book_award_slugs[:2]:
            award_name = _AWARD_DISPLAY.get(slug) or slug.replace("_", " ").title()
            award_node = f"award::{slug}"
            if not graph.has_node(award_node):
                graph.add_node(award_node, type="award", name=award_name)
            if not graph.has_edge(book_id, award_node):
                graph.add_edge(book_id, award_node, weight=0.7)

            for book in fetch_books_by_award(slug, limit=5):
                norm = normalize_title(book["title"]).lower()
                if norm in read_titles or norm in already_added:
                    continue
                if hide_started_series and any(_detect_series(rt, book["title"]) for rt in all_read_titles):
                    continue
                unread_node = f"rec::{book['title']}::{book['author']}"
                if not graph.has_node(unread_node):
                    graph.add_node(
                        unread_node,
                        type="book",
                        title=book["title"],
                        author=book.get("author", ""),
                        unread=True,
                        cover_url=book["cover_url"],
                        reason=f"Also won the {award_name}",
                        signals=[{"label": "Award", "value": award_name}],
                        similarity_score=_SIMILARITY_SCORES["award"],
                    )
                graph.add_edge(unread_node, award_node, type="recommendation", weight=0.7)
                already_added.add(norm)

    # --- Era-based recommendations ---
    if book_first_publish_year and _SIMILARITY_SCORES["era"] >= min_similarity:
        decade_start = (book_first_publish_year // 10) * 10
        decade_label = f"{decade_start}s"
        era_node = f"era::{decade_start}"
        if not graph.has_node(era_node):
            graph.add_node(era_node, type="era", name=decade_label)
        if not graph.has_edge(book_id, era_node):
            graph.add_edge(book_id, era_node, weight=0.6)

        primary_genre = ranked_genres[0] if ranked_genres else None
        for book in fetch_books_by_era(decade_start, primary_genre, limit=5):
            norm = normalize_title(book["title"]).lower()
            if norm in read_titles or norm in already_added:
                continue
            if hide_started_series and any(_detect_series(rt, book["title"]) for rt in all_read_titles):
                continue
            unread_node = f"rec::{book['title']}::{book['author']}"
            if not graph.has_node(unread_node):
                graph.add_node(
                    unread_node,
                    type="book",
                    title=book["title"],
                    author=book.get("author", ""),
                    unread=True,
                    cover_url=book["cover_url"],
                    reason=f"Popular from the {decade_label}",
                    signals=[{"label": "Era", "value": decade_label}],
                    similarity_score=_SIMILARITY_SCORES["era"],
                )
            graph.add_edge(unread_node, era_node, type="recommendation", weight=0.5)
            already_added.add(norm)

    html = visualize_book_ego_graph_interactive(graph, book_id)
    return HttpResponse(html)


def book_details_view(request, book_id):
    """Return detailed book info and similar books for the sidebar detail panel."""
    book = next((b for b in state.BOOK_NODES if b.id == book_id), None)
    if not book:
        return JsonResponse({"error": "Book not found"}, status=404)

    similar = []
    seen_ids = {book.id}

    # Genre matches first (up to 3)
    if book.subjects:
        book_genre_set = set(book.subjects)
        for other in state.BOOK_NODES:
            if other.id in seen_ids or len(similar) >= 3:
                break
            if other.subjects and other.author != book.author:
                shared = book_genre_set & set(other.subjects)
                if shared:
                    similar.append({
                        "id": other.id,
                        "title": other.title,
                        "author": other.author,
                        "cover_url": other.cover_url,
                        "reason": f"Shares genre: {next(iter(shared))}",
                    })
                    seen_ids.add(other.id)

    # Same-author fills remaining slots (up to 2)
    for other in state.BOOK_NODES:
        if other.id in seen_ids or len(similar) >= 5:
            break
        if other.author == book.author:
            reason = "Shared universe" if _detect_series(book.title, other.title) else "Same author"
            similar.append({
                "id": other.id,
                "title": other.title,
                "author": other.author,
                "cover_url": other.cover_url,
                "reason": reason,
            })
            seen_ids.add(other.id)

    return JsonResponse({
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "rating": book.rating,
        "pages": book.page_count,
        "genres": book.subjects[:5] if book.subjects else [],
        "cover_url": book.cover_url,
        "description": book.description,
        "similar": similar,
    })


def best_recommendation_view(request):
    """Return the single best recommendation with explanation reasons."""
    if not state.BOOK_NODES:
        return JsonResponse({"error": "No data loaded"}, status=404)

    genre_counts: dict = {}
    for book in state.BOOK_NODES:
        for genre in book.subjects or []:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    if not genre_counts:
        return JsonResponse({"error": "No genre data available"}, status=404)

    read_authors = {b.author for b in state.BOOK_NODES}
    read_titles_norm = {normalize_title(b.title).lower() for b in state.BOOK_NODES}
    top_genres = sorted(genre_counts, key=genre_counts.get, reverse=True)[:3]

    candidates = []
    seen_norms: set = set()

    for genre in top_genres:
        for book in fetch_books_by_subject(genre, limit=10):
            norm = normalize_title(book["title"]).lower()
            if norm in read_titles_norm or norm in seen_norms:
                continue
            seen_norms.add(norm)

            score = genre_counts.get(genre, 0)
            reasons = [f"Same genre cluster as {genre_counts[genre]} books you liked"]

            if book.get("author") in read_authors:
                score += 5
                reasons.insert(0, "Same author as books you enjoyed")

            candidates.append({
                "title": book["title"],
                "author": book.get("author", ""),
                "cover_url": book.get("cover_url", ""),
                "reasons": reasons[:3],
                "score": score,
            })

    if not candidates:
        return JsonResponse({"error": "No recommendations found"}, status=404)

    return JsonResponse(max(candidates, key=lambda x: x["score"]))


def filter_options_view(request):
    """Return available genres, authors, and year range for graph filtering."""
    if not state.BOOK_NODES:
        return JsonResponse({"genres": [], "authors": [], "year_min": 1900, "year_max": 2024})

    genre_counts: dict = {}
    authors: set = set()
    years = []

    for book in state.BOOK_NODES:
        if book.author:
            authors.add(book.author)
        for genre in book.subjects or []:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
        if book.first_publish_year:
            years.append(book.first_publish_year)

    top_genres = sorted(genre_counts, key=genre_counts.get, reverse=True)[:30]

    return JsonResponse({
        "genres": top_genres,
        "authors": sorted(authors),
        "year_min": min(years) if years else 1900,
        "year_max": max(years) if years else 2024,
    })
