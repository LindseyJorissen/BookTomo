import pandas as pd
import datetime
import threading

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from books.graph_engine import state
from books.graph_engine.extract import extract_books_from_df
from books.graph_engine.visualize_interactive import visualize_book_ego_graph_interactive
from books.googlebooks.client import (
    fetch_book_data as gb_fetch_book_data,
    fetch_books_by_genre,
    fetch_books_by_author as gb_fetch_books_by_author,
)
from books.openlibrary.background import load_remaining_covers
from books.openlibrary.client import (
    fetch_unread_books_by_author,
    fetch_books_by_subject,
    fetch_work_data,
    normalize_title,
)


def compute_cadence(date_series):
    """
    Berekent gemiddeld aantal dagen tussen 2 gelezen boeken, door een reeks datums te vergelijken
    Geeft None terug als er minder dan 2 datums zijn (kan niet vergelijken met 1 datum)
    """
    dates = (
        date_series.dropna()       # Lege datums verwijderen
        .dt.date                   # Tijdstempel → alleen datum
        .drop_duplicates()
        .sort_values()             # Oud → nieuw sorteren
        .tolist()
    )

    if len(dates) < 2:
        return None

    # Bereken het aantal dagen tussen leesbeurten
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]

    return {
        "avg_days": round(sum(gaps) / len(gaps), 1),
        "median_days": sorted(gaps)[len(gaps) // 2],
        "fastest_days": min(gaps),
        "slowest_days": max(gaps),
        "first_finished": dates[0].isoformat(),
        "last_finished": dates[-1].isoformat(),
    }


@csrf_exempt  # voor lokaal testen - frontend en backend draaien apart, anders krijg je foutmeldingen
def upload_goodreads(request):
    """
    Verwerkt een geüploade Goodreads-CSV en retourneert leesstatistieken als JSON.
    Bouwt ook de globale graaf en start een achtergrondthread voor ontbrekende omslagen.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    df = pd.read_csv(file)

    # Filter alleen gelezen boeken (als die kolom zelfs aanwezig is)
    read_df = df
    if "Exclusive Shelf" in df.columns:
        read_df = df[df["Exclusive Shelf"] == "read"]

    # Zet CSV-data om naar 'BookNodes' en genereer de auteur-graaf
    read_books = extract_books_from_df(read_df)
    state.BOOK_NODES = read_books
    from books.graph_engine.builder import build_author_graph
    state.GRAPH = build_author_graph(read_books)

    # Datumkolommen aanmaken voor statistieken
    df["Date Read"] = pd.to_datetime(df.get("Date Read"), errors="coerce")
    df["Year Read"] = df["Date Read"].dt.year
    df["Month Read"] = df["Date Read"].dt.month

    current_year = datetime.date.today().year
    df_current_year = df[df["Year Read"] == current_year]

    cadence_overall = compute_cadence(df["Date Read"])
    cadence_this_year = compute_cadence(df_current_year["Date Read"])

    # Aantal gelezen boeken per jaar (voor staafdiagram)
    yearly_counts = (
        df["Year Read"]
        .dropna()
        .value_counts()
        .sort_index()
        .to_dict()
    )

    # Aantal gelezen boeken per maand in het huidige jaar
    monthly_counts = (
        df_current_year["Month Read"]
        .dropna()
        .value_counts()
        .sort_index()
        .to_dict()
        if not df_current_year.empty
        else {}
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

        # Aantal boeken per publicatiejaar (all time)
        pub_counts_all = (
            years.astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )

        # Aantal boeken per publicatiejaar (alleen dit jaar gelezen)
        pub_counts_this_year = (
            df_current_year["Original Publication Year"]
            .dropna()
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
            if not df_current_year.empty
            else {}
        )

    # Scatterplot-datapunten: publicatiejaar vs. jaar gelezen
    scatter_points_all = [
        {
            "pub_year": int(row["Original Publication Year"]),
            "read_value": int(row["Year Read"]),
        }
        for _, row in df[["Original Publication Year", "Year Read"]]
        .dropna()
        .iterrows()
    ]

    # Scatterplot-datapunten: publicatiejaar vs. maand gelezen (dit jaar)
    scatter_points_this_year = [
        {
            "pub_year": int(row["Original Publication Year"]),
            "read_value": int(row["Month Read"]),
        }
        for _, row in df_current_year[
            ["Original Publication Year", "Month Read"]
        ]
        .dropna()
        .iterrows()
    ]

    def compute_stats(subset):
        """Berekent samenvattende statistieken voor een subset van het dataframe."""
        if subset.empty:
            return {
                "total_books": 0,
                "total_pages": 0,
                "avg_rating": 0,
                "top_author": None,
            }

        avg_rating = 0
        if "My Rating" in subset.columns:
            rated = subset[subset["My Rating"] > 0]  # Goodreads slaat 0 op als 'niet beoordeeld'
            if not rated.empty:
                avg_rating = round(rated["My Rating"].mean(), 2)

        total_pages = int(
            subset["Number of Pages"].fillna(0).sum()
        )

        # Meest voorkomende auteur
        top_author = (
            subset["Author"].mode()[0]
            if "Author" in subset.columns
            else None
        )

        return {
            "total_books": len(subset),
            "total_pages": total_pages,
            "avg_rating": avg_rating,
            "top_author": top_author,
        }

    def compute_book_lengths(subset):
        """
        Berekent paginastatistieken: gemiddelde, langste boek en histogram per paginabereik.
        Geeft None terug als er geen paginadata beschikbaar is.
        """
        pages = subset["Number of Pages"].dropna()
        if pages.empty:
            return None

        longest = subset.loc[pages.idxmax()]

        # Verdeel paginaantallen in intervallen voor het histogram
        bins = [
            (0, 200, "0-200"),
            (200, 300, "200-300"),
            (300, 400, "300-400"),
            (400, 500, "400-500"),
            (500, float("inf"), "500+"),
        ]

        histogram = [
            {
                "range": label,
                "count": int(
                    pages[(pages >= low) & (pages < high)].count()
                ),
            }
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

    stats = {
        "overall": {
            **compute_stats(read_df),
            "cadence": cadence_overall,
        },
        "this_year": {
            **compute_stats(df_current_year),
            "cadence": cadence_this_year,
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
                # Filter op gelezen boeken
                df_current_year[df_current_year["Exclusive Shelf"] == "read"]
                if "Exclusive Shelf" in df_current_year.columns
                else df_current_year
            ),
        },
        "oldest_pub_year": oldest_pub_year,
        "books": [
            {
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "cover_url": book.cover_url,
            }
            for book in read_books
        ],
    }

    # Start achtergrondthread voor omslagen die nog niet zijn opgehaald
    threading.Thread(
        target=load_remaining_covers,
        daemon=True
    ).start()

    return JsonResponse(stats)


def book_graph_view(request, book_id):
    """
    Genereert een interactieve ego-graaf rondom het geselecteerde boek.
    
    Voegt twee soorten aanbevelingen toe aan de graaf:
      1. Ongelezen boeken van dezelfde auteur
      2. Boeken met gemeenschappelijke onderwerpen als het geselecteerde boek (via OpenLibrary)
    Return: een PyVis-gegenereerde HTML weergave
    """
    if state.GRAPH is None:
        return HttpResponse("Graph not built yet", status=400)

    # Werk op een kopie zodat de globale graaf niet wordt aangepast
    graph = state.GRAPH.copy()

    # Verzamel genormaliseerde titels van gelezen boeken (duplicaten voorkomen)
    read_titles = {
        normalize_title(data["title"]).lower()
        for _, data in graph.nodes(data=True)
        if data.get("type") == "book" and not data.get("unread")
    }

    author = graph.nodes.get(book_id, {}).get("author")
    if not author:
        return HttpResponse("Author not found", status=400)

    # --- Author-based recommendations (Google Books → OpenLibrary fallback) ---
    unread_books = gb_fetch_books_by_author(author=author, read_titles=read_titles, limit=8)
    if not unread_books:
        unread_books = fetch_unread_books_by_author(author=author, read_titles=read_titles, limit=8)

    for book in unread_books:
        unread_node = f"rec::{book['title']}::{book['author']}"

        if not graph.has_node(unread_node):
            graph.add_node(
                unread_node,
                type="book",
                title=book["title"],
                author=book["author"],
                unread=True,
                cover_url=book["cover_url"],
                reason=f"Same author as {author}",
            )

        graph.add_edge(book_id, unread_node, type="recommendation", weight=0.6)

        author_node = f"author::{author}"
        if not graph.has_node(author_node):
            graph.add_node(author_node, type="author", name=author)

        graph.add_edge(unread_node, author_node, weight=0.4)

    # --- Genre-based recommendations ---
    # Score each genre in the graph by the sum of ratings of books connected to it.
    genre_scores = {}
    for node, data in graph.nodes(data=True):
        if data.get("type") != "subject":
            continue
        genre_name = data.get("name", "")
        for neighbor in graph.neighbors(node):
            nb_data = graph.nodes.get(neighbor, {})
            if nb_data.get("type") == "book" and not nb_data.get("unread"):
                genre_scores[genre_name] = (
                    genre_scores.get(genre_name, 0) + (nb_data.get("rating") or 3)
                )

    # Fetch genres for the selected book (Google Books → OpenLibrary fallback)
    book_title = graph.nodes.get(book_id, {}).get("title", "")
    book_genres = []
    if book_title:
        gb_data = gb_fetch_book_data(book_title, author)
        if gb_data:
            book_genres = gb_data.get("genres", [])
        if not book_genres:
            ol_data = fetch_work_data(book_title, author)
            if ol_data:
                book_genres = ol_data.get("subjects", [])

    ranked_genres = sorted(
        book_genres,
        key=lambda g: genre_scores.get(g, 0),
        reverse=True,
    )[:3]

    already_added = {normalize_title(b["title"]).lower() for b in unread_books}

    for genre in ranked_genres:
        genre_node = f"subject::{genre}"
        if not graph.has_node(genre_node):
            graph.add_node(genre_node, type="subject", name=genre)

        if not graph.has_edge(book_id, genre_node):
            graph.add_edge(book_id, genre_node, weight=0.8)

        # Google Books genre search → OpenLibrary fallback
        genre_books = fetch_books_by_genre(genre, limit=5) or fetch_books_by_subject(genre, limit=5)

        for book in genre_books:
            norm = normalize_title(book["title"]).lower()
            if norm in read_titles or norm in already_added:
                continue

            unread_node = f"rec::{book['title']}::{book['author']}"
            if not graph.has_node(unread_node):
                graph.add_node(
                    unread_node,
                    type="book",
                    title=book["title"],
                    author=book["author"],
                    unread=True,
                    cover_url=book["cover_url"],
                    reason=f"Shares genre: {genre}",
                )

            graph.add_edge(unread_node, genre_node, type="recommendation", weight=0.5)
            already_added.add(norm)

    html = visualize_book_ego_graph_interactive(graph, book_id)
    return HttpResponse(html)


def book_covers_view(request):
    """
    Returned alle bekende omslagfoto's als JSON.
    Wordt aangeroepen vanuit de frontend om omslagen bij te werken
    die door het achtergrondproces zijn ingeladen na het uploaden.
    """
    return JsonResponse({
        "covers": [
            {
                "id": book.id,
                "cover_url": book.cover_url,
            }
            for book in state.BOOK_NODES
            if book.cover_url
        ]
    })
