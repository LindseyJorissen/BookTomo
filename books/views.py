import pandas as pd
import datetime
import threading

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from books.graph_engine import state
from books.graph_engine.extract import extract_books_from_df
from books.graph_engine.visualize_interactive import visualize_book_ego_graph_interactive
from books.openlibrary.background import load_remaining_covers
from books.openlibrary.client import fetch_unread_books_by_author, normalize_title


def compute_cadence(date_series):
    dates = (
        date_series.dropna()  # removes missing dates
        .dt.date  # removes timestamp -> keep only day
        .drop_duplicates()
        .sort_values()  # old -> new
        .tolist()
    )

    if len(dates) < 2:  # needs at least 2 dates to check time between
        return None

    gaps = [(dates[i] - dates[i - 1]).days for i in
            range(1, len(dates))]  # example: date(2023, 1, 10) - date(2023, 1, 5) -> gaps = [5]

    return {
        "avg_days": round(sum(gaps) / len(gaps), 1),
        "median_days": sorted(gaps)[len(gaps) // 2],
        "fastest_days": min(gaps),
        "slowest_days": max(gaps),
        "first_finished": dates[0].isoformat(),
        "last_finished": dates[-1].isoformat(),
    }


@csrf_exempt  # Do not require a CSRF token (testing)
def upload_goodreads(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"},
                            status=400)  # file upload is post -> reject any request that's not POST

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file uploaded"},
                            status=400)  # take the file that's uploaded in a dict -> otherwise error

    df = pd.read_csv(file)
    read_df = df
    if "Exclusive Shelf" in df.columns:
        read_df = df[df["Exclusive Shelf"] == "read"]

    read_books = extract_books_from_df(read_df)
    state.BOOK_NODES = read_books
    from books.graph_engine.builder import build_author_graph
    state.GRAPH = build_author_graph(read_books)

    df["Date Read"] = pd.to_datetime(df.get("Date Read"), errors="coerce")
    df["Year Read"] = df["Date Read"].dt.year
    df["Month Read"] = df["Date Read"].dt.month

    current_year = datetime.date.today().year
    df_current_year = df[df["Year Read"] == current_year]

    cadence_overall = compute_cadence(df["Date Read"])
    cadence_this_year = compute_cadence(df_current_year["Date Read"])

    yearly_counts = (
        df["Year Read"]
        .dropna()
        .value_counts()
        .sort_index()
        .to_dict()
    )

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

        pub_counts_all = (
            years.astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )

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

    scatter_points_all = [
        {
            "pub_year": int(row["Original Publication Year"]),
            "read_value": int(row["Year Read"]),
        }
        for _, row in df[["Original Publication Year", "Year Read"]]
        .dropna()
        .iterrows()
    ]

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
        if subset.empty:
            return {
                "total_books": 0,
                "total_pages": 0,
                "avg_rating": 0,
                "top_author": None,
            }

        avg_rating = 0
        if "My Rating" in subset.columns:
            rated = subset[subset["My Rating"] > 0]
            if not rated.empty:
                avg_rating = round(rated["My Rating"].mean(), 2)

        total_pages = int(
            subset["Number of Pages"].fillna(0).sum()
        )

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
        pages = subset["Number of Pages"].dropna()
        if pages.empty:
            return None

        longest = subset.loc[pages.idxmax()]

        bins = [
            (0, 200, "0–200"),
            (200, 300, "200–300"),
            (300, 400, "300–400"),
            (400, 500, "400–500"),
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

    stats = {"overall": {
        **compute_stats(read_df),
        "cadence": cadence_overall,
    }, "this_year": {
        **compute_stats(df_current_year),
        "cadence": cadence_this_year,
    }, "yearly_books": yearly_counts, "monthly_books": monthly_counts, "publication_years_overall": pub_counts_all,
        "publication_years_this_year": pub_counts_this_year, "scatter_publication_vs_read_all": scatter_points_all,
        "scatter_publication_vs_read_year": scatter_points_this_year, "book_lengths": {
            "overall": compute_book_lengths(read_df),
            "this_year": compute_book_lengths(
                df_current_year[df_current_year["Exclusive Shelf"] == "read"]
                if "Exclusive Shelf" in df_current_year.columns
                else df_current_year
            ),
        }, "oldest_pub_year": oldest_pub_year, "books": [
            {
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "cover_url": book.cover_url,
            }
            for book in read_books
        ]}

    threading.Thread(
        target=load_remaining_covers,
        daemon=True
    ).start()

    return JsonResponse(stats)


def book_graph_view(request, book_id):
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

    unread_books = fetch_unread_books_by_author(
        author=author,
        read_titles=read_titles,
        limit=8
    )

    for book in unread_books:
        unread_node = f"ol::{book['title']}::{book['author']}"

        if not graph.has_node(unread_node):
            graph.add_node(
                unread_node,
                type="book",
                title=book["title"],
                author=book["author"],
                unread=True,
                cover_url=book["cover_url"],
            )

        graph.add_edge(
            book_id,
            unread_node,
            type="recommendation",
            reason=f"Geschreven door dezelfde auteur ({author})",
            weight=0.6
        )

        author_node = f"author::{author}"
        if not graph.has_node(author_node):
            graph.add_node(author_node, type="author", name=author)

        graph.add_edge(unread_node, author_node, weight=0.4)

    html = visualize_book_ego_graph_interactive(graph, book_id)
    return HttpResponse(html)


def book_covers_view(request):
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
